import React, { useMemo } from 'react';
import { Repeat } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { detectSubscriptions } from '../../lib/subscriptionDetection';
import { formatCurrency } from '../../lib/utils';
import { isWithinAnalysisWindow } from '../../lib/analysisPeriod';

export const SubscriptionsCard: React.FC = () => {
  const { transactions, analysisPeriod } = useAppContext();

  const subscriptions = useMemo(() => {
    const inPeriod = transactions.filter((t) =>
      isWithinAnalysisWindow(t.date, analysisPeriod),
    );
    return detectSubscriptions(inPeriod);
  }, [transactions, analysisPeriod]);

  const monthlyTotal = subscriptions.reduce((s, sub) => s + sub.monthlyAmount, 0);

  return (
    <div className="bento-card flex flex-col">
      <div className="flex items-center justify-between mb-6 border-b border-lumio-line pb-4">
        <h3 className="font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted">
          Subscriptions
        </h3>
        {subscriptions.length > 0 && (
          <span className="text-[10px] font-bold text-lumio-muted uppercase tracking-wider">
            ~{formatCurrency(monthlyTotal)}/mo
          </span>
        )}
      </div>

      {subscriptions.length === 0 ? (
        <p className="text-sm text-lumio-muted">
          No recurring subscriptions detected in this period. Add transactions for services like Netflix, Spotify, or Jio Hotstar to see them here.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {subscriptions.slice(0, 6).map((sub) => (
            <div
              key={sub.displayName}
              className="flex items-center justify-between gap-3 py-3 border-b border-lumio-line/40 last:border-0"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center border border-lumio-line/40 shrink-0">
                  <Repeat className="w-4 h-4 text-lumio-muted" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{sub.displayName}</p>
                  <p className="text-[10px] text-lumio-muted uppercase tracking-wider">
                    {sub.occurrences} charge{sub.occurrences !== 1 ? 's' : ''}
                    {sub.source === 'recurring' ? ' · recurring' : ''}
                  </p>
                </div>
              </div>
              <span className="text-sm font-semibold text-lumio-text shrink-0">
                {formatCurrency(sub.monthlyAmount)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
