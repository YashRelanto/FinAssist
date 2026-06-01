-- Nightly cron: invoke train-forecast Edge Function (JWT disabled on function).
create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

do $$
begin
  if exists (select 1 from cron.job where jobname = 'train-forecast-nightly') then
    perform cron.unschedule('train-forecast-nightly');
  end if;
end $$;

select cron.schedule(
  'train-forecast-nightly',
  '0 2 * * *',
  $$
  select net.http_post(
    url := 'https://wequiafwuvugkzgqzety.supabase.co/functions/v1/train-forecast',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body := '{}'::jsonb
  ) as request_id;
  $$
);
