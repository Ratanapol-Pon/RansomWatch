import base64
import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_foundation_db import migrate, payload

from apps.api.main import app
from packages.line.client import LineClient, valid_signature
from packages.line.worker import (
    command_text,
    process_events,
    queue_alerts,
    quiet,
    send_pending,
    summary_window,
)
from packages.scraper.pipeline import ingest_payloads
from packages.shared.models import LineDelivery, LineEvent, LineGroup


def group(now, **changes):
    return LineGroup(
        group_id="Ctest",
        name="Test group",
        active=True,
        joined=True,
        activated_at=now - timedelta(days=60),
        last_membership_at=now - timedelta(days=60),
        language="en",
        delivery_mode="monthly",
        countries=["TH"],
        attack_types=[],
        digest_hour=8,
        quiet_start=22,
        quiet_end=8,
        include_global_reports=True,
        **changes,
    )


def test_signature_is_over_exact_raw_bytes():
    body = b'{"events": []}'
    signature = base64.b64encode(hmac.new(b"test-secret", body, hashlib.sha256).digest()).decode()
    assert valid_signature(body, signature, "test-secret")
    assert not valid_signature(body + b" ", signature, "test-secret")
    assert not valid_signature(body, signature, "")
    assert not valid_signature(body, "ลายเซ็น", "test-secret")


def test_monthly_summary_uses_previous_calendar_month_in_bangkok():
    now = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)  # 08:00 Bangkok
    item = group(now)
    start, end, key = summary_window(item, now)
    assert start == datetime(2026, 8, 31, 17, tzinfo=UTC)
    assert end == datetime(2026, 9, 30, 17, tzinfo=UTC)
    assert key == "monthly:2026-09"
    assert summary_window(item, now - timedelta(seconds=1)) is None
    assert quiet(item, now - timedelta(seconds=1))
    assert not quiet(item, now)


def test_webhook_deduplicates_and_ignores_ordinary_conversation(db, monkeypatch):
    conn, schema = db
    migrate(conn, schema)

    @contextmanager
    def local_session():
        with Session(bind=conn) as session:
            yield session
            session.commit()

    monkeypatch.setattr("packages.shared.db.get_session", local_session)
    monkeypatch.setattr(
        "apps.api.line_webhook.get_settings", lambda: SimpleNamespace(line_channel_secret="secret")
    )

    def event(identity, message):
        return {
            "webhookEventId": identity,
            "type": "message",
            "source": {"type": "group", "groupId": "Ctest"},
            "message": {"type": "text", "text": message},
            "replyToken": "transient",
        }

    body = json.dumps(
        {
            "events": [
                event("ordinary", "Private group discussion"),
                event("command", "!latest"),
                {"source": "invalid"},
                {
                    "type": "message",
                    "source": {"type": "group", "groupId": "Ctest"},
                    "message": "invalid",
                },
            ]
        }
    ).encode()
    signature = base64.b64encode(hmac.new(b"secret", body, hashlib.sha256).digest()).decode()
    with TestClient(app) as client:
        assert (
            client.post(
                "/webhooks/line", content=body, headers={"x-line-signature": "bad"}
            ).status_code
            == 401
        )
        for _ in range(2):
            assert (
                client.post(
                    "/webhooks/line", content=body, headers={"x-line-signature": signature}
                ).status_code
                == 200
            )
    with Session(bind=conn) as session:
        assert session.scalar(select(func.count()).select_from(LineEvent)) == 1
        assert session.get(LineEvent, "ordinary") is None


def test_join_pending_activation_and_replies_scrub_transient_content(db):
    conn, schema = db
    migrate(conn, schema)
    now = datetime.now(UTC)
    calls = []
    client = SimpleNamespace(reply=lambda *args: calls.append(args))
    with Session(bind=conn) as session:
        event = LineEvent(
            event_id="join",
            received_at=now,
            payload={"group_id": "Ctest", "type": "join", "timestamp": int(now.timestamp() * 1000)},
        )
        session.add(event)
        session.flush()
        process_events(session, client, now)
        row = session.get(LineGroup, "Ctest")
        assert row.active is False and row.delivery_mode == "monthly"
        assert not calls
        row.active = True
        session.add(
            LineEvent(
                event_id="help",
                received_at=now,
                payload={
                    "group_id": "Ctest",
                    "type": "message",
                    "reply_token": "one-use",
                    "text": "!help",
                },
            )
        )
        session.flush()
        process_events(session, client, now)
        assert len(calls) == 1
        assert "reply_token" not in session.get(LineEvent, "help").payload


