# RansomWatch TH — Phased Build Plan (for opencode / VSCode)

## Feature retirement ? 2026-09-13

At the owner's request, remove BD follow-up from the dashboard, API, Discord
commands, and AI tools, and stop creating follow-up rows. Retain the legacy table
and records for history. Watchlists, incident monitoring, immediate Discord alerts,
and English monthly LINE summaries remain supported. This supersedes all BD
pipeline requirements in the historical MVP plan below.

## Approved expansion — 2026-09-10

The owner approved starting the first upgrade phase and requested a separate
`dark_web_url` column. Upgrade numbering below is separate from the original MVP
phase numbers retained in this document. The existing tech stack is unchanged.

| Upgrade | Scope | Status |
|---|---|---|
| 1 | Data foundation, evidence identity, accurate dates, dark-web URL metadata | Implementation and local verification; see [runbook](docs/UPGRADE_PHASE_1.md) |
| 2 | ThaiCERT/news and KEV collectors, classification and source health | Implemented and locally verified; see [runbook](docs/UPGRADE_PHASE_2.md) |
| 3 | Authenticated dashboard (including dark-web URL column), filtered API, watchlists | Implemented and locally verified; see [runbook](docs/UPGRADE_PHASE_3_4.md) |
| 4 | LINE Official Account group bot, subscriptions and quota controls | Implemented and locally verified; English monthly summaries by default |
| 5 | Deployment hardening and pilot | Container configuration and runbook prepared; GitHub push approved; live deployment/pilot pending configuration and migrations |

Confirmed delivery preference: Discord alerts immediately when a new eligible
incident is ingested; LINE sends English monthly summaries (first day, 08:00
Asia/Bangkok). LINE scheduling is independent of Discord. Public-source publication
and collector polling determine detection latency; this does not promise detection
at the exact time an attack occurs.

Upgrade 1 supersedes the old company/group deduplication rule in §3 and automatic
ThaiCERT confirmation in the legacy backlog. Incidents require victim metadata;
campaigns and advisories live in a separate `threat_reports` table and do not count
as victim incidents. Sources start as claimed/reported until evidence is reviewed.
Historical imports are stored with alerts suppressed. The dark-web URL is optional,
HTTP(S) `.onion` link metadata, separate from `source_url`; it is not crawled.

Upgrade 1 acceptance: migration preserves incident IDs and BD links; repeat imports
create no duplicates; distinct dated attacks survive; explicit attack dates are kept;
publication dates are separate; onion URLs validate and round-trip; historical imports
send no alerts; advisories do not affect victim counts; new tables are private.

The remainder describes the original MVP and is retained as historical context.

Upgrade 2 acceptance: live ThaiCERT and KEV feeds parse; repeated report imports do
not duplicate records; corrections update the same source record; Thai/English news
classification is reviewable; malformed feeds fail visibly; one feed failure does
not stop others; retry delays and source freshness are recorded; news and advisories
do not create victim incidents or alerts. Optional additional RSS sources require
explicit configuration. Dashboard access and review actions are Upgrade 3.

> **One-line pitch:** A monitoring + alerting tool that tracks Thai companies hit by
> ransomware, aggregates data from public APIs and web scraping, and pushes real-time
> alerts to Discord (with an interactive chatbot) and email — doubling as a JasTel BD
> prospect-intelligence pipeline.

**Working name:** RansomWatch TH
**Owner:** Rz (Cyber Security BD @ JasTel)
**Executor:** opencode agent inside VSCode
**Date drafted:** 2026-08-11 (v2 — lean MVP path)

---

## 0. MVP Strategy (READ THIS FIRST — v2 change)

**The full product has 7 phases, but the value chain works with only 4.**
The core loop is: *Thai company gets hit → Rz knows within minutes → it becomes a BD
conversation / warm prospect.* That loop needs ingestion + alerts + chatbot — **not** a
web dashboard (ransomware.live already has a good one).

**Build order (MVP fast path, ~1 week):**

```
Phase 0 (scaffold) → Phase 1 (ingestion) → Phase 3 (alerts) → Phase 4 (chatbot)
```

