import React from 'react';
import { motion } from 'motion/react';
import { APP_NAME } from '../../lib/utils';

const CHART_POINTS = [38, 52, 45, 68, 58, 72, 64, 78, 71, 85];
const CHART_WIDTH = 320;
const CHART_HEIGHT = 88;

function buildChartPath(points: number[]) {
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;
  const step = CHART_WIDTH / (points.length - 1);

  const coords = points.map((v, i) => {
    const x = i * step;
    const y = CHART_HEIGHT - ((v - min) / range) * (CHART_HEIGHT - 8) - 4;
    return [x, y] as const;
  });

  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const area = `${line} L${CHART_WIDTH},${CHART_HEIGHT} L0,${CHART_HEIGHT} Z`;
  return { line, area };
}

const EXPENSE_CATEGORIES = [
  { label: 'Food', pct: 32, color: '#FF4B2B' },
  { label: 'Travel', pct: 24, color: '#FF416C' },
  { label: 'Shopping', pct: 18, color: '#E94057' },
  { label: 'Other', pct: 26, color: '#d4d4d4' },
];

const TOP_SPENDING = [
  { merchant: 'Swiggy', amount: '₹12,400' },
  { merchant: 'Amazon', amount: '₹9,850' },
  { merchant: 'Uber', amount: '₹4,200' },
];

