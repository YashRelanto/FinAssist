import React, { useEffect, useState } from 'react';
import { AlertTriangle, CreditCard, Sparkles, RefreshCw } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { activeUserId } from '../../lib/activeUserId';
import { apiFetch } from '../../lib/api';

type CreditAlert = {
  account: string;
  borrowed?: number;
  credit_limit?: number;
  utilization_pct?: number;
  severity?: string;
  message: string;
};

type AccountSpendingInsight = {
  account: string;
  majority_category: string;
  analysis: string;
};

type HubAnalysis = {
  month?: string;
  credit_card_alerts?: CreditAlert[];
  account_spending?: AccountSpendingInsight[];
  summary?: string;
  has_accounts?: boolean;
  transaction_count?: number;
};

interface QuickActionCardProps {
  hasAccounts?: boolean;
  refreshKey?: string | number;
}

export const QuickActionCard: React.FC<QuickActionCardProps> = ({ hasAccounts, refreshKey }) => {
  const { user } = useAppContext();
  const [analysis, setAnalysis] = useState<HubAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadAnalysis = async () => {
    const uid = activeUserId(user);
    if (!uid || !hasAccounts) {
      setAnalysis(null);
      return;
    }

    setLoading(true);
    setError('');
    try {
      const res = await apiFetch(
        `/api/account-hub-analysis?user_id=${encodeURIComponent(uid)}`,
      );
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || 'Failed to load account analysis');
      }
      setAnalysis(data);
    } catch (err: any) {
      setError(err.message || 'Unable to load analysis');
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.isAuthenticated && hasAccounts) {
      // Defer LLM-backed analysis until after initial render.
      const w = window as any;
      const run = () => loadAnalysis();
      if (typeof w.requestIdleCallback === 'function') {
        w.requestIdleCallback(run, { timeout: 2000 });
      } else {
        setTimeout(run, 350);
      }
    }
  }, [user?.isAuthenticated, user?.userId, user?.id, hasAccounts, refreshKey]);

  const creditAlerts = analysis?.credit_card_alerts ?? [];
  const spendingInsights = analysis?.account_spending ?? [];

  return (
    <div className="lg:col-span-4 bg-primary text-white p-6 rounded-[32px] soft-shadow relative overflow-hidden flex flex-col min-h-[200px]">
      <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16 blur-2xl" />

      <div className="relative z-10 flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5" />
          <h4 className="text-sm font-black uppercase tracking-widest">Account Intelligence</h4>
        </div>
        {hasAccounts && (
          <button
            type="button"
            onClick={loadAnalysis}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-white/10 transition disabled:opacity-50"
            title="Refresh analysis"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>

      <div className="relative z-10 flex-1 space-y-4 overflow-y-auto max-h-[320px] pr-1">
        {!hasAccounts && (
          <p className="text-sm text-white/80 leading-relaxed">
            Link a checking, savings, or credit card account to get AI-powered utilization
            warnings and spending diversity insights for this month.
          </p>
        )}

        {hasAccounts && loading && !analysis && (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="w-6 h-6 animate-spin text-white/70" />
          </div>
        )}

        {error && (
          <p className="text-xs font-medium text-red-100 bg-red-500/20 rounded-xl px-3 py-2">
            {error}
          </p>
        )}

        {hasAccounts && analysis && !loading && (
          <>
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/60">
              {analysis.month ?? 'This month'}
            </p>

            {creditAlerts.length > 0 && (
              <div className="space-y-2">
                {creditAlerts.map((alert) => (
                  <div
                    key={alert.account}
                    className="bg-white/10 border border-white/20 rounded-2xl p-3 flex gap-2"
                  >
                    <AlertTriangle className="w-4 h-4 shrink-0 text-amber-200 mt-0.5" />
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-wider text-amber-100">
                        {alert.account}
                        {alert.utilization_pct != null ? ` · ${alert.utilization_pct}% used` : ''}
                      </p>
                      <p className="text-xs text-white/90 mt-1 leading-relaxed">{alert.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {spendingInsights.length > 0 ? (
              <div className="space-y-2">
                {spendingInsights.map((item) => (
                  <div
                    key={item.account}
                    className="bg-white/10 rounded-2xl p-3 border border-white/10"
                  >
                    <p className="text-[10px] font-black uppercase tracking-wider text-white/70">
                      {item.account}
                    </p>
                    <p className="text-[10px] font-bold text-emerald-100 mt-1">
                      {item.majority_category}
                    </p>
                    <p className="text-xs text-white/90 mt-1 leading-relaxed">{item.analysis}</p>
                  </div>
                ))}
              </div>
            ) : (
              !creditAlerts.length && (
                <p className="text-sm text-white/75 leading-relaxed">
                  {analysis.summary ??
                    'No expense transactions this month yet. Add transactions to see per-account category insights.'}
                </p>
              )
            )}

            {creditAlerts.length === 0 &&
              spendingInsights.length > 0 &&
              analysis.transaction_count === 0 && (
                <p className="text-xs text-white/60">
                  Credit utilization warnings appear when a credit card with a limit is linked.
                </p>
              )}
          </>
        )}
      </div>

      {hasAccounts && !loading && analysis && creditAlerts.length === 0 && spendingInsights.length === 0 && (
        <div className="relative z-10 mt-3 flex items-center gap-2 text-white/50">
          <CreditCard className="w-4 h-4" />
          <span className="text-[10px] font-bold uppercase tracking-widest">
            Insights update as you add accounts & transactions
          </span>
        </div>
      )}
    </div>
  );
};