**Defer until the MVP proves useful:** Phase 2 (web dashboard), Phase 5 (Thai-source
scrapers), Phase 6 (deployment hardening). The full 7-phase map is in §3 — opencode
should treat Phases 2/5/6 as a backlog, not a commitment.

**MVP infrastructure is deliberately minimal:**
- Alerts via **Supabase Edge Function → Discord webhook + Resend email** (no always-on
  server needed for one-way alerts)
- The **persistent Discord bot process** is only introduced in Phase 4, when interactive
  slash commands require it
- Target cost for month 1: **~$0** (Supabase free tier + Resend free tier 100 emails/day
  + Discord free)

---

## 1. Product Definition

### 1.1 What it does
1. **Collects** ransomware-victim data about organizations in **Thailand** from:
   - Public threat-intel APIs (primary: **Ransomware.live API v2** — free, no key needed,
     supports country filtering with `country=TH`)
   - Web scraping of public sources (news, ThaiCERT/NCSA announcements, ransomwatch data)
     — *deferred to Phase 5*
   - ~~Dark-web DLS scraping via Tor~~ — **explicitly out of scope for v1** (see §5)
2. **Stores** incidents in Postgres (Supabase) with deduplication.
3. **Tracks** a watchlist of customers/prospects with a **BD follow-up pipeline**
   (`not_contacted → contacted → meeting_booked → po_won`).
4. **Alerts** new incidents via Discord + email within ~1 minute of ingestion.
5. **Answers questions** via a Discord chatbot (slash commands + free-text Q&A), including
   a `/brief` command that produces customer-meeting-ready talking points.
6. **Mobile**: PWA (installable on phone) — deferred with the dashboard to Phase 2/6.

### 1.2 Why it matters (business framing)
Thailand entered the **global top-10 most ransomware-targeted countries** in Q1 2026
(Check Point Research). For a cyber-security BD role, knowing which Thai companies got
hit, by which group, and when = warm prospect list + credibility in customer
conversations. The pipeline-tracking layer turns "monitoring" into a measurable
sales-intelligence story (incidents → contacts → meetings → POs).

### 1.3 Data sources (verified, with references)

| Source | Type | Access | Notes |
|---|---|---|---|
| **Ransomware.live API v2** | REST API | Free, no API key | Base URL `https://api.ransomware.live/v2`. Endpoints: `/victims`, `/country/victims/{code}`, `/recent`, `/groups`, `/cyberattacks`. Has `/country/victims/TH` for Thailand. Docs: https://github.com/JMousqueton/ransomware.live |
| **Ransomware.live MCP server** | MCP tools | Free, open source | https://github.com/Cyreslab-AI/ransomware-live-mcp-server — reference for the chatbot layer |
| **Ransomwatch (GitHub)** | Scraped DLS data, open source | Free | https://github.com/captainGeech42/ransomwatch — posts scraped from ransomware leak sites, good secondary/fallback source |
| **ThaiCERT / NCSA Thailand** | Website scraping | Public | https://www.thaicert.or.th — national incident stats + threat news. Scrape news page; respect robots.txt and rate limits |
| **Ransom-DB** | REST API | Paid plans | https://www.ransom-db.com — only consider if free sources prove insufficient |
| **Thai news (Bangkok Post, The Standard, etc.)** | RSS/scraping | Public | Keyword-based: "ransomware", "แรนซัมแวร์", company names on watchlist |

> ⚠️ **Legal/ToS note for opencode:** Only scrape public pages, honor `robots.txt`,
> keep request rates low (≥ 30s between hits per site), and never download or host
> actual leaked victim data — only metadata (victim name, group, date, source URL).
>
> ⚠️ **PDPA caution (Thailand):** Never copy leaked *personal* data into any field.
> Keep `description` factual ("group claims X GB exfiltrated"). If individuals are
> named in a leak post, do not reproduce names. When demoing to customers, frame the
> tool as "public threat-intel aggregation" — never imply dark-web access.

---

## 2. Tech Stack (fixed decisions — opencode should not re-litigate)

