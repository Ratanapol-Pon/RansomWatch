# Dashboard, LINE groups, and deployment handoff

Implemented and locally verified on 2026-09-10; the owner approved the GitHub push.
Production migration and live LINE deployment remain pending. No live LINE messages
were sent during implementation or verification.

## Confirmed channel timing

The owner's requested setup is **immediate Discord incident alerts** and
**monthly LINE summaries**. These paths are independent:

- Discord: inserting a new alert-eligible incident triggers the existing alert
  dispatcher immediately. Enabled Discord alert rules determine which incidents
  are sent. Historical imports and reports that are not victim incidents remain
  excluded. LINE quiet hours and monthly scheduling do not affect this dispatcher.
- LINE: keep `LINE_DEFAULT_DELIVERY=monthly` and group delivery mode `monthly`.
  English summaries run on the first day of each month at 08:00 Bangkok by default.

“Immediate” means after collection, not at the moment the attack occurs. The
ransomware collector polls every 15 minutes, and a source may publish an incident
later than its attack date. A live rollout must retain the incident INSERT webhook,
dispatcher configuration, and an enabled matching Discord rule.

## What is included

- Next.js dashboard: overview counts and trends, paginated incident and report
  search, attack/country/date filters, separate **Dark web URL** column and evidence
  details, human report review, source health, watchlists, private BD pipeline,
  alert rules, LINE group settings and delivery history.
- FastAPI checks Supabase Auth on each request and an explicit database membership.
  Viewers see public-source intelligence; analysts can review reports and manage
  customer follow-up; administrators also manage alert rules and LINE groups.
- LINE webhook validates the signature before parsing. A durable inbox deduplicates
  events. Only membership events and recognized commands are retained; ordinary
  group conversation is discarded. Reply tokens and command text are removed after
  processing. Group member profiles and customer notes are not sent to LINE.
- New groups are inactive until an administrator activates them. Defaults are
  **English**, **monthly summary**, **TH**, and global vulnerability advisories.
  The summary is scheduled for the **first day of each month at 08:00 Asia/Bangkok**.
  Default quiet hours are 22:00–08:00. Language, delivery mode, country and attack
  filters, summary hour and quiet hours are editable per group.
- Monthly summaries cover observations collected in the previous calendar month,
  starting no earlier than group activation. A midmonth activation receives its
  first summary next month. Counts describe collected public reports, not the
  number of all attacks. Daily summaries and immediate victim alerts are opt-in.
  Immediate mode covers eligible incidents, not general news or advisory updates.
- `!latest`, `!company NAME`, `!reports`, `!stats`, `!brief`, `!help` query the database
  using the group's filters. Briefings are deterministic sourced excerpts, with no
  LLM requirement. Commands can reply during quiet hours; quiet hours apply to pushes.

## Apply migrations first

Back up the production database, stop collectors/workers, and apply the three
upgrade migrations in order after the original 0001–0003 migrations:

1. `20260910124341_threat_intelligence_foundation.sql`
2. `20260910130021_collector_health_and_review.sql`
3. `20260910161359_dashboard_access_and_line.sql`

Existing incident IDs and customer follow-up links remain intact. Follow the
[Upgrade 1](UPGRADE_PHASE_1.md) and [Upgrade 2](UPGRADE_PHASE_2.md) runbooks for legacy
enrichment and collector rollout. The new tables use RLS and deny direct access to
`anon` and `authenticated`. The API/worker use the private database connection.
Do not enable public read policies to make the dashboard work.

## Configure and run

Use `.env.example` for server settings and `apps/web/.env.example` for browser
settings. Keep real values in `.env`, `apps/web/.env.local`, or host secret settings.

