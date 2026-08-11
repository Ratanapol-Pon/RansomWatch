create extension if not exists pg_net with schema extensions;

create or replace function public.notify_incident_insert() returns trigger
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  fn_url text;
  secret text;
begin
  select decrypted_secret into fn_url
  from vault.decrypted_secrets
  where name = 'alert_dispatcher_url';
  select decrypted_secret into secret
  from vault.decrypted_secrets
  where name = 'alert_dispatcher_secret';

  if fn_url is null or secret is null then
    raise warning 'alert dispatcher not configured: missing vault secrets';
    return new;
  end if;

  perform net.http_post(
    url := fn_url,
    body := jsonb_build_object(
      'type', TG_OP,
      'table', TG_TABLE_NAME,
      'schema', TG_TABLE_SCHEMA,
      'record', to_jsonb(new),
      'old_record', null
    ),
    headers := jsonb_build_object(
      'content-type', 'application/json',
      'x-webhook-secret', secret
    ),
    timeout_milliseconds := 5000
  );
  return new;
end;
$$;

drop trigger if exists incidents_alert_webhook on public.incidents;
create trigger incidents_alert_webhook
after insert on public.incidents
for each row execute function public.notify_incident_insert();