| Layer | Choice | Why |
|---|---|---|
| Database | **Supabase (hosted Postgres)** | Free tier, realtime, auth built-in; owner already has access |
| Backend API | **FastAPI (Python 3.12)** | Best fit for scraping/data pipelines; clean OpenAPI docs |
| Scraper/scheduler | Python: `httpx`, `beautifulsoup4`, `feedparser`, `APScheduler` | Worker service |
| Alert delivery (MVP) | **Supabase Edge Function → Discord webhook + Resend API** | Zero always-on infra; ~$0/month |
| Discord bot (Phase 4) | **`discord.py`** (same Python codebase) | Slash commands + chatbot; reuses DB models |
| Frontend (Phase 2, deferred) | Next.js 14+ (App Router) + TS + Tailwind + shadcn/ui, configured as PWA | One codebase for web + installable mobile |
| Email | **Resend** free tier | 100 emails/day is plenty; do NOT hand-roll SMTP |
| LLM (chatbot) | Cheapest capable model first (the task is "map question → query function"); no premium models needed | Cost control |
| Infra (Phase 6) | Docker; Vercel (web) + Railway/Render (api+bot) | Only when persistence is needed |

**Time handling rule (global):** store everything in **UTC** (ransomware.live timestamps
are UTC), display and schedule in **Asia/Bangkok**. The Monday digest must fire at
**08:00 Bangkok time**, not UTC.

**Repo layout opencode should create:**

```
ransomwatch-th/
├── apps/
│   ├── web/          # Next.js PWA (Phase 2 — deferred)
│   └── api/          # FastAPI backend
├── packages/
│   ├── scraper/      # Python: collectors (API pullers + web scrapers)
│   ├── bot/          # Python: discord.py bot + chatbot logic (Phase 4)
│   └── shared/       # Python: DB models (SQLAlchemy), schemas (Pydantic), config
├── supabase/
│   └── functions/
│       └── alert-dispatcher/   # Edge Function: incident.created → Discord + email
├── infra/
│   └── docker-compose.yml
├── .env.example
├── PLAN.md           # this file
└── AGENTS.md         # instructions for opencode (see §7)
```

---

## 3. Data Model (target schema — Phase 1 builds this)

```sql
-- incidents: one row per claimed ransomware victim event
incidents
  id              uuid pk
  victim_name     text not null
  normalized_name text          -- lowercase, punctuation stripped (for dedup)
  domain          text
  country         text default 'TH'
  sector          text
  group_name      text          -- ransomware group, e.g. 'lockbit', 'qilin'
  discovered_at   timestamptz   -- when WE first saw it (UTC)
  attack_date     date          -- when attack happened (if known)
  source          text          -- 'ransomware_live' | 'ransomwatch' | 'thaicert' | 'news'
  source_url      text
  description     text          -- factual only; never leaked personal data (PDPA)
  status          text default 'unverified'  -- unverified | confirmed | removed | paid
  watchlist_hit   boolean default false
  raw             jsonb         -- original payload for audit
  unique (normalized_name, group_name, source)   -- dedup key

-- watchlist: companies Rz cares about (customers/prospects)
watchlist
  id uuid pk
  name text not null
  aliases text[]                -- alternate spellings, Thai name, domains
  domains text[]
  priority int default 1        -- 1=high (customer), 2=medium, 3=low
  notes text

-- BD pipeline: tracks follow-up on watchlist-matched incidents (v2 addition)
-- Turns "monitoring" into measurable sales intelligence:
-- incidents → contacted → meetings → POs
pipeline
  id               uuid pk
  incident_id      uuid references incidents
  watchlist_id     uuid references watchlist
  follow_up_status text default 'not_contacted'
                   -- not_contacted | contacted | meeting_booked | po_won | dead
  owner_note       text          -- e.g. "spoke to IT mgr 12 Aug, send proposal"
  updated_at       timestamptz
  unique (incident_id, watchlist_id)

-- alert_rules: who gets notified how
alert_rules
  id uuid pk
  name text
  match_mode text               -- 'any_thailand' | 'watchlist_only' | 'group' | 'sector'
  match_value text
  channel text                  -- 'discord' | 'email' | 'both'
  discord_channel_id text
  email_recipients text[]
  enabled boolean default true

-- alert_log: delivery audit (prevents duplicate alerts)
alert_log
  id uuid pk
  incident_id uuid references incidents
  rule_id uuid references alert_rules
  channel text
  sent_at timestamptz
  success boolean
  error text
```

