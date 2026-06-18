import React from 'react';
import { 
  ArrowUpRight, 
  ArrowDownLeft, 
  ShoppingBag, 
  Coffee, 
  Home, 
  Car, 
  Tv, 
  Smartphone, 
  CreditCard,
  ExternalLink,
  Plus
} from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { cn, formatCurrency } from '../../lib/utils';

interface Transaction {
  id: string;
  date: string;
  merchant: string;
  amount: number;
  type: 'income' | 'expense';
  category: string;
  subCategory: string;
  account: string;
}

interface RecentTransactionsProps {
  transactions?: Transaction[];
  variant?: 'default' | 'bento';
  onAddTransaction?: () => void;
}

const CATEGORY_ICONS: Record<string, any> = {
  'Food & Drinks': Coffee,
  'Shopping': ShoppingBag,
  'Housing': Home,
  'Transportation': Car,
  'Vehicle': Car,
  'Life & Entertainment': Tv,
  'Communication/PC': Smartphone,
  'Financial Expense': CreditCard,
  'others': Plus,
};

export const RecentTransactions: React.FC<RecentTransactionsProps> = ({
  transactions = [],
  variant = 'default',
  onAddTransaction,
}) => {
  const { setCurrentPage } = useAppContext();
  const wrapperClass = variant === 'bento'
    ? 'bento-card flex flex-col min-h-[320px]'
    : 'lg:col-span-8 bg-surface-container-lowest p-6 rounded-[24px] soft-shadow border border-outline-variant/30 flex flex-col min-h-[400px]';

  return (
    <div className={wrapperClass}>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          {variant !== 'bento' && (
            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center text-primary">
              <ExternalLink className="w-5 h-5" />
            </div>
          )}
          <div>
            <h4 className={variant === 'bento' ? 'font-label text-[12px] font-semibold uppercase tracking-widest text-lumio-muted' : 'text-xl font-bold text-on-surface'}>
              Recent Transactions
            </h4>
            {variant !== 'bento' && (
              <p className="text-[10px] font-black text-outline uppercase tracking-widest mt-0.5">Your latest movements</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onAddTransaction && (
            <button
              type="button"
              onClick={onAddTransaction}
              className="text-[10px] font-bold uppercase tracking-widest hover:underline"
            >
              + Add
            </button>
          )}
          <button 
            type="button"
            onClick={() => setCurrentPage('transactions')}
            className={variant === 'bento'
              ? 'font-label text-[10px] font-bold uppercase tracking-widest border-b border-lumio-black hover:opacity-70'
              : 'px-4 py-2 bg-surface-container-high hover:bg-surface-container-highest text-primary text-[10px] font-black uppercase tracking-widest rounded-xl transition-all border border-outline-variant/30'}
          >
            View All
          </button>
        </div>
      </div>

      <div className="flex-1 space-y-3">
        {transactions.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-10">
            <div className="w-16 h-16 bg-surface-container-low rounded-full flex items-center justify-center mb-4 text-outline/20">
              <Plus className="w-8 h-8" />
            </div>
            <p className="text-xs font-black text-outline uppercase tracking-widest">No recent transactions</p>
          </div>
        ) : (
          transactions.map((t, idx) => {
            const Icon = CATEGORY_ICONS[t.category] || CATEGORY_ICONS['others'];
            const isExpense = t.type === 'expense';

            return (
              <div 
                key={t.id}
                className="group flex items-center justify-between p-4 bg-surface-container-low hover:bg-surface-container-high rounded-[20px] border border-transparent hover:border-outline-variant/50 transition-all duration-300"
              >
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "w-12 h-12 rounded-2xl flex items-center justify-center transition-transform group-hover:scale-110",
                    isExpense ? "bg-error/10 text-error" : "bg-success/10 text-success"
                  )}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="flex flex-col min-w-0">
                    <span className="text-sm font-black text-on-surface truncate tracking-tight">{t.merchant}</span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] font-bold text-outline uppercase tracking-wider">{t.category}</span>
                      <span className="w-1 h-1 rounded-full bg-outline-variant/50" />
                      <span className="text-[10px] font-bold text-outline-variant">{t.date}</span>
                    </div>
                  </div>
                </div>

                <div className="text-right flex flex-col items-end">
                  <div className={cn(
                    "flex items-center gap-1 text-sm font-black tracking-tight",
                    isExpense ? "text-on-surface" : "text-success"
                  )}>
                    {isExpense ? (
                      <ArrowUpRight className="w-3.5 h-3.5 text-error opacity-50" />
                    ) : (
                      <ArrowDownLeft className="w-3.5 h-3.5 text-success opacity-50" />
                    )}
                    {formatCurrency(t.amount)}
                  </div>
                  <span className="text-[9px] font-black text-outline uppercase tracking-tighter mt-1 opacity-50">{t.account}</span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  );
};
