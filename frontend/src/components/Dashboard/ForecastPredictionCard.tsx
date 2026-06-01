import React from 'react';

import { motion } from 'motion/react';

import { Zap, RefreshCcw } from 'lucide-react';

import { useAppContext } from '../../context/AppContext';

import { activeUserId } from '../../lib/activeUserId';

import { cn, formatCurrency } from '../../lib/utils';

const API_BASE = 'http://localhost:8000';

interface PredictedWeek {
  week: number;
  label: string;
  week_start: string;
  amount: number;
}

interface ForecastSummary {
  success: boolean;
  predicted_weeks?: PredictedWeek[];
  budget_alert?: boolean;
  budget_alert_message?: string | null;
  message?: string;
}

export const ForecastPredictionCard: React.FC = () => {
  const { user } = useAppContext();
  const [forecast, setForecast] = React.useState<ForecastSummary | null>(null);
  const [loading, setLoading] = React.useState(true);

  const fetchForecast = React.useCallback(async () => {
    const uid = activeUserId(user);
    if (!uid) return;
    try {
      setLoading(true);
      const res = await fetch(
        `${API_BASE}/api/forecast?user_id=${encodeURIComponent(uid)}&days=30`,
      );
      const data = await res.json();
      setForecast(data);
    } catch (e) {
      console.error('Failed to load dashboard forecast', e);
    } finally {
      setLoading(false);
    }
  }, [user?.userId, user?.id]);

  React.useEffect(() => {
    if (user?.isAuthenticated) fetchForecast();
  }, [user?.isAuthenticated, fetchForecast]);

  const predictedWeeks = forecast?.predicted_weeks ?? [];

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
              Prophet · per-user model · 4-week horizon
            </motion.p>
          </motion.div>
        </motion.div>

        <motion.button
          type="button"
          onClick={fetchForecast}
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
          <motion.p className="text-[10px] font-black text-outline uppercase tracking-[0.2em] mb-4">
            Predicted spend by week
          </motion.p>
          {predictedWeeks.length > 0 ? (
            <motion.div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {predictedWeeks.map((week) => (
                <motion.div
                  key={week.week}
                  className="bg-surface-container-low rounded-2xl p-4 border border-outline-variant/20"
                >
                  <motion.p className="text-[10px] font-black text-outline uppercase tracking-widest mb-1">
                    {week.label}
                  </motion.p>
                  <motion.p className="text-[10px] font-bold text-outline mb-2">
                    {week.week_start}
                  </motion.p>
                  <motion.p className="text-xl font-black text-on-surface">
                    {formatCurrency(week.amount)}
                  </motion.p>
                </motion.div>
              ))}
            </motion.div>
          ) : (
            <motion.p className="text-2xl font-black text-on-surface">—</motion.p>
          )}
          {forecast?.budget_alert && forecast.budget_alert_message && (
            <motion.p className="text-xs font-bold text-error mt-3">{forecast.budget_alert_message}</motion.p>
          )}
          {!forecast?.success && forecast?.message && (
            <motion.p className="text-xs font-bold text-outline mt-3">{forecast.message}</motion.p>
          )}
        </motion.div>
      )}
    </motion.div>
  );
};
