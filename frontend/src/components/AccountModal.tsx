import React, { useState, useEffect } from 'react';
import { X, Building2, CreditCard, DollarSign, Wallet, ShieldCheck } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { CURRENCY_SYMBOL } from '../lib/utils';

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

const accountTypes = [
  { value: 'checking', label: 'Checking Account', icon: Building2 },
  { value: 'savings', label: 'Savings Account', icon: ShieldCheck },
  { value: 'credit_card', label: 'Credit Card', icon: CreditCard },
  { value: 'wallet', label: 'Digital Wallet', icon: Wallet },
  { value: 'cash', label: 'Cash Wallet', icon: DollarSign },
];

export const AccountModal: React.FC<AccountModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const { user } = useAppContext();
  const [formData, setFormData] = useState({
    account_name: '',
    account_type: 'checking',
    current_balance: 0,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setFormData({
        account_name: '',
        account_type: 'checking',
        current_balance: 0,
      });
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch('http://localhost:8000/api/accounts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user?.userId,
          account_name: formData.account_name,
          account_type: formData.account_type,
          current_balance: formData.current_balance,
        }),
      });

      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.detail || 'Failed to link account');
      }

      if (onSuccess) {
        onSuccess();
      }
      onClose();
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4 backdrop-blur-sm transition-all duration-300">
      <div className="bg-surface-container-lowest w-full max-w-lg rounded-[28px] shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col transform transition-all scale-100">
        <div className="px-8 py-5 border-b border-outline-variant/20 flex justify-between items-center bg-surface-container-low">
          <div>
            <h3 className="text-xl font-black text-on-surface tracking-tight">Link Bank Account</h3>
            <p className="text-[10px] text-outline font-bold uppercase tracking-wider mt-0.5">Secure, real-time manual ledger integration</p>
          </div>
          <button 
            onClick={onClose} 
            className="p-2 hover:bg-surface-container-high rounded-full text-outline hover:text-on-surface transition-all active:scale-90"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-8 space-y-6 overflow-y-auto max-h-[75vh]">
          {error && (
            <div className="p-4 bg-error-container/10 border border-error-container/30 text-error text-xs font-bold rounded-xl">
              {error}
            </div>
          )}

          <div className="space-y-5">
            <div>
              <label className="block text-[10px] font-black text-outline uppercase tracking-widest mb-2 px-1">Account Name</label>
              <div className="relative">
                <input 
                  required
                  type="text" 
                  value={formData.account_name}
                  onChange={(e) => setFormData({...formData, account_name: e.target.value})}
                  placeholder="e.g. Chase checking, Apple Credit Card" 
                  className="w-full px-5 py-4 bg-surface-container-low rounded-2xl border border-outline-variant/50 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all text-sm font-bold text-on-surface placeholder:text-outline/40" 
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-black text-outline uppercase tracking-widest mb-2 px-1">Account Type</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {accountTypes.map(t => {
                  const Icon = t.icon;
                  const isSelected = formData.account_type === t.value;
                  return (
                    <button
                      key={t.value}
                      type="button"
                      onClick={() => setFormData({...formData, account_type: t.value})}
                      className={`p-4 rounded-2xl border-2 transition-all text-left flex flex-col gap-2 items-start justify-between min-h-[90px] ${
                        isSelected 
                          ? 'border-primary bg-primary/5 shadow-md shadow-primary/5' 
                          : 'border-outline-variant/30 hover:border-primary/45 bg-transparent'
                      }`}
                    >
                      <div className={`p-2 rounded-xl ${isSelected ? 'bg-primary/10 text-primary' : 'bg-surface-container-high text-outline'}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <span className={`text-xs font-extrabold transition-all leading-tight ${isSelected ? 'text-primary' : 'text-on-surface-variant'}`}>{t.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-black text-outline uppercase tracking-widest mb-2 px-1">Starting Balance</label>
              <div className="relative">
                <div className="absolute left-5 top-1/2 -translate-y-1/2 text-primary font-black text-base">
                  {CURRENCY_SYMBOL}
                </div>
                <input 
                  required
                  type="number" 
                  step="0.01"
                  value={formData.current_balance || ''}
                  onChange={(e) => setFormData({...formData, current_balance: parseFloat(e.target.value) || 0})}
                  placeholder="0.00" 
                  className="w-full pl-12 pr-5 py-4 bg-surface-container-low rounded-2xl border border-outline-variant/50 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all text-sm font-bold text-on-surface placeholder:text-outline/40" 
                />
              </div>
              <p className="text-[9px] text-outline font-medium tracking-wide mt-1.5 px-1 leading-relaxed">
                Enter your current balance. You can add transactions later to keep the balance synced in real-time.
              </p>
            </div>
          </div>

          <div className="pt-4 border-t border-outline-variant/20 flex gap-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-4 bg-surface-container-low text-on-surface font-bold rounded-2xl hover:bg-surface-container-high transition-all active:scale-[0.98]"
            >
              Cancel
            </button>
            <button 
              type="submit"
              disabled={isSubmitting}
              className="flex-1 py-4 bg-primary text-white font-bold rounded-2xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Linking...</span>
                </>
              ) : (
                'Link Account'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