**Dedup rule (important):** an incident is "new" only if
`(normalized_name, group_name)` has never been seen from ANY source.
Same victim appearing on both ransomware.live and a news site = ONE incident,
append extra sources to `raw`.

**Normalization rule (Thai companies):** lowercase, strip `co., ltd.`, `pcl`,
`จำกัด`, `มหาชน`, punctuation, extra whitespace. Watchlist `aliases` handles the rest
(e.g. "Bangkok Airways", "Bangkok Airways PCL", "การบินกรุงเทพ").

---

## 4. Phases

> MVP fast path = **0 → 1 → 3 → 4** (~1 week). Phases 2, 5, 6 are backlog.
> Give opencode ONE phase at a time. Acceptance criteria are the contract.

---

### 🟦 Phase 0 — Project Scaffold (0.5 day) [MVP]

**Goal:** runnable skeleton with env management.

**Tasks for opencode:**
1. Create the repo layout from §2 (skip `apps/web` for now — create an empty placeholder
   dir only, or omit entirely).
2. `apps/api`: FastAPI with `uvicorn`, health endpoint `GET /health` → `{"status":"ok"}`.
3. `packages/shared`: SQLAlchemy models + Pydantic schemas for the 5 tables in §3
   (including `pipeline`).
4. `.env.example` with: `SUPABASE_URL`, `SUPABASE_KEY`, `DATABASE_URL`,
   `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_ALERT_CHANNEL_ID`,
   `DISCORD_WEBHOOK_URL`, `DISCORD_ADMIN_ROLE_ID`,
   `RESEND_API_KEY`, `ALERT_EMAIL_FROM`, `LLM_API_KEY`, `LLM_MODEL`,
   `RANSOMWARE_LIVE_BASE=https://api.ransomware.live/v2`, `TZ_DISPLAY=Asia/Bangkok`.
5. README with run instructions (`make dev` / `uv` / `pnpm`).

**Acceptance criteria:**
- [ ] `GET /health` returns 200 locally
- [ ] Migration SQL creates all 5 tables in Supabase
- [ ] No secrets committed; `.env` is gitignored

---

### 🟦 Phase 1 — Data Ingestion MVP (1–2 days) [MVP]

**Goal:** Thai ransomware incidents flowing into Postgres automatically — **including a
historical backfill so the tool has demo value on day one.**

**Tasks for opencode:**
1. `packages/scraper/collectors/ransomware_live.py`:
   - Poll `GET {BASE}/country/victims/TH` and `GET {BASE}/recent` (filter `country == "TH"`)
   - Every **15 minutes** via APScheduler (do NOT poll faster — free tier, be polite;
     set a real `User-Agent`, 30s timeout)
2. **Backfill job (run once):** pull the last 12 months of Thai victims from
   ransomware.live so the DB starts with real history (e.g. the Bangkok Airways/LockBit
   entry). This also stress-tests name normalization against real messy data immediately.
3. `packages/scraper/pipeline.py`:
   - Normalize victim name (rules in §3) → check dedup key → insert or merge
   - On NEW incident: write to `incidents`, emit internal event `incident.created`
4. Matching engine v1: case-insensitive substring match of `normalized_name` against
   `watchlist` (name + aliases + domains) → set `incident.watchlist_hit = true`;
   auto-create a `pipeline` row (`not_contacted`) for each watchlist match.
5. CLI: `python -m packages.scraper.run --once` and `--backfill 12m` for manual testing.

**Acceptance criteria:**
- [ ] Backfill imports ≥ 12 months of TH history; running it twice creates no duplicates
- [ ] Poller inserts new incidents and survives API errors (logs, backoff, never crashes)
- [ ] A watchlist entry matching a known past victim sets `watchlist_hit` and creates a
      `pipeline` row
- [ ] UTC storage verified; display helpers render Bangkok time correctly

---

