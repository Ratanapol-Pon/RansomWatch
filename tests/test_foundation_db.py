"""Real Postgres integration tests; opt in with TEST_DATABASE_URL on localhost.

Each test uses a fresh schema. No production configuration or .env is read.
The outbound Supabase function is replaced by a local recording trigger.
"""

import os
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from packages.scraper.pipeline import ingest_payloads, upgrade_legacy_incidents
from packages.shared.models import Incident, IncidentSource, Pipeline, ThreatReport, Watchlist
from packages.shared.schemas import IncidentRead

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260910124341_threat_intelligence_foundation.sql"


@pytest.fixture
def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to an isolated local PostgreSQL database")
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if parsed.host not in ("127.0.0.1", "localhost", "::1"):
        pytest.fail("integration tests require a loopback TEST_DATABASE_URL")
    schema = "test_foundation_" + uuid.uuid4().hex
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.exec_driver_sql(f'create schema "{schema}"')
        conn.exec_driver_sql(f'set search_path to "{schema}"')
        for role in ("anon", "authenticated", "service_role"):
            conn.exec_driver_sql(
                f"do $$ begin create role {role}; exception when duplicate_object then null; end $$"
            )
        conn.exec_driver_sql((ROOT / "supabase/migrations/0001_init.sql").read_text())
        conn.exec_driver_sql(
            (ROOT / "supabase/migrations/0002_rls.sql").read_text().replace("public.", f"{schema}.")
        )
        # Simulate the existing trigger boundary; never install pg_net or call a real destination.
        conn.exec_driver_sql("""
            create table delivered (incident_id uuid);
            create function notify_incident_insert() returns trigger language plpgsql as $$
            begin insert into delivered values(new.id); return new; end $$;
        """)
        conn.commit()
        try:
            yield conn, schema
        finally:
            conn.rollback()
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql("set search_path to public")
            conn.exec_driver_sql(f'drop schema "{schema}" cascade')
    engine.dispose()


def migrate(conn, schema):
    conn.exec_driver_sql(MIGRATION.read_text().replace("public.", f"{schema}."))
    followup = ROOT / "supabase/migrations/20260910130021_collector_health_and_review.sql"
    conn.exec_driver_sql(followup.read_text().replace("public.", f"{schema}."))
    latest = ROOT / "supabase/migrations/20260910161359_dashboard_access_and_line.sql"
    conn.exec_driver_sql(latest.read_text().replace("public.", f"{schema}."))
    conn.commit()
    conn.execution_options(isolation_level="READ COMMITTED")


def payload(**overrides):
    return {
        "post_title": "Example Company",
        "group_name": "ExampleActor",
        "country": "TH",
        "published": "2026-09-10T08:00:00Z",
        "post_url": "http://actor.onion/post/1",
        **overrides,
    }


def test_migration_preserves_ids_links_and_corrects_legacy_metadata(db):
    conn, schema = db
    incident_id, watch_id, pipeline_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    import json

    conn.execute(
        text("""
        insert into incidents(id, victim_name, normalized_name, group_name, source, source_url,
                              attack_date, discovered_at, raw)
        values(:id, 'Example Company', 'example company', 'exampleactor', 'ransomware_live',
               'http://actor.onion/post/1', '2026-09-10', '2026-09-10T09:00:00Z',
               cast(:raw as jsonb))
    """),
        {"id": incident_id, "raw": json.dumps(payload())},
    )
    conn.execute(
        text("insert into watchlist(id, name) values(:id, 'Example Company')"), {"id": watch_id}
    )
    conn.execute(
        text("""
        insert into pipeline(id, incident_id, watchlist_id, follow_up_status, owner_note)
        values(:id, :incident, :watch, 'meeting_booked', 'Preserve this note')
    """),
        {"id": pipeline_id, "incident": incident_id, "watch": watch_id},
    )
    conn.commit()
    migrate(conn, schema)
    with Session(bind=conn) as session:
        assert upgrade_legacy_incidents(session) == 1
        session.commit()
        assert upgrade_legacy_incidents(session) == 0
        item = session.get(Incident, incident_id)
        assert item.attack_date is None
        assert item.raw["_legacy_attack_date"] == "2026-09-10"
        assert item.dark_web_url == "http://actor.onion/post/1"
        assert item.published_at == datetime(2026, 9, 10, 8, tzinfo=UTC)
        assert session.get(Pipeline, pipeline_id).follow_up_status == "meeting_booked"
        assert session.get(Pipeline, pipeline_id).owner_note == "Preserve this note"
        assert ingest_payloads(session, [payload()]).inserted == 0
        assert session.scalar(select(func.count()).select_from(Incident)) == 1
        assert session.scalar(text("select count(*) from delivered")) == 0
        serialized = IncidentRead.model_validate(item)
        assert serialized.dark_web_url == item.dark_web_url


