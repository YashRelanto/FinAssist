import React from 'react';

import { motion } from 'motion/react';

import { Zap, RefreshCcw } from 'lucide-react';

import { useAppContext } from '../../context/AppContext';

import { cn, formatCurrency } from '../../lib/utils';

interface PredictedMonth {
  month: string;
  label: string;
  month_start: string;
  month_end: string;
  amount: number;
}

interface ForecastSummary {
  success: boolean;
  period_label?: string;
  predicted_months?: PredictedMonth[];
  predicted_next_month?: number;
  prev_period_spend?: number;
  prev_month_spend?: number;
  budget_alert?: boolean;
  budget_alert_message?: string | null;
  message?: string;
  user_model_available?: boolean;
  history_months?: number;
  min_months_required?: number;
}

export const ForecastPredictionCard: React.FC = () => {
  const { user, analysisPeriod, loadForecast } = useAppContext();
  const [forecast, setForecast] = React.useState<ForecastSummary | null>(null);
  const [loading, setLoading] = React.useState(true);

  const fetchForecast = React.useCallback(async (options?: { force?: boolean }) => {
    if (!user?.isAuthenticated) return;
    try {
      setLoading(true);
      const data = await loadForecast({ period: analysisPeriod, force: options?.force });
      setForecast(data as ForecastSummary | null);
    } catch (e) {
      console.error('Failed to load dashboard forecast', e);
    } finally {
      setLoading(false);
    }
  }, [user?.isAuthenticated, loadForecast, analysisPeriod]);

  React.useEffect(() => {
    if (user?.isAuthenticated) fetchForecast();
  }, [user?.isAuthenticated, fetchForecast]);

  const predictedMonths = forecast?.predicted_months ?? [];
  const nextMonth = predictedMonths[0];
  const prevSpend = forecast?.prev_period_spend ?? forecast?.prev_month_spend;

  return (
    <motion.div className="lg:col-span-12 bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 flex flex-col">
      <motion.div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <motion.div className="flex items-center gap-3">
          <motion.div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
            <Zap className="w-5 h-5" />
          </motion.div>
          <motion.div>
            <motion.h3 className="text-lg font-black tracking-tight">Expense Forecast</motion.h3>
            <motion.p className="text-[10px] font-bold text-outline uppercase tracking-widest">
              Prophet · next calendar month
            </motion.p>
          </motion.div>
        </motion.div>

        <motion.button
          type="button"
          onClick={() => fetchForecast({ force: true })}
          className="p-2 rounded-xl border border-outline-variant/50 hover:bg-surface-container-low transition-colors self-end sm:self-auto"
          aria-label="Refresh forecast"
        >
          <RefreshCcw className={cn('w-4 h-4 text-outline', loading && 'animate-spin')} />
        </motion.button>
      </motion.div>

      {loading && !forecast ? (
        <motion.div className="flex-1 flex items-center justify-center min-h-[120px]">
          <motion.div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary" />
        </motion.div>
      ) : (
        <motion.div className="flex-1">
          {forecast?.period_label && (
            <motion.p className="text-[10px] font-bold text-outline mb-3">{forecast.period_label}</motion.p>
          )}
          <motion.p className="text-[10px] font-black text-outline uppercase tracking-[0.2em] mb-4">
            Predicted spend (next month)
          </motion.p>
          {nextMonth ? (
            <motion.div className="bg-surface-container rounded-2xl p-4 border border-outline-variant/20">
              <motion.div className="flex items-center justify-between">
                <motion.div>
                  <motion.p className="text-sm font-black text-on-surface">{nextMonth.label}</motion.p>
                  <motion.p className="text-[9px] font-bold text-outline">
                    {nextMonth.month_start} → {nextMonth.month_end}
                  </motion.p>
                </motion.div>
                <motion.p className="text-lg font-black text-on-surface">
                  {formatCurrency(nextMonth.amount)}
                </motion.p>
              </motion.div>
            </motion.div>
          ) : (
            <motion.p className="text-2xl font-black text-on-surface">—</motion.p>
          )}
          {forecast?.predicted_next_month != null && nextMonth && (
            <motion.div className="mt-4 flex items-center justify-between">
              <motion.span className="text-xs font-black text-outline uppercase tracking-widest">
                Predicted total
              </motion.span>
              <motion.span className="text-sm font-black text-on-surface">
                {formatCurrency(forecast.predicted_next_month)}
              </motion.span>
            </motion.div>
          )}
          {prevSpend != null && nextMonth && (
            <motion.p className="text-[10px] text-outline font-bold text-right mt-0.5">
              vs {formatCurrency(prevSpend)} in comparison period
            </motion.p>
          )}
          {!nextMonth && forecast?.message && (
            <motion.p className="text-xs font-bold text-outline mt-3">{forecast.message}</motion.p>
          )}
          {nextMonth && forecast?.budget_alert && forecast.budget_alert_message && (
            <motion.p className="text-xs font-bold text-error mt-3">{forecast.budget_alert_message}</motion.p>
          )}
        </motion.div>
      )}
    </motion.div>
  );
};
