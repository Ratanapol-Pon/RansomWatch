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
