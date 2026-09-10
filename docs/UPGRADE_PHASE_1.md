# Upgrade 1: threat intelligence data foundation

Implemented on 2026-09-10. This is the first phase of the broader monitoring upgrade,
not a rerun of the original ransomware collector MVP phase. The dashboard and LINE
bot are subsequent phases. No new external feed is enabled by this change.

## Data changes

- `incidents.dark_web_url`: optional HTTP(S) `.onion` link, stored separately from
  `source_url`. The mapper prefers the explicit field, then an onion URL in the
  source/post URL. It never fetches the link. Existing source citations remain usable.
- `published_at`: source publication time. `discovered_at` remains our collection
  time. `attack_date` is populated only from an explicit `attack_date` or `attackdate`.
  Timestamps are UTC; presentation remains Asia/Bangkok.
- `attack_types`: ransomware, extortion, data_breach, phishing, bec, malware, ddos,
  defacement, exploitation, other. Multiple tags are supported.
- `affected_products`, `cve_ids`: structured lists for later product/CVE filtering.
- `confidence`: claimed, reported, confirmed, disputed. Legacy lifecycle `status`
  remains separate for compatibility. A collector never confirms its own claims.
- `alert_eligible`: false for historical imports; respected by both the database
  trigger and dispatcher, plus internal ingestion events.
- `incident_sources`: source identity, URLs, publication time, first/last seen, and
  raw payload. Database uniqueness on `(source, source_record_key)` prevents replay.
- `threat_reports`: campaign/advisory records without requiring a victim. Existing
  victim counts query `incidents`, so advisories do not inflate those statistics.

New tables use RLS with no frontend policies and no anon/authenticated privileges.
Backend service-role access is granted. Dashboard access policies belong to Upgrade 3.
There are no new environment variables for the running application.

## Identity and evidence

Prefer the source's `id`, `victim_id`, or `source_record_id`. Otherwise hash the
normalized company, actor, source URL, and UTC publication timestamp (explicit attack
date if publication is absent). Changing descriptive text or tags does not create a
new identity. The same company/actor on a different publication date can be a separate
attack; the old company/group unique constraint is removed.

Cross-source automatic merging requires the same normalized company and known actor,
the exact publication time, and a shared non-root story URL, with overlapping attack
tags and no conflicting attack dates. Ambiguous reports remain separate for review.
Unknown actors alone never establish a cross-source match. This favors avoiding false
merges; later manual review can consolidate independently worded reports.

Without source IDs, timestamps, or distinct URLs, a feed cannot distinguish two
otherwise identical attacks. Corrected publication timestamps without a stable source
ID can also appear as a new observation. These are source-quality limitations, not
evidence that a second attack occurred.

Ingestion holds a PostgreSQL transaction advisory lock until commit so multiple worker
instances cannot race the source identity check. This intentionally serializes the
small current ingestion workload. Every new incident and evidence record commits in
the same transaction. Repeated identical polls update last-seen metadata without
continually appending the same raw payload.

## Existing records and rollout

Migration: `supabase/migrations/20260910124341_threat_intelligence_foundation.sql`.
Prerequisites: existing migrations 0001 through 0003. Keep the old scraper paused
throughout the upgrade: old code still uses the obsolete company/group dedup rule.

1. Take a database backup and record incident/pipeline counts before rollout.
2. Deploy the updated alert dispatcher first. It is backward compatible with records
   that do not yet have `alert_eligible`.
3. Apply the new SQL migration through the project's normal Supabase migration flow.
   It runs in one transaction, retains every incident ID and foreign key, and inserts
   no incidents. Do not edit or replay the old migration files.
4. With the new Python code, run `uv run python -m packages.scraper.run --upgrade-legacy`.
   This enriches existing rows in place, creates evidence rows, and sends no alerts.
   It is idempotent and also runs automatically before ingestion as a safety net.
