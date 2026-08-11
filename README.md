# RansomWatch TH

Monitoring + alerting for Thai ransomware victims, with a BD follow-up pipeline.
Stack and phases are defined in `PLAN.md` (source of truth). Agent rules in `AGENTS.md`.

## Layout

```
apps/api            FastAPI backend (GET /health)
apps/web            Next.js PWA (Phase 2 - deferred, placeholder)
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

## Run

```bash
make dev               # or: uv run uvicorn apps.api.main:app --reload
```

Health check: `curl http://127.0.0.1:8000/health` -> `{"status":"ok"}`

## Database migration

Apply `supabase/migrations/0001_init.sql` in the Supabase SQL editor
(or `psql $DATABASE_URL -f supabase/migrations/0001_init.sql`).
Creates: incidents, watchlist, pipeline, alert_rules, alert_log.

## Scraper (Phase 1)

```bash
uv run python -m packages.scraper.run --backfill 12m   # one-time 12-month TH history import
uv run python -m packages.scraper.run --once           # single poll cycle
uv run python -m packages.scraper.run                  # scheduler: polls every 15 min
```

Source: ransomware.live API v2 free tier (endpoints `/countryvictims/TH`, `/recentvictims`;
1 req/min politeness enforced, 62s spacing, 30s timeout, 429 backoff).

## Discord bot (Phase 4)

```bash
make bot              # or: uv run python -m packages.bot.bot
```

Slash commands: `/latest`, `/victim`, `/group`, `/stats`, `/brief`, `/pipeline` (all users);
`/watch`, `/unwatch`, `/pipeline_update` (admin role `DISCORD_ADMIN_ROLE_ID` only).
Free-text Q&A: post in the `#ask-ransomwatch` channel (or set `DISCORD_ASK_CHANNEL_ID`).
Answers come only from DB query tools via LLM tool-calling, always with `source_url`
citations; the bot never invents incidents. Requires `LLM_API_KEY` + `LLM_MODEL`
(OpenAI-compatible API; optional `LLM_BASE_URL` for other providers). Without them the
slash commands still work and the chatbot replies with a not-configured message.

## Tests

```bash
uv run pytest -q
```

## Conventions

- Python 3.12 + uv + ruff; Node + pnpm + prettier (Node phases only).
- Timestamps stored UTC, displayed/scheduled Asia/Bangkok.
- One commit per task; secrets only via `.env`.
