-- Optional credit limit for credit_card accounts (utilization analysis).
alter table public.accounts
  add column if not exists credit_limit numeric(14, 2);