| Setting | Location | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Server | Private PostgreSQL connection; use TLS for hosted Supabase |
| `SUPABASE_URL` | API | Project URL |
| `SUPABASE_AUTH_KEY` | API | Supabase publishable key or legacy anon key for Auth verification |
| `WEB_ORIGINS` | API | JSON array of exact allowed dashboard origins |
| `API_PORT` | API | Listening port, default 8000; match your host's exposed port |
| `LINE_CHANNEL_SECRET` | API | Messaging API channel secret for webhook verification |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE worker | Messaging API channel access token |
| `LINE_DEFAULT_LANGUAGE` | LINE worker | `en` (default) or `th` |
| `LINE_DEFAULT_DELIVERY` | LINE worker | `monthly` (default), `digest`, or `immediate` |
| `NEXT_PUBLIC_API_URL` | Web build | API origin visible to the browser |
| `NEXT_PUBLIC_SUPABASE_URL` | Web build | Same Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Web build | Publishable/anon key only |

Never use a service-role key as a `NEXT_PUBLIC_*` value. Next.js embeds public
configuration at build time: rebuild and redeploy the web app when these change.

Create an email/password user in Supabase Auth, then enroll its UUID explicitly:

```bash
uv sync --frozen
uv run python -m apps.api.members --user-id YOUR_AUTH_USER_UUID --role admin
```

The dashboard has a password sign-in form and no self-registration or role elevation.
Use the same CLI with `--role viewer` / `--role analyst` for other users or `--disable`
to revoke dashboard access. Supabase user metadata never grants access.

Run each service in a separate terminal from the repository root:

```bash
uv run python -m apps.api.main
uv run python -m packages.scraper.run
uv run python -m packages.line.worker
```

For the web app:

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://127.0.0.1:3000`. On Windows, use `npx.cmd --yes pnpm` if pnpm is not
installed. API documentation is at `/docs`; `/health` is a process liveness check,
not a database readiness check. API data and responses use `Cache-Control: no-store`.
The web manifest supports a standalone display; offline data access is not provided.

## Container and hosting configuration

`infra/docker-compose.services.yml` reuses an existing Supabase database. It does
not create or migrate one. Set the public build settings in root `.env` for Compose.

```bash
docker compose --env-file .env -f infra/docker-compose.services.yml --profile web up -d --build
# Start only after LINE account/webhook setup:
docker compose --env-file .env -f infra/docker-compose.services.yml --profile line up -d line
# Run one collector instance; avoid duplicating the existing hosted scheduler:
docker compose --env-file .env -f infra/docker-compose.services.yml --profile collectors up -d scraper
```

Local ports bind to loopback. For hosting, configure HTTPS with your provider or
reverse proxy, set the final API URL in the web build and exact web origin in
`WEB_ORIGINS`. The root Dockerfile supports these independent service modules:

| Service | `SERVICE_MODULE` |
| --- | --- |
| API | `apps.api.main` |
| LINE worker | `packages.line.worker` |
| Collector | `packages.scraper.run` |
| Existing Discord bot | `packages.bot.bot` |

Run one LINE worker for the initial pilot. Containers use restart policies in the
Compose file. The web Dockerfile builds static Next.js output and serves it with
Nginx. Alternatively, `pnpm build` produces `apps/web/out` for static hosting;
the API and worker must run separately. Sites publishing has not been performed;
GitHub delivery does not configure the hosted API, authentication, or LINE account.

## Connect the LINE Official Account

1. Enable Messaging API for the account and configure the two private LINE server
   values above. Set the webhook to `https://YOUR_API_HOST/webhooks/line`.
