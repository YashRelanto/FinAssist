import React from 'react';
import { formatCurrency } from '../../lib/utils';

interface MerchantAnalyticsPanelProps {
  topMerchants: { name: string; total: number; txn_count: number }[];
  merchantGrowth: { name: string; current_total: number; prior_total: number; growth_pct: number }[];
  concentration?: { top_n: number; pct_of_total: number };
  fastestGrowingInsight?: string;
  concentrationInsight?: string;
  loading?: boolean;
}

export const MerchantAnalyticsPanel: React.FC<MerchantAnalyticsPanelProps> = ({
  topMerchants,
  merchantGrowth,
  concentration,
  fastestGrowingInsight,
  concentrationInsight,
  loading,
}) => {
  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-64" />
    );
  }

  const maxTotal = topMerchants[0]?.total ?? 1;

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 space-y-8">
      <h3 className="text-lg font-black tracking-tight">Merchant Analytics</h3>

      {concentration && concentration.pct_of_total > 0 && (
        <p className="text-sm font-medium text-on-surface/80">
          {concentrationInsight ||
            `Top ${concentration.top_n} merchants account for ${concentration.pct_of_total}% of total spending.`}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mb-4">Top Merchants</p>
          <div className="space-y-4">
            {topMerchants.length ? (
              topMerchants.map((m, i) => (
                <div key={m.name} className="space-y-1.5">
                  <div className="flex justify-between text-xs font-bold">
                    <span>
                      {i + 1}. {m.name}
                    </span>
                    <span>{formatCurrency(m.total)}</span>
                  </div>
                  <div className="h-1.5 bg-surface-container rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full"
                      style={{ width: `${(m.total / maxTotal) * 100}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-outline">{m.txn_count} transactions</p>
                </div>
              ))
            ) : (
              <p className="text-xs text-outline">No merchant data.</p>
            )}
          </div>
        </div>

        <div>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mb-4">Merchant Growth</p>
          <div className="space-y-3">
            {merchantGrowth.length ? (
              merchantGrowth.slice(0, 6).map((m) => (
                <div key={m.name} className="flex justify-between items-center text-xs font-bold">
                  <span>{m.name}</span>
                  <span className="text-error bg-error/10 px-2 py-0.5 rounded-full">
                    +{m.growth_pct}%
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-outline">No growth data for comparison window.</p>
            )}
          </div>
          {fastestGrowingInsight && (
            <p className="text-xs text-primary font-medium bg-primary/5 rounded-xl px-3 py-2 mt-4">
              {fastestGrowingInsight}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
