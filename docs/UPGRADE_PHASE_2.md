# Upgrade 2: broader threat collection

Implemented locally on 2026-09-10. This phase collects and classifies broader public
threat reports; the dashboard and LINE bot remain subsequent phases. Existing live
Supabase and Railway services have not been changed.

## Sources and interpretation

| Source | Input | Storage and meaning |
|---|---|---|
| CISA KEV | Official JSON catalog | Advisory per CVE; confirmed exploitation, not a confirmed victim incident |
| ThaiCERT | Official RSS feed | Reviewable news reports with Thai/English attack tags and CVEs |
| Additional news | Operator-configured RSS/Atom URLs | Same reviewable news pipeline; no unconfigured publishers are scraped |

Verified endpoints:
- <https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json>
- <https://www.thaicert.or.th/feed/>
- <https://www.thaicert.or.th/robots.txt>

KEV records use CVE IDs as stable identities. `published_at` represents the catalog's
`dateAdded`, not vulnerability disclosure date or attack date. `raw` retains the
source JSON, including required action, due date, and ransomware-use indicator.
An indicator of ransomware use does not turn a CVE into a victim incident.

RSS/Atom identity uses a hash of the feed GUID/ID, falling back to its article URL.
Changed titles or descriptions update the same report. Classification uses explicit
Thai and English keyword rules across titles and summaries; detected tags are hints
for review, not assertions that an organization was attacked. CVE mentions alone do
not imply exploitation. `country` stays unknown unless later reviewed; a Thai
publisher can describe an attack elsewhere. RSS news starts with `needs_review=true`
and `confidence=reported`. Refreshing it preserves completed human review decisions.

RSS storage retains source metadata and a short plain-text excerpt (up to 600
characters), not full article bodies or `content:encoded`. Article links are cited
but never crawled. The existing `dark_web_url` field is preserved when a source link
is an onion URL; the worker does not fetch onion destinations.

RSS records can be read in the database or previewed from the CLI now. Review UI,
explicit victim promotion, and sharing new report types through bots are later
phases. No victim is inferred automatically from a headline, and these reports
produce no incident-created alerts or BD pipeline rows.

## Collection and health

Ransomware polling remains every 15 minutes. A separate scheduler job runs the new
feeds every 60 minutes by default. Each job coalesces missed runs and permits one
instance per worker. An individual feed error does not block the other feeds.

Public feed requests have a 30-second timeout and a 5 MB decoded response limit.
RSS access checks robots.txt, respects disallow/crawl-delay, and spaces requests to
the same host by at least 30 seconds. Redirects are reported as errors: configure the
canonical feed URL. If robots.txt cannot be verified (other than a 404), collection
fails visibly. Crawl delays above 60 seconds require a different polling strategy
and are reported instead of blocking the worker indefinitely.

`source_health` records status (`ok`, `degraded`, `error`), attempt/success times,
fetched/inserted/updated/filtered/rejected counts, consecutive failures, last error,
and next retry time. Partial malformed data is marked degraded; a malformed or
unexpectedly empty feed is an error. An unrelated-only valid feed can succeed with
all records explicitly counted as filtered.

Failures schedule exponential retry delays from 15 minutes up to 6 hours; an upstream
`Retry-After` can extend that delay. Actual retries occur on the next scheduled or
manual poll after the deadline. The health CLI flags data stale when no successful
fetch exists or the last success is older than twice the configured poll interval.
Health counters cover the new feeds; the existing ransomware worker retains its logs.
They do not represent complete internet attack coverage or guarantee source uptime.

## Configuration and commands

Defaults and examples are in `.env.example`:

| Setting | Default |
|---|---|
| `CISA_KEV_ENABLED` | `true` |
| `CISA_KEV_URL` | Official CISA JSON endpoint |
| `THAICERT_ENABLED` | `true` |
| `THAICERT_FEED_URL` | Official ThaiCERT RSS endpoint |
| `NEWS_RSS_URLS` | `[]` (JSON array of approved feed URLs) |
| `INTEL_POLL_MINUTES` | `60` (minimum 15) |

The first KEV collection imports the current catalog; it does not flood alert channels.
ThaiCERT imports only entries present in its current feed. Historical news crawling
and additional publishers are not automatically enabled.

```bash
# Read-only live source check; no database or messaging credentials needed.
uv run python -m packages.scraper.run --preview
uv run python -m packages.scraper.run --preview --source thaicert

# Persist once after migration; a failed/degraded source returns exit code 1.
uv run python -m packages.scraper.run --once
uv run python -m packages.scraper.run --once --source cisa_kev

# Run scheduler, or inspect health (timestamps are UTC, explicitly offset).
uv run python -m packages.scraper.run
uv run python -m packages.scraper.run --source-health
```

Source selectors: `all`, `ransomware_live`, `cisa_kev`, `thaicert`, `news`.
`--preview` supports the intelligence feeds; `--backfill` remains ransomware-only.
Additional RSS publishers must be enabled through `NEWS_RSS_URLS`, respecting their
access terms. No paid feeds or API keys are required for the two default new sources.

## Migration and rollout

Apply the Upgrade 1 migration and legacy enrichment as documented in its runbook,
then `supabase/migrations/20260910130021_collector_health_and_review.sql` before
starting this version. The second migration adds the `news` report kind, review and
update fields, indexes, and backend-only source health. It performs no incident inserts
and creates no outbound hooks. Source-health RLS is enabled; anon/authenticated access
is revoked. Existing incident IDs, BD links, and source evidence remain intact.

Run `uv sync --frozen` to install locked dependencies, including feedparser and
BeautifulSoup. The existing Dockerfile already uses the lockfile. Keep older workers
paused during rollout and follow the Upgrade 1 backup/recovery sequence. This task
prepared the code and migrations; it did not apply them to hosted services or push Git.

## Acceptance evidence — 2026-09-10

| Check | Result | Evidence |
|---|---|---|
| Live official feed parsing | PASS | Preview: 1,703 KEV entries; ThaiCERT 9 accepted, 1 filtered, 0 rejected |
| Live data imported twice locally | PASS | 1,712 initial inserts; replay: 0 inserts, 0 updates; 0 victim incidents and 0 alerts |
| Stable report identity and corrections | PASS | DB replay/update test retains report ID and discovery time |
| No victim-count inflation or alert flood | PASS | Advisory/news ingestion writes no incidents or notification records |
| Human review survives refresh | PASS | Database test preserves reviewed country, kind, confidence, and tags |
| Thai/English tags and CVEs | PASS | Collector tests include Thai malware, phishing, DDoS, and CVE mentions |
| Broken feeds fail visibly | PASS | Tests cover malformed JSON/XML, empty feeds, invalid records, and HTTP limits |
| Politeness and retry handling | PASS | Robots disallow/cache/delay and Retry-After tests |
| Failure isolation and recovery | PASS | One failed source is deferred while another persists; recovery clears failures |
| Private source-health table | PASS | Migrated database verifies RLS and no authenticated SELECT privilege |
| Python suite with isolated DB enabled | PASS | `uv run python -m pytest -q` → **104 passed**, including 13 DB integration tests |
| Alert regressions | PASS | `node --test supabase/functions/_shared/alerting_test.ts` → **21 passed** |
| Lint and whitespace | PASS | `uv run ruff check .`; `git diff --check` |
| Hosted rollout | NOT RUN | Live database and deployed services unchanged |

The database tests apply both upgrade migrations to an isolated PGlite database.
The outbound Supabase function is replaced by a local recording trigger, so tests
cannot send real messages. Native multiworker concurrency and hosted Vault/pg_net
delivery remain deployment checks.
