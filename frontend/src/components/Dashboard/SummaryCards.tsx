import React from 'react';
import { ArrowUpRight, ArrowDownRight, Sparkles } from 'lucide-react';
import { cn, formatCurrency } from '../../lib/utils';

interface SummaryCardsProps {
  data?: {
    fixed_income: number;
    fixed_expense?: number;
    net_inflow?: number;
    net_outflow?: number;
    net_savings: number;
    savings_rate: number;
  };
  periodLabel?: string;
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({ data, periodLabel }) => {
  const periodHint = periodLabel ?? 'Selected period';
  const netSavings = data?.net_savings ?? 0;
  const savingsRate = data?.savings_rate ?? 0;

  const stats = [
    {
      label: 'Fixed Income',
      value: `+${formatCurrency(data?.fixed_income || 0)}`,
      trend: periodHint,
      up: null,
      desc: 'From profile',
      color: 'text-success',
    },
    {
      label: 'Fixed Expense',
      value: `-${formatCurrency(data?.fixed_expense || 0)}`,
      trend: periodHint,
      up: false as boolean | null,
      desc: 'Rent + EMI',
      color: 'text-error',
    },
    {
      label: 'Net Inflow',
      value: `+${formatCurrency(data?.net_inflow || 0)}`,
      trend: periodHint,
      up: true as boolean | null,
      desc: 'In period',
      color: 'text-success',
    },
    {
      label: 'Net Outflow',
      value: `-${formatCurrency(data?.net_outflow || 0)}`,
      trend: periodHint,
      up: false as boolean | null,
      desc: 'Outflows in period',
      color: 'text-error',
    },
    {
      label: 'Net Savings',
      value: `${netSavings >= 0 ? '+' : ''}${formatCurrency(netSavings)}`,
      trend: netSavings >= 0 ? 'Surplus' : 'Deficit',
      up: netSavings >= 0,
      desc: 'In period',
      color: netSavings >= 0 ? 'text-success' : 'text-error',
    },
    {
      label: 'Savings Rate',
      value: `${savingsRate}%`,
      trend: 'Goal: 60%',
      up: savingsRate >= 60,
      desc: 'Of income',
      progress: Math.min(Math.max(savingsRate, 0), 100),
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-6 gap-6">
      {stats.map((stat, i) => (
        <div
          key={i}
          className="bg-surface-container-lowest p-6 rounded-[32px] soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[160px]"
        >
          <div>
            <p className="text-[10px] text-outline font-black uppercase tracking-[0.15em] mb-3">
              {stat.label}
            </p>
            <h3
              className={cn(
                'text-2xl font-black font-display tracking-tight',
                stat.color ? stat.color : 'text-on-surface',
              )}
            >
              {stat.value}
            </h3>
          </div>

          <div className="mt-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                {stat.up !== null && stat.label !== 'Net Savings' && (
                  stat.up ? (
                    <ArrowUpRight className="w-3.5 h-3.5 text-success" />
                  ) : (
                    <ArrowDownRight className="w-3.5 h-3.5 text-error" />
                  )
                )}
                {stat.label === 'Net Savings' && (
                  <Sparkles
                    className={cn(
                      'w-3.5 h-3.5',
                      netSavings >= 0 ? 'text-success' : 'text-error',
                    )}
                  />
                )}
                <span
                  className={cn(
                    'text-[11px] font-black tracking-tight',
                    stat.up === true
                      ? 'text-success'
                      : stat.up === false
                        ? 'text-error'
                        : 'text-on-surface',
                  )}
                >
                  {stat.trend}
                </span>
              </div>
              <span className="text-[10px] text-outline font-bold text-right leading-tight max-w-[60px]">
                {stat.desc}
              </span>
            </div>
            {stat.progress !== undefined && (
              <div className="w-full bg-surface-container h-1.5 rounded-full mt-3 overflow-hidden">
                <div
                  className="bg-primary h-full transition-all duration-1000"
                  style={{ width: `${stat.progress}%` }}
                />
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
