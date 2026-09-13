# RansomWatch TH

Public-source cyberattack monitoring, an authenticated dashboard, Discord alerts,
and LINE group summaries, with a focus on Thailand.
Stack and phases are defined in `PLAN.md` (source of truth). Agent rules in `AGENTS.md`.

## Broader threat monitoring upgrade

Upgrade 1 adds the data foundation for additional attack types, separate campaign and
advisory records, source-evidence deduplication, accurate publication/attack dates, and
the optional `dark_web_url` column. Historical imports suppress alerts.

**Existing installations must apply the new migration before running upgraded code.**
See [Upgrade 1 rollout and verification](docs/UPGRADE_PHASE_1.md).

Upgrade 2 adds **CISA KEV**, **ThaiCERT RSS**, and configurable additional RSS/Atom
feeds, with Thai/English attack tags, CVE extraction, a news review queue, and source
health/backoff. Reports are stored separately from victim incidents. See the
[Upgrade 2 runbook](docs/UPGRADE_PHASE_2.md) for setup and acceptance evidence.

```bash
uv run python -m packages.scraper.run --preview       # fetch new feeds, no DB writes
uv run python -m packages.scraper.run --once          # ransomware + enabled new feeds
uv run python -m packages.scraper.run --source-health # new-feed status and freshness
```

Upgrades 3–4 add the **dashboard and LINE group bot**, including the separate
**Dark web URL** column, report review, source health, and customer watchlists. New LINE groups default to **English monthly summaries**,
scheduled on the **first day of the month at 08:00 Bangkok**, after activation.

**Channel timing:** Discord dispatches each new eligible incident immediately after
ingestion, subject to its enabled alert rules. LINE sends monthly summaries by
default; its schedule and quiet hours do not delay Discord. Detection depends on
source publication and polling (the ransomware collector polls every 15 minutes),
so this is immediate on discovery, not necessarily at the time of the attack.

Apply all three upgrade migrations before starting the new API and worker. See
the [dashboard and LINE launch runbook](docs/UPGRADE_PHASE_3_4.md) for account
setup, environment variables, Docker services, and verification results.
The dashboard, API, collector, Discord bot, and LINE worker are deployed on Railway.
LINE group activation and a live group pilot remain operator setup steps.

```bash
uv run python -m apps.api.main        # authenticated dashboard API + LINE webhook
uv run python -m packages.line.worker # LINE commands and scheduled messages
# In apps/web, after configuring .env.local:
pnpm install --frozen-lockfile
pnpm dev
```

BD follow-up was removed on 2026-09-13: the board, API routes, Discord commands,
and automatic follow-up creation are retired. Existing records remain archived;
watchlist matching and alert delivery continue.

## Features (MVP — tags `phase-0`…`phase-4`, `mvp`)

- **Ingestion (Phase 1):** ransomware.live API v2 collector for Thailand (`country=TH`),
  one-time 12-month backfill + 15-min scheduler that never crashes on collector errors.
  Evidence-based deduplication, raw payload merge, watchlist matching, and
  `incident.created` events.
- **Alerts (Phase 3):** Supabase Edge Function (`alert-dispatcher`) triggered by a DB
  webhook on `incidents` INSERT → Discord webhook (red embed + role mention for
  watchlist hits, orange otherwise) + Resend email. Every delivery written to
  `alert_log`; the log is checked before sending — never alert twice. 3× retry with
  backoff, then the error is logged.
- **Discord bot (Phase 4):**
  - Slash commands (everyone): `/latest [n]`, `/victim <name>`, `/group <name>`,
    `/stats [7d|30d|90d]` (matplotlib chart), `/brief [topic] [period]` (≤5 sourced,
    speakable bullets).
  - Slash commands (admin role only): `/watch <company>`, `/unwatch <company>`.
  - Free-text Q&A in `#ask-ransomwatch`: LLM tool-calling into read-only DB query
    functions. Answers come **only** from tool results, always with `source_url`
    citations — the bot never invents incidents. No records → it says so.
- **API (Phase 0):** FastAPI `GET /health`.
- **Conventions:** timestamps stored UTC, displayed/scheduled Asia/Bangkok; no leaked
  personal data copied into any field (Thailand PDPA).

## Layout

