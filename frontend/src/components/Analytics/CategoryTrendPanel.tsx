import React, { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
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

interface CategoryTrendPanelProps {
  trends: CategoryTrend[];
  insights?: Record<string, string>;
  loading?: boolean;
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
  loading,
}) => {
  const [open, setOpen] = useState<string | null>(trends[0]?.category ?? null);
  const top = useMemo(() => trends.slice(0, 5), [trends]);

  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-48" />
    );
  }

  if (!top.length) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
        <h3 className="text-lg font-black mb-2 tracking-tight">Category Trend Analysis</h3>
        <p className="text-sm text-outline">No category spending in this period.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
      <h3 className="text-lg font-black mb-6 tracking-tight">Category Trend Analysis</h3>
      <div className="space-y-3">
        {top.map((t, index) => {
          const isOpen = open === t.category;
          const color = categoryColor(t.category, index);
          const chartData = t.monthly_evolution.map((m) => ({
            month: m.month,
            label: m.label,
            amount: m.amount,
          }));
          const evolution = t.monthly_evolution
            .filter((m) => m.amount > 0)
            .map((m) => `${m.label} ${formatCurrency(m.amount)}`)
            .join(' · ');

          return (
            <div key={t.category} className="border border-outline-variant/20 rounded-2xl overflow-hidden">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : t.category)}
                className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-surface-container-low/50 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-black text-on-surface truncate">{t.category}</p>
                  <p className="text-xs text-outline mt-0.5">{formatCurrency(t.total)} total</p>
                </div>
                <CategorySparkline data={chartData} color={color} />
                <div className="flex items-center gap-3 shrink-0">
                  {t.mom_change_pct != null && (
                    <span
                      className={cn(
                        'text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap',
                        t.mom_change_pct > 0 ? 'bg-error/10 text-error' : 'bg-secondary/10 text-secondary',
                      )}
                    >
                      {t.mom_change_pct > 0 ? '+' : ''}
                      {t.mom_change_pct}% MoM
                    </span>
                  )}
                  <ChevronDown
                    className={cn('w-4 h-4 text-outline transition-transform', isOpen && 'rotate-180')}
                  />
                </div>
              </button>

              {isOpen && (
                <div className="px-5 pb-4 space-y-3 border-t border-outline-variant/10 pt-3">
                  <CategoryTrendChart data={chartData} color={color} />
                  {evolution && (
                    <p className="text-xs font-medium text-on-surface/80 leading-relaxed">{evolution}</p>
                  )}
                  {insights[t.category] && (
                    <p className="text-xs text-primary font-medium bg-primary/5 rounded-xl px-3 py-2">
                      {insights[t.category]}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
