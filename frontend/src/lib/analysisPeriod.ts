export type AnalysisPeriod = '1m' | '3m' | '6m' | '1y' | 'all';

export const DEFAULT_ANALYSIS_PERIOD: AnalysisPeriod = '1m';

export const ANALYSIS_PERIOD_OPTIONS: { value: AnalysisPeriod; label: string }[] = [
  { value: '1m', label: '1 Month' },
  { value: '3m', label: '3 Months' },
  { value: '6m', label: '6 Months' },
  { value: '1y', label: '1 Year' },
  { value: 'all', label: 'All Time' },
];

const STORAGE_KEY = 'finassist_analysis_period';

export function loadStoredAnalysisPeriod(): AnalysisPeriod {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw && ANALYSIS_PERIOD_OPTIONS.some((o) => o.value === raw)) {
      return raw as AnalysisPeriod;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_ANALYSIS_PERIOD;
}

export function storeAnalysisPeriod(period: AnalysisPeriod): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, period);
  } catch {
    /* ignore */
  }
}

function monthStart(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d: Date, months: number): Date {
  const y = d.getFullYear();
  const m = d.getMonth() + months;
  const nd = new Date(y, m, Math.min(d.getDate(), new Date(y, m + 1, 0).getDate()));
  return nd;
}

/** Calendar window aligned with backend `resolve_analysis_window`. */
export function resolveAnalysisWindow(
  period: AnalysisPeriod,
  reference: Date = new Date(),
): {
  startDate: string | null;
  endDate: string;
  periodLabel: string;
} {
  const end = reference.toISOString().slice(0, 10);
  if (period === 'all') {
    return { startDate: null, endDate: end, periodLabel: 'All time' };
  }
  
  const months = 
    period === '1m' ? 1 : 
    period === '3m' ? 3 : 
    period === '6m' ? 6 :
    period === '1y' ? 12 : 1;
    
  const start = addMonths(monthStart(reference), -(months - 1));
  const startDate = start.toISOString().slice(0, 10);
  
  const label =
    period === '1m'
      ? reference.toLocaleString('en', { month: 'long', year: 'numeric' }) + ' (month to date)'
      : `${start.toLocaleString('en', { month: 'short', year: 'numeric' })} – ${reference.toLocaleString('en', { month: 'short', year: 'numeric' })}`;
  return { startDate, endDate: end, periodLabel: label };
}

export function isWithinAnalysisWindow(
  dateStr: string,
  period: AnalysisPeriod,
  reference: Date = new Date(),
): boolean {
  const d = dateStr.slice(0, 10);
  const { startDate, endDate } = resolveAnalysisWindow(period, reference);
  if (startDate && d < startDate) return false;
  return d <= endDate;
}

export type DashboardPeriodSlice = {
  period?: AnalysisPeriod;
  period_label?: string;
  chart_data?: Array<{ name?: string; month?: string; date?: string; expense?: number }>;
  chart_granularity?: 'daily' | 'monthly';
  summary?: {
    net_outflow?: number;
    expense_change_pct?: number | null;
    [key: string]: unknown;
  };
  expense_breakdown_month?: Array<{ name: string; value: number }>;
  top_spending?: Array<{ merchant: string; total: number; count?: number }>;
  spending_anomalies?: Array<Record<string, unknown>>;
  financial_health?: Record<string, unknown> | null;
};

export function getDashboardPeriodSlice(
  dashboardSummary: { period_data?: Partial<Record<AnalysisPeriod, DashboardPeriodSlice>>; period?: AnalysisPeriod } | null,
  period: AnalysisPeriod,
): DashboardPeriodSlice | null {
  if (!dashboardSummary) return null;
  const slice = dashboardSummary.period_data?.[period];
  if (slice) return slice;
  if (!dashboardSummary.period_data && dashboardSummary.period === period) {
    return dashboardSummary as DashboardPeriodSlice;
  }
  if (!dashboardSummary.period_data && !dashboardSummary.period) {
    return dashboardSummary as DashboardPeriodSlice;
  }
  return null;
}
