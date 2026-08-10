# Kickoff prompt for opencode — paste this as your first message

> Assumes `RANSOMWATCH_TH_PLAN.md` is in the repo root. If you keep it elsewhere,
> update the path in the prompt before pasting.

````
You are the coding agent building **RansomWatch TH**. Before writing any code, read
`RANSOMWATCH_TH_PLAN.md` in this repo root IN FULL — it is the single source of truth
for stack, schema, phases, and acceptance criteria. Also follow these standing rules:

1. **Build order is strictly MVP fast path: Phase 0 → 1 → 3 → 4.** Phases 2, 5, 6 are
   backlog — do not build them unless I explicitly ask.
2. Do not change stack decisions in PLAN §2 without asking me first.
3. Never commit secrets. All config from `.env`; update `.env.example` when you add
   a variable. If you need a credential that only I can create (Discord bot token,
   Resend API key, Supabase keys), STOP and give me exact click-by-click setup
   instructions instead of guessing or stubbing silently.
4. All timestamps: store UTC, display/schedule Asia/Bangkok.
5. Every collector must dedup on (normalized_name, group_name), store the raw payload,
   and never crash the scheduler loop on error.
6. Alerts (Phase 3) use Supabase Edge Function → Discord webhook + Resend. Do NOT build
   a persistent bot process until Phase 4.
7. Small, tested commits — one per task, clear messages. Python 3.12 + uv + ruff;
   Node + pnpm + prettier.
8. At the end of each phase, print the phase's acceptance checklist with pass/fail
   evidence (commands run + outputs). Do not proceed until I confirm.
9. **Git/GitHub:** the remote for this project is
   https://github.com/Ratanapol-Pon/RansomWatch.git
   - During Phase 0: `git init`, create a `.gitignore` that excludes `.env`,
     `__pycache__`, `node_modules`, `.venv`, `dist`, `build`, `*.log`; then set the
     remote: `git remote add origin https://github.com/Ratanapol-Pon/RansomWatch.git`
     and work on the `main` branch.
   - Before the FIRST commit and before EVERY push: run a secret scan
     (`git grep -nE "(api[_-]?key|token|secret|password|webhook)" -- . ':!.env.example' ':!PLAN.md'`
     or equivalent) and verify `.env` is NOT tracked (`git status --ignored`).
   - NEVER push on your own. When a phase passes its checklist, ASK ME for permission
     to push. On my approval, push with: `git push -u origin main`.
   - If push fails due to auth, STOP and give me setup steps (Git credential manager,
     PAT, or SSH) — never hardcode or embed credentials in the remote URL.
   - One commit per task, then tag each completed phase: `git tag phase-0`, etc.,
     and push tags with the branch.

**Your task now: execute Phase 0 (Project Scaffold) exactly as specified in PLAN.md §4
Phase 0, including the repo layout from PLAN.md §2, the migration SQL for all 5 tables
in PLAN.md §3 (incidents, watchlist, pipeline, alert_rules, alert_log), and the git
setup from rule 9.**

When Phase 0's acceptance checklist passes, stop and report. I will review before
authorizing the push and Phase 1.
````

---

# Phase-handoff prompts (use after each phase is confirmed)

## After Phase 0 passes → approve push + start Phase 1

````
Phase 0 confirmed. Approved to push: commit any remaining work, tag `phase-0`, and run
`git push -u origin main --tags` to https://github.com/Ratanapol-Pon/RansomWatch.git
(after the secret scan from rule 9 passes — show me its output first).

Then execute **Phase 1 (Data Ingestion MVP)** from PLAN.md §4: ransomware.live
collector (15-min APScheduler polling, polite User-Agent, 30s timeout), the 12-month
historical backfill job, the normalization + dedup pipeline, watchlist matching, and
auto-creation of `pipeline` rows on watchlist hits. Include the `--once` and
`--backfill 12m` CLI commands. Print the acceptance checklist with evidence when done
and stop.
````

## After Phase 1 passes → approve push + start Phase 3

````
Phase 1 confirmed. Approved to push: tag `phase-1` and push main + tags to origin
(after the secret scan — show me the output first).

Then execute **Phase 3 (Alerts)** from PLAN.md §4 (skipping Phase 2 — it is backlog):
Supabase Edge Function `alert-dispatcher` triggered by a Database Webhook on incidents
INSERT, Discord webhook embeds (red + role mention for watchlist hits, orange
otherwise), Resend email alerts, alert_log dedup, 3x retry with backoff, and the
alert-volume guard. If you need me to create the Discord webhook URL or Resend API
key, stop and give me click-by-click setup steps. Print the acceptance checklist with
evidence when done and stop.
````

## After Phase 3 passes → approve push + start Phase 4

````
Phase 3 confirmed. Approved to push: tag `phase-3` and push main + tags to origin
(after the secret scan — show me the output first).

Then execute **Phase 4 (Discord Chatbot)** from PLAN.md §4: discord.py bot with all 9
slash commands (/latest, /victim, /group, /stats, /brief, /watch, /unwatch, /pipeline,
/pipeline_update), the free-text chatbot channel with LLM tool-calling that may ONLY
answer from tool results with source citations, and the admin-role permission model.
If you need the Discord bot token or LLM API key, stop and give me setup steps. Print
the acceptance checklist with evidence when done and stop.
````

## After Phase 4 passes → final push (MVP complete)

````
Phase 4 confirmed — MVP complete. Final push: tag `mvp` and `phase-4`, push main +
tags to https://github.com/Ratanapol-Pon/RansomWatch.git (after the secret scan —
show me the output first). Then update the README with: current feature list, setup
instructions, env var table, and a "backlog" section listing deferred Phases 2, 5, 6.
Commit the README update and push once more.
````