```
apps/api            Authenticated FastAPI backend + LINE webhook
apps/web            Next.js monitoring dashboard
packages/line       LINE API client, durable inbox/outbox worker
packages/scraper    Collectors + scheduler (Phase 1)
packages/bot        discord.py bot (Phase 4)
packages/shared     SQLAlchemy models, Pydantic schemas, config
supabase/migrations SQL migrations (0001_init.sql = 5 tables)
supabase/functions  Edge Functions (alert-dispatcher, Phase 3)
infra               docker-compose (local Postgres, optional)
```

## Setup

```bash
cp .env.example .env   # fill in values (never commit .env)
uv sync                # installs Python 3.12 + deps
```

Apply the migration in the Supabase SQL editor
(or `psql $DATABASE_URL -f supabase/migrations/0001_init.sql`).
Creates: incidents, watchlist, pipeline (legacy archive only), alert_rules, alert_log.

### Environment variables

| Variable                                              | Required for       | Notes                                                        |
| ----------------------------------------------------- | ------------------ | ------------------------------------------------------------ |
| `SUPABASE_URL`                                        | alerts             | Project URL                                                  |
| `SUPABASE_KEY`                                        | alerts (fallback)  | anon/service key for local tools                             |
| `SUPABASE_SERVICE_ROLE_KEY`                           | alerts             | Edge Function DB access (auto-provided by Supabase)          |
| `DATABASE_URL`                                        | scraper, bot, api  | Postgres connection string                                   |
| `DISCORD_BOT_TOKEN`                                   | bot                | Discord developer portal; enable Message Content intent      |
| `DISCORD_GUILD_ID`                                    | bot                | guild for instant slash-command sync                         |
| `DISCORD_ALERT_CHANNEL_ID`                            | alerts             | alert channel                                                |
| `DISCORD_WEBHOOK_URL`                                 | alerts             | channel webhook for alert embeds                             |
| `DISCORD_ADMIN_ROLE_ID`                               | alerts, bot        | role mention on watchlist hits; gates admin commands         |
| `DISCORD_ASK_CHANNEL_ID`                              | bot (optional)     | defaults to channel named `ask-ransomwatch`                  |
| `RESEND_API_KEY`                                      | alerts             | resend.com API key                                           |
| `ALERT_EMAIL_FROM`                                    | alerts             | verified sender, e.g. `RansomWatch <alerts@yourdomain>`      |
| `ALERT_DISPATCHER_SECRET`                             | alerts             | shared secret; DB webhook must send it as `x-webhook-secret` |
| `LLM_API_KEY`                                         | chatbot            | OpenAI-compatible API key                                    |
| `LLM_MODEL`                                           | chatbot            | cheapest capable model, e.g. `gpt-4o-mini`                   |
| `LLM_BASE_URL`                                        | chatbot (optional) | blank = OpenAI; e.g. `https://api.deepseek.com/v1`           |
| `RANSOMWARE_LIVE_BASE`                                | scraper            | default `https://api.ransomware.live/v2`                     |
| `TZ_DISPLAY`                                          | all                | default `Asia/Bangkok`                                       |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | local dev          | infra/docker-compose only                                    |

## Run

```bash
make dev               # FastAPI: uvicorn apps.api.main:app --reload
make bot               # Discord bot (Phase 4)
```

Health check: `curl http://127.0.0.1:8000/health` -> `{"status":"ok"}`

## Scraper (Phase 1)

```bash
uv run python -m packages.scraper.run --backfill 12m   # one-time 12-month TH history import
uv run python -m packages.scraper.run --once           # single poll cycle
uv run python -m packages.scraper.run                  # scheduler: polls every 15 min
```

Source: ransomware.live API v2 free tier (endpoints `/countryvictims/TH`, `/recentvictims`;
1 req/min politeness enforced, 62s spacing, 30s timeout, 429 backoff).

## Alerts (Phase 3)

```bash
supabase functions deploy alert-dispatcher
supabase secrets set DISCORD_WEBHOOK_URL=... DISCORD_ADMIN_ROLE_ID=... \
  RESEND_API_KEY=... ALERT_EMAIL_FROM=... ALERT_DISPATCHER_SECRET=...
```

Then create a Supabase Database Webhook on `incidents` INSERT pointing at the
function URL with header `x-webhook-secret: $ALERT_DISPATCHER_SECRET`.

