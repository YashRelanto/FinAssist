import React from 'react';
import { Building2, CreditCard, History } from 'lucide-react';
import { cn, formatCurrency } from '../../lib/utils';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

interface LinkedAccountsProps {
  accounts?: any[];
}

export const LinkedAccounts: React.FC<LinkedAccountsProps> = ({ accounts }) => {
  if (!accounts || accounts.length === 0) {
    return (
      <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-surface-container-lowest p-6 rounded-[24px] border border-outline-variant/30 soft-shadow flex flex-col min-h-[160px] col-span-3">
          <ComingSoonPlaceholder message="No accounts linked yet" />
        </div>
      </div>
    );
  }

  return (
    <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
       {accounts.slice(0, 3).map((acc, i) => {
         const isCredit = acc.account_type?.toLowerCase().includes('credit');
         return (
           <div key={i} className="bg-surface-container-lowest p-6 rounded-[24px] border border-outline-variant/30 soft-shadow group hover:border-primary transition-all cursor-pointer">
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
              <h4 className="font-bold text-on-surface mt-1">{acc.account_name}</h4>
              <p className="text-xl font-black text-on-surface mt-4 tracking-tighter">{formatCurrency(acc.current_balance)}</p>
              <div className="flex items-center gap-1.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                 <History className="w-3 h-3 text-outline" />
                 <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Live Sync</span>
              </div>
           </div>
         );
       })}
    </div>
  );
};