### 🟩 Phase 2 — Web Dashboard + REST API (2–3 days) [BACKLOG]

> Build ONLY if the MVP (Discord-first workflow) leaves you wanting a visual surface
> to show customers or your VP. ransomware.live's own dashboard covers casual browsing.

**Tasks for opencode:** REST API (`/api/incidents` with filters, `/api/incidents/{id}`,
`/api/stats/summary`, CRUD for watchlist/alert-rules/pipeline) + Next.js PWA with
KPI cards, incidents table, incident detail, watchlist page, **pipeline board view**
(kanban: not_contacted → contacted → meeting_booked → po_won). Recharts for charts.
Dark-mode-first, mobile responsive.

**Acceptance criteria (when scheduled):**
- [ ] Dashboard loads real data < 2s; PWA installable on phone
- [ ] Pipeline board updates `follow_up_status` via drag or dropdown
- [ ] Filters and search work end-to-end at 390px width

---

### 🟦 Phase 3 — Alerts: Discord + Email (1–2 days) [MVP]

**Goal:** new incident → Discord message + email within ~1 minute — **using Supabase
Edge Functions, no always-on bot server.**

**Tasks for opencode:**
1. `supabase/functions/alert-dispatcher/index.ts` (Deno Edge Function):
   - Triggered by a Supabase Database Webhook on `incidents` INSERT
   - Evaluate `alert_rules` → dispatch per rule
2. **Discord:** POST to `DISCORD_WEBHOOK_URL` with an embed:
   ```
   🚨 New Ransomware Victim — Thailand
   Victim: {name} ({sector})
   Group: {group_name}
   Discovered: {time, Asia/Bangkok} | Source: {source_url}
   ⚠️ WATCHLIST MATCH: {matched company} — pipeline row created
   ```
   Watchlist hits → red embed + role mention; regular → orange.
3. **Email:** Resend API, HTML template, subject
   `[RansomWatch TH] {victim} hit by {group}`.
4. Write every delivery to `alert_log`; **check the log before sending** — never alert
   twice for the same incident+rule. Retry failures 3× with backoff, then log the error.
5. **Alert-volume guard:** only genuinely new incidents alert. Digest-style volume
   belongs in the weekly summary (Phase 5), not the live channel — a channel that pings
   20×/day becomes wallpaper.

**Acceptance criteria:**
- [ ] Seeding a test incident triggers Discord + email within 1 minute
- [ ] Re-seeding the same incident sends nothing (alert_log dedup works)
- [ ] Watchlist rule and "all Thailand" rule behave differently as configured
- [ ] Edge Function logs show clean error handling on a forced Resend/Discord failure

---

### 🟦 Phase 4 — Discord Chatbot (2–3 days) [MVP]

**Goal:** users *query* the data through Discord. **This is the first phase that needs
the persistent `discord.py` bot process** (host on Railway/Render free/cheap tier).

**Tasks for opencode:**

1. Slash commands (discord.py app_commands):
   - `/latest [n]` — last n Thai incidents (default 5)
   - `/victim <name>` — search incidents by company name
   - `/group <name>` — group profile + its Thai victims
   - `/stats [period]` — summary chart (7d/30d/90d) as an attached image (matplotlib)
   - `/brief <sector|group|period>` — **customer-meeting-ready brief** (v2 addition):
     5 spoken-style bullet points — victim count, top groups, notable incidents WITH
     source URLs, one trend line. This is the artifact to review before walking into a
     customer meeting. Example: `/brief manufacturing 90d`
   - `/watch <company>` / `/unwatch <company>` — watchlist management (admin role only)
   - `/pipeline` — **BD funnel view** (v2 addition): *"3 watchlist companies hit this
     quarter → 1 contacted → 0 meetings → 0 POs"*
   - `/pipeline_update <company> <status>` — advance `follow_up_status` (admin only)
2. Free-text chatbot in a designated `#ask-ransomwatch` channel:
   - NL question → LLM → **tool-calling** into the same query functions as the slash
     commands → answer with citations (source URLs).
   - Use the cheapest capable model; the task is routing questions to query functions.
   - Hard rule: answer ONLY from tool results. System prompt must say: "If the tools
     return no data, say so. Never invent incidents."
