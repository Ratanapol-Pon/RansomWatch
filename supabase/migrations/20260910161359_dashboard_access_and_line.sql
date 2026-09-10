begin;
alter table public.threat_reports add column promoted_incident_id uuid references public.incidents(id);
create table public.dashboard_members (
  user_id uuid primary key,
  role text not null check (role in ('viewer','analyst','admin')),
  enabled boolean not null default true
);
create table public.line_groups (
  group_id text primary key, name text not null, joined boolean not null default true,
  active boolean not null default false,
  language text not null default 'en' check (language in ('en','th')),
  delivery_mode text not null default 'monthly' check (delivery_mode in ('monthly','digest','immediate')),
  countries text[] not null default array['TH']::text[], attack_types text[] not null default '{}',
  include_global_reports boolean not null default true,
  digest_hour int not null default 8 check (digest_hour between 0 and 23),
  quiet_start int not null default 22 check (quiet_start between 0 and 23),
  quiet_end int not null default 8 check (quiet_end between 0 and 23),
  activated_at timestamptz, last_membership_at timestamptz not null default now(),
  last_command_at timestamptz
);
create table public.line_events (
  event_id text primary key, payload jsonb not null,
  received_at timestamptz not null default now(), processed boolean not null default false, error text
);
create index line_events_pending_idx on public.line_events(received_at) where not processed;
create table public.line_deliveries (
  id uuid primary key default gen_random_uuid(), group_id text not null references public.line_groups(group_id),
  delivery_key text not null, message text not null,
  created_at timestamptz not null default now(), first_attempt_at timestamptz, sent_at timestamptz,
  attempts int not null default 0, next_attempt_at timestamptz, error text,
  constraint uq_line_delivery unique(group_id, delivery_key)
);
create index line_deliveries_pending_idx on public.line_deliveries(next_attempt_at) where sent_at is null;
alter table public.dashboard_members enable row level security;
alter table public.line_groups enable row level security;
alter table public.line_events enable row level security;
alter table public.line_deliveries enable row level security;
-- All data goes through the authenticated FastAPI boundary. No direct browser table access.
revoke all on public.dashboard_members, public.line_groups, public.line_events, public.line_deliveries
  from anon, authenticated;
grant select,insert,update,delete on public.dashboard_members, public.line_groups,
  public.line_events, public.line_deliveries to service_role;
commit;