5. Verify counts, source rows, date corrections, and existing pipeline notes. Resume
   the updated worker only after these checks pass. Keep the Discord bot on matching
   code after the schema is applied.

The legacy enrichment uses the primary stored payload for attribution. Previously
merged payloads lacked per-source provenance; they remain in `raw` without inventing
their origin. Historical attacks already collapsed by the old logic are not silently
split or reparented. Source-key collisions between legacy rows abort enrichment for
review, preserving both records and their BD links.

For known ransomware sources, enrichment removes a legacy attack date only when it
equals the source publication date and there is no explicit attack date. The previous
value is retained as `raw._legacy_attack_date`. Distinct dates and reviewed statuses
are preserved. Explicit feed attack dates take precedence.

If SQL fails, the transaction rolls back. If enrichment fails, its transaction rolls
back and the worker should stay paused while the flagged records are reviewed. Do
not downgrade to old ingestion logic once separate attacks have been stored. A full
rollback requires the pre-upgrade backup and matching code, coordinated before new
production ingestion resumes.

## Verification

Unit suite: `uv run python -m pytest -q` (database tests skip without a test URL).
Lint: `uv run ruff check .`.
Alert suite: `node --test supabase/functions/_shared/alerting_test.ts`.

Database suite: set `TEST_DATABASE_URL` to an isolated local Postgres instance and run
`uv run python -m pytest tests/test_foundation_db.py -q`. The tests reject non-loopback
hosts, use temporary schemas, never read the application's `.env`, and replace the
outbound Supabase webhook with a local recording trigger. They verify the actual SQL
migration and Python SQLAlchemy ingestion against Postgres, not an SQLite substitute.

On machines without Docker/Postgres, a disposable Postgres WASM test server can be run:

```powershell
npx.cmd --yes @electric-sql/pglite-socket --host=127.0.0.1 --port=55439
```

In a second terminal:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:55439/postgres?sslmode=disable'
uv run python -m pytest -q
```

PGlite validates SQL, constraints, triggers, and ORM behavior locally. Its connection
model differs from hosted Postgres; it does not validate multiworker concurrency or
Supabase Vault/pg_net network delivery. A hosted smoke test remains part of rollout.

## Acceptance results — 2026-09-10

Local implementation is complete; the hosted database and deployed services have not
been changed. Existing README edits and `live_stats_30d.png` were preserved.

| Check | Result | Evidence |
|---|---|---|
| Existing IDs and BD links/notes survive migration | PASS | `test_migration_preserves_ids_links_and_corrects_legacy_metadata` |
| Replay deduplication and separate dated attacks | PASS | `test_repeat_poll_cross_source_evidence_and_repeat_attacks` |
| Publication dates separate from explicit attack dates | PASS | Mapping tests and legacy migration test |
| Dark-web URL validation and model serialization | PASS | URL/schema tests and migration round-trip assertion |
| Historical imports send no alerts | PASS | Database recording trigger, internal-event test, dispatcher test |
| Advisories excluded from victim counts | PASS | `test_advisory_not_in_incident_counts_and_rls_is_enabled` |
| New tables private by default | PASS | RLS and anon privilege assertions against the migrated database |
| Atomic rollback of incident, evidence and BD writes | PASS | `test_transaction_failure_rolls_back_incident_evidence_pipeline_and_trigger` |
| Python regression suite with database tests enabled | PASS | `uv run python -m pytest -q` → **79 passed** (including 9 DB integration tests) |
| Alert regression suite | PASS | `node --test supabase/functions/_shared/alerting_test.ts` → **21 passed** |
| Python lint | PASS | `uv run ruff check .` → **All checks passed!** |
| Hosted rollout and network delivery | NOT RUN | Requires applying this reviewed migration and matching code to the deployment |

Database tests used an isolated in-memory PGlite instance with the production migration
SQL, PostgreSQL constraints, and SQLAlchemy/psycopg. The only substituted behavior was
the outbound notification function, so test execution could not send real messages.
