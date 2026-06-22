import type { BudgetUtilizationItem } from '../types';
import type { Goal, FundingSource, FundedBreakdownItem } from '../types';

export interface SavingsTrajectory {
  has_data: boolean;
  monthly_income: number;
  monthly_expenses: number;
  monthly_net_savings: number;
  previous_month_net: number;
  savings_growth_pct: number;
  title: string;
  description: string;
  stroke_pct: number;
}

export interface GoalWithProgress extends Goal {
  progress_pct: number;
  funding_sources?: FundingSource[];
  funded_breakdown?: FundedBreakdownItem[];
}

/** Build live funded amount + breakdown from cached money-source data (optimistic UI). */
export function buildFundedSnapshot(
  fundingSources: FundingSource[],
  accounts: any[],
  investmentsData: any | null,
  fixedDepositsData: any | null,
): { current: number; breakdown: FundedBreakdownItem[] } {
  let current = 0;
  const breakdown: FundedBreakdownItem[] = [];
  for (const src of fundingSources) {
    let value = 0;
    let name = src.name || '';
    if (src.type === 'account') {
      const acc = accounts.find((a) => String(a.account_id) === src.id);
      value = Number(acc?.current_balance) || 0;
      name = name || acc?.account_name || 'Account';
    } else if (src.type === 'mutual_fund') {
      const h = (investmentsData?.holdings || []).find(
        (x: any) => String(x.ticker) === src.id,
      );
      value = Number(h?.current_value) || 0;
      name = name || h?.name || src.id;
    } else if (src.type === 'fixed_deposit') {
      const f = (fixedDepositsData?.fixed_deposits || []).find(
        (x: any) => String(x.fd_id) === src.id,
      );
      value = Number(f?.current_value) || 0;
      name = name || f?.label || f?.bank_name || 'Fixed Deposit';
    }
    current += value;
    breakdown.push({
      type: src.type,
      id: src.id,
      name,
      current_value: value,
      available: true,
    });
  }
  return { current: Math.round(current * 100) / 100, breakdown };
}

export function toGoalWithProgress(
  goal: Omit<Goal, 'id'> & { id: string },
  funded: { current: number; breakdown: FundedBreakdownItem[] },
  fundingSources: FundingSource[],
): GoalWithProgress {
  const target = goal.target || 0;
  const current =
    fundingSources.length > 0 ? funded.current : goal.current || 0;
  const progress_pct =
    target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
  return {
    ...goal,
    current,
    progress_pct,
    fundingSources,
    funding_sources: fundingSources,
    funded_breakdown: fundingSources.length ? funded.breakdown : [],
  };
}

