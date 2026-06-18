import React from 'react';
import { Building2, CreditCard, History, Plus, Wallet, ShieldCheck, DollarSign } from 'lucide-react';
import { cn, formatCurrency } from '../../lib/utils';

interface LinkedAccountsCardProps {
  accounts?: any[];
  onAddAccount: () => void;
  variant?: 'default' | 'bento';
}

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: 'Checking',
  savings: 'Savings',
  credit_card: 'Credit Card',
  wallet: 'Wallet',
  cash: 'Cash',
};

function getAccountIcon(type: string) {
  switch ((type || '').toLowerCase()) {
    case 'credit_card':
      return CreditCard;
    case 'savings':
      return ShieldCheck;
    case 'wallet':
      return Wallet;
    case 'cash':
      return DollarSign;
    default:
      return Building2;
  }
}

function formatAccountType(type: string) {
  const key = (type || '').toLowerCase();
  return ACCOUNT_TYPE_LABELS[key] || type?.replace(/_/g, ' ') || 'Account';
}

function formatAccountBalance(acc: any) {
  const isCredit = (acc.account_type || '').toLowerCase() === 'credit_card';
  if (isCredit) {
    const borrowed = Math.abs(parseFloat(acc.current_balance) || 0);
    const limit = parseFloat(acc.credit_limit) || 0;
    if (limit > 0) {
      const util = Math.round((borrowed / limit) * 100);
      return `${formatCurrency(borrowed)} / ${formatCurrency(limit)} (${util}%)`;
    }
    return formatCurrency(borrowed);
  }
  return formatCurrency(acc.current_balance);
}

export const LinkedAccountsCard: React.FC<LinkedAccountsCardProps> = ({
  accounts,
  onAddAccount,
  variant = 'default',
}) => {
  const cardClass = variant === 'bento'
    ? 'bento-card'
    : 'bg-surface-container-lowest rounded-[24px] border border-outline-variant/30';

  if (!accounts || accounts.length === 0) {
    return (
      <div className={cn(variant === 'bento' ? '' : 'lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6')}>
        <div className={cn(cardClass, 'text-center flex flex-col items-center justify-center min-h-[180px] w-full')}>
          <div className="w-12 h-12 bg-lumio-black/10 text-lumio-black rounded-full flex items-center justify-center mb-3">
            <Building2 className="w-6 h-6" />
          </div>
          <p className="text-sm font-bold">No linked accounts yet</p>
          <p className="text-xs text-lumio-muted mt-1 mb-4 max-w-xs">Link accounts or upload statements to start tracking.</p>
          <button
            type="button"
            onClick={onAddAccount}
            className="px-5 py-2.5 bg-lumio-black text-white font-bold text-xs rounded-full hover:bg-lumio-black/80 transition-all flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" /> Link Account
          </button>
        </div>
      </div>
    );
  }

  if (variant === 'bento') {
    return (
      <div className="bento-card">
        <div className="flex justify-between items-center mb-6 border-b border-lumio-line pb-4">
          <h3 className="font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted">
            Linked Accounts ({accounts.length})
          </h3>
          <button type="button" onClick={onAddAccount} className="text-[10px] font-bold uppercase tracking-widest hover:underline">
            + Add
          </button>
        </div>
        <div className="space-y-4 max-h-[360px] overflow-y-auto scrollbar-hide pr-1">
          {accounts.map((acc) => {
            const Icon = getAccountIcon(acc.account_type);
            const accountKey = acc.account_id ?? acc.account_name;
            return (
              <div
                key={accountKey}
                className="flex justify-between items-center py-2 border-b border-lumio-line/40 last:border-0 gap-3"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-white border border-white/60 flex items-center justify-center shadow-sm shrink-0">
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{acc.account_name}</p>
                    <p className="text-[10px] text-lumio-muted uppercase tracking-wider">
                      {formatAccountType(acc.account_type)}
                      {acc.bank_name ? ` · ${acc.bank_name}` : ''}
                    </p>
                  </div>
                </div>
                <span className="font-bold text-sm shrink-0 text-right">{formatAccountBalance(acc)}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
      {accounts.map((acc) => {
        const isCredit = acc.account_type?.toLowerCase().includes('credit');
        const Icon = getAccountIcon(acc.account_type);
        const accountKey = acc.account_id ?? acc.account_name;
        return (
          <div key={accountKey} className="bg-surface-container-lowest p-6 rounded-[24px] border border-outline-variant/30 soft-shadow group hover:border-primary transition-all cursor-pointer flex flex-col justify-between min-h-[160px] hover:-translate-y-0.5 duration-300">
            <div>
              <div className="flex justify-between items-start mb-4">
                <div className={cn(
                  "p-2.5 rounded-xl",
                  isCredit ? "bg-teal-50 text-teal-600" : "bg-blue-50 text-blue-600"
                )}>
                  <Icon className="w-5 h-5" />
                </div>
                <div className="w-2 h-2 rounded-full bg-secondary animate-pulse" title="Synced"></div>
              </div>
              <p className="text-[10px] font-black text-outline uppercase tracking-widest leading-none">{formatAccountType(acc.account_type)}</p>
              <h4 className="font-bold text-on-surface mt-1 text-sm line-clamp-1">{acc.account_name}</h4>
            </div>
            <div>
              <p className="text-xl font-black text-on-surface mt-4 tracking-tighter">{formatAccountBalance(acc)}</p>
              <div className="flex items-center gap-1.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <History className="w-3 h-3 text-outline" />
                <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Live Sync</span>
              </div>
            </div>
          </div>
        );
      })}

      <button
        onClick={onAddAccount}
        className="bg-surface-container-lowest/30 p-6 rounded-[24px] border-2 border-dashed border-outline-variant/60 hover:border-primary/60 hover:bg-surface-container-lowest hover:text-primary transition-all duration-300 cursor-pointer flex flex-col items-center justify-center min-h-[160px] group hover:-translate-y-0.5"
      >
        <div className="w-10 h-10 rounded-full border border-dashed border-outline-variant group-hover:border-primary group-hover:bg-primary/5 flex items-center justify-center mb-2 transition-all">
          <Plus className="w-5 h-5 text-outline group-hover:text-primary transition-all" />
        </div>
        <span className="text-xs font-black text-outline uppercase tracking-widest group-hover:text-primary transition-all">Link Account</span>
        <span className="text-[9px] text-outline/60 mt-1 font-medium group-hover:text-primary/75 transition-all text-center">Add Checking, Savings, or Credit Card</span>
      </button>
    </div>
  );
};
