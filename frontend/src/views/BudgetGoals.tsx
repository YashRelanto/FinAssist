import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Home,
  Utensils,
  Car,
  ShoppingBag,
  Landmark,
  MoreHorizontal,
  Laptop,
  CreditCard,
  ShieldCheck,
  Plus,
  AlertCircle,
  Target,
  Edit2,
  Trash2,
  PiggyBank,
  Sparkles,
} from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';
import { defaultBudgetPeriodDates } from '../lib/budgetPeriod';
import { useAppContext } from '../context/AppContext';
import { GoalModal } from '../components/GoalModal';
import { BudgetModal } from '../components/BudgetModal';
import { Budget } from '../types';
import { GoalWithProgress, SavingsTrajectory } from '../lib/budgetGoalsApi';
import type { BudgetUtilizationItem } from '../types';
import { PageHeader, PageLoading, PageShell, lumio } from '../components/PageShell';

const getCategoryIcon = (category: string) => {
  switch (category) {
    case 'Food & Drinks':
      return Utensils;
    case 'Shopping':
      return ShoppingBag;
    case 'Housing':
      return Home;
    case 'Transportation':
      return Car;
    case 'Vehicle':
      return Car;
    case 'Life & Entertainment':
      return Target;
    case 'Communication/PC':
      return Laptop;
    case 'Financial Expense':
      return CreditCard;
    case 'Investments':
      return Landmark;
    case 'Income':
      return PiggyBank;
    default:
      return MoreHorizontal;
  }
};

const defaultTrajectory: SavingsTrajectory = {
  has_data: false,
  monthly_income: 0,
  monthly_expenses: 0,
  monthly_net_savings: 0,
  previous_month_net: 0,
  savings_growth_pct: 0,
  title: 'No Trajectory Data Yet',
  description:
    'Once you log income and expenses, we will project your savings trajectory from your real transaction history.',
  stroke_pct: 0,
};

