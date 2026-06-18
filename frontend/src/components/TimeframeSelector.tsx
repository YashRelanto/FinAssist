import React from 'react';
import { Calendar, ChevronDown } from 'lucide-react';
import { motion } from 'motion/react';
import {
  ANALYSIS_PERIOD_OPTIONS,
  type AnalysisPeriod,
} from '../lib/analysisPeriod';
import { cn } from '../lib/utils';

interface TimeframeSelectorProps {
  value: AnalysisPeriod;
  onChange: (period: AnalysisPeriod) => void;
  className?: string;
  tone?: 'light' | 'dark';
}

export const TimeframeSelector: React.FC<TimeframeSelectorProps> = ({
  value,
  onChange,
  className,
  tone = 'light',
}) => {
  const [open, setOpen] = React.useState(false);
  const selected = ANALYSIS_PERIOD_OPTIONS.find((o) => o.value === value);

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex items-center gap-2 transition-colors font-semibold text-sm px-3 py-1.5 rounded-full border',
          tone === 'dark'
            ? 'text-page-bg/80 hover:text-page-bg border-page-bg/20 bg-white/5'
            : 'text-on-surface-variant hover:text-primary border-outline-variant/40 bg-surface-container-low',
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Calendar className="w-4 h-4 shrink-0" />
        <span className="hidden sm:inline">{selected?.label ?? '1 Month'}</span>
        <span className="sm:hidden">{selected?.value === 'all' ? 'All' : selected?.label}</span>
        <ChevronDown className={cn('w-4 h-4 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden />
          <motion.ul
            role="listbox"
            className="absolute right-0 top-full mt-2 w-48 bg-surface-container-lowest rounded-2xl shadow-xl border border-outline-variant/30 py-2 z-50"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {ANALYSIS_PERIOD_OPTIONS.map((opt) => (
              <li key={opt.value}>
                <button
                  type="button"
                  role="option"
                  aria-selected={value === opt.value}
                  onClick={() => {
                    onChange(opt.value);
                    setOpen(false);
                  }}
                  className={cn(
                    'w-full text-left px-4 py-2.5 text-sm font-bold transition-colors',
                    value === opt.value
                      ? 'bg-primary/10 text-primary'
                      : 'text-on-surface-variant hover:bg-surface-container-low',
                  )}
                >
                  {opt.label}
                </button>
              </li>
            ))}
          </motion.ul>
        </>
      )}
    </div>
  );
};