## Deployment (Railway)

Two always-on services run from one repo + one root `Dockerfile`
(`python:3.12-slim` + `uv sync --frozen --no-dev`). No `.env` is baked into the
image — all config comes from Railway environment variables. Supabase stays the
DB; `DATABASE_URL` must be the Supabase pooler URL (publicly reachable).

| Railway service | `SERVICE_MODULE` variable        | Module run                  | Other env vars to set                                                                                                                    |
| --------------- | -------------------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `bot`           | *(unset — Dockerfile default)*   | `packages.bot.bot`          | `DATABASE_URL`, `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_ADMIN_ROLE_ID`, `DISCORD_ASK_CHANNEL_ID`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `TZ_DISPLAY` |
| `scraper`       | `packages.scraper.run`           | `packages.scraper.run`      | `DATABASE_URL`, `RANSOMWARE_LIVE_BASE`, `TZ_DISPLAY`                                                                                     |

The image's `CMD` is `python -m ${SERVICE_MODULE:-packages.bot.bot}`: which
service starts is selected by the `SERVICE_MODULE` env var, not by a Railway
custom start command (the dashboard's Custom Start Command does not persist
reliably, so it is not used). Leave `SERVICE_MODULE` unset on the `bot` service;
set it to `packages.scraper.run` on the `scraper` service (Settings → Variables).

Deploy steps: Railway dashboard → New Project → Deploy from GitHub repo
(`Ratanapol-Pon/RansomWatch`) → it detects the root `Dockerfile`. Add a second
service from the same repo and set `SERVICE_MODULE=packages.scraper.run` in its
Variables. Paste the other env vars per service (Settings → Variables).
Railway auto-restarts crashed processes by default (restart policy: On Failure,
max 10 retries — Settings → Deploy).

### Runbook

- **Logs:** Railway dashboard → service → Deployments → View Logs (live tail).
  Scraper logs `poll done: country=X/Y new, recent=X/Y new` every 15 min;
  bot logs `logged in as RansomWatch TH#…` + `slash commands synced` on boot.
- **Restart:** service → Settings → Restart (or push a commit — auto-redeploys).
- **Redeploy previous version:** Deployments → pick older deploy → Redeploy.
- **Rotate keys:**
  1. `DISCORD_BOT_TOKEN`: Discord Dev Portal → Bot → Reset Token → update the
     `bot` service variable (service restarts automatically on variable change).
  2. `DATABASE_URL`: Supabase → Settings → Database → reset password → update
     BOTH `bot` and `scraper` variables + any local `.env`.
  3. `LLM_API_KEY`: provider console → new key → update `bot` variable.
  4. Alert secrets (`DISCORD_WEBHOOK_URL`, `RESEND_API_KEY`,
     `ALERT_DISPATCHER_SECRET`): `supabase secrets set …` — no Railway change
     needed (alerts run in Supabase Edge Functions, not Railway).
- **Add a new source:** new collector in `packages/scraper/collectors/`, wire
  into `poll_once`, push — the `scraper` service auto-redeploys.

## Tests

```bash
uv run python -m pytest -q
node --test supabase/functions/_shared/alerting_test.ts
```

## Backlog (deferred — see PLAN.md §3)

- **Phase 2 — Web dashboard:** Next.js 14+ PWA (App Router, Tailwind, shadcn/ui) for
  incidents, watchlist, and pipeline management. `apps/web` is a placeholder.
- **Phase 5 — Thai-source scrapers + weekly digest:** ThaiCERT news scraper
  (`source='thaicert'`, `status='confirmed'`), RSS + keyword filter (incl. Thai
  keywords), ransomwatch secondary source, Monday 08:00 Bangkok digest to
  Discord + email. Scrapers must fail loudly on HTML structure changes.
- **Phase 6 — Deployment hardening:** Docker; hosting split (Vercel web,
  Railway/Render api+bot); uptime monitoring; the >24h bot-stability criterion
  is verified here.

## Conventions

- Python 3.12 + uv + ruff; Node + pnpm + prettier (supabase/functions, Phase 2).
- Timestamps stored UTC, displayed/scheduled Asia/Bangkok.
- One commit per task; secrets only via `.env` (gitignored); secret scan before every push.
