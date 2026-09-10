begin;
alter table public.threat_reports
  drop constraint threat_reports_kind_check,
  add constraint threat_reports_kind_check check (kind in ('campaign', 'advisory', 'news')),
  add column needs_review boolean not null default true,
  add column updated_at timestamptz not null default now();

create table public.source_health (
  source text primary key,
  status text not null check (status in ('ok', 'degraded', 'error')),
  last_attempt_at timestamptz not null,
  last_success_at timestamptz,
  next_retry_at timestamptz,
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  fetched integer not null default 0,
  inserted integer not null default 0,
  updated integer not null default 0,
  rejected integer not null default 0,
  filtered integer not null default 0,
  last_error text
);
alter table public.source_health enable row level security;
revoke all on public.source_health from anon, authenticated;
grant select, insert, update, delete on public.source_health to service_role;
create index threat_reports_review_idx on public.threat_reports(needs_review, discovered_at desc);
create index threat_reports_cve_idx on public.threat_reports using gin(cve_ids);
create index threat_reports_attack_types_idx on public.threat_reports using gin(attack_types);
commit;