def test_repeat_poll_cross_source_evidence_and_repeat_attacks(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        session.add(Watchlist(name="Example Company", aliases=[], domains=[]))
        session.flush()
        first = ingest_payloads(session, [payload()])
        original_id = first.new_incidents[0].id
        assert first.inserted == 1
        assert first.pipeline_rows == 1
        for _ in range(3):
            assert ingest_payloads(session, [payload()]).inserted == 0
        assert session.get(Incident, original_id).raw == payload()
        assert ingest_payloads(session, [payload()], source="ransomwatch").inserted == 0
        # Reused post URL on a later date must not collapse a new attack.
        assert ingest_payloads(session, [payload(published="2026-10-12T08:00:00Z")]).inserted == 1
        assert session.scalar(select(func.count()).select_from(Incident)) == 2
        assert session.scalar(select(func.count()).select_from(IncidentSource)) == 3
        assert session.scalar(select(func.count()).select_from(Pipeline)) == 2
        assert session.scalar(text("select count(*) from delivered")) == 2


def test_source_id_survives_changed_publication_time(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        first = ingest_payloads(session, [payload(id="feed-1")])
        updated = payload(id="feed-1", published="2026-09-11T08:00:00Z", attackdate="2026-09-01")
        assert ingest_payloads(session, [updated]).inserted == 0
        assert first.new_incidents[0].attack_date == date(2026, 9, 1)
        evidence = session.scalar(select(IncidentSource))
        assert evidence.published_at == datetime(2026, 9, 11, 8, tzinfo=UTC)
        assert first.new_incidents[0].published_at == evidence.published_at


def test_category_enrichment_does_not_duplicate_source_observation(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        assert ingest_payloads(session, [payload()]).inserted == 1
        changed = payload(attack_types=["ransomware", "extortion"])
        assert ingest_payloads(session, [changed]).inserted == 0
        assert session.scalar(select(func.count()).select_from(Incident)) == 1


def test_transaction_failure_rolls_back_incident_evidence_pipeline_and_trigger(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        session.add(Watchlist(name="Example Company", aliases=[], domains=[]))
        session.commit()
        assert ingest_payloads(session, [payload()]).inserted == 1
        session.rollback()
        for model in (Incident, IncidentSource, Pipeline):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(text("select count(*) from delivered")) == 0


def test_shared_homepage_and_conflicting_attack_dates_do_not_merge(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        home = payload(post_url="http://actor.onion/")
        assert ingest_payloads(session, [home]).inserted == 1
        assert ingest_payloads(session, [home], source="ransomwatch").inserted == 1
        first = payload(attackdate="2026-09-01")
        second = payload(attackdate="2026-09-02")
        assert ingest_payloads(session, [first]).inserted == 1
        assert ingest_payloads(session, [second], source="ransomwatch").inserted == 1


def test_unknown_actor_and_different_sources_do_not_merge_by_company(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        report = payload(
            group_name=None, attack_types=["data_breach"], post_url="https://news.test/a"
        )
        first = ingest_payloads(session, [report], source="news")
        assert first.new_incidents[0].group_name is None
        assert first.new_incidents[0].confidence == "reported"
        assert ingest_payloads(session, [report], source="news").inserted == 0
        other = {**report, "post_url": "https://other.test/b"}
        assert ingest_payloads(session, [other], source="thaicert").inserted == 1


def test_backfill_suppresses_webhook_and_internal_events(db, monkeypatch):
    conn, schema = db
    migrate(conn, schema)
    events = []
    monkeypatch.setattr("packages.scraper.pipeline.emit", lambda *args: events.append(args))
    with Session(bind=conn) as session:
        result = ingest_payloads(session, [payload()], alert_eligible=False)
        assert result.inserted == 1
        assert events == []
        assert session.scalar(text("select count(*) from delivered")) == 0
        assert ingest_payloads(session, [payload()]).inserted == 0
        assert result.new_incidents[0].alert_eligible is False


def test_advisory_not_in_incident_counts_and_rls_is_enabled(db):
    conn, schema = db
    migrate(conn, schema)
    with Session(bind=conn) as session:
        session.add(
            ThreatReport(
                kind="advisory",
                title="Example advisory",
                source="cisa_kev",
                source_record_key="CVE-2026-12345",
                source_url="https://example.test/advisory",
                cve_ids=["CVE-2026-12345"],
            )
        )
        session.flush()
        assert session.scalar(select(func.count()).select_from(Incident)) == 0
        assert session.scalar(select(func.count()).select_from(ThreatReport)) == 1
        assert session.scalar(text("select count(*) from delivered")) == 0
        for table in ("incident_sources", "threat_reports"):
            enabled = session.scalar(
                text("""
                select relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = :schema and c.relname = :table
            """),
                {"schema": schema, "table": table},
            )
            assert enabled is True
            assert (
                session.scalar(
                    text("select has_table_privilege('anon', :table, 'SELECT')"),
                    {"table": f"{schema}.{table}"},
                )
                is False
            )