export const LandingHeroDashboard: React.FC = () => {
  const { line, area } = buildChartPath(CHART_POINTS);
  const healthScore = 72;
  const circumference = 289;
  const offset = circumference - (healthScore / 100) * circumference;

  return (
    <div className="w-full h-full min-h-[280px] bg-gradient-to-br from-soft-card-2 via-[#f7f6f2] to-soft-card text-left overflow-hidden">
      <div className="h-full flex flex-col p-4 sm:p-5 md:p-6">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center justify-between gap-3 mb-3 sm:mb-4"
        >
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-full border border-lumio-line bg-white flex items-center justify-center shrink-0">
              <span className="text-[10px] font-bold text-lumio-black">F</span>
            </div>
            <span className="font-display text-sm font-bold text-lumio-text truncate">{APP_NAME}</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {['1M', '3M', '6M'].map((p) => (
              <span
                key={p}
                className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
                  p === '3M'
                    ? 'bg-lumio-black text-white'
                    : 'text-lumio-muted border border-lumio-line/40'
                }`}
              >
                {p}
              </span>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.05 }}
          className="mb-3 sm:mb-4"
        >
          <p className="font-display text-lg sm:text-xl text-lumio-text tracking-tight font-light">
            Financial Overview
          </p>
          <p className="text-[10px] sm:text-xs text-lumio-muted">Your unified command center</p>
        </motion.div>

        <div className="flex-1 grid grid-cols-12 gap-2 sm:gap-3 min-h-0">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.1 }}
            className="col-span-12 lg:col-span-8 bento-card !p-3 sm:!p-4 flex flex-col min-h-0"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <p className="font-label text-[9px] sm:text-[10px] font-semibold uppercase tracking-widest text-lumio-muted mb-1">
                  Monthly Spend Trend
                </p>
                <p className="font-display text-xl sm:text-2xl font-bold text-lumio-text leading-none">
                  ₹84,250
                </p>
              </div>
              <span className="chip-success font-label text-[9px] flex items-center gap-0.5 shrink-0">
                <span className="material-symbols-outlined text-[12px]">arrow_downward</span>
                8%
              </span>
            </div>
            <div className="flex-1 min-h-[72px] sm:min-h-[88px] relative">
              <svg
                viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                className="w-full h-full"
                preserveAspectRatio="none"
              >
                <defs>
                  <linearGradient id="heroChartFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#FF4B2B" stopOpacity="0.25" />
                    <stop offset="100%" stopColor="#FF4B2B" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path d={area} fill="url(#heroChartFill)" />
                <path
                  d={line}
                  fill="none"
                  stroke="#FF4B2B"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.15 }}
            className="col-span-12 lg:col-span-4 bento-card !p-3 sm:!p-4 flex flex-col relative overflow-hidden"
          >
            <div className="absolute -top-10 -right-10 w-24 h-24 bg-emerald-tint rounded-full opacity-40 blur-2xl pointer-events-none" />
            <p className="font-label text-[9px] sm:text-[10px] font-semibold uppercase tracking-widest text-lumio-muted mb-2 relative z-10">
              Financial Health
            </p>
            <div className="flex items-center gap-3 relative z-10">
              <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-full border border-lumio-line flex items-center justify-center relative bg-white/50 shrink-0">
                <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(0,0,0,0.06)" strokeWidth="4" />
                  <circle
                    cx="50"
                    cy="50"
                    r="46"
                    fill="none"
                    stroke="#10B981"
                    strokeWidth="4"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="text-center">
                  <span className="block font-display text-xl sm:text-2xl font-bold leading-none">{healthScore}</span>
                  <span className="font-label text-[8px] text-emerald-solid uppercase tracking-widest">Good</span>
                </div>
              </div>
              <div className="flex-1 space-y-1.5 text-[10px] sm:text-xs min-w-0">
                <div className="flex justify-between gap-2">
                  <span className="text-lumio-muted">Savings</span>
                  <span className="font-medium">18%</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-lumio-muted">Net savings</span>
                  <span className="font-medium">₹15.2k</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-lumio-muted">Buffer</span>
                  <span className="font-medium">4.2 mo</span>
                </div>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.2 }}
            className="col-span-6 lg:col-span-4 bento-card !p-3 sm:!p-4 hidden sm:flex flex-col"
          >
            <p className="font-label text-[9px] font-semibold uppercase tracking-widest text-lumio-muted mb-2">
              Expense Split
            </p>
            <div className="flex gap-2 items-end h-14 mb-2">
              {EXPENSE_CATEGORIES.map((c) => (
                <div key={c.label} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t-md"
                    style={{ height: `${c.pct}%`, backgroundColor: c.color, minHeight: 4 }}
                  />
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-x-2 gap-y-1">
              {EXPENSE_CATEGORIES.slice(0, 3).map((c) => (
                <span key={c.label} className="text-[9px] text-lumio-muted flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c.color }} />
                  {c.label}
                </span>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.25 }}
            className="col-span-6 lg:col-span-4 bento-card !p-3 sm:!p-4 hidden sm:flex flex-col"
          >
            <p className="font-label text-[9px] font-semibold uppercase tracking-widest text-lumio-muted mb-2">
              Top Spending
            </p>
            <div className="space-y-2 flex-1">
              {TOP_SPENDING.map((item) => (
                <div key={item.merchant} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-6 h-6 rounded-lg bg-white border border-lumio-line/40 flex items-center justify-center text-[10px] font-bold shrink-0">
                      {item.merchant.charAt(0)}
                    </div>
                    <span className="text-[10px] sm:text-xs font-medium truncate">{item.merchant}</span>
                  </div>
                  <span className="text-[10px] text-lumio-muted shrink-0">{item.amount}</span>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.3 }}
            className="col-span-12 lg:col-span-4 bento-card !p-3 sm:!p-4 hidden md:flex flex-col border border-emerald-500/10"
          >
            <div className="flex items-center gap-1.5 mb-2">
              <span className="material-symbols-outlined text-emerald-600 text-sm">auto_awesome</span>
              <p className="font-label text-[9px] font-semibold uppercase tracking-widest text-lumio-muted">
                AI Insight
              </p>
            </div>
            <p className="text-[10px] sm:text-xs text-lumio-text/85 leading-relaxed line-clamp-3">
              Savings rate is below target — redirect ₹8,000 from discretionary spend to build your
              emergency buffer toward 6 months.
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  );
};
