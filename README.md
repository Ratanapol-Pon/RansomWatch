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

## Conventions

- Python 3.12 + uv + ruff; Node + pnpm + prettier (Node phases only).
- Timestamps stored UTC, displayed/scheduled Asia/Bangkok.
- One commit per task; secrets only via `.env`.
