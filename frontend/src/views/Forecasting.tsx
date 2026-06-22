
import React from 'react';
import { AlertCircle, TrendingDown, TrendingUp } from 'lucide-react';
import { motion } from 'motion/react';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency } from '../lib/utils';
import { PageHeader, PageShell } from '../components/PageShell';
import {
  type AnalysisPeriod,
  ANALYSIS_PERIOD_OPTIONS,
} from '../lib/analysisPeriod';
import { CategoryTrendPanel } from '../components/Analytics/CategoryTrendPanel';
import { CategoryShareChart } from '../components/Analytics/CategoryShareChart';
import { MerchantAnalyticsPanel } from '../components/Analytics/MerchantAnalyticsPanel';
import { SpendingBehaviorPanel } from '../components/Analytics/SpendingBehaviorPanel';
import { FinancialInsightsPanel } from '../components/Analytics/FinancialInsightsPanel';

interface ForecastData {
  predicted_next_month?: number;
  predicted_month_start?: string;
  predicted_month_end?: string;
  prev_period_spend?: number;
  prev_month_spend?: number;
  total_analyzed_spending?: number;
  period_label?: string;
  comparison_period_label?: string;
  period_change_pct?: number;
  budget_alert?: boolean;
  budget_alert_message?: string | null;
  message?: string;
  model_name?: string;
  model_loaded?: boolean;
  insights?: {
    outlier?: { amount: number; merchant: string; category: string } | null;
    recurring?: { count: number; monthly_total: number } | null;
  };
}

interface AccountOption {
  account_id: string;
  account_name: string;
}

interface CategoryOption {
  category_id: string;
  main_category: string;
}

const DEFAULT_ANALYTICS_PERIOD: AnalysisPeriod = '3m';