def test_monthly_queue_replay_and_quota_guard(db):
    conn, schema = db
    migrate(conn, schema)
    now = datetime.now(UTC).replace(day=1, hour=3, minute=0, second=0, microsecond=0)
    with Session(bind=conn) as session:
        row = group(now)
        session.add(row)
        session.flush()
        queue_alerts(session, now)
        queue_alerts(session, now)
        session.flush()
        assert session.scalar(select(func.count()).select_from(LineDelivery)) == 1
        sent = []
        client = SimpleNamespace(
            quota_available=lambda _: False, push=lambda *args: sent.append(args)
        )
        send_pending(session, client, now)
        assert not sent
        delivery = session.scalar(select(LineDelivery))
        assert delivery.sent_at is None and "quota" in delivery.error
        delivery.next_attempt_at = now
        client.quota_available = lambda _: True
        send_pending(session, client, now)
        assert len(sent) == 1 and delivery.sent_at is not None
        assert sent[0][2] == str(delivery.id)


def test_commands_exclude_bd_notes_and_respect_country(db):
    conn, schema = db
    migrate(conn, schema)
    now = datetime.now(UTC)
    with Session(bind=conn) as session:
        ingest_payloads(session, [payload()], now=now - timedelta(hours=1))
        item = group(now)
        message = command_text(session, item, "!latest", now)
        assert "Example Company" in message and "http://actor.onion/post/1" in message
        item.countries = ["JP"]
        assert "No matching" in command_text(session, item, "!latest", now)


def test_push_retry_uses_same_idempotency_key_and_accepts_previous_success():
    headers = []

    def handler(request):
        headers.append(request.headers.get("x-line-retry-key"))
        return httpx.Response(409, headers={"x-line-accepted-request-id": "accepted"})

    client = LineClient(
        "token",
        httpx.Client(base_url="https://api.line.me", transport=httpx.MockTransport(handler)),
    )
    client.push("Ctest", "Example", "known-delivery-id")
    assert headers == ["known-delivery-id"]


def test_immediate_queue_advances_beyond_first_batch(db):
    conn, schema = db
    migrate(conn, schema)
    now = datetime.now(UTC).replace(hour=3)
    with Session(bind=conn) as session:
        item = group(now)
        item.delivery_mode = "immediate"
        session.add(item)
        ingest_payloads(
            session,
            [
                payload(
                    post_title=f"Company {i}",
                    source_record_id=f"item-{i}",
                    post_url=f"https://example.test/{i}",
                )
                for i in range(103)
            ],
            now=now - timedelta(hours=1),
        )
        session.flush()
        queue_alerts(session, now)
        assert session.scalar(select(func.count()).select_from(LineDelivery)) == 100
        queue_alerts(session, now)
        assert session.scalar(select(func.count()).select_from(LineDelivery)) == 103
        queue_alerts(session, now)
        assert session.scalar(select(func.count()).select_from(LineDelivery)) == 103


def test_leave_cancels_delivery_and_old_join_does_not_reactivate(db):
    conn, schema = db
    migrate(conn, schema)
    now = datetime.now(UTC).replace(hour=3)
    with Session(bind=conn) as session:
        item = group(now)
        session.add(item)
        session.flush()
        delivery = LineDelivery(group_id=item.group_id, delivery_key="test", message="Test")
        session.add(delivery)
        session.add(
            LineEvent(
                event_id="leave",
                received_at=now,
                payload={
                    "type": "leave",
                    "group_id": item.group_id,
                    "timestamp": int(now.timestamp() * 1000),
                },
            )
        )
        session.flush()
        process_events(session, SimpleNamespace(), now)
        session.add(
            LineEvent(
                event_id="old-join",
                received_at=now,
                payload={
                    "type": "join",
                    "group_id": item.group_id,
                    "timestamp": int((now - timedelta(days=1)).timestamp() * 1000),
                },
            )
        )
        session.flush()
        process_events(session, SimpleNamespace(), now)
        assert not item.active and not item.joined
        send_pending(session, SimpleNamespace(), now)
        assert delivery.attempts == 5 and delivery.sent_at is None


def test_old_delivery_is_not_retried_after_line_idempotency_window(db):
    conn, schema = db
    migrate(conn, schema)
    now = datetime.now(UTC).replace(hour=3)
    with Session(bind=conn) as session:
        item = group(now)
        session.add(item)
        session.flush()
        delivery = LineDelivery(
            group_id=item.group_id,
            delivery_key="old",
            message="Test",
            created_at=now - timedelta(hours=24),
        )
        session.add(delivery)
        session.flush()
        send_pending(session, SimpleNamespace(), now)
        assert delivery.sent_at is None and "retry window" in delivery.error
