import React from 'react';

import { useAppContext } from '../context/AppContext';

import { SummaryCards } from '../components/Dashboard/SummaryCards';
import { FinancialPerformanceChart } from '../components/Dashboard/FinancialPerformanceChart';
import { LinkedAccounts } from '../components/Dashboard/LinkedAccounts';
import { QuickActionCard } from '../components/Dashboard/QuickActionCard';
import { ExpenseBreakdown } from '../components/Dashboard/ExpenseBreakdown';
import { BudgetUtilization } from '../components/Dashboard/BudgetUtilization';
import { RecentTransactions } from '../components/Dashboard/RecentTransactions';
import { QuickAddForm } from '../components/Dashboard/QuickAddForm';
import { AIInsights } from '../components/Dashboard/AIInsights';
import { ForecastPredictionCard } from '../components/Dashboard/ForecastPredictionCard';

import { AccountModal } from '../components/AccountModal';

export const Dashboard: React.FC = () => {
  const { user, dashboardSummary, loadDashboardSummary } = useAppContext();
  const [loading, setLoading] = React.useState(false);
  const [isAccountModalOpen, setIsAccountModalOpen] = React.useState(false);

  const fetchDashboardData = React.useCallback(
    async (options?: { silent?: boolean; force?: boolean }) => {
      try {
        if (!options?.silent) setLoading(true);
        await loadDashboardSummary({ force: options?.force });
      } finally {
        if (!options?.silent) setLoading(false);
      }
    },
    [loadDashboardSummary],
  );

  const handleAccountCreated = (account: Record<string, unknown>) => {
    // Dashboard is centralized now; just force refresh.
    void fetchDashboardData({ silent: true, force: true });
  };

  React.useEffect(() => {
    if (user?.isAuthenticated) {
      fetchDashboardData();
    }
  }, [user?.isAuthenticated, fetchDashboardData]);

  React.useEffect(() => {
    if (!user?.isAuthenticated) return;
    const onFocus = () => fetchDashboardData({ silent: true });
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [user?.isAuthenticated, fetchDashboardData]);

  if ((loading || !dashboardSummary) && user?.isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    );
  }

  const dashboardData = dashboardSummary;

  return (
    <div className="space-y-8 pb-10">
      
      {/* Summary Cards */}
      <SummaryCards
        data={dashboardData?.summary}
        periodLabel={dashboardData?.period_label}
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <ForecastPredictionCard />
      </div>

      {/* Linked Accounts + Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        <div className="lg:col-span-12">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-black text-outline uppercase tracking-[0.2em] px-2">
              Your Financial Hub
            </h3>

            <button
              onClick={() => setIsAccountModalOpen(true)}
              className="text-[10px] font-black text-primary uppercase tracking-widest hover:underline"
            >
              Manage Accounts
            </button>
          </div>
        </div>

        {/* Linked Accounts */}
        <LinkedAccounts 
          accounts={dashboardData?.accounts} 
          onAddAccount={() => setIsAccountModalOpen(true)}
        />

        {/* Quick Actions */}
        <QuickActionCard
          hasAccounts={(dashboardData?.accounts?.length ?? 0) > 0}
          refreshKey={`${dashboardData?.accounts?.length ?? 0}-${dashboardData?.recent_transactions?.length ?? 0}`}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Financial Performance */}
        <FinancialPerformanceChart
          data={dashboardData?.chart_data}
        />

        {/* Expense Breakdown */}
        <ExpenseBreakdown initialData={dashboardData?.expense_breakdown_month} />
      </div>

      {/* Budget + Recent Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Budget Utilization */}
        <BudgetUtilization items={dashboardData?.budget_utilization} />

        {/* Recent Transactions */}
        <RecentTransactions
          transactions={dashboardData?.recent_transactions}
        />
      </div>

      {/* Quick Add + AI Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Quick Add Form */}
        <QuickAddForm
          onSuccess={() => fetchDashboardData({ force: true })}
          accounts={dashboardData?.accounts}
        />

        {/* AI Insights */}
        <AIInsights />
      </div>

      {/* Account Modal */}
      <AccountModal
        isOpen={isAccountModalOpen}
        onClose={() => setIsAccountModalOpen(false)}
        onSuccess={handleAccountCreated}
      />
    </div>
  );
};