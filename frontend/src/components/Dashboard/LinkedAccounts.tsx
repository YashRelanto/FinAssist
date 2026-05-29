import React from 'react';
import { Building2, CreditCard, History, Plus } from 'lucide-react';
import { cn, formatCurrency } from '../../lib/utils';

interface LinkedAccountsProps {
  accounts?: any[];
  onAddAccount: () => void;
}

export const LinkedAccounts: React.FC<LinkedAccountsProps> = ({ accounts, onAddAccount }) => {
  if (!accounts || accounts.length === 0) {
    return (
      <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="col-span-3 bg-surface-container-lowest p-8 rounded-[24px] border border-outline-variant/30 text-center flex flex-col items-center justify-center min-h-[180px] w-full transition-all duration-300 hover:border-primary/20">
          <div className="w-12 h-12 bg-primary/10 text-primary rounded-full flex items-center justify-center mb-3">
            <Building2 className="w-6 h-6 animate-pulse" />
          </div>
          <p className="text-sm font-extrabold text-on-surface">No linked accounts yet</p>
          <p className="text-xs text-outline/70 mt-1 mb-4">Link checking, savings, or credit card manually or upload bank statements to start tracking.</p>
          <button 
            onClick={onAddAccount}
            className="px-5 py-2.5 bg-primary text-white font-bold text-xs rounded-xl shadow-md hover:brightness-110 active:scale-95 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-4 h-4" /> Link New Account
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
      {accounts.slice(0, 5).map((acc, i) => {
        const isCredit = acc.account_type?.toLowerCase().includes('credit');
        return (
          <div key={i} className="bg-surface-container-lowest p-6 rounded-[24px] border border-outline-variant/30 soft-shadow group hover:border-primary transition-all cursor-pointer flex flex-col justify-between min-h-[160px] hover:-translate-y-0.5 duration-300">
            <div>
              <div className="flex justify-between items-start mb-4">
                <div className={cn(
                  "p-2.5 rounded-xl", 
                  isCredit ? "bg-teal-50 text-teal-600" : "bg-blue-50 text-blue-600"
                )}>
                  {isCredit ? <CreditCard className="w-5 h-5" /> : <Building2 className="w-5 h-5" />}
                </div>
                <div className="w-2 h-2 rounded-full bg-secondary animate-pulse" title="Synced"></div>
              </div>
              <p className="text-[10px] font-black text-outline uppercase tracking-widest leading-none">{acc.account_type}</p>
              <h4 className="font-bold text-on-surface mt-1 text-sm line-clamp-1">{acc.account_name}</h4>
            </div>
            <div>
              <p className="text-xl font-black text-on-surface mt-4 tracking-tighter">{formatCurrency(acc.current_balance)}</p>
              <div className="flex items-center gap-1.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <History className="w-3 h-3 text-outline" />
                <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Live Sync</span>
              </div>
            </div>
          </div>
        );
      })}

      {/* Dashed plus card */}
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

