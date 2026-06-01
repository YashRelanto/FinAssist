-- Private bucket for per-user Prophet model artifacts (joblib + manifest).
-- Service role (backend) reads/writes; not public.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'forecast-models',
  'forecast-models',
  false,
  524288000, -- 500 MB
  array['application/octet-stream', 'application/json']::text[]
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- Service role bypasses RLS; policies for service_role access.
drop policy if exists "forecast_models_service_read" on storage.objects;
drop policy if exists "forecast_models_service_write" on storage.objects;
drop policy if exists "forecast_models_service_update" on storage.objects;
drop policy if exists "forecast_models_service_delete" on storage.objects;

create policy "forecast_models_service_read"
on storage.objects for select
to service_role
using (bucket_id = 'forecast-models');

create policy "forecast_models_service_write"
on storage.objects for insert
to service_role
with check (bucket_id = 'forecast-models');

create policy "forecast_models_service_update"
on storage.objects for update
to service_role
using (bucket_id = 'forecast-models');

create policy "forecast_models_service_delete"
on storage.objects for delete
to service_role
using (bucket_id = 'forecast-models');

-- Optional: track training runs (metadata only; binaries live in Storage)
create table if not exists public.forecast_model_runs (
  id uuid primary key default gen_random_uuid(),
  trained_at timestamptz not null default now(),
  trained_users integer not null default 0,
  test_mape double precision,
  storage_bucket text not null default 'forecast-models',
  storage_bundle_key text not null default 'production/expense_forecast_prophet.joblib',
  status text not null default 'completed',
  error_message text,
  created_at timestamptz not null default now()
);

alter table public.forecast_model_runs enable row level security;

drop policy if exists "forecast_model_runs_service_all" on public.forecast_model_runs;

create policy "forecast_model_runs_service_all"
on public.forecast_model_runs
for all
to service_role
using (true)
with check (true);
