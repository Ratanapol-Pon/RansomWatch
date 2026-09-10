from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_foundation_db import migrate
from test_intelligence_collectors import kev

from packages.scraper.collectors.cisa_kev import parse_kev
from packages.scraper.collectors.feed_http import FeedError
from packages.scraper.reports import ingest_reports
from packages.scraper.sources import run_source
from packages.shared.models import Incident, SourceHealth, ThreatReport
from packages.shared.schemas import ThreatReportCreate


def test_report_replay_updates_source_without_duplicate_or_alert(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        report = parse_kev(kev()).reports[0]
        assert ingest_reports(session, [report]).inserted == 1
        session.flush()
        original = session.scalar(select(ThreatReport))
        original_id, first_seen = original.id, original.discovered_at
        replay = ingest_reports(session, [report])
        assert replay.inserted == 0 and replay.updated == 0
        changed = report.model_copy(update={"description": "Corrected source description"})
        assert ingest_reports(session, [changed]).updated == 1
        assert original.id == original_id and original.discovered_at == first_seen
        assert session.scalar(select(func.count()).select_from(ThreatReport)) == 1
        assert session.scalar(select(func.count()).select_from(Incident)) == 0
        assert session.scalar(text("select count(*) from delivered")) == 0


def test_feed_refresh_preserves_human_review_decisions(db):
    conn, schema = db
    migrate(conn, schema)
    report = ThreatReportCreate(
        kind="news",
        title="Example",
        source="thaicert",
        source_record_key="news-1",
        source_url="https://example.test/news",
        attack_types=["other"],
    )
    with Session(bind=conn) as session:
        ingest_reports(session, [report])
        session.flush()
        row = session.scalar(select(ThreatReport))
        row.needs_review = False
        row.country = "JP"
        row.confidence = "confirmed"
        row.attack_types = ["data_breach"]
        row.kind = "campaign"
        session.flush()
        ingest_reports(session, [report])
        assert row.country == "JP" and row.kind == "campaign"
        assert row.attack_types == ["data_breach"] and row.confidence == "confirmed"


def test_source_failure_backoff_and_other_source_success(db, monkeypatch):
    conn, schema = db
    migrate(conn, schema)

    @contextmanager
    def local_session():
        with Session(bind=conn) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    now = datetime(2026, 9, 10, 8, tzinfo=UTC)
    monkeypatch.setattr("packages.scraper.sources.get_session", local_session)
    monkeypatch.setattr("packages.scraper.sources.utcnow", lambda: now)
    attempts = []

    def broken():
        attempts.append(1)
        raise FeedError("HTTP 429", retry_at=now + timedelta(hours=1))

    assert run_source("broken_feed", broken) is False
    assert run_source("broken_feed", broken) is False
    assert len(attempts) == 1
    assert run_source("cisa_kev", lambda: parse_kev(kev())) is True
    with Session(bind=conn) as session:
        broken_health = session.get(SourceHealth, "broken_feed")
        assert broken_health.status == "error"
        assert broken_health.consecutive_failures == 1
        assert broken_health.next_retry_at == now + timedelta(hours=1)
        assert session.get(SourceHealth, "cisa_kev").inserted == 1
    monkeypatch.setattr("packages.scraper.sources.utcnow", lambda: now + timedelta(hours=2))
    assert run_source("broken_feed", lambda: parse_kev(kev())) is True
    with Session(bind=conn) as session:
        recovered = session.get(SourceHealth, "broken_feed")
        assert recovered.status == "ok" and recovered.consecutive_failures == 0
        assert recovered.next_retry_at is None
        assert session.scalar(text("select count(*) from delivered")) == 0


def test_source_health_table_is_private(db):
    conn, schema = db
    migrate(conn, schema)
    assert (
        conn.scalar(
            text("select has_table_privilege('authenticated', :table, 'SELECT')"),
            {"table": f"{schema}.source_health"},
        )
        is False
    )
    assert (
        conn.scalar(
            text("select relrowsecurity from pg_class where oid = cast(:table as regclass)"),
            {"table": f"{schema}.source_health"},
        )
        is True
    )