3. Permissions: read-only commands for everyone; `/watch`, `/unwatch`,
   `/pipeline_update` restricted to `DISCORD_ADMIN_ROLE_ID`.

**Acceptance criteria:**
- [ ] All 9 commands return correct data from the live DB
- [ ] `/brief` output is speakable as-is (≤ 5 bullets, all claims sourced)
- [ ] "Who got hit in Thailand this month?" free-text returns a sourced answer
- [ ] A company NOT in the DB returns "no records" — never a hallucinated incident
- [ ] Non-admin users are rejected politely on admin commands
- [ ] Bot auto-reconnects and stays up > 24h

---

### 🟩 Phase 5 — Thai-Source Scrapers + Weekly Digest (2–3 days) [BACKLOG]

**Goal:** catch incidents ransomware.live misses; add the weekly rhythm.

**Tasks for opencode:**
1. `collectors/thaicert.py` — scrape ThaiCERT news pages; `source='thaicert'`,
   `status='confirmed'`.
2. `collectors/news_rss.py` — RSS feeds + keyword filter (`ransomware`, `แรนซัมแวร์`,
   `ข้อมูลรั่ว`, watchlist names). Lightweight classifier to confirm "ransomware at a
   Thai org" and extract the victim name.
3. `collectors/ransomwatch.py` — ransomwatch data as a secondary source.
4. **Weekly digest job:** every **Monday 08:00 Asia/Bangkok** → Discord + email:
   last week's incidents, top groups, watchlist/pipeline status.
5. All scrapers: fail LOUDLY on HTML structure changes (alert admin channel), never
   silently return zero results.

**Acceptance criteria (when scheduled):**
- [ ] ThaiCERT items appear with correct source attribution
- [ ] Keyword filter < 30% obvious false positives on a 50-item manual sample
- [ ] Weekly digest fires at 08:00 Bangkok time Monday (test via manual trigger)

---

### 🟩 Phase 6 — Deployment + Hardening (2 days) [BACKLOG]

**Goal:** production-grade, monitorable.

**Tasks for opencode:**
1. Deploy: api + bot → Railway/Render; web (if built) → Vercel; Supabase stays as DB.
2. Auth on web app (Supabase Auth magic link) if Phase 2 was built; admin pages
   require login.
3. Observability: structured logs, daily heartbeat to Discord admin channel
   ("alive, N incidents today"), Supabase backups, weekly CSV export of incidents.
4. Full runbook in README: restart, key rotation, adding a new source.

**Acceptance criteria (when scheduled):**
- [ ] Public HTTPS for api (+ web if built); bot up 24/7 with auto-restart
- [ ] Daily heartbeat arrives; runbook verified by following it cold

---

## 5. Explicitly OUT of scope (v1)

- ❌ **Self-scraping dark-web DLS over Tor** — ransomware.live already aggregates these
  publicly; self-scraping adds Tor infra + constantly-breaking parsers for marginal gain.
  Revisit only if data gaps prove real.
