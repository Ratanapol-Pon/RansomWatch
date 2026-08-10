create table if not exists incidents (
  id              uuid primary key default gen_random_uuid(),
  victim_name     text not null,
  normalized_name text,
  domain          text,
  country         text default 'TH',
  sector          text,
  group_name      text,
  discovered_at   timestamptz,
  attack_date     date,
  source          text,
  source_url      text,
  description     text,
  status          text default 'unverified',
  watchlist_hit   boolean default false,
  raw             jsonb,
  unique (normalized_name, group_name, source)
);

create table if not exists watchlist (
  id       uuid primary key default gen_random_uuid(),
  name     text not null,
  aliases  text[],
  domains  text[],
  priority int default 1,
  notes    text
);

create table if not exists pipeline (
  id               uuid primary key default gen_random_uuid(),
  incident_id      uuid references incidents(id) not null,
  watchlist_id     uuid references watchlist(id) not null,
  follow_up_status text default 'not_contacted',
  owner_note       text,
  updated_at       timestamptz default now(),
  unique (incident_id, watchlist_id)
);

create table if not exists alert_rules (
  id                 uuid primary key default gen_random_uuid(),
  name               text,
  match_mode         text,
  match_value        text,
  channel            text,
  discord_channel_id text,
  email_recipients   text[],
  enabled            boolean default true
);

create table if not exists alert_log (
  id          uuid primary key default gen_random_uuid(),
  incident_id uuid references incidents(id) not null,
  rule_id     uuid references alert_rules(id) not null,
  channel     text,
  sent_at     timestamptz,
  success     boolean,
  error       text
);