export const BudgetGoals: React.FC = () => {
  const {
    deleteGoal,
    user,
    budgets,
    addBudget,
    deleteBudget,
    budgetGoalsSummary,
    loadBudgetGoalsSummary,
    authReady,
  } = useAppContext();

  const [goalModalOpen, setGoalModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<GoalWithProgress | undefined>(
    undefined
  );

  const [budgetModalOpen, setBudgetModalOpen] = useState(false);
  const [editingBudget, setEditingBudget] = useState<Budget | undefined>(
    undefined
  );

  const [loading, setLoading] = useState(false);
  const refreshSummary = useCallback(
    async (options?: { force?: boolean }) => {
      if (!options?.force && budgetGoalsSummary) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        await loadBudgetGoalsSummary({ force: options?.force });
      } finally {
        setLoading(false);
      }
    },
    [loadBudgetGoalsSummary, budgetGoalsSummary],
  );

  useEffect(() => {
    if (!authReady || !user?.isAuthenticated) return;
    refreshSummary();
  }, [authReady, user?.isAuthenticated, refreshSummary]);

  useEffect(() => {
    if (!user?.isAuthenticated) return;
    const onFocus = () => refreshSummary({ force: true });
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [user?.isAuthenticated, refreshSummary]);

  const closeGoalModal = () => {
    setGoalModalOpen(false);
    refreshSummary({ force: true });
  };

  const closeBudgetModal = () => {
    setBudgetModalOpen(false);
    refreshSummary({ force: true });
  };

  const budgetUtilization = useMemo(
    () =>
      (budgetGoalsSummary?.budget_utilization ?? []) as BudgetUtilizationItem[],
    [budgetGoalsSummary],
  );
  const goalItems = useMemo(
    () => (budgetGoalsSummary?.goals ?? []) as GoalWithProgress[],
    [budgetGoalsSummary],
  );
  const trajectory = (budgetGoalsSummary?.trajectory ??
    defaultTrajectory) as SavingsTrajectory;

  const budgetItems = budgetUtilization.map((item) => ({
    id: item.id,
    raw: budgets.find((b) => b.id === item.id),
    icon: getCategoryIcon(item.category),
    label: item.budget_name,
    sub: `${item.category} · active period`,
    spent: item.spent,
    total: item.limit,
    percent: Math.min(100, item.utilization_pct),
    color: item.over_budget
      ? 'bg-error'
      : item.alert
        ? 'bg-tertiary'
        : 'bg-primary',
    alert: item.alert,
    status: `${Math.round(item.utilization_pct)}% Utilized`,
    overBudget: item.over_budget,
  }));

  const totalSpent = budgetItems.reduce((acc, item) => acc + item.spent, 0);
  const totalBudget = budgetItems.reduce((acc, item) => acc + item.total, 0);

  const handleEditGoal = (g: GoalWithProgress) => {
    setEditingGoal(g);
    setGoalModalOpen(true);
  };

  const handleAddGoal = () => {
    setEditingGoal(undefined);
    setGoalModalOpen(true);
  };

  const handleEditBudget = (b: Budget) => {
    setEditingBudget(b);
    setBudgetModalOpen(true);
  };

  const handleAddBudget = () => {
    setEditingBudget(undefined);
    setBudgetModalOpen(true);
  };

  const handleAutoGenerateBudgets = () => {
    const monthDates = defaultBudgetPeriodDates('monthly');
    const defaultBudgets = [
      {
        categoryName: 'Housing',
        budgetName: 'Housing & Utilities',
        amount: user.fixedRent || 2000,
        period: 'monthly',
        startDate: monthDates.startDate,
        endDate: monthDates.endDate,
        alertThreshold: 90,
      },
      {
        categoryName: 'Food & Drinks',
        budgetName: 'Dining & Food Outing',
        amount: 800,
        period: 'monthly',
        startDate: monthDates.startDate,
        endDate: monthDates.endDate,
        alertThreshold: 85,
      },
      {
        categoryName: 'Transportation',
        budgetName: 'Transportation Commute',
        amount: 450,
        period: 'monthly',
        startDate: monthDates.startDate,
        endDate: monthDates.endDate,
        alertThreshold: 80,
      },
      {
        categoryName: 'Shopping',
        budgetName: 'Groceries Shopping',
        amount: 600,
        period: 'monthly',
        startDate: monthDates.startDate,
        endDate: monthDates.endDate,
        alertThreshold: 80,
      },
    ];

    defaultBudgets.forEach((b) => addBudget(b));
  };

  if (!authReady || (loading && !budgetGoalsSummary)) {
    return <PageLoading />;
  }

  return (
    <PageShell>
      <PageHeader
        title="Budget & Goals"
        description="Strategic oversight of your financial commitments. Budget utilization is computed from live expenses within each budget's date range."
        actions={
          <button type="button" onClick={handleAddGoal} className={lumio.btnPrimary}>
            <Plus className="w-4 h-4" /> Create Goal
          </button>
        }
      />

      <section className="space-y-6">
        <div className="flex justify-between items-center">
          <h3 className="text-xl font-bold">Strategic Savings Goals</h3>
          <div className="bg-primary/10 text-primary px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest">
            {goalItems.length} Active Goals
          </div>
        </div>

        {goalItems.length === 0 ? (
          <div className="py-10 px-6 border-2 border-dashed border-outline-variant/40 rounded-2xl text-center">
            <Target className="w-10 h-10 text-primary mx-auto mb-3" />
            <p className="text-sm text-outline font-medium">
              No savings goals yet. Create one to track progress toward your
              target amount.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {goalItems.map((goal) => {
              const progress = goal.progress_pct;
              return (
                <div
                  key={goal.id}
                  className="bg-surface-container-lowest rounded-2xl border border-outline-variant/30 soft-shadow p-6 flex flex-col hover-lift h-full group relative"
                >
                  <div className="flex justify-between items-start mb-6">
                    <div className="p-2.5 rounded-xl bg-primary/10 text-primary">
                      <Target className="w-5 h-5 shadow-sm" />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleEditGoal(goal)}
                        className="p-1.5 text-outline hover:text-primary hover:bg-primary-container/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm('Delete this goal?')) {
                            deleteGoal(goal.id);
                          refreshSummary({ force: true });
                          }
                        }}
                        className="p-1.5 text-outline hover:text-error hover:bg-error-container/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                      <span
                        className={cn(
                          'px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider',
                          goal.color.replace('bg-', 'bg-') + '/10',
                          goal.color.replace('bg-', 'text-')
                        )}
                      >
                        {progress}% Complete
                      </span>
                    </div>
                  </div>
                  <h4 className="text-lg font-bold mb-2">{goal.label}</h4>
                  <p className="text-xs text-outline font-medium mb-4 leading-relaxed line-clamp-2">
                    {goal.sub}
                  </p>
                  {trajectory.has_data && (
                    <p className="text-[10px] font-bold text-secondary uppercase tracking-widest mb-4">
                      Net savings this month:{' '}
                      {formatCurrency(trajectory.monthly_net_savings)}
                    </p>
                  )}

                  <div className="mt-auto space-y-4">
                    <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest">
                      <span className="text-outline">Saved toward goal</span>
                      <span className="text-on-surface">
                        {formatCurrency(goal.current)} /{' '}
                        {formatCurrency(goal.target)}
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-surface-container-high rounded-full overflow-hidden">
                      <div
                        className={cn(
                          goal.color,
                          'h-full transition-all duration-1000'
                        )}
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <div className="flex justify-between items-center pt-2">
                      <div className="flex items-center gap-1.5 text-outline">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span className="text-[10px] font-bold uppercase tracking-widest">
                          Target: {goal.date}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="bg-surface-container-lowest rounded-2xl soft-shadow p-6 lg:p-8 border border-outline-variant/30">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 border-b border-outline-variant/30 pb-4 gap-4">
          <div>
            <h3 className="text-xl font-bold">Monthly Budget Allocations</h3>
            <p className="text-xs text-outline font-medium mt-1">
              Utilization = expenses in the budget period for that category ÷
              budget limit.
            </p>
          </div>
          <div className="flex gap-3 w-full sm:w-auto">
            {budgetItems.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-1 bg-surface-container-high rounded-lg">
                <span className="text-xs font-bold text-outline uppercase tracking-widest">
                  Spent:
                </span>
                <span className="text-sm font-bold text-on-surface">
                  {formatCurrency(totalSpent)} / {formatCurrency(totalBudget)}
                </span>
              </div>
            )}
            <button
              onClick={handleAddBudget}
              className="px-4 py-2 bg-primary text-white font-bold rounded-lg text-xs hover:brightness-110 transition-all flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" /> Create Budget
            </button>
          </div>
        </div>

        {budgets.length === 0 ? (
          <div className="py-12 px-6 border-2 border-dashed border-outline-variant/40 rounded-2xl flex flex-col items-center justify-center text-center">
            <Sparkles className="w-12 h-12 text-primary mb-4 animate-bounce" />
            <h4 className="text-lg font-bold mb-1">Set Up Your First Budget</h4>
            <p className="text-sm text-outline max-w-sm font-medium mb-6">
              Create category spending limits to track real-time utilization from
              your transactions.
            </p>
            <div className="flex gap-4">
              <button
                onClick={handleAutoGenerateBudgets}
                className="px-6 py-2.5 rounded-xl bg-secondary/10 hover:bg-secondary/20 text-secondary font-bold text-xs shadow-sm transition-all"
              >
                Auto-Generate Default Budgets
              </button>
              <button
                onClick={handleAddBudget}
                className="px-6 py-2.5 rounded-xl bg-primary hover:brightness-110 text-white font-bold text-xs shadow-md transition-all flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" /> Create From Scratch
              </button>
            </div>
          </div>
        ) : budgetItems.length === 0 ? (
          <div className="py-10 text-center text-sm text-outline font-medium">
            No active budgets for the current date range. Adjust start/end dates
            on your budgets or add new ones.
          </div>
        ) : (
          <div className="space-y-8">
            {budgetItems.map((item) => (
              <div key={item.id} className="group relative pr-16">
                <div className="flex justify-between items-center mb-3">
                  <div className="flex items-center gap-4">
                    <div
                      className={cn(
                        'w-12 h-12 rounded-xl flex items-center justify-center transition-all',
                        item.alert
                          ? 'bg-error/10 text-error'
                          : 'bg-surface-container-high text-primary'
                      )}
                    >
                      <item.icon className="w-5 h-5" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-on-surface">
                        {item.label}
                      </p>
                      <p
                        className={cn(
                          'text-[10px] font-bold uppercase tracking-[0.15em]',
                          item.alert ? 'text-error' : 'text-outline'
                        )}
                      >
                        {item.sub}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-on-surface">
                      {formatCurrency(item.spent)} of {formatCurrency(item.total)}
                    </p>
                    <p
                      className={cn(
                        'text-[10px] font-bold uppercase tracking-widest mt-0.5',
                        item.alert || item.overBudget
                          ? 'text-error'
                          : 'text-on-surface-variant'
                      )}
                    >
                      {item.status}
                      {item.overBudget ? ' · Over budget' : ''}
                    </p>
                  </div>
                </div>
                <div className="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
                  <div
                    className={cn(
                      item.color,
                      'h-full transition-all duration-1000 ease-out'
                    )}
                    style={{ width: `${item.percent}%` }}
                  />
                </div>

                {item.raw && (
                  <div className="absolute right-0 top-1/2 -translate-y-1/2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => handleEditBudget(item.raw!)}
                      className="p-2 text-outline hover:text-primary bg-surface-container-high hover:bg-primary/10 rounded-lg transition-all"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm('Delete this budget?')) {
                          deleteBudget(item.id);
                          refreshSummary({ force: true });
                        }
                      }}
                      className="p-2 text-outline hover:text-error bg-surface-container-high hover:bg-error/10 rounded-lg transition-all"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <GoalModal
        isOpen={goalModalOpen}
        onClose={closeGoalModal}
        editingGoal={editingGoal}
      />

      <BudgetModal
        isOpen={budgetModalOpen}
        onClose={closeBudgetModal}
        editingBudget={editingBudget}
      />
    </PageShell>
  );
};
