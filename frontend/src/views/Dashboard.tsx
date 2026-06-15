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
  const { user, dashboardSummary, loadDashboardSummary, loadAccountHubAnalysis, transactions, accounts, analysisPeriod } = useAppContext();
  const [isAccountModalOpen, setIsAccountModalOpen] = React.useState(false);
  const hubAnalysisScheduledRef = React.useRef(false);

  const refreshDashboard = React.useCallback(
    async (options?: { force?: boolean }) => {
      await loadDashboardSummary({ force: options?.force });
    },
    [loadDashboardSummary],
  );

  const handleAccountCreated = () => {
    void refreshDashboard({ force: true });
    void loadAccountHubAnalysis({ force: true });
  };

  React.useEffect(() => {
    if (!user?.isAuthenticated || hubAnalysisScheduledRef.current) return;
    const hasAccounts = (dashboardSummary?.accounts?.length ?? 0) > 0;
    if (!hasAccounts) return;
    hubAnalysisScheduledRef.current = true;
    void loadAccountHubAnalysis();
  }, [user?.isAuthenticated, dashboardSummary?.accounts?.length, loadAccountHubAnalysis]);

  if (!dashboardSummary && user?.isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    );
  }

  const dashboardData = dashboardSummary;

  const mappedSummary = dashboardData?.summary
    ? {
        fixed_income: dashboardData.summary.monthly_income,
        fixed_expense: dashboardData.summary.fixed_expense,
        net_inflow: dashboardData.summary.net_inflow,
        net_outflow: dashboardData.summary.net_outflow,
        net_savings: dashboardData.summary.net_savings,
        savings_rate: dashboardData.summary.savings_rate,
      }
    : undefined;

  return (
    <div className="space-y-8 pb-10">
      
      {/* Summary Cards */}
      <SummaryCards
        data={mappedSummary}
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
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Financial Performance */}
        <FinancialPerformanceChart
          data={dashboardData?.chart_data}
          accounts={accounts}
          transactions={transactions}
          analysisPeriod={analysisPeriod}
        />

        {/* Expense Breakdown */}
        <ExpenseBreakdown analysisPeriod={analysisPeriod} />
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
          onSuccess={() => refreshDashboard({ force: true })}
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