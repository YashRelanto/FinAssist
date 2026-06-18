import type { BudgetUtilizationItem } from '../types';
import type { Goal } from '../types';

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
}

