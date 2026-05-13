import React from 'react';
import { ArrowUpRight, ArrowDownRight, Sparkles } from 'lucide-react';
import { cn, formatCurrency } from '../../lib/utils';

interface SummaryCardsProps {
  data?: {
    total_balance: number;
    monthly_income: number;
    monthly_expenses: number;
    net_savings: number;
    savings_rate: number;
  };
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({ data }) => {
  const stats = [
    { label: 'Total Balance', value: formatCurrency(data?.total_balance || 0), trend: '+0%', up: true, desc: 'Live data' },
    { label: 'Monthly Income', value: `+${formatCurrency(data?.monthly_income || 0)}`, trend: 'Current', up: null, desc: 'This month', color: 'text-secondary' },
    { label: 'Monthly Expenses', value: `-${formatCurrency(data?.monthly_expenses || 0)}`, trend: 'Current', up: false, desc: 'This month', color: 'text-error' },
    { label: 'Net Savings', value: `+${formatCurrency(data?.net_savings || 0)}`, trend: 'Active', up: true, desc: 'Monthly Net' },
    { label: 'Savings Rate', value: `${data?.savings_rate || 0}%`, trend: 'Goal: 60%', up: (data?.savings_rate || 0) >= 60, desc: 'Efficiency', progress: data?.savings_rate || 0 },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
      {stats.map((stat, i) => (
        <div key={i} className="bg-surface-container-lowest p-6 rounded-[32px] soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[160px]">
          <div>
            <p className="text-[10px] text-outline font-black uppercase tracking-[0.15em] mb-3">{stat.label}</p>
            <h3 className={cn(
              "text-2xl font-black font-display tracking-tight",
              stat.color ? stat.color : "text-on-surface"
            )}>
              {stat.value}
            </h3>
          </div>
          
          <div className="mt-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                {stat.up !== null && stat.label !== 'Net Savings' && (
                  stat.up ? <ArrowUpRight className="w-3.5 h-3.5 text-secondary" /> : <ArrowDownRight className="w-3.5 h-3.5 text-error" />
                )}
                {stat.label === 'Net Savings' && <Sparkles className="w-3.5 h-3.5 text-secondary" />}
                <span className={cn(
                  "text-[11px] font-black tracking-tight",
                  stat.up === true ? "text-secondary" : stat.up === false ? "text-error" : "text-on-surface"
                )}>
                  {stat.trend}
                </span>
              </div>
              <span className="text-[10px] text-outline font-bold text-right leading-tight max-w-[60px]">
                {stat.desc}
              </span>
            </div>
            {stat.progress && (
              <div className="w-full bg-surface-container h-1.5 rounded-full mt-3 overflow-hidden">
                <div className="bg-primary h-full transition-all duration-1000" style={{ width: `${stat.progress}%` }}></div>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
