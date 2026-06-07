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
  periodLabel?: string;
  className?: string;
}

export const TimeframeSelector: React.FC<TimeframeSelectorProps> = ({
  value,
  onChange,
  periodLabel,
  className,
}) => {
  const [open, setOpen] = React.useState(false);
  const selected = ANALYSIS_PERIOD_OPTIONS.find((o) => o.value === value);

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-on-surface-variant hover:text-primary transition-colors font-semibold text-sm px-3 py-2 rounded-xl border border-outline-variant/40 bg-surface-container-low"
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

      {periodLabel && (
        <p className="hidden lg:block absolute right-0 top-full mt-14 text-[10px] font-bold text-outline uppercase tracking-widest whitespace-nowrap pointer-events-none">
          {periodLabel}
        </p>
      )}
    </div>
  );
};
