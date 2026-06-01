import type { BudgetUtilizationItem } from '../components/Dashboard/BudgetUtilization';
import type { Goal } from '../types';

import { apiFetch } from './api';

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

export interface BudgetGoalsSummary {
  success: boolean;
  budget_utilization: BudgetUtilizationItem[];
  goals: GoalWithProgress[];
  trajectory: SavingsTrajectory;
}

export async function fetchBudgetGoalsSummary(
  userId: string
): Promise<BudgetGoalsSummary> {
  const response = await apiFetch(
    `/api/budget-goals-summary?user_id=${encodeURIComponent(userId)}`
  );
  const data = await response.json();
  if (!response.ok || !data.success) {
    throw new Error(data.detail || 'Failed to load budget and goals summary');
  }
  return data as BudgetGoalsSummary;
}
