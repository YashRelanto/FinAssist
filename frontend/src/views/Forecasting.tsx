
import React from 'react';
import {
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Eye,
  RefreshCcw,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { motion } from 'motion/react';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency } from '../lib/utils';

const heatmapColors = [
  'bg-blue-50',
  'bg-blue-100',
  'bg-blue-200',
  'bg-blue-300',
  'bg-blue-500',
  'bg-blue-700',
];

interface DailyPrediction {
  date: string;
  day: string;
  amount: number;
  is_weekend: boolean;
}

interface PredictedMonth {
  month: string;
  label: string;
  month_start: string;
  month_end: string;
  amount: number;
  daily_breakdown?: DailyPrediction[];
}

interface ForecastData {
  success: boolean;
  message?: string;
  model_loaded?: boolean;
  model_name?: string;
  period?: string;
  period_label?: string;
  start_date?: string | null;
  end_date?: string;
  predicted_next_month?: number;
  predicted_month_start?: string;
  predicted_month_end?: string;
  predicted_months?: PredictedMonth[];
  prev_period_spend?: number;
  prev_month_spend?: number;
  total_analyzed_spending: number;
  period_change_pct: number;
  period_change_direction: string;
  budget_alert?: boolean;
  budget_alert_message?: string | null;
  monthly_chart: { name: string; date_range?: string; value: number; is_forecast?: boolean; is_partial?: boolean }[];
  top_categories: { name: string; value: number }[];
  merchants: { name: string; value: number; total: number }[];
  heatmap: { date: string | null; amount: number; intensity: number }[];
  flow: { accounts_total: number; active_categories: number; identified_merchants: number };
  insights: {
    outlier?: { amount: number; merchant: string; category: string } | null;
    recurring?: { count: number; monthly_total: number } | null;
  };
  accuracy_pct?: number | null;
  model_type?: string;
  available_models?: { id: string; label: string; loaded: boolean; accuracy_pct: number | null }[];
}

interface AccountOption {
  account_id: string;
  account_name: string;
}

interface CategoryOption {
  category_id: string;
  main_category: string;
}

