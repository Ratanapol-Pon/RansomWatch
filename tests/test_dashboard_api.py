from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_foundation_db import migrate, payload

from apps.api.auth import Principal, current_user, database
from apps.api.main import app
from packages.scraper.pipeline import ingest_payloads
from packages.shared.models import Incident, Pipeline, ThreatReport


@pytest.fixture
def api(db):
    conn, schema = db
    migrate(conn, schema)
    user = Principal(uuid4(), "admin")

    def sessions():
        with Session(bind=conn) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[database] = sessions
    app.dependency_overrides[current_user] = lambda: user
    with TestClient(app) as client:
        yield client, conn, user
    app.dependency_overrides.clear()


def test_unauthenticated_requests_rejected_without_database():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/incidents").status_code == 401
        assert client.get("/api/line/groups").status_code == 401


def test_incident_filters_details_and_no_raw_payload(api):
    client, conn, user = api
    with Session(bind=conn) as session:
        ingest_payloads(session, [payload()])
        session.commit()
    result = client.get("/api/incidents?days=0&country=TH&attack_type=ransomware").json()
    assert result["total"] == 1
    row = result["items"][0]
    assert row["dark_web_url"] == "http://actor.onion/post/1"
    assert "raw" not in row
    assert client.get("/api/incidents?days=0&country=JP").json()["total"] == 0
    assert client.get("/api/incidents?days=0&q=%25").json()["total"] == 0
    detail = client.get("/api/incidents/" + row["id"]).json()
    assert len(detail["sources"]) == 1 and "raw" not in detail["sources"][0]
    assert client.get("/api/incidents/" + str(uuid4())).status_code == 404
    assert client.get("/api/incidents?limit=1000").status_code == 422
    summary = client.get("/api/summary").json()
    assert summary["incidents"] == 1
    assert summary["timeline"][0]["count"] == 1
    assert {"type": "ransomware", "count": 1} in summary["attack_types"]


def test_viewer_cannot_access_customer_data_or_mutate(api):
    client, conn, user = api
    user.role = "viewer"
    for path in ("/api/watchlist", "/api/alert-rules", "/api/line/groups"):
        assert client.get(path).status_code == 403
    assert client.post("/api/watchlist", json={"name": "Example"}).status_code == 403
    assert client.get("/api/incidents?watchlist_only=true").status_code == 403
    assert client.get("/api/summary").json()["watchlist_hits"] is None


def test_watchlist_matches_without_creating_follow_up_records(api):
    client, conn, user = api
    with Session(bind=conn) as session:
        ingest_payloads(session, [payload()])
        session.commit()
    response = client.post(
        "/api/watchlist", json={"name": "Example Company", "priority": 1, "notes": "Private note"}
    )
    assert response.status_code == 200, response.text
    identity = response.json()["id"]
    assert client.post("/api/watchlist", json={"name": "Example Company"}).status_code == 409
    assert client.get("/api/pipeline").status_code == 404
    assert client.patch("/api/pipeline/" + str(uuid4()), json={}).status_code == 404
    with Session(bind=conn) as session:
        assert session.scalar(select(Incident)).watchlist_hit is True
        assert session.scalar(select(Pipeline)) is None
    assert client.delete("/api/watchlist/" + identity).status_code == 200


def test_legacy_follow_up_records_are_preserved(api):
    from uuid import UUID

    from packages.bot.queries import Queries

    client, conn, user = api
    with Session(bind=conn) as session:
        incident = ingest_payloads(session, [payload()]).new_incidents[0]
        incident_id = incident.id
        session.commit()
    identity = client.post("/api/watchlist", json={"name": "Example Company"}).json()["id"]
    with Session(bind=conn) as session:
        archived = Pipeline(
            incident_id=incident_id,
            watchlist_id=UUID(identity),
            follow_up_status="meeting_booked",
            owner_note="Historical note",
        )
        session.add(archived)
        session.commit()
    assert client.get("/api/pipeline").status_code == 404
    assert client.delete("/api/watchlist/" + identity).status_code == 409
    with Session(bind=conn) as session:
        with pytest.raises(ValueError, match="archived records"):
            Queries(session).remove_watch("Example Company")
        assert session.scalar(select(Pipeline)).owner_note == "Historical note"


def test_report_review_and_explicit_promotion_are_idempotent(api):
    client, conn, user = api
    with Session(bind=conn) as session:
        report = ThreatReport(
            kind="news",
            title="Example reported breach",
            source="news",
            source_record_key="report-one",
            source_url="https://example.test/news",
            attack_types=["data_breach"],
        )
        session.add(report)
        session.flush()
        identity = str(report.id)
        session.commit()
    assert (
        client.patch(
            "/api/reports/" + identity,
            json={"kind": "news", "confidence": "reported", "country": "TH", "needs_review": False},
        ).status_code
        == 200
    )
    body = {
        "victim_name": "Example Org",
        "country": "TH",
        "attack_types": ["data_breach"],
        "confidence": "reported",
    }
    first = client.post("/api/reports/" + identity + "/promote", json=body)
    assert first.status_code == 200, first.text
    again = client.post("/api/reports/" + identity + "/promote", json=body)
    assert again.json() == first.json()
    with Session(bind=conn) as session:
        rows = session.scalars(select(Incident)).all()
        assert len(rows) == 1 and rows[0].alert_eligible is False


def test_membership_is_checked_independently_of_supabase_user_metadata(api, monkeypatch):
    from apps.api.auth import verified_identity
    from packages.shared.models import DashboardMember

    client, conn, user = api
    app.dependency_overrides.pop(current_user)
    app.dependency_overrides[verified_identity] = lambda: user.user_id
    assert client.get("/api/me").status_code == 403
    with Session(bind=conn) as session:
        session.add(DashboardMember(user_id=user.user_id, role="viewer", enabled=True))
        session.commit()
    assert client.get("/api/me").json()["role"] == "viewer"
    assert client.post("/api/alert-rules", json={"name": "Unauthorized"}).status_code == 403


def test_invalid_auth_token_is_rejected(monkeypatch):
    import httpx
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    from apps.api.auth import verified_identity

    monkeypatch.setattr(
        "apps.api.auth.get_settings",
        lambda: SimpleNamespace(supabase_url="https://auth.test", supabase_auth_key="public-key"),
    )
    monkeypatch.setattr("apps.api.auth.httpx.get", lambda *a, **kw: httpx.Response(401))
    with pytest.raises(HTTPException) as error:
        verified_identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid"))
    assert error.value.status_code == 401


def test_group_filter_changes_cancel_queued_messages(api):
    from datetime import UTC, datetime

    from packages.shared.models import LineDelivery, LineGroup

    client, conn, user = api
    with Session(bind=conn) as session:
        session.add(
            LineGroup(
                group_id="Ctest",
                name="Test",
                joined=True,
                active=True,
                activated_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(LineDelivery(group_id="Ctest", delivery_key="monthly:test", message="Old"))
        session.commit()
    body = {
        "name": "Test",
        "active": True,
        "language": "en",
        "delivery_mode": "monthly",
        "countries": ["JP"],
    }
    assert client.patch("/api/line/groups/Ctest", json=body).status_code == 200
    delivery = client.get("/api/line/deliveries").json()[0]
    assert delivery["attempts"] == 5 and "settings changed" in delivery["error"]
    assert (
        client.patch("/api/line/groups/Ctest", json={**body, "countries": ["invalid"]}).status_code
        == 422
    )
