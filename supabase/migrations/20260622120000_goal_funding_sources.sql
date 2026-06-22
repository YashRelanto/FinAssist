-- Link savings goals to live money sources (mutual funds, FDs, bank accounts).
-- Each entry: {"type": "mutual_fund" | "fixed_deposit" | "account", "id": "<source id>", "name": "<label>"}
-- For mutual_fund, id = scheme_code; for fixed_deposit, id = fd_id; for account, id = account_id.
ALTER TABLE public.goals
  ADD COLUMN IF NOT EXISTS funding_sources jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.goals.funding_sources IS
  'Linked money sources whose live value auto-updates goal progress: [{type, id, name}]';
