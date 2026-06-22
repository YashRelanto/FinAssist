import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { cn, formatCurrency } from '../../lib/utils';

const heatmapColors = [
  'bg-blue-50',
  'bg-blue-100',
  'bg-blue-200',
  'bg-blue-300',
  'bg-blue-500',
  'bg-blue-700',
];

interface WeekdayVsWeekend {
  weekday_total: number;
  weekend_total: number;
  weekday_avg_per_day?: number;
  weekend_avg_per_day?: number;
  weekend_multiplier?: number;
}

interface SpendingBehaviorPanelProps {
  weekdayVsWeekend?: WeekdayVsWeekend;
  dayOfWeekHeatmap?: { day: string; amount: number; intensity: number }[];
  transactionFrequency?: {
    avg_per_day: number;
    total_days_with_txns: number;
    total_txns: number;
  };
  weekendInsight?: string | string[];
  timeOfDayInsight?: string | string[];
  loading?: boolean;
}

export const SpendingBehaviorPanel: React.FC<SpendingBehaviorPanelProps> = ({
  weekdayVsWeekend,
  dayOfWeekHeatmap = [],
  transactionFrequency,
  weekendInsight,
  timeOfDayInsight,
  loading,
}) => {
  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-64" />
    );
  }

  const weekdayAvg =
    weekdayVsWeekend?.weekday_avg_per_day ??
    (weekdayVsWeekend?.weekday_total != null ? weekdayVsWeekend.weekday_total / 5 : 0);
  const weekendAvg =
    weekdayVsWeekend?.weekend_avg_per_day ??
    (weekdayVsWeekend?.weekend_total != null ? weekdayVsWeekend.weekend_total / 2 : 0);

  const barData =
    weekdayVsWeekend && (weekdayAvg > 0 || weekendAvg > 0)
      ? [
          { name: 'Weekday', total: weekdayAvg },
          { name: 'Weekend', total: weekendAvg },
        ]
      : [];

  const orderedHeatmap = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => {
    const entry = dayOfWeekHeatmap.find((d) => d.day === day);
    return entry ?? { day, amount: 0, intensity: 0 };
  });

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 space-y-8">
      <h3 className="text-lg font-black tracking-tight">Spending Behavior</h3>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mb-1">
            Weekday vs Weekend
          </p>
          <p className="text-[10px] text-outline/70 mb-4">Average spend per calendar day in period</p>
          <div className="h-[180px]">
            {barData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" opacity={0.5} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                  <YAxis hide />
                  <Tooltip formatter={(v: number) => formatCurrency(v)} />
                  <Bar dataKey="total" fill="#004ac6" radius={[8, 8, 0, 0]} barSize={48} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-outline">No behavior data.</p>
            )}
          </div>
          {weekendInsight && (
            <div className="text-xs text-primary font-medium bg-primary/5 rounded-xl px-3 py-2 mt-3">
              {Array.isArray(weekendInsight) ? (
                <ul className="list-disc pl-4 space-y-1">
                  {weekendInsight.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              ) : (
                <p>{weekendInsight}</p>
              )}
            </div>
          )}
        </div>

        <div>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mb-1">
            Spending by Day of Week
          </p>
          <p className="text-[10px] text-outline/70 mb-4">Total spend on each weekday (Mon–Sun)</p>
          <div className="grid grid-cols-7 gap-2">
            {orderedHeatmap.map((d) => (
              <div key={d.day} className="text-center space-y-1">
                <div
                  title={`${d.day}: ${formatCurrency(d.amount)}`}
                  className={cn(
                    'aspect-square rounded-lg border border-outline-variant/10',
                    d.amount > 0
                      ? heatmapColors[d.intensity] ?? heatmapColors[1]
                      : 'bg-surface-container-low/80',
                  )}
                />
                <span className="text-[9px] font-bold text-outline">{d.day}</span>
              </div>
            ))}
          </div>
          {timeOfDayInsight && (
            <div className="text-xs text-primary font-medium bg-primary/5 rounded-xl px-3 py-2 mt-3">
              {Array.isArray(timeOfDayInsight) ? (
                <ul className="list-disc pl-4 space-y-1">
                  {timeOfDayInsight.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              ) : (
                <p>{timeOfDayInsight}</p>
              )}
            </div>
          )}
        </div>
      </div>

      {transactionFrequency && transactionFrequency.avg_per_day > 0 && (
        <div className="border-t border-outline-variant/20 pt-6">
          <p className="text-sm font-black">
            You average {Math.round(transactionFrequency.avg_per_day)} transactions per active day (
            {transactionFrequency.total_txns} across {transactionFrequency.total_days_with_txns} days).
          </p>
        </div>
      )}
    </div>
  );
};