export const Forecasting: React.FC = () => {
  const {
    user,
    accounts,
    transactions,
    analysisPeriod,
    loadAccounts,
    loadTransactions,
    loadForecast,
  } = useAppContext();
  const [forecast, setForecast] = React.useState<ForecastData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [categories, setCategories] = React.useState<CategoryOption[]>([]);
  const [accountId, setAccountId] = React.useState('');
  const [categoryId, setCategoryId] = React.useState('');
  const [merchant, setMerchant] = React.useState('');
  const [draftMerchant, setDraftMerchant] = React.useState('');

  const fetchForecast = React.useCallback(
    async (options?: { force?: boolean }) => {
      if (!user?.isAuthenticated) return;
      try {
        setLoading(true);
        const data = await loadForecast({
          period: analysisPeriod,
          accountId,
          categoryId,
          merchant,
          force: options?.force,
        });
        setForecast(data as ForecastData | null);
      } finally {
        setLoading(false);
      }
    },
    [user?.isAuthenticated, loadForecast, analysisPeriod, accountId, categoryId, merchant],
  );

  React.useEffect(() => {
    if (user?.isAuthenticated) {
      loadAccounts();
      loadTransactions();
    }
  }, [user?.isAuthenticated, loadAccounts, loadTransactions]);

  React.useEffect(() => {
    if (user?.isAuthenticated) {
      fetchForecast();
    }
  }, [user?.isAuthenticated, fetchForecast]);

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

  const chartData = forecast?.monthly_chart?.length ? forecast.monthly_chart : [];
  const prevSpend = forecast?.prev_period_spend ?? forecast?.prev_month_spend;

  const categoryColors = ['#d1e4ff', '#004ac6', '#ffdad6', '#e2e2e6'];
  const topCats = forecast?.top_categories?.slice(0, 3) || [];

  if (loading && !forecast) {
    return (
      <motion.div className="flex items-center justify-center min-h-[400px]">
        <motion.div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary" />
      </motion.div>
    );
  }

  const changeDown = (forecast?.period_change_pct ?? 0) < 0;
  const changeAbs = Math.abs(forecast?.period_change_pct ?? 0);

  return (
    <div className="space-y-8 pb-20">
      {forecast?.budget_alert && forecast.budget_alert_message && (
        <motion.div className="bg-error/5 border border-error/20 p-4 rounded-2xl flex items-center justify-between group">
          <motion.div className="flex items-center gap-4">
            <motion.div className="w-10 h-10 bg-error/10 rounded-full flex items-center justify-center text-error">
              <AlertCircle className="w-5 h-5" />
            </motion.div>
            <motion.div>
              <motion.p className="text-sm font-black text-on-surface tracking-tight">
                {forecast.budget_alert_message}
              </motion.p>
              <motion.p className="text-[10px] font-bold text-error uppercase tracking-widest mt-0.5">
                Model: {forecast.model_name || 'Prophet (per user)'}
                {!forecast.model_loaded && ' — waiting for nightly model training'}
              </motion.p>
            </motion.div>
          </motion.div>
        </motion.div>
      )}

      {!forecast?.success && forecast?.message && (
        <motion.div className="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/30 text-sm font-bold text-outline">
          {forecast.message}
        </motion.div>
      )}

      <motion.div className="flex flex-col md:flex-row gap-4 items-end md:items-center bg-surface-container-lowest p-6 rounded-3xl border border-outline-variant/30">
        <motion.div className="grid grid-cols-2 md:grid-cols-3 gap-4 flex-1">
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
          onClick={() => {
            setMerchant(draftMerchant.trim());
          }}
          className="bg-primary text-white px-8 py-3 rounded-xl font-bold text-sm shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all"
        >
          Apply Filters
        </motion.button>
      </motion.div>

      <motion.div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <motion.div className="lg:col-span-8 space-y-8">
          <motion.div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 relative overflow-hidden">
            <motion.div className="absolute top-0 left-0 w-2 h-full bg-secondary" />
            <motion.div className="flex justify-between items-start">
              <motion.div>
                <motion.p className="text-[10px] font-black text-outline uppercase tracking-[0.2em] mb-2">
                  Total spending ({forecast?.period_label ?? 'selected period'})
                </motion.p>
                <motion.h2 className="text-5xl font-black text-on-surface">
                  {formatCurrency(forecast?.total_analyzed_spending ?? 0)}
                </motion.h2>
              </motion.div>
              <motion.div className="text-right">
                <motion.div
                  className={cn(
                    'flex items-center justify-end gap-1 font-black',
                    changeDown ? 'text-secondary' : 'text-error',
                  )}
                >
                  {changeDown ? (
                    <TrendingDown className="w-5 h-5" />
                  ) : (
                    <TrendingUp className="w-5 h-5" />
                  )}
                  <motion.span className="text-xl">{changeAbs}%</motion.span>
                </motion.div>
                <motion.p className="text-[10px] font-bold text-outline uppercase tracking-widest mt-1">
                  {changeDown ? 'lower' : 'higher'} than comparison period
                </motion.p>
              </motion.div>
            </motion.div>
          </motion.div>

          <motion.div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
            <motion.h3 className="text-lg font-black mb-1 px-2 tracking-tight">
              Actual + Predicted Spending
            </motion.h3>
            <motion.p className="text-[10px] font-bold text-outline uppercase tracking-widest mb-6 px-2">
              Calendar months in range (actual) + next month (predicted)
            </motion.p>
            <motion.div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" opacity={0.5} />
                  <XAxis
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 9, fill: '#64748B', fontWeight: 600 }}
                    interval={0}
                  />
                  <YAxis hide />
                  <Tooltip
                    cursor={{ fill: '#F1F5F9' }}
                    contentStyle={{
                      borderRadius: '16px',
                      border: 'none',
                      boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
                    }}
                    formatter={(value: number, _name: string, props: any) => [
                      formatCurrency(value),
                      props.payload?.is_forecast ? 'Predicted' : 'Actual',
                    ]}
                    labelFormatter={(label: string, payload: any[]) => {
                      const dateRange = payload?.[0]?.payload?.date_range;
                      return dateRange || label;
                    }}
                  />
                  <Bar dataKey="value" radius={[8, 8, 8, 8]} barSize={44}>
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={
                          entry.is_forecast
                            ? '#94a3b8'
                            : categoryColors[index % categoryColors.length]
                        }
                        stroke={entry.is_forecast ? '#475569' : undefined}
                        strokeWidth={entry.is_forecast ? 1.5 : 0}
                        fillOpacity={entry.is_forecast ? 0.55 : 1}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </motion.div>
            {/* Chart Legend */}
            <motion.div className="flex justify-center gap-6 mt-6 flex-wrap items-center">
              <motion.div className="flex items-center gap-2">
                <motion.div className="w-3 h-3 rounded-sm" style={{ backgroundColor: categoryColors[0] }} />
                <motion.span className="text-[10px] font-bold text-outline uppercase tracking-widest">Actual</motion.span>
              </motion.div>
              <motion.div className="flex items-center gap-2">
                <motion.div className="w-3 h-3 rounded-sm opacity-55" style={{ backgroundColor: '#94a3b8', border: '1.5px solid #475569' }} />
                <motion.span className="text-[10px] font-bold text-outline uppercase tracking-widest">Predicted</motion.span>
              </motion.div>
              {topCats.map((c, i) => (
                <motion.div key={c.name} className="flex items-center gap-2">
                  <motion.div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: categoryColors[(i + 1) % categoryColors.length] }}
                  />
                  <motion.span className="text-[10px] font-bold text-outline uppercase tracking-widest">
                    {c.name}
                  </motion.span>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>

          <motion.div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <motion.div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
              <motion.h3 className="text-sm font-black mb-6 tracking-tight uppercase">
                Top Merchants
              </motion.h3>
              <motion.div className="space-y-6">
                {(forecast?.merchants?.length ? forecast.merchants : []).map((m, i) => (
                  <motion.div key={i} className="space-y-2">
                    <motion.div className="flex justify-between items-center">
                      <motion.span className="text-xs font-bold text-on-surface">{m.name}</motion.span>
                      <motion.span className="text-xs font-black">{formatCurrency(m.value)}</motion.span>
                    </motion.div>
                    <motion.div className="w-full bg-surface-container h-2 rounded-full overflow-hidden">
                      <motion.div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${m.total > 0 ? (m.value / m.total) * 100 : 0}%` }}
                      />
                    </motion.div>
                  </motion.div>
                ))}
                {!forecast?.merchants?.length && (
                  <motion.p className="text-xs text-outline">No merchant data in this period.</motion.p>
                )}
              </motion.div>
            </motion.div>

            <motion.div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
              <motion.h3 className="text-sm font-black mb-6 tracking-tight uppercase">
                Spending Heatmap
              </motion.h3>
              <motion.div className="grid grid-cols-7 gap-1">
                {(forecast?.heatmap?.length ? forecast.heatmap : []).map((day, i) => (
                  <motion.div
                    key={day.date ?? i}
                    title={day.date ? `${day.date}: ${formatCurrency(day.amount)}` : ''}
                    className={cn(
                      'aspect-square rounded-md',
                      heatmapColors[day.intensity] ?? heatmapColors[0],
                    )}
                  />
                ))}
              </motion.div>
              <motion.div className="flex justify-between mt-4 items-center">
                <motion.span className="text-[10px] font-bold text-outline uppercase">Less</motion.span>
                <motion.div className="flex gap-1">
                  {heatmapColors.map((c, i) => (
                    <motion.div key={i} className={cn('w-2 h-2 rounded-sm', c)} />
                  ))}
                </motion.div>
                <motion.span className="text-[10px] font-bold text-outline uppercase">More</motion.span>
              </motion.div>
            </motion.div>
          </motion.div>

          <motion.div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
            <motion.h3 className="text-sm font-black mb-8 tracking-tight uppercase">Flow Analysis</motion.h3>
            <motion.div className="flex items-center justify-between relative px-4 flex-wrap gap-4">
              <motion.div className="bg-primary/5 p-4 rounded-xl border border-primary/10 text-center w-28">
                <motion.p className="text-[10px] font-black text-primary uppercase mb-1">Accounts</motion.p>
                <motion.p className="text-sm font-black">
                  {formatCurrency(forecast?.flow?.accounts_total ?? 0)}
                </motion.p>
              </motion.div>
              <motion.div className="flex-1 h-[2px] bg-primary/20 relative mx-4 min-w-[40px]" />
              <motion.div className="bg-secondary/5 p-4 rounded-xl border border-secondary/10 text-center w-28">
                <motion.p className="text-[10px] font-black text-secondary uppercase mb-1">Categories</motion.p>
                <motion.p className="text-sm font-black">
                  {forecast?.flow?.active_categories ?? 0} Active
                </motion.p>
              </motion.div>
              <motion.div className="flex-1 h-[2px] bg-secondary/20 relative mx-4 min-w-[40px]" />
              <motion.div className="bg-outline/5 p-4 rounded-xl border border-outline/10 text-center w-28">
                <motion.p className="text-[10px] font-black text-outline uppercase mb-1">Merchants</motion.p>
                <motion.p className="text-sm font-black">
                  {forecast?.flow?.identified_merchants ?? 0} Identified
                </motion.p>
              </motion.div>
            </motion.div>
          </motion.div>
        </motion.div>

        <motion.div className="lg:col-span-4 space-y-8">
          <motion.div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 space-y-8 h-full">
            <motion.div className="flex items-center gap-3">
              <Eye className="w-5 h-5 text-primary" />
              <motion.h3 className="text-lg font-black tracking-tight">Deep Insights</motion.h3>
            </motion.div>

            <motion.div className="space-y-6">
              {forecast?.insights?.outlier && (
                <motion.div className="bg-primary/5 p-6 rounded-2xl border border-primary/10">
                  <motion.p className="text-[10px] font-black text-primary uppercase tracking-widest mb-2">
                    Outlier Detected
                  </motion.p>
                  <motion.p className="text-xs font-bold leading-relaxed">
                    Single transaction of {formatCurrency(forecast.insights.outlier.amount)} in{' '}
                    {forecast.insights.outlier.category} at {forecast.insights.outlier.merchant}.
                  </motion.p>
                </motion.div>
              )}

              {forecast?.insights?.recurring && (
                <motion.div className="bg-secondary/5 p-6 rounded-2xl border border-secondary/10">
                  <motion.p className="text-[10px] font-black text-secondary uppercase tracking-widest mb-2">
                    Recurring Analysis
                  </motion.p>
                  <motion.p className="text-xs font-bold leading-relaxed">
                    {forecast.insights.recurring.count} recurring merchants detected, totaling{' '}
                    {formatCurrency(forecast.insights.recurring.monthly_total)}/month (avg per merchant).
                  </motion.p>
                </motion.div>
              )}

              <motion.div className="bg-secondary/5 p-6 rounded-2xl border border-secondary/10">
                <motion.p className="text-[10px] font-black text-secondary uppercase tracking-widest mb-2">
                  Goal Trajectory
                </motion.p>
                <motion.p className="text-xs font-bold leading-relaxed">
                  Based on your spending trend, stay on track for your{' '}
                  {user.primaryGoal || 'savings goal'} by keeping weekly expenses near your recent average.
                </motion.p>
              </motion.div>

              {forecast?.predicted_months && forecast.predicted_months.length > 0 && (
                <motion.div className="bg-error/5 p-6 rounded-2xl border border-error/10">
                  <motion.p className="text-[10px] font-black text-error uppercase tracking-widest mb-1">
                    Next month prediction
                  </motion.p>
                  <motion.div className="space-y-4">
                    {forecast.predicted_months.map((month) => (
                      <motion.div
                        key={month.month}
                        className="bg-surface-container-lowest rounded-xl p-3 border border-outline-variant/20"
                      >
                        <motion.div className="flex items-center justify-between mb-2">
                          <motion.span className="text-[10px] font-black text-on-surface uppercase tracking-wide">
                            {month.label}
                          </motion.span>
                          <motion.span className="text-xs font-black text-on-surface">
                            {formatCurrency(month.amount)}
                          </motion.span>
                        </motion.div>
                        {month.daily_breakdown && month.daily_breakdown.length > 0 && (
                          <motion.div className="grid grid-cols-7 gap-0.5">
                            {month.daily_breakdown.map((day) => (
                              <motion.div
                                key={day.date}
                                className={cn(
                                  'rounded-md p-1 text-center',
                                  day.is_weekend
                                    ? 'bg-secondary/15 border border-secondary/20'
                                    : 'bg-surface-container',
                                )}
                                title={`${day.date}: ${formatCurrency(day.amount)}`}
                              >
                                <motion.p
                                  className={cn(
                                    'text-[8px] font-black uppercase mb-0.5',
                                    day.is_weekend ? 'text-secondary' : 'text-outline',
                                  )}
                                >
                                  {day.day}
                                </motion.p>
                                <motion.p className="text-[8px] font-bold text-on-surface leading-none">
                                  {day.amount > 999
                                    ? `${(day.amount / 1000).toFixed(1)}k`
                                    : day.amount > 0
                                      ? Math.round(day.amount).toLocaleString()
                                      : '—'}
                                </motion.p>
                              </motion.div>
                            ))}
                          </motion.div>
                        )}
                      </motion.div>
                    ))}
                  </motion.div>
                  <motion.div className="mt-4 pt-4 border-t border-error/10 flex justify-between items-center">
                    <motion.span className="text-[10px] font-black text-error uppercase tracking-widest">
                      Predicted total
                    </motion.span>
                    <motion.span className="text-sm font-black text-on-surface">
                      {formatCurrency(forecast.predicted_next_month ?? 0)}
                    </motion.span>
                  </motion.div>
                  {prevSpend != null && (
                    <motion.p className="text-[10px] text-outline font-bold mt-1 text-right">
                      vs {formatCurrency(prevSpend)} in comparison period
                    </motion.p>
                  )}
                </motion.div>
              )}
            </motion.div>

            <motion.div className="pt-12 mt-auto">
              <motion.div className="flex items-center justify-between mb-4">
                <motion.p className="text-[10px] font-black text-outline uppercase">Forecast accuracy</motion.p>
                <motion.button
                  type="button"
                  onClick={() => fetchForecast({ force: true })}
                  className="p-1 hover:text-primary transition-colors"
                  aria-label="Refresh forecast"
                >
                  <RefreshCcw className="w-3 h-3 text-outline" />
                </motion.button>
              </motion.div>
              <motion.div className="flex flex-col items-center justify-center p-8 bg-surface-container-low rounded-3xl relative overflow-hidden">
                <motion.div className="relative w-24 h-24 flex items-center justify-center">
                  <motion.svg className="w-full h-full -rotate-90">
                    <motion.circle
                      cx="48"
                      cy="48"
                      r="40"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="8"
                      className="text-primary/10"
                    />
                    <motion.circle
                      cx="48"
                      cy="48"
                      r="40"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="8"
                      strokeDasharray="251.2"
                      strokeDashoffset={
                        forecast?.accuracy_pct != null
                          ? 251.2 - (251.2 * forecast.accuracy_pct) / 100
                          : 200
                      }
                      className="text-secondary"
                    />
                  </motion.svg>
                  <motion.span className="absolute text-xl font-black">
                    {forecast?.accuracy_pct != null ? `${forecast.accuracy_pct}%` : '—'}
                  </motion.span>
                </motion.div>
                <motion.p className="text-[10px] font-bold text-outline uppercase tracking-widest mt-6 text-center">
                  {forecast?.model_loaded
                    ? `${forecast.model_name} · nightly-trained per-user model`
                    : 'Models refresh nightly from your transaction database'}
                </motion.p>
              </motion.div>
            </motion.div>
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  );
};
