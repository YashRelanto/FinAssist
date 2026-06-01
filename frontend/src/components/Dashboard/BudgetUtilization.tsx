import React from 'react';
import { AlertTriangle, Target } from 'lucide-react';
import { cn, formatCurrency } from '../../lib/utils';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export interface BudgetUtilizationItem {
  id: string;
  budget_name: string;
  category: string;
  limit: number;
  spent: number;
  utilization_pct: number;
  alert_threshold: number;
  over_budget: boolean;
  alert: boolean;
}

interface BudgetUtilizationProps {
  items?: BudgetUtilizationItem[];
}

export const BudgetUtilization: React.FC<BudgetUtilizationProps> = ({ items = [] }) => {
  const active = items.filter((b) => b.limit > 0);

  return (
    <div className="lg:col-span-4 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 space-y-6 flex flex-col min-h-[300px]">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center text-primary">
          <Target className="w-5 h-5" />
        </div>
        <div>
          <h4 className="text-lg font-bold">Budget Utilization</h4>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest">
            Active budgets · calendar period
          </p>
        </div>
      </div>

      {active.length === 0 ? (
        <ComingSoonPlaceholder />
      ) : (
        <div className="space-y-4 flex-1">
          {active.map((budget) => (
            <div key={budget.id} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-black text-on-surface truncate">
                    {budget.budget_name}
                  </p>
                  <p className="text-[10px] font-bold text-outline uppercase tracking-wider">
                    {budget.category}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p
                    className={cn(
                      'text-sm font-black',
                      budget.over_budget ? 'text-error' : 'text-on-surface',
                    )}
                  >
                    {budget.utilization_pct}%
                  </p>
                  <p className="text-[9px] font-bold text-outline">
                    {formatCurrency(budget.spent)} / {formatCurrency(budget.limit)}
                  </p>
                </div>
              </div>
              <div className="w-full bg-surface-container h-2 rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full transition-all duration-700',
                    budget.over_budget
                      ? 'bg-error'
                      : budget.alert
                        ? 'bg-amber-500'
                        : 'bg-primary',
                  )}
                  style={{ width: `${Math.min(budget.utilization_pct, 100)}%` }}
                />
              </div>
              {budget.alert && (
                <p
                  className={cn(
                    'text-[10px] font-bold flex items-center gap-1',
                    budget.over_budget ? 'text-error' : 'text-amber-600',
                  )}
                >
                  <AlertTriangle className="w-3 h-3" />
                  {budget.over_budget
                    ? 'Over budget'
                    : `Above ${budget.alert_threshold}% threshold`}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
