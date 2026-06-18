import React, { useMemo } from 'react';

import { useAppContext } from '../context/AppContext';
import { ExpenseBreakdown } from '../components/Dashboard/ExpenseBreakdown';
import { RecentTransactions } from '../components/Dashboard/RecentTransactions';
import { QuickAddModal } from '../components/Dashboard/QuickAddModal';
import { LinkedAccounts } from '../components/Dashboard/LinkedAccounts';
import { AccountModal } from '../components/AccountModal';
import {
  DashboardHero,
  MonthlySpendTrend,
  FinancialHealthCard,
  AnomaliesCard,
} from '../components/Dashboard/DashboardHero';
import { PageShell } from '../components/PageShell';
import { formatCurrency } from '../lib/utils';
import {
  type AnalysisPeriod,
  getDashboardPeriodSlice,
} from '../lib/analysisPeriod';

export const Dashboard: React.FC = () => {
  const {
    user,
    authReady,
    dashboardSummary,
    loadDashboardSummary,
    loadFinancialHealthInsights,
    dashboardSummaryLoading,
    analysisPeriod,
    setAnalysisPeriod,
  } = useAppContext();
  const [isAccountModalOpen, setIsAccountModalOpen] = React.useState(false);
  const [isQuickAddOpen, setIsQuickAddOpen] = React.useState(false);
  const [healthInsights, setHealthInsights] = React.useState<any | null>(null);
  const [healthInsightsLlmLoading, setHealthInsightsLlmLoading] = React.useState(false);

  const periodData = useMemo(
    () => getDashboardPeriodSlice(dashboardSummary, analysisPeriod),
    [dashboardSummary, analysisPeriod],
  );

  const loadHealthInsightsPipeline = React.useCallback(
    (force?: boolean) => {
      void loadFinancialHealthInsights({ force, llm: false }).then((data) => {
        if (data) setHealthInsights(data);
      });
      setHealthInsightsLlmLoading(true);
      void loadFinancialHealthInsights({ force, llm: true }).then((data) => {
        if (data?.source === 'llm') setHealthInsights(data);
        setHealthInsightsLlmLoading(false);
      });
    },
    [loadFinancialHealthInsights],
  );

  const refreshDashboard = React.useCallback(
    async (options?: { force?: boolean }) => {
      await loadDashboardSummary({ force: options?.force });
      loadHealthInsightsPipeline(options?.force);
    },
    [loadDashboardSummary, loadHealthInsightsPipeline],
  );

  React.useEffect(() => {
    if (!user?.isAuthenticated) return;
    loadHealthInsightsPipeline();
  }, [user?.isAuthenticated, loadHealthInsightsPipeline]);

  const handleAccountCreated = () => {
    void refreshDashboard({ force: true });
  };

  if (!authReady || (dashboardSummaryLoading && !dashboardSummary)) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-lumio-black" />
      </div>
    );
  }

  const summary = periodData?.summary;
  const chartData = periodData?.chart_data ?? [];
  const recentTx = dashboardSummary?.recent_transactions ?? [];
  const topSpending = periodData?.top_spending ?? [];
  const anomalies = periodData?.spending_anomalies ?? [];
  const financialHealth = dashboardSummary?.financial_health;
  const expenseBreakdown = periodData?.expense_breakdown_month ?? [];

  const totalExpense = summary?.net_outflow ?? 0;
  const expenses = chartData.map((d) => d.expense ?? 0).filter((v) => v > 0);
  const priorExpense = expenses.length >= 2 ? expenses[expenses.length - 2] : null;
  const currentExpense = expenses.length >= 1 ? expenses[expenses.length - 1] : totalExpense;
  const changePct =
    summary?.expense_change_pct ??
    (priorExpense && priorExpense > 0
      ? Math.round(((currentExpense - priorExpense) / priorExpense) * 100)
      : null);

  return (
    <PageShell>
      <DashboardHero
        onRefresh={() => void refreshDashboard({ force: true })}
        loading={dashboardSummaryLoading}
      />

      <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="col-span-1 lg:col-span-8 flex flex-col gap-8">
          <MonthlySpendTrend
            chartData={chartData}
            totalExpense={totalExpense}
            predictedNextMonth={periodData?.predicted_next_month ?? dashboardSummary?.forecast?.predicted_next_month}
            predictedMonthLabel={periodData?.predicted_month_label ?? dashboardSummary?.forecast?.predicted_month_label}
            changePct={changePct}
            analysisPeriod={analysisPeriod}
            chartGranularity={periodData?.chart_granularity}
            loading={dashboardSummaryLoading && !periodData}
            onPeriodChange={(p: AnalysisPeriod) => setAnalysisPeriod(p)}
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bento-card !p-0 overflow-hidden">
              <ExpenseBreakdown
                analysisPeriod={analysisPeriod}
                variant="bento"
                breakdownData={expenseBreakdown}
              />
            </div>

            <div className="bento-card flex flex-col">
              <h3 className="font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted mb-6 border-b border-lumio-line pb-4">
                Top Spending
              </h3>
              {topSpending.length === 0 ? (
                <p className="text-sm text-lumio-muted">No spending data for this period.</p>
              ) : (
                <div className="flex flex-col">
                  {topSpending.map((item) => (
                    <div
                      key={item.merchant}
                      className="flex justify-between items-center py-4 border-b border-lumio-line/50 last:border-0"
                    >
                      <div className="flex items-center gap-4 min-w-0">
                        <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center text-sm font-bold border border-white/60 shadow-sm shrink-0">
                          {item.merchant.charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <span className="font-medium text-sm block truncate">{item.merchant}</span>
                          {item.count != null && item.count > 1 && (
                            <span className="text-[10px] text-lumio-muted uppercase tracking-wider">
                              {item.count} transactions
                            </span>
                          )}
                        </div>
                      </div>
                      <span className="text-lumio-muted text-sm font-medium shrink-0 ml-2">
                        {formatCurrency(item.total)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <LinkedAccounts
            accounts={dashboardSummary?.accounts}
            onAddAccount={() => setIsAccountModalOpen(true)}
            variant="bento"
          />

          <RecentTransactions
            transactions={recentTx}
            variant="bento"
            onAddTransaction={() => setIsQuickAddOpen(true)}
          />
        </div>

        <div className="col-span-1 lg:col-span-4 flex flex-col gap-8">
          <FinancialHealthCard
            health={financialHealth}
            summary={summary}
            insights={healthInsights}
            insightsLlmLoading={healthInsightsLlmLoading}
          />
          <AnomaliesCard anomalies={anomalies} />
        </div>
      </div>

      <AccountModal
        isOpen={isAccountModalOpen}
        onClose={() => setIsAccountModalOpen(false)}
        onSuccess={handleAccountCreated}
      />

      <QuickAddModal
        isOpen={isQuickAddOpen}
        onClose={() => setIsQuickAddOpen(false)}
        onSuccess={() => void refreshDashboard({ force: true })}
        accounts={dashboardSummary?.accounts}
      />
    </PageShell>
  );
};