2. Verify the webhook and enable webhook delivery/redelivery. Enable **Allow bot
   to join group chats** in the channel's Messaging API settings. LINE permits one
   Official Account in a group at a time. See [LINE group setup](https://developers.line.biz/en/docs/messaging-api/group-chats/).
3. Invite the account to your pilot group. Its signed join event registers an
   inactive group. If it was already invited before webhook setup, send `!help`
   to register it without activating it.
4. In the dashboard's **Alerts & LINE**, name the group and activate it. Check
   English, monthly summary, country scope and quiet hours before saving.
5. Send `!help` and `!latest` in the pilot group, then verify sourced replies and
   delivery history. If the bot leaves and rejoins, activate it again.

The webhook follows LINE's [raw-body signature verification](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/).
Push retries reuse a durable UUID, including after ambiguous network failures.
LINE's retry-key retention is 24 hours; this worker stops messages 23 hours after
queue creation to avoid retrying outside that window. See [LINE retry behavior](https://developers.line.biz/en/docs/messaging-api/retrying-api-request/).

## Operations and recovery

- **Source outage:** inspect Source health for errors, retry time and staleness.
  Freshness uses twice `INTEL_POLL_MINUTES`. This view covers the new intelligence
  feeds; the legacy ransomware collector continues to report through its logs.
- **Delivery failure/quota:** inspect Alerts & LINE delivery history. The worker
  checks account quota and group size before pushes, defers insufficient quota for
  six hours, and limits push attempts to five. The provider's quota remains the
  authority; concurrent activity from other services can consume capacity.
- **Group setting changes:** pending messages are cancelled and keep their unique
  keys. Updated filters apply to future queues; a cancelled monthly summary is not
  automatically resent that month. This avoids reusing an accepted retry key with
  changed content. Deactivation or a leave event stops pending delivery.
- **Restart:** restart the affected service. Inbox/outbox records survive. Expired
  command replies are discarded instead of converted to unsolicited push messages.
- **Key rotation:** replace the key in host secret settings and restart the affected
  API or worker. Public web-key changes require a rebuild. Never log tokens or
  webhook bodies. Processed command content is scrubbed; operational IDs and delivery
  metadata remain for deduplication. No automatic metadata retention purge is enabled.
- **Rollback:** stop the upgraded services and restore the prior application
  release. Keep the additive tables/columns; do not drop incident/evidence data.
  Use the database backup for an actual data recovery, with collectors stopped.

## Acceptance evidence

Verified locally on 2026-09-10. Database integration used an isolated, disposable
PGlite PostgreSQL engine over loopback, with simulated outbound database triggers.
LINE HTTP calls and Supabase Auth verification were mocked in automated tests.

| Acceptance check | Result / evidence |
| --- | --- |
| Migration/data preservation, collectors, API permissions and LINE regressions | PASS: `uv run python -m pytest -q` with loopback `TEST_DATABASE_URL`: **122 passed** |
| Existing Discord/email alerts | PASS: `node --test supabase/functions/_shared/alerting_test.ts`: **21 passed** |
| Python lint | PASS: `uv run ruff check .`: **All checks passed** |
| Dashboard TypeScript and static production build | PASS: `pnpm build`: compiled, typechecked and exported `/` and `/_not-found` |
| Local web availability | PASS: HTTP GET `http://127.0.0.1:3000` returned **200** |
| API HTTP smoke | PASS: `/health` returned 200; unauthenticated `/api/incidents` returned 401 with no-store |
| Credential-pattern scan | PASS: 109 text files checked; no configured secret values or common private-key/token patterns found |
| Admin enrollment command | PASS: `python -m apps.api.members --help` |
| Real hosted Supabase Auth and migration rollout | PENDING: live configuration and rollout |
| Browser interaction / visual QA | NOT RUN |
| Docker image build/runtime | NOT RUN: Docker unavailable in this environment |
| Live LINE webhook, replies and scheduled delivery | PENDING: LINE credentials and pilot group setup |

The Python suite emits one dependency deprecation warning from Starlette's use of
httpx in its test client. No tests fail or skip in the final database-enabled run.

For repeatable database checks, start an isolated local PostgreSQL instance and
set `TEST_DATABASE_URL` to its loopback connection. A lightweight alternative used
here was `npx.cmd --yes @electric-sql/pglite-socket --host=127.0.0.1 --port=55439`.
Tests create and remove their own schemas and reject remote test database URLs.

The upgrade is ready for deployment review. Live acceptance remains open until
hosted migrations, account configuration, and a real pilot have been completed.
