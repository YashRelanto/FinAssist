import React, { useCallback, useEffect, useState } from 'react';
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
import { useAppContext } from '../context/AppContext';
import { GoalModal } from '../components/GoalModal';
import { BudgetModal } from '../components/BudgetModal';
import { Budget } from '../types';
import { activeUserId } from '../lib/activeUserId';
import {
  fetchBudgetGoalsSummary,
  GoalWithProgress,
  SavingsTrajectory,
} from '../lib/budgetGoalsApi';
import type { BudgetUtilizationItem } from '../components/Dashboard/BudgetUtilization';

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
  } = useAppContext();

  const userId = activeUserId(user);

  const [goalModalOpen, setGoalModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<GoalWithProgress | undefined>(
    undefined
  );

  const [budgetModalOpen, setBudgetModalOpen] = useState(false);
  const [editingBudget, setEditingBudget] = useState<Budget | undefined>(
    undefined
  );

  const [loading, setLoading] = useState(true);
  const [budgetUtilization, setBudgetUtilization] = useState<
    BudgetUtilizationItem[]
  >([]);
  const [goalItems, setGoalItems] = useState<GoalWithProgress[]>([]);
  const [trajectory, setTrajectory] =
    useState<SavingsTrajectory>(defaultTrajectory);

  const refreshSummary = useCallback(async () => {
    if (!userId) {
      setBudgetUtilization([]);
      setGoalItems([]);
      setTrajectory(defaultTrajectory);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const data = await fetchBudgetGoalsSummary(userId);
      setBudgetUtilization(data.budget_utilization ?? []);
      setGoalItems(data.goals ?? []);
      setTrajectory(data.trajectory ?? defaultTrajectory);
    } catch (error) {
      console.error('Failed to load budget & goals summary', error);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    refreshSummary();
  }, [refreshSummary]);

  useEffect(() => {
    if (!userId) return;
    const onFocus = () => refreshSummary();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [userId, refreshSummary]);

  const closeGoalModal = () => {
    setGoalModalOpen(false);
    refreshSummary();
  };

  const closeBudgetModal = () => {
    setBudgetModalOpen(false);
    refreshSummary();
  };

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
  const strokeOffset = 351.8 - (351.8 * trajectory.stroke_pct) / 100;

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
    const defaultBudgets = [
      {
        categoryName: 'Housing',
        budgetName: 'Housing & Utilities',
        amount: user.fixedRent || 2000,
        period: 'monthly',
        startDate: new Date().toISOString().split('T')[0],
        endDate: new Date(new Date().setMonth(new Date().getMonth() + 1))
          .toISOString()
          .split('T')[0],
        alertThreshold: 90,
      },
      {
        categoryName: 'Food & Drinks',
        budgetName: 'Dining & Food Outing',
        amount: 800,
        period: 'monthly',
        startDate: new Date().toISOString().split('T')[0],
        endDate: new Date(new Date().setMonth(new Date().getMonth() + 1))
          .toISOString()
          .split('T')[0],
        alertThreshold: 85,
      },
      {
        categoryName: 'Transportation',
        budgetName: 'Transportation Commute',
        amount: 450,
        period: 'monthly',
        startDate: new Date().toISOString().split('T')[0],
        endDate: new Date(new Date().setMonth(new Date().getMonth() + 1))
          .toISOString()
          .split('T')[0],
        alertThreshold: 80,
      },
      {
        categoryName: 'Shopping',
        budgetName: 'Groceries Shopping',
        amount: 600,
        period: 'monthly',
        startDate: new Date().toISOString().split('T')[0],
        endDate: new Date(new Date().setMonth(new Date().getMonth() + 1))
          .toISOString()
          .split('T')[0],
        alertThreshold: 80,
      },
    ];

    defaultBudgets.forEach((b) => addBudget(b));
  };

  if (loading && goalItems.length === 0 && budgetItems.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-10">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
        <div>
          <h2 className="text-3xl font-bold text-on-surface">Budget & Goals</h2>
          <p className="text-on-surface-variant mt-2 max-w-2xl text-sm font-medium">
            Strategic oversight of your financial commitments. Budget utilization
            is computed from your live expenses within each budget&apos;s date
            range.
          </p>
        </div>
        <div className="flex gap-4 w-full md:w-auto">
          <button
            onClick={handleAddGoal}
            className="flex-1 md:flex-none px-6 py-2.5 rounded-lg bg-primary text-white font-bold text-sm hover:brightness-110 shadow-md transition-all flex items-center justify-center gap-2"
          >
            <Plus className="w-4 h-4" /> Create New Goal
          </button>
        </div>
      </div>

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
                            refreshSummary();
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
                        item.alert ? 'text-error' : 'text-secondary'
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
                          refreshSummary();
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

      <div className="bg-inverse-surface rounded-2xl p-8 text-white flex flex-col md:flex-row items-center justify-between gap-8 h-full">
        <div className="max-w-2xl">
          <h4 className="text-2xl font-bold mb-3">{trajectory.title}</h4>
          <p className="opacity-80 text-sm leading-relaxed font-medium">
            {trajectory.description}
          </p>
        </div>
        <div className="relative w-32 h-32 flex items-center justify-center flex-shrink-0">
          <svg className="w-full h-full transform -rotate-90">
            <circle
              className="text-white/10"
              cx="64"
              cy="64"
              fill="transparent"
              r="56"
              stroke="currentColor"
              strokeWidth="8"
            />
            <circle
              className="text-secondary"
              cx="64"
              cy="64"
              fill="transparent"
              r="56"
              stroke="currentColor"
              strokeDasharray="351.8"
              strokeDashoffset={strokeOffset}
              strokeWidth="8"
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute flex flex-col items-center">
            <span className="text-3xl font-bold">
              {trajectory.has_data
                ? `${trajectory.savings_growth_pct > 0 ? '+' : ''}${trajectory.savings_growth_pct}%`
                : '0%'}
            </span>
            <span className="text-[8px] font-bold opacity-60 uppercase tracking-widest">
              vs last month
            </span>
          </div>
        </div>
      </div>

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
    </div>
  );
};
