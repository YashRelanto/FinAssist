import React, { useState, useEffect } from 'react';
import { 
  Building2, 
  CreditCard, 
  Wallet, 
  ShieldCheck, 
  DollarSign, 
  Plus, 
  Trash2, 
  ArrowLeft, 
  Loader2, 
  AlertTriangle,
  History,
  Lock
} from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency, CURRENCY_SYMBOL } from '../lib/utils';
import { activeUserId } from '../lib/activeUserId';
import { apiFetch } from '../lib/api';
import { AccountModal } from '../components/AccountModal';

export const LinkedAccounts: React.FC = () => {
  const { user, setCurrentPage } = useAppContext();
  const [accounts, setAccounts] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<any | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchAccounts = async () => {
    const uid = activeUserId(user);
    if (!user.isAuthenticated || !uid) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/accounts?user_id=${encodeURIComponent(uid)}`);
      const data = await res.json();
      if (data.success) {
        setAccounts(data.data ?? []);
      } else {
        throw new Error(data.detail || 'Failed to load accounts');
      }
    } catch (err: any) {
      console.error(err);
      setError('Could not retrieve linked accounts. Please make sure the backend is active.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, [user.userId, user.id, user.isAuthenticated]);

  const handleDelete = async (accountId: string) => {
    setIsDeleting(true);
    try {
      const res = await fetch(`http://localhost:8000/api/accounts/${accountId}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (data.success) {
        setAccounts(prev => prev.filter(acc => acc.account_id !== accountId));
        setDeleteTarget(null);
      } else {
        throw new Error(data.detail || 'Failed to delete account');
      }
    } catch (err: any) {
      console.error(err);
      alert(err.message || 'Error occurred while deleting the account.');
    } finally {
      setIsDeleting(false);
    }
  };

  const getAccountIcon = (type: string) => {
    switch (type?.toLowerCase()) {
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
  };

  const getAccountStyle = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'credit_card':
        return { color: "text-teal-600", bg: "bg-teal-50" };
      case 'savings':
        return { color: "text-secondary", bg: "bg-secondary/10" };
      case 'wallet':
        return { color: "text-purple-600", bg: "bg-purple-50" };
      case 'cash':
        return { color: "text-emerald-600", bg: "bg-emerald-50" };
      default:
        return { color: "text-primary", bg: "bg-primary/10" };
    }
  };

  return (
    <div className="max-w-5xl space-y-8 pb-20">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <button 
            onClick={() => setCurrentPage('settings')}
            className="flex items-center gap-2 text-xs font-black text-primary uppercase tracking-widest hover:underline mb-2 transition-all active:scale-95"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to Settings
          </button>
          <h2 className="text-3xl font-bold text-on-surface">Linked Bank Accounts</h2>
          <p className="text-on-surface-variant font-medium text-sm mt-1">Manage secure ledger connections, check starting balances, or delete stale links.</p>
        </div>
        
        <button 
          onClick={() => setIsModalOpen(true)}
          className="px-5 py-3 bg-primary text-white font-bold text-xs rounded-xl shadow-lg hover:brightness-110 active:scale-95 transition-all flex items-center justify-center gap-2 shrink-0"
        >
          <Plus className="w-4 h-4" /> Link New Account
        </button>
      </header>

      {error && (
        <div className="p-4 bg-error-container/10 border border-error-container/30 text-error text-xs font-bold rounded-2xl flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="w-10 h-10 text-primary animate-spin" />
          <p className="text-xs text-outline font-bold uppercase tracking-wider">Retrieving Accounts...</p>
        </div>
      ) : accounts.length === 0 ? (
        <div className="bg-surface-container-lowest p-12 rounded-[32px] border border-outline-variant/30 text-center flex flex-col items-center justify-center min-h-[300px] transition-all duration-300">
          <div className="w-16 h-16 bg-primary/10 text-primary rounded-full flex items-center justify-center mb-4">
            <Building2 className="w-8 h-8 animate-pulse" />
          </div>
          <h3 className="text-lg font-black text-on-surface">No Linked Accounts Found</h3>
          <p className="text-xs text-outline max-w-sm mt-2 mb-6 leading-relaxed">
            Connect checking accounts, savings portfolios, digital wallets, or credit cards manually. Keep starting balances in sync automatically.
          </p>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="px-6 py-3.5 bg-primary text-white font-bold text-xs rounded-xl shadow-md hover:brightness-110 active:scale-95 transition-all flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" /> Link First Account
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {accounts.map(acc => {
            const style = getAccountStyle(acc.account_type);
            const Icon = getAccountIcon(acc.account_type);

            return (
              <div 
                key={acc.account_id} 
                className="bg-surface-container-lowest p-6 rounded-[28px] border border-outline-variant/30 soft-shadow group hover:border-primary transition-all flex flex-col justify-between min-h-[190px] duration-300 relative overflow-hidden"
              >
                <div>
                  <div className="flex justify-between items-start mb-4">
                    <div className={cn("p-3 rounded-xl", style.bg, style.color)}>
                      <Icon className="w-5 h-5" />
                    </div>
                    
                    <button 
                      onClick={() => setDeleteTarget(acc)}
                      className="p-2 bg-surface-container-low hover:bg-error-container/10 hover:text-error text-outline/60 rounded-xl transition-all active:scale-90"
                      title="Delete Bank Link"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  
                  <p className="text-[10px] font-black text-outline uppercase tracking-widest leading-none">{acc.account_type?.replace('_', ' ')}</p>
                  <h4 className="font-bold text-on-surface mt-1 text-base line-clamp-1">{acc.account_name}</h4>
                </div>
                
                <div className="mt-6 flex justify-between items-end">
                  <div>
                    <p className="text-2xl font-black text-on-surface tracking-tighter">
                      {formatCurrency(parseFloat(acc.current_balance))}
                    </p>
                    <div className="flex items-center gap-1.5 mt-1.5 text-outline/80">
                      <History className="w-3.5 h-3.5" />
                      <span className="text-[9px] font-bold uppercase tracking-wider">Synced Ledger</span>
                    </div>
                  </div>
                  
                  <div className="p-2 bg-secondary/5 rounded-xl border border-secondary/10 flex items-center gap-1 text-secondary text-[8px] font-black uppercase tracking-widest">
                    <Lock className="w-3 h-3" /> Secure
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Premium Centered Confirmation Modal Popup */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4 backdrop-blur-sm transition-all duration-300">
          <div className="bg-surface-container-lowest w-full max-w-md rounded-[28px] shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col transform transition-all scale-100 p-8 space-y-6">
            <div className="flex flex-col items-center text-center space-y-4">
              <div className="w-16 h-16 bg-error/10 text-error rounded-full flex items-center justify-center animate-bounce">
                <AlertTriangle className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-xl font-black text-on-surface tracking-tight">Delete Bank Account</h3>
                <p className="text-[10px] text-error font-bold uppercase tracking-wider mt-1">Warning: Irreversible Action</p>
              </div>
              <p className="text-xs text-outline leading-relaxed font-medium">
                Are you sure you want to delete <span className="font-extrabold text-on-surface">"{deleteTarget.account_name}"</span>?
                
              </p>
            </div>

            <div className="flex gap-4">
              <button
                disabled={isDeleting}
                onClick={() => setDeleteTarget(null)}
                className="flex-1 py-3.5 bg-surface-container-low hover:bg-surface-container-high text-on-surface font-extrabold text-xs rounded-2xl active:scale-[0.98] transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                disabled={isDeleting}
                onClick={() => handleDelete(deleteTarget.account_id)}
                className="flex-1 py-3.5 bg-error text-white font-extrabold text-xs rounded-2xl shadow-lg shadow-error/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  'Yes, Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <AccountModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onSuccess={(account) => {
          if (account?.account_id) {
            setAccounts((prev) => {
              if (prev.some((a) => a.account_id === account.account_id)) return prev;
              return [...prev, account];
            });
          }
          void fetchAccounts();
        }}
      />
    </div>
  );
};
