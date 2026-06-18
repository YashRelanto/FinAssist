import React, { useMemo, useRef, useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { formatCurrency } from '../../lib/utils';
import { useAppContext } from '../../context/AppContext';

interface DashboardHeroProps {
  onRefresh: () => void;
  loading?: boolean;
}

export const DashboardHero: React.FC<DashboardHeroProps> = ({ onRefresh, loading }) => (
  <div className="mb-12 flex flex-col md:flex-row justify-between items-end gap-6 border-b border-lumio-line pb-8">
    <div>
      <h1 className="font-display text-4xl md:text-5xl text-lumio-text tracking-tighter mb-2 font-light">
        Financial Overview
      </h1>
      <p className="text-lumio-muted">Your intelligent foundation for asset management.</p>
    </div>
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        className="w-8 h-8 rounded-full border border-lumio-line flex items-center justify-center hover:bg-lumio-black hover:text-white transition-colors disabled:opacity-50"
      >
        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
      </button>
    </div>
  </div>
);

interface MonthlySpendTrendProps {
  chartData?: Array<{
    name?: string;
    month?: string;
    date?: string;
    expense?: number;
    actual_expense?: number | null;
    predicted_expense?: number | null;
    is_forecast?: boolean;
  }>;
  totalExpense?: number;
  predictedNextMonth?: number | null;
  predictedMonthLabel?: string | null;
  changePct?: number | null;
  analysisPeriod: string;
  chartGranularity?: 'daily' | 'monthly';
  loading?: boolean;
  onPeriodChange: (period: '1m' | '3m' | '6m' | '1y' | 'all') => void;
}

export const MonthlySpendTrend: React.FC<MonthlySpendTrendProps> = ({
  chartData = [],
  totalExpense = 0,
  predictedNextMonth,
  predictedMonthLabel,
  changePct,
  analysisPeriod,
  chartGranularity = 'monthly',
  loading = false,
  onPeriodChange,
}) => {
  const { currentPage } = useAppContext();
  const isChartVisible = currentPage === 'dashboard';
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [chartReady, setChartReady] = useState(false);
  const isDaily = chartGranularity === 'daily' || analysisPeriod === '1m';

  const points = useMemo(() => {
    let mapped = chartData.map((item) => ({
      label: item.name || item.month || '',
      date: item.date,
      actual:
        item.actual_expense != null
          ? item.actual_expense
          : item.is_forecast
            ? null
            : (item.expense ?? 0),
      predicted: item.predicted_expense ?? null,
      isForecast: Boolean(item.is_forecast),
    }));

    const forecastIdx = mapped.findIndex((p) => p.isForecast);
    if (forecastIdx > 0) {
      const bridge = mapped[forecastIdx - 1];
      if (bridge.predicted == null && bridge.actual != null) {
        mapped = mapped.map((p, i) =>
          i === forecastIdx - 1 ? { ...p, predicted: p.actual } : p,
        );
      }
    } else if (predictedNextMonth && predictedNextMonth > 0 && mapped.length > 0) {
      const lastIdx = mapped.length - 1;
      mapped = mapped.map((p, i) =>
        i === lastIdx ? { ...p, predicted: p.actual ?? p.predicted } : p,
      );
      const forecastLabel = (predictedMonthLabel ?? 'Next').split(' ')[0].slice(0, 3);
      mapped.push({
        label: forecastLabel,
        date: undefined,
        actual: null,
        predicted: predictedNextMonth,
        isForecast: true,
      });
    }

    return mapped;
  }, [chartData, predictedNextMonth, predictedMonthLabel]);

  useEffect(() => {
    if (!isChartVisible) {
      setChartReady(false);
      return;
    }
    const el = chartContainerRef.current;
    if (!el) return;
    const check = () => {
      const { width, height } = el.getBoundingClientRect();
      setChartReady(width > 0 && height > 0);
    };
    check();
    const obs = new ResizeObserver(check);
    obs.observe(el);
    return () => obs.disconnect();
  }, [isChartVisible, chartData.length, points.length]);

  const hasSpend = points.some((p) => (p.actual ?? 0) > 0 || (p.predicted ?? 0) > 0);
  const periods: Array<{ id: '1m' | '3m' | '6m' | '1y' | 'all'; label: string }> = [
    { id: '1m', label: '1M' },
    { id: '3m', label: '3M' },
    { id: '6m', label: '6M' },
    { id: '1y', label: 'YTD' },
    { id: 'all', label: 'All' },
  ];

  const formatYAxis = (value: number) => {
    if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
    if (value >= 1000) return `₹${(value / 1000).toFixed(0)}k`;
    return `₹${value}`;
  };

  return (
    <div className="bento-card flex flex-col min-h-[400px]">
      <div className="flex flex-col sm:flex-row justify-between items-start mb-6 gap-4">
        <div>
          <h2 className="font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted mb-2">
            {isDaily ? 'Daily Spend Trend' : 'Monthly Spend Trend'}
          </h2>
          <div className="flex items-baseline gap-4 flex-wrap">
            <span className="font-display text-4xl md:text-5xl font-bold text-lumio-text tracking-tight leading-none">
              {formatCurrency(totalExpense)}
            </span>
            {changePct !== null && changePct !== undefined && (
              <span className="chip-success font-label flex items-center gap-1 text-xs">
                <span className="material-symbols-outlined text-[14px]">
                  {changePct <= 0 ? 'arrow_downward' : 'arrow_upward'}
                </span>
                {Math.abs(changePct).toFixed(0)}% vs prior
              </span>
            )}
            {predictedNextMonth != null && predictedNextMonth > 0 && (
              <span className="text-xs text-lumio-muted font-medium">
                Predicted {predictedMonthLabel ?? 'next month'}: {formatCurrency(predictedNextMonth)}
              </span>
            )}
          </div>
        </div>
        <div className="flex bg-white/50 backdrop-blur-sm rounded-full p-1 border border-white shadow-sm shrink-0">
          {periods.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={loading}
              onClick={() => onPeriodChange(p.id)}
              className={`px-3 sm:px-4 py-1.5 rounded-full text-xs font-bold transition-colors disabled:opacity-50 ${
                analysisPeriod === p.id ? 'bg-lumio-black text-white shadow-md' : 'text-lumio-muted hover:bg-white'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {points.length === 0 ? (
        <p className="text-sm text-lumio-muted flex-1 flex items-center justify-center min-h-[220px]">
          No expense data for this period.
        </p>
      ) : (
        <div className="flex-1 w-full min-h-[240px] relative" ref={chartContainerRef}>
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/40 backdrop-blur-[1px] rounded-xl">
              <RefreshCw className="w-6 h-6 animate-spin text-lumio-muted" />
            </div>
          )}
          {isChartVisible && chartReady ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={points} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: '#6b7280' }}
                tickLine={false}
                axisLine={{ stroke: 'rgba(0,0,0,0.08)' }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#6b7280' }}
                tickLine={false}
                axisLine={false}
                width={52}
                tickFormatter={formatYAxis}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const row = payload[0].payload as {
                    label: string;
                    date?: string;
                    actual: number | null;
                    predicted: number | null;
                    isForecast?: boolean;
                  };
                  const displayLabel = row.date
                    ? new Date(`${row.date}T00:00:00`).toLocaleDateString('en', {
                        month: 'short',
                        day: 'numeric',
                      })
                    : row.label;
                  const value = row.isForecast ? row.predicted : row.actual;
                  return (
                    <div className="bg-lumio-black text-white font-label text-[11px] py-2 px-3 rounded-xl shadow-xl">
                      <p className="text-white/70 uppercase tracking-wider mb-1">{displayLabel}</p>
                      <p className="font-bold">
                        {value != null ? formatCurrency(value) : '—'}
                        {row.isForecast ? ' (predicted)' : ''}
                      </p>
                    </div>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#0a0a0a"
                strokeWidth={2.5}
                dot={
                  isDaily
                    ? false
                    : {
                        r: 4,
                        fill: '#0a0a0a',
                        stroke: '#fff',
                        strokeWidth: 2,
                      }
                }
                activeDot={{ r: 6, fill: '#0a0a0a' }}
                connectNulls={false}
              />
              <Line
                type="monotone"
                dataKey="predicted"
                stroke="#64748b"
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={(props) => {
                  const { cx, cy, payload } = props;
                  if (cx == null || cy == null || payload?.predicted == null) return null;
                  return (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={payload.isForecast ? 5 : 3}
                      fill={payload.isForecast ? '#64748b' : '#fff'}
                      stroke="#64748b"
                      strokeWidth={2}
                    />
                  );
                }}
                activeDot={{ r: 6, fill: '#64748b' }}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
          ) : (
            <div className="h-[240px] flex items-center justify-center">
              {!isChartVisible ? null : <RefreshCw className="w-5 h-5 animate-spin text-lumio-muted" />}
            </div>
          )}
          <div className="flex justify-center gap-6 mt-3 text-[10px] font-bold uppercase tracking-widest text-lumio-muted">
            <span className="flex items-center gap-2">
              <span className="w-6 h-0.5 bg-lumio-black rounded" /> Actual
            </span>
            <span className="flex items-center gap-2">
              <span className="w-6 h-0.5 border-t-2 border-dashed border-lumio-muted rounded" /> Predicted
            </span>
          </div>
          {!hasSpend && (
            <p className="text-center text-xs text-lumio-muted mt-2">No spending recorded in this window yet.</p>
          )}
        </div>
      )}
    </div>
  );
};

interface FinancialHealthCardProps {
  health?: {
    score?: number;
    label?: string;
    savings_rate?: number;
    debt_to_income_pct?: number;
    net_savings?: number;
    emergency_buffer_months?: number | null;
    avg_credit_utilization_pct?: number | null;
  } | null;
  summary?: {
    savings_rate?: number;
    net_savings?: number;
    monthly_income?: number;
    fixed_expense?: number;
  };
  insights?: {
    analysis?: string;
    recommendations?: string[];
    pillar_insights?: Array<{ pillar: string; status: string; insight: string }>;
    source?: string;
  } | null;
  insightsLlmLoading?: boolean;
}

export const FinancialHealthCard: React.FC<FinancialHealthCardProps> = ({
  health,
  summary,
  insights,
  insightsLlmLoading,
}) => {
  const savingsRate = health?.savings_rate ?? summary?.savings_rate ?? 0;
  const netSavings = health?.net_savings ?? summary?.net_savings ?? 0;
  const score = health?.score ?? 0;
  const label = health?.label ?? 'Needs Work';
  const debtToIncome = health?.debt_to_income_pct ?? 0;
  const emergencyMonths = health?.emergency_buffer_months;
  const creditUtil = health?.avg_credit_utilization_pct;
  const circumference = 289;
  const offset = circumference - (score / 100) * circumference;

  const rows = [
    { label: 'Savings Rate', value: `${savingsRate}%` },
    { label: 'Debt-to-Income', value: `${debtToIncome}%` },
    { label: 'Net Savings', value: formatCurrency(netSavings) },
    {
      label: 'Emergency Buffer',
      value:
        emergencyMonths == null || emergencyMonths === undefined
          ? '—'
          : `${emergencyMonths} mo`,
    },
  ];
  if (creditUtil != null) {
    rows.push({ label: 'Credit Utilization', value: `${creditUtil}%` });
  }

  return (
    <div className="bento-card relative overflow-hidden flex flex-col min-h-[400px]">
      <div className="absolute -top-20 -right-20 w-64 h-64 bg-emerald-tint rounded-full opacity-30 pointer-events-none blur-3xl" />
      <h2 className="font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted mb-8 border-b border-lumio-line pb-4 relative z-10">
        Financial Health
      </h2>
      <div className="flex flex-col items-center py-4 mb-8 relative z-10">
        <div className="w-40 h-40 rounded-full border border-lumio-line flex items-center justify-center relative bg-white/40 shadow-inner">
          <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(0,0,0,0.05)" strokeWidth="4" />
            <circle
              cx="50"
              cy="50"
              r="46"
              fill="none"
              stroke="#10B981"
              strokeWidth="4"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
            />
          </svg>
          <div className="text-center">
            <span className="block font-display text-5xl font-bold text-lumio-text leading-none tracking-tighter">{score}</span>
            <span className="font-label text-[10px] text-emerald-solid uppercase tracking-widest mt-1 block">{label}</span>
          </div>
        </div>
      </div>
      <div className="flex-1 flex flex-col gap-4 relative z-10 text-sm">
        {rows.map((row) => (
          <div key={row.label} className="flex justify-between items-center border-b border-lumio-line/50 pb-3">
            <span className="text-lumio-muted">{row.label}</span>
            <span className="font-medium">{row.value}</span>
          </div>
        ))}
      </div>

      {(insightsLlmLoading || insights?.analysis || (insights?.recommendations?.length ?? 0) > 0) && (
        <div className="mt-6 pt-6 border-t border-lumio-line/60 relative z-10 space-y-4">
          <div className="flex items-center gap-2">
            <h3 className="font-label text-[10px] font-semibold uppercase tracking-widest text-lumio-muted">
              AI Analysis
            </h3>
            {insightsLlmLoading && (
              <span className="inline-block w-3 h-3 border-2 border-emerald-solid/30 border-t-emerald-solid rounded-full animate-spin" />
            )}
          </div>

          {insights?.analysis ? (
            <p className="text-xs text-lumio-text/85 leading-relaxed">{insights.analysis}</p>
          ) : insightsLlmLoading ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-3 bg-lumio-line/40 rounded w-full" />
              <div className="h-3 bg-lumio-line/40 rounded w-5/6" />
            </div>
          ) : null}

          {(insights?.recommendations?.length ?? 0) > 0 && (
            <div>
              <p className="font-label text-[10px] font-semibold uppercase tracking-widest text-lumio-muted mb-2">
                Recommendations
              </p>
              <ul className="space-y-2">
                {insights!.recommendations!.map((rec, i) => (
                  <li key={i} className="text-xs text-lumio-text/80 flex gap-2 leading-relaxed">
                    <span className="text-emerald-solid shrink-0">•</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

interface AnomalyItem {
  merchant: string;
  amount: number;
  pct_above_avg?: number;
  pctAboveAvg?: number;
}

interface AnomaliesCardProps {
  anomalies: AnomalyItem[];
}

export const AnomaliesCard: React.FC<AnomaliesCardProps> = ({ anomalies }) => {
  if (anomalies.length === 0) return null;

  return (
    <div className="bento-card border border-error/20 bg-error-container/10">
      <div className="flex justify-between items-center mb-6 border-b border-error/10 pb-4">
        <h3 className="font-label text-[12px] font-semibold uppercase tracking-widest text-error flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">warning</span>
          Anomalies Detected
        </h3>
      </div>
      <div className="flex flex-col gap-3">
        {anomalies.slice(0, 3).map((a) => {
          const pctAbove = a.pct_above_avg ?? a.pctAboveAvg ?? 0;
          return (
          <div
            key={`${a.merchant}-${a.amount}`}
            className="bg-white/60 backdrop-blur-md border border-error/20 rounded-2xl p-4 flex justify-between items-center shadow-sm"
          >
            <div>
              <p className="font-medium text-lumio-text">{a.merchant}</p>
              <p className="font-label text-[10px] text-error uppercase tracking-wider mt-1">
                {pctAbove}% higher than average
              </p>
            </div>
            <span className="font-bold text-error text-lg">{formatCurrency(a.amount)}</span>
          </div>
        );
        })}
      </div>
    </div>
  );
};