- ❌ Hosting or downloading leaked victim data — metadata only, always (PDPA)
- ❌ Ransom-negotiation or payment tracking
- ❌ Multi-country support (architecture shouldn't *prevent* it; v1 = Thailand only)
- ❌ Native iOS/Android apps (PWA covers it if/when the dashboard is built)
- ❌ Multi-tenancy / user accounts until someone other than Rz needs to log in

## 6. Risks & Notes for opencode

1. **Ransomware.live rate limits** — free tier; cache aggressively, poll ≤ every 15 min,
   real `User-Agent`, 30s timeouts.
2. **Victim-name normalization is the hardest correctness problem** — Thai companies
   appear as "ABC Co., Ltd.", "ABC (Thailand)", Thai script, etc. Follow the §3
   normalization rules; maintain aliases in the watchlist. The Phase 1 backfill exists
   specifically to expose normalization bugs early.
3. **False positives hurt credibility** — this tool feeds BD conversations. Every alert
   must carry `source_url`; the bot must never present unverified claims as confirmed.
4. **Secrets** — `.env` only, never in code or git. Rotate if leaked.
5. **Alert fatigue** — live channel = new incidents only. Volume goes in the weekly digest.
6. **Timezone bugs** — UTC storage, Asia/Bangkok display/schedule. Test the Monday 08:00
   digest explicitly; naive cron will fire at the wrong local time.

## 7. Suggested timeline (MVP fast path)

| Phase | Duration | Cumulative | Track |
|---|---|---|---|
| 0 Scaffold | 0.5 d | 0.5 d | **MVP** |
| 1 Ingestion + backfill | 1–2 d | ~2 d | **MVP** |
| 3 Alerts (Edge Functions) | 1–2 d | ~4 d | **MVP** |
| 4 Chatbot + /brief + /pipeline | 2–3 d | **~1 week** | **MVP** |
| 2 Dashboard (PWA) | 2–3 d | — | backlog |
| 5 Thai sources + digest | 2–3 d | — | backlog |
| 6 Deploy & harden | 2 d | — | backlog |

**MVP = ~1 week of focused build.** Backlog phases add up to ~2 more weeks, scheduled
only when the MVP earns them.

---

## 8. AGENTS.md — paste-ready instructions for opencode

```markdown
# Instructions for the coding agent

You are building RansomWatch TH per PLAN.md in this repo. Rules:

1. MVP build order is Phase 0 → 1 → 3 → 4 (see PLAN.md §0). Phases 2, 5, 6 are
   backlog — do NOT build them unless explicitly asked.
2. Do not start a phase until the previous phase's acceptance criteria pass.
3. Do not change the tech stack decisions in PLAN.md §2 without asking.
4. Never commit secrets. All config comes from .env; update .env.example when
   you add a variable.
5. Every collector must: dedup against (normalized_name, group_name), store the
   raw payload, and never crash the scheduler loop on error.
6. All timestamps: store UTC, display/schedule Asia/Bangkok.
7. Alerts (Phase 3) run via Supabase Edge Function + Discord webhook + Resend.
   Do NOT build a persistent bot server until Phase 4.
8. The Discord bot and any LLM feature must NEVER invent incidents. Answers
   come from the database only, always with source_url.
9. Never copy leaked personal data into any field (Thailand PDPA). Descriptions
   stay factual.
10. After each phase, print the acceptance checklist with pass/fail evidence
    (commands run + outputs) before moving on.
11. Prefer small, tested commits: one commit per task, clear message.
12. Python: 3.12, uv. Node: pnpm. Format: ruff + prettier.
13. GitHub remote: https://github.com/Ratanapol-Pon/RansomWatch.git
    - Work on `main`; `.gitignore` must exclude `.env`, `__pycache__`,
      `node_modules`, `.venv`, `dist`, `build`, `*.log`.
    - Run a secret scan before every commit/push; `.env` must never be tracked.
    - NEVER push without explicit owner approval. After each confirmed phase:
      tag it (`phase-0` … `phase-4`, `mvp`) and push branch + tags on approval.
    - On auth failure, stop and ask the owner for credential setup — never embed
      tokens in the remote URL.
```

---

## 9. References

- Ransomware.live (data source + API): https://www.ransomware.live/about · API v2 docs: https://github.com/JMousqueton/ransomware.live
- Ransomware.live MCP server (chatbot reference): https://github.com/Cyreslab-AI/ransomware-live-mcp-server
- Ransomwatch (secondary scraped-DLS dataset): https://github.com/captainGeech42/ransomwatch
- ThaiCERT / NCSA: https://www.thaicert.or.th/en/homepage/
- Thailand top-10 ransomware target (Q1 2026, Check Point via SecurityBrief Asia): https://securitybrief.asia/story/ransomware-shifts-to-fewer-groups-as-thailand-targeted
- 2026 Ransomware Report (Black Kite, 7,551 victims Apr 2025–Mar 2026): https://blackkite.com/reports/2026-ransomware-report
- discord.py slash commands: https://discordpy.readthedocs.io/en/stable/interactions/api.html
- Supabase Database Webhooks + Edge Functions: https://supabase.com/docs/guides/database/webhooks
- Resend (email API): https://resend.com/docs
