-- Support multi-asset portfolio analysis (stocks, ETFs, bonds, gold)
ALTER TABLE public.investments
  ADD COLUMN IF NOT EXISTS asset_type text NOT NULL DEFAULT 'mutual_fund';

ALTER TABLE public.investments
  ADD COLUMN IF NOT EXISTS symbol text;

COMMENT ON COLUMN public.investments.asset_type IS
  'mutual_fund | stock | etf | bond | gold | sip';
