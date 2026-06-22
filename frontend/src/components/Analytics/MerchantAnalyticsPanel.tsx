import React from 'react';
import { formatCurrency } from '../../lib/utils';

interface MerchantAnalyticsPanelProps {
  topMerchants: { name: string; total: number; txn_count: number }[];
  merchantGrowth: {
    name: string;
    current_total: number;
    prior_total: number;
    growth_pct: number;
    growth_display?: string;
    growth_insight?: string;
  }[];
  concentration?: { top_n: number; pct_of_total: number };
  fastestGrowingInsight?: string | Record<string, unknown>;
  concentrationInsight?: string | { top_n?: number; pct_of_total?: number };
  loading?: boolean;
}

function formatConcentrationText(
  insight: MerchantAnalyticsPanelProps['concentrationInsight'],
  concentration?: { top_n: number; pct_of_total: number },
): string | null {
  if (typeof insight === 'string' && insight.trim()) {
    return insight;
  }
  const conc =
    insight && typeof insight === 'object' && 'pct_of_total' in insight
      ? insight
      : concentration;
  if (conc?.pct_of_total && conc.pct_of_total > 0) {
    return `Top ${conc.top_n ?? 5} merchants account for ${conc.pct_of_total}% of total spending.`;
  }
  return null;
}

function formatGrowthBadge(m: {
  growth_pct: number;
  growth_display?: string;
}): string {
  if (m.growth_display) return m.growth_display;
  return m.growth_pct < 0 ? `${m.growth_pct}%` : `+${m.growth_pct}%`;
}

function formatFastestGrowingText(
  insight: MerchantAnalyticsPanelProps['fastestGrowingInsight'],
): string | null {
  if (typeof insight === 'string' && insight.trim()) {
    return insight;
  }
  if (insight && typeof insight === 'object' && 'growth_insight' in insight) {
    const m = insight as { growth_insight?: string };
    if (m.growth_insight) return m.growth_insight;
  }
  if (insight && typeof insight === 'object' && 'name' in insight && 'growth_pct' in insight) {
    const m = insight as {
      name: string;
      growth_pct: number;
      growth_display?: string;
      prior_total?: number;
      current_total?: number;
    };
    const badge = formatGrowthBadge(m);
    if (m.prior_total != null && m.current_total != null) {
      return `${m.name} spending changed ${badge} vs the prior period (${formatCurrency(m.prior_total)} → ${formatCurrency(m.current_total)}).`;
    }
    return `${m.name} is your fastest growing merchant (${badge}).`;
  }
  return null;
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
  const concentrationText = formatConcentrationText(concentrationInsight, concentration);
  const fastestGrowingText = formatFastestGrowingText(fastestGrowingInsight);

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 space-y-8">
      <h3 className="text-lg font-black tracking-tight">Merchant Analytics</h3>

      {concentrationText && (
        <p className="text-sm font-medium text-on-surface/80">{concentrationText}</p>
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
                <div key={m.name} className="space-y-1">
                  <div className="flex justify-between items-center text-xs font-bold gap-3">
                    <span className="truncate">{m.name}</span>
                    <span
                      className={
                        m.growth_pct < 0
                          ? 'text-success bg-success/10 px-2 py-0.5 rounded-full shrink-0'
                          : 'text-error bg-error/10 px-2 py-0.5 rounded-full shrink-0'
                      }
                    >
                      {formatGrowthBadge(m)}
                    </span>
                  </div>
                  <p className="text-[10px] text-outline font-medium">
                    {formatCurrency(m.prior_total)} → {formatCurrency(m.current_total)}
                  </p>
                </div>
              ))
            ) : (
              <p className="text-xs text-outline">No growth data for comparison window.</p>
            )}
          </div>
          {fastestGrowingText && (
            <p className="text-xs text-primary font-medium bg-primary/5 rounded-xl px-3 py-2 mt-4">
              {fastestGrowingText}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
