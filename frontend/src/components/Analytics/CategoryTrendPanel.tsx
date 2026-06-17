import React, { useMemo, useState } from 'react';
import { ChevronDown, Lightbulb } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { cn, formatCurrency } from '../../lib/utils';

const CATEGORY_COLORS: Record<string, string> = {
  'Food & Drinks': '#FF6B6B',
  Shopping: '#4D96FF',
  Housing: '#6BCB77',
  Transportation: '#FFD93D',
  Vehicle: '#FF9F43',
  'Life & Entertainment': '#A55EEF',
  'Communication/PC': '#48DBFB',
  'Financial Expense': '#546E7A',
  Investments: '#10AC84',
  Others: '#95A5A6',
};

const FALLBACK_COLORS = ['#FF6B6B', '#4D96FF', '#6BCB77', '#FFD93D', '#A55EEF'];

function categoryColor(name: string, index: number): string {
  return CATEGORY_COLORS[name] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

interface CategoryTrend {
  category: string;
  total: number;
  monthly_evolution: { month: string; label: string; amount: number }[];
  consecutive_growth_months?: number;
  mom_change_pct?: number | null;
}

interface CategoryAnalysisCard {
  category: string;
  headline: string;
  analysis: string;
  suggestion: string;
}

interface CategoryTrendPanelProps {
  trends: CategoryTrend[];
  insights?: Record<string, string>;
  categoryAnalysis?: CategoryAnalysisCard[];
  loading?: boolean;
  aiLoading?: boolean;
}

function buildTrendExplanation(
  trend: CategoryTrend,
  insight?: string,
  analysis?: CategoryAnalysisCard,
): string {
  const parts: string[] = [];
  const activeMonths = trend.monthly_evolution.filter((m) => m.amount > 0);
  const growth = trend.consecutive_growth_months ?? 0;
  const mom = trend.mom_change_pct;

  parts.push(
    `${trend.category} accounts for ${formatCurrency(trend.total)} in the selected period.`,
  );

  if (activeMonths.length >= 2) {
    const first = activeMonths[0];
    const last = activeMonths[activeMonths.length - 1];
    const delta = last.amount - first.amount;
    const direction = delta > 0 ? 'increased' : delta < 0 ? 'decreased' : 'held steady';
    parts.push(
      `Monthly spend ${direction} from ${formatCurrency(first.amount)} in ${first.label} to ${formatCurrency(last.amount)} in ${last.label}.`,
    );
  } else if (activeMonths.length === 1) {
    parts.push(
      `Spend was recorded in ${activeMonths[0].label} only (${formatCurrency(activeMonths[0].amount)}); add more history for a clearer trend.`,
    );
  }

  if (growth >= 2) {
    parts.push(
      `Spending has risen for ${growth} consecutive months — a sustained upward pattern that may compound if left unchecked.`,
    );
  } else if (mom != null && mom > 10) {
    parts.push(
      `The latest month is up ${mom}% versus the prior month, indicating accelerating spend in this category.`,
    );
  } else if (mom != null && mom < -10) {
    parts.push(
      `The latest month is down ${Math.abs(mom)}% versus the prior month, showing a meaningful pullback.`,
    );
  } else if (mom != null) {
    parts.push(
      `Month-over-month change is modest (${mom > 0 ? '+' : ''}${mom}%), suggesting relatively stable spending behavior.`,
    );
  } else {
    parts.push('Not enough monthly history yet to compute a month-over-month comparison.');
  }

  if (insight && !analysis?.analysis?.includes(insight)) {
    parts.push(insight);
  }
  if (analysis?.analysis) {
    parts.push(analysis.analysis);
  }

  return parts.join(' ');
}

const CategorySparkline: React.FC<{
  data: { label: string; amount: number }[];
  color: string;
}> = ({ data, color }) => {
  const hasSpend = data.some((d) => d.amount > 0);
  if (!hasSpend) {
    return <div className="w-20 h-8 flex items-center justify-center text-[9px] text-outline">—</div>;
  }
  return (
    <div className="w-20 h-8 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, left: 2, bottom: 4 }}>
          <Line
            type="monotone"
            dataKey="amount"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

const CategoryTrendChart: React.FC<{
  data: { label: string; amount: number; month: string }[];
  color: string;
}> = ({ data, color }) => {
  const hasSpend = data.some((d) => d.amount > 0);
  if (!hasSpend) {
    return (
      <p className="text-xs text-outline py-4 text-center">No monthly spend recorded for this category.</p>
    );
  }
  return (
    <div className="h-[140px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" opacity={0.45} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: '#64748B', fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis hide />
          <Tooltip
            formatter={(value: number) => formatCurrency(value)}
            labelFormatter={(label: string) => label}
            contentStyle={{
              borderRadius: '12px',
              border: 'none',
              fontSize: '11px',
              boxShadow: '0 4px 12px rgb(0 0 0 / 0.08)',
            }}
          />
          <Line
            type="monotone"
            dataKey="amount"
            stroke={color}
            strokeWidth={2.5}
            dot={{ r: 3, fill: color, stroke: '#fff', strokeWidth: 1.5 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export const CategoryTrendPanel: React.FC<CategoryTrendPanelProps> = ({
  trends,
  insights = {},
  categoryAnalysis = [],
  loading,
  aiLoading,
}) => {
  const [open, setOpen] = useState<string | null>(trends[0]?.category ?? null);
  const top = useMemo(() => trends.slice(0, 5), [trends]);

  const analysisByCategory = useMemo(() => {
    const map: Record<string, CategoryAnalysisCard> = {};
    for (const row of categoryAnalysis) {
      if (row.category) map[row.category] = row;
    }
    return map;
  }, [categoryAnalysis]);

  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-48" />
    );
  }

  if (!top.length) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
        <h3 className="text-lg font-black mb-2 tracking-tight">Category Deep Dive</h3>
        <p className="text-sm text-outline">No category spending in this period.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
      <div className="flex items-center gap-2 mb-2">
        <h3 className="text-lg font-black tracking-tight">Category Deep Dive</h3>
        {aiLoading && (
          <span className="inline-block w-3.5 h-3.5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        )}
      </div>
      <p className="text-xs text-outline font-medium mb-6 leading-relaxed">
        Top categories by spend with monthly trajectory, trend context, and actionable notes.
      </p>
      <div className="space-y-3">
        {top.map((t, index) => {
          const isOpen = open === t.category;
          const color = categoryColor(t.category, index);
          const chartData = t.monthly_evolution.map((m) => ({
            month: m.month,
            label: m.label,
            amount: m.amount,
          }));
          const analysis = analysisByCategory[t.category];
          const insight = insights[t.category];
          const trendExplanation = buildTrendExplanation(t, insight, analysis);
          const suggestion =
            analysis?.suggestion ||
            (t.consecutive_growth_months && t.consecutive_growth_months >= 2
              ? `Set a weekly cap for ${t.category} and review merchants driving the streak.`
              : `Track ${t.category} weekly against your budget.`);

          return (
            <div key={t.category} className="border border-outline-variant/20 rounded-2xl overflow-hidden">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : t.category)}
                className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-surface-container-low/50 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-black text-on-surface truncate">
                    {analysis?.headline || t.category}
                  </p>
                  <p className="text-xs text-outline mt-0.5">{formatCurrency(t.total)} total</p>
                </div>
                <CategorySparkline data={chartData} color={color} />
                <div className="flex items-center gap-3 shrink-0">
                  {t.mom_change_pct != null && (
                    <span
                      className={cn(
                        'text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap',
                        t.mom_change_pct > 0 ? 'bg-error/10 text-error' : 'bg-success/10 text-success',
                      )}
                    >
                      {t.mom_change_pct > 0 ? '+' : ''}
                      {t.mom_change_pct}% MoM
                    </span>
                  )}
                  {(t.consecutive_growth_months ?? 0) >= 2 && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-error/10 text-error whitespace-nowrap">
                      {t.consecutive_growth_months}mo streak
                    </span>
                  )}
                  <ChevronDown
                    className={cn('w-4 h-4 text-outline transition-transform', isOpen && 'rotate-180')}
                  />
                </div>
              </button>

              {isOpen && (
                <div className="px-5 pb-4 space-y-4 border-t border-outline-variant/10 pt-4">
                  <CategoryTrendChart data={chartData} color={color} />
                  <div className="space-y-2">
                    <p className="text-[10px] font-black text-outline uppercase tracking-widest">
                      Trend observed
                    </p>
                    <p className="text-xs font-medium text-on-surface/85 leading-relaxed">
                      {trendExplanation}
                    </p>
                  </div>
                  <div className="flex gap-2.5 items-start bg-primary/5 rounded-xl px-3 py-2.5">
                    <Lightbulb className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                    <p className="text-xs text-primary font-medium leading-relaxed">{suggestion}</p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
