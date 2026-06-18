import React from 'react';
import { RefreshCw } from 'lucide-react';
import { cn } from '../lib/utils';

export const lumio = {
  page: 'space-y-8 pb-10',
  card: 'bento-card',
  cardFlat: 'bg-white/70 backdrop-blur-xl border border-white/40 rounded-3xl shadow-[0_8px_32px_0_rgba(31,38,135,0.07)] p-6 md:p-8',
  label: 'font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted',
  input:
    'w-full bg-soft-card-2 border border-lumio-line/50 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-lumio-black/15 transition-all',
  select:
    'w-full bg-soft-card-2 border border-lumio-line/50 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-lumio-black/15 appearance-none font-medium',
  btnPrimary:
    'inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-full bg-lumio-black text-white font-label text-[10px] font-bold uppercase tracking-wider hover:bg-lumio-black/80 transition-colors disabled:opacity-50',
  btnSecondary:
    'inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-full border border-lumio-line bg-white/60 font-label text-[10px] font-bold uppercase tracking-wider hover:bg-white transition-colors',
  btnGhost:
    'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-full text-lumio-muted hover:text-lumio-text hover:bg-soft-card transition-colors',
  tableWrap: 'bento-card !p-0 overflow-hidden',
  tableHead: 'bg-soft-card/50 border-b border-lumio-line/40 text-[10px] text-lumio-muted font-bold uppercase tracking-widest',
  tableRow: 'hover:bg-soft-card/40 transition-colors border-b border-lumio-line/20 last:border-0',
  spinner: 'animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-lumio-black',
  empty:
    'py-12 px-6 border-2 border-dashed border-lumio-line/50 rounded-3xl text-center text-sm text-lumio-muted',
};

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  onRefresh?: () => void;
  loading?: boolean;
  periodLabel?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  actions,
  onRefresh,
  loading,
  periodLabel,
}) => (
  <div className="mb-10 flex flex-col md:flex-row justify-between items-end gap-6 border-b border-lumio-line pb-8">
    <div>
      <h1 className="font-display text-4xl md:text-5xl text-lumio-text tracking-tighter mb-2 font-light">
        {title}
      </h1>
      {description && <p className="text-lumio-muted text-sm md:text-base max-w-2xl">{description}</p>}
      {periodLabel && (
        <p className={cn(lumio.label, 'mt-3 normal-case tracking-normal text-[11px]')}>
          {periodLabel}
        </p>
      )}
    </div>
    <div className="flex items-center gap-3 flex-wrap">
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="w-9 h-9 rounded-full border border-lumio-line flex items-center justify-center hover:bg-lumio-black hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
        </button>
      )}
      {actions}
    </div>
  </div>
);

export const PageLoading: React.FC = () => (
  <div className="flex items-center justify-center min-h-[400px]">
    <div className={lumio.spinner} />
  </div>
);

interface PageShellProps {
  children: React.ReactNode;
  className?: string;
}

export const PageShell: React.FC<PageShellProps> = ({ children, className }) => (
  <div className={cn(lumio.page, 'w-full max-w-[1200px] mx-auto', className)}>{children}</div>
);