export const Forecasting: React.FC = () => {
  const {
    user,
    accounts,
    transactions,
    loadForecast,
    loadSpendingAnalytics,
    loadFinancialInsights,
  } = useAppContext();

  const [analyticsPeriod, setAnalyticsPeriod] = React.useState<AnalysisPeriod>(DEFAULT_ANALYTICS_PERIOD);
  const [forecast, setForecast] = React.useState<ForecastData | null>(null);
  const [analytics, setAnalytics] = React.useState<any | null>(null);
  const [insights, setInsights] = React.useState<any | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [insightsLlmLoading, setInsightsLlmLoading] = React.useState(false);
  const [categories, setCategories] = React.useState<CategoryOption[]>([]);
  const [accountId, setAccountId] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [merchant, setMerchant] = React.useState('');
  const [draftMerchant, setDraftMerchant] = React.useState('');

  const filterParams = React.useMemo(
    () => ({
      period: analyticsPeriod,
      accountId: accountId || undefined,
      categoryId: categoryId || undefined,
      merchant: merchant || undefined,
    }),
    [analyticsPeriod, accountId, categoryId, merchant],
  );

  const fetchAll = React.useCallback(
    async (options?: { force?: boolean }) => {
      if (!user?.isAuthenticated) return;
      try {
        setLoading(true);
        const [forecastData, analyticsData] = await Promise.all([
          loadForecast({ ...filterParams, force: options?.force }),
          loadSpendingAnalytics({ ...filterParams, force: options?.force }),
        ]);
        setForecast(forecastData as ForecastData | null);
        setAnalytics(analyticsData);
      } finally {
        setLoading(false);
      }

      const instantInsights = await loadFinancialInsights({
        ...filterParams,
        llm: false,
        force: options?.force,
      });
      setInsights(instantInsights);

      setInsightsLlmLoading(true);
      void loadFinancialInsights({ ...filterParams, llm: true, force: true }).then((data) => {
        if (data?.source === 'llm') setInsights(data);
        setInsightsLlmLoading(false);
      });
    },
    [user?.isAuthenticated, loadForecast, loadSpendingAnalytics, loadFinancialInsights, filterParams],
  );

  React.useEffect(() => {
    if (user?.isAuthenticated) {
      void fetchAll();
    }
  }, [user?.isAuthenticated, fetchAll]);

  React.useEffect(() => {
    if (!transactions?.length) {
      setCategories([]);
      return;
    }
    const seen = new Map<string, string>();
    for (const t of transactions as any[]) {
      if (t?.category_id && t?.category) {
        seen.set(String(t.category_id), String(t.category));
      }
    }
    setCategories(
      Array.from(seen.entries()).map(([category_id, main_category]) => ({
        category_id,
        main_category,
      })),
    );
  }, [transactions]);

  const prevSpend = forecast?.prev_period_spend ?? forecast?.prev_month_spend;
  const currentSpend = analytics?.total_spend ?? forecast?.total_analyzed_spending;
  const periodLabel = analytics?.period_label ?? forecast?.period_label;
  const comparisonLabel =
    analytics?.comparison_period_label ?? forecast?.comparison_period_label;
  const predicted = forecast?.predicted_next_month ?? 0;
  const changePct = forecast?.period_change_pct ?? 0;
  const changeDown = changePct < 0;
  const changeAbs = Math.abs(changePct);

  const categoryInsightMap = React.useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of insights?.category_trends || []) {
      if (row.category && row.insight) map[row.category] = row.insight;
    }
    return map;
  }, [insights]);

  const predictedLabel = React.useMemo(() => {
    if (forecast?.predicted_month_start) {
      const d = new Date(`${forecast.predicted_month_start}T00:00:00`);
      return d.toLocaleString('en', { month: 'long', year: 'numeric' });
    }
    return 'next month';
  }, [forecast?.predicted_month_start]);

  return (
    <PageShell>
      <PageHeader
        title="Analytics"
        description="Category trends, merchant patterns, and AI-powered spending insights."
        onRefresh={() => void fetchAll({ force: true })}
        loading={loading}
      />

      {forecast?.budget_alert && forecast.budget_alert_message && (
        <motion.div className="bg-error/5 border border-error/20 p-4 rounded-2xl flex items-center gap-4">
          <AlertCircle className="w-5 h-5 text-error shrink-0" />
          <p className="text-sm font-black text-on-surface tracking-tight">{forecast.budget_alert_message}</p>
        </motion.div>
      )}

      <motion.div className="flex flex-col md:flex-row gap-4 items-end md:items-center bg-surface-container-lowest p-6 rounded-3xl border border-outline-variant/30">
        <motion.div className="grid grid-cols-2 md:grid-cols-4 gap-4 flex-1">
          <motion.div className="space-y-1.5">
            <motion.label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">
              Period
            </motion.label>
            <motion.select
              value={analyticsPeriod}
              onChange={(e) => setAnalyticsPeriod(e.target.value as AnalysisPeriod)}
              className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none"
            >
              {ANALYSIS_PERIOD_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </motion.select>
          </motion.div>
          <motion.div className="space-y-1.5">
            <motion.label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">
              Account
            </motion.label>
            <motion.select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none"
            >
              <option value="">All Accounts</option>
              {(accounts as AccountOption[]).map((a) => (
                <option key={a.account_id} value={a.account_id}>
                  {a.account_name}
                </option>
              ))}
            </motion.select>
          </motion.div>
          <motion.div className="space-y-1.5">
            <motion.label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">
              Category
            </motion.label>
            <motion.select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none"
            >
              <option value="">All Categories</option>
              {categories.map((c) => (
                <option key={c.category_id} value={c.category_id}>
                  {c.main_category}
                </option>
              ))}
            </motion.select>
          </motion.div>
          <motion.div className="space-y-1.5">
            <motion.label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">
              Merchant
            </motion.label>
            <motion.input
              type="text"
              value={draftMerchant}
              onChange={(e) => setDraftMerchant(e.target.value)}
              placeholder="Filter by merchant..."
              className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none"
            />
          </motion.div>
        </motion.div>
        <motion.button
          onClick={() => setMerchant(draftMerchant.trim())}
          className="bg-primary text-white px-8 py-3 rounded-xl font-bold text-sm shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all"
        >
          Apply Filters
        </motion.button>
      </motion.div>

      <motion.div className={cn(
        "bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 relative overflow-hidden",
        loading && "animate-pulse",
      )}>
        <motion.div className="absolute top-0 left-0 w-2 h-full bg-secondary" />
        <motion.div className="flex justify-between items-start flex-wrap gap-4">
          <motion.div>
            <motion.p className="text-[10px] font-black text-outline uppercase tracking-[0.2em] mb-2">
              Predicted spend — {predictedLabel}
            </motion.p>
            <motion.h2 className="text-5xl font-black text-on-surface">
              {forecast ? formatCurrency(predicted) : '—'}
            </motion.h2>
            {forecast && currentSpend != null && (
              <motion.p className="text-xs text-lumio-muted font-medium mt-2">
                {formatCurrency(currentSpend)} spent
                {periodLabel ? ` · ${periodLabel}` : ' in selected period'}
              </motion.p>
            )}
            {forecast && prevSpend != null && comparisonLabel && (
              <motion.p className="text-[11px] text-outline font-bold mt-1">
                Prior period spend: {formatCurrency(prevSpend)} ({comparisonLabel})
              </motion.p>
            )}
          </motion.div>
          {changePct !== 0 && (
            <motion.div className="text-right">
              <motion.div
                className={cn(
                  'flex items-center justify-end gap-1 font-black',
                  changeDown ? 'text-emerald-700' : 'text-red-600',
                )}
              >
                {changeDown ? <TrendingDown className="w-5 h-5" /> : <TrendingUp className="w-5 h-5" />}
                <motion.span className="text-xl">{changeAbs}%</motion.span>
              </motion.div>
              <motion.p className="text-[10px] font-bold text-lumio-muted uppercase tracking-widest mt-1">
                {changeDown ? 'lower' : 'higher'} than {
                  analyticsPeriod === '1m' ? 'last month' :
                  analyticsPeriod === '3m' ? 'last 3 months' :
                  analyticsPeriod === '6m' ? 'last 6 months' :
                  analyticsPeriod === '1y' ? 'last year' : 'previous period'
                }
              </motion.p>
            </motion.div>
          )}
        </motion.div>
      </motion.div>

      {(forecast?.insights?.outlier || forecast?.insights?.recurring) && (
        <motion.div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {forecast.insights.outlier && (
            <motion.div className="bg-primary/5 p-6 rounded-2xl border border-primary/10">
              <p className="text-[10px] font-black text-primary uppercase tracking-widest mb-2">
                Outlier Detected
              </p>
              <p className="text-xs font-bold leading-relaxed">
                Single transaction of {formatCurrency(forecast.insights.outlier.amount)} in{' '}
                {forecast.insights.outlier.category} at {forecast.insights.outlier.merchant}.
              </p>
            </motion.div>
          )}
          {forecast.insights.recurring && (
            <motion.div className="bg-secondary/5 p-6 rounded-2xl border border-secondary/10">
              <p className="text-[10px] font-black text-secondary uppercase tracking-widest mb-2">
                Recurring Analysis
              </p>
              <p className="text-xs font-bold leading-relaxed">
                {forecast.insights.recurring.count} recurring merchants detected, totaling{' '}
                {formatCurrency(forecast.insights.recurring.monthly_total)}/month (avg per merchant).
              </p>
            </motion.div>
          )}
        </motion.div>
      )}

      <FinancialInsightsPanel
        executiveSummary={insights?.executive_summary}
        recommendations={insights?.recommendations}
        loading={loading}
        aiLoading={insightsLlmLoading}
      />

      <CategoryTrendPanel
        trends={analytics?.category_trends || []}
        insights={categoryInsightMap}
        categoryAnalysis={insights?.category_analysis}
        loading={loading}
        aiLoading={insightsLlmLoading}
      />

      <CategoryShareChart
        data={analytics?.category_share || []}
        totalSpend={analytics?.total_spend}
        loading={loading}
      />

      <MerchantAnalyticsPanel
        topMerchants={analytics?.merchant_analytics?.top_merchants || []}
        merchantGrowth={analytics?.merchant_analytics?.merchant_growth || []}
        concentration={analytics?.merchant_analytics?.concentration}
        fastestGrowingInsight={insights?.merchant_insights?.fastest_growing}
        concentrationInsight={insights?.merchant_insights?.concentration}
        loading={loading}
      />

      <SpendingBehaviorPanel
        weekdayVsWeekend={analytics?.spending_behavior?.weekday_vs_weekend}
        dayOfWeekHeatmap={analytics?.spending_behavior?.day_of_week_heatmap}
        transactionFrequency={analytics?.spending_behavior?.transaction_frequency}
        weekendInsight={
          analytics?.spending_behavior?.weekend_insight ??
          insights?.behavior_insights?.weekend
        }
        timeOfDayInsight={
          analytics?.spending_behavior?.peak_insight ??
          insights?.behavior_insights?.time_of_day
        }
        loading={loading}
      />
    </PageShell>
  );
};
