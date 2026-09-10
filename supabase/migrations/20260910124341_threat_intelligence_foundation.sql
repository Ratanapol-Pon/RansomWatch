-- Upgrade 1: additive fields and evidence identity. Pause old workers before rollout.
-- Existing incident IDs and every FK remain intact. No incident INSERTs/backfill alerts.
begin;

alter table public.incidents
  add column published_at timestamptz,
  add column dark_web_url text,
  add column attack_types text[] not null default array['ransomware']::text[],
  add column affected_products text[] not null default '{}'::text[],
  add column cve_ids text[] not null default '{}'::text[],
  add column confidence text not null default 'claimed',
  add column alert_eligible boolean not null default true;

alter table public.incidents
  drop constraint if exists incidents_normalized_name_group_name_source_key,
  drop constraint if exists uq_incidents_dedup,
  add constraint incidents_confidence_check
    check (confidence in ('claimed', 'reported', 'confirmed', 'disputed')),
  add constraint incidents_attack_types_check check (attack_types <@ array[
    'ransomware', 'extortion', 'data_breach', 'phishing', 'bec', 'malware',
    'ddos', 'defacement', 'exploitation', 'other']::text[]);

update public.incidents set confidence = 'confirmed' where status = 'confirmed';
update public.incidents set attack_types = array['other']::text[],
  confidence = case when status = 'confirmed' then 'confirmed' else 'reported' end
  where source is null or source not in ('ransomware_live', 'ransomwatch');
update public.incidents set group_name = null where lower(group_name) = 'unknown';

create table public.incident_sources (
  id uuid primary key default gen_random_uuid(),
  incident_id uuid not null references public.incidents(id),
  source text not null,
  source_record_key text not null,
  source_url text,
  dark_web_url text,
  published_at timestamptz,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  raw jsonb not null,
  constraint uq_incident_source unique (source, source_record_key)
);
create index incident_sources_incident_idx on public.incident_sources(incident_id);
create index incidents_entity_idx on public.incidents(normalized_name, group_name);
create index incidents_country_discovered_idx
  on public.incidents(country, discovered_at desc);
create index incidents_attack_types_idx on public.incidents using gin(attack_types);

-- Campaign/advisory records cannot accidentally enter existing victim-count queries.
create table public.threat_reports (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('campaign', 'advisory')),
  title text not null,
  source text not null,
  source_record_key text not null,
  source_url text not null,
  dark_web_url text,
  country text,
  attack_types text[] not null default '{}'::text[],
  affected_products text[] not null default '{}'::text[],
  cve_ids text[] not null default '{}'::text[],
  confidence text not null default 'reported'
    check (confidence in ('claimed', 'reported', 'confirmed', 'disputed')),
  published_at timestamptz,
  discovered_at timestamptz not null default now(),
  description text,
  raw jsonb,
  constraint uq_threat_report unique(source, source_record_key),
  constraint threat_reports_attack_types_check check (attack_types <@ array[
    'ransomware', 'extortion', 'data_breach', 'phishing', 'bec', 'malware',
    'ddos', 'defacement', 'exploitation', 'other']::text[])
);
create index threat_reports_kind_published_idx
  on public.threat_reports(kind, published_at desc);
alter table public.incident_sources enable row level security;
alter table public.threat_reports enable row level security;
-- Backend-only until the dashboard phase defines explicit user policies.
revoke all on public.incident_sources, public.threat_reports from anon, authenticated;
grant select, insert, update, delete on public.incident_sources, public.threat_reports
  to service_role;

-- The trigger and dispatcher both honor suppression, including external DB webhooks.
drop trigger if exists incidents_alert_webhook on public.incidents;
create trigger incidents_alert_webhook after insert on public.incidents
for each row when (new.alert_eligible)
execute function public.notify_incident_insert();

commit;
