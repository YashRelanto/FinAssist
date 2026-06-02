
import React, { useState, useEffect } from 'react';
import { X, Calendar, Tag, User, FileText } from 'lucide-react';
import { Transaction } from '../types';
import { useAppContext } from '../context/AppContext';
import { CURRENCY_SYMBOL } from '../lib/utils';

interface TransactionModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingTransaction?: Transaction;
  accounts?: any[];
  onSaved?: () => void;
}

export const TransactionModal: React.FC<TransactionModalProps> = ({
  isOpen,
  onClose,
  editingTransaction,
  accounts = [],
  onSaved,
}) => {
  const { addTransaction, updateTransaction, categories, pendingDate, resetPendingDate } = useAppContext();
  
  const defaultAccount = accounts.length > 0 ? accounts[0].account_id : 'HDFC Bank';

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [formData, setFormData] = useState<Omit<Transaction, 'id'>>({
    date: new Date().toISOString().split('T')[0],
    merchant: '',
    category: 'Housing',
    subCategory: '',
    amount: 0,
    account: defaultAccount,
    type: 'expense',
    notes: ''
  });

  useEffect(() => {
    if (isOpen) {
      setSaveError(null);
      if (editingTransaction) {
        const { id, ...rest } = editingTransaction;
        setFormData({
          ...rest,
          account: editingTransaction.account_id || editingTransaction.account || defaultAccount
        });
      } else if (pendingDate) {
        setFormData({
          date: pendingDate,
          merchant: '',
          category: 'Housing',
          subCategory: '',
          amount: 0,
          account: defaultAccount,
          type: 'expense',
          notes: ''
        });
        resetPendingDate();
      } else {
        setFormData({
          date: new Date().toISOString().split('T')[0],
          merchant: '',
          category: 'Housing',
          subCategory: '',
          amount: 0,
          account: defaultAccount,
          type: 'expense',
          notes: ''
        });
      }
    }
  }, [editingTransaction, isOpen, pendingDate, accounts]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);

    if (editingTransaction) {
      updateTransaction(editingTransaction.id, formData, (success) => {
        setIsSaving(false);
        if (success) {
          onSaved?.();
          onClose();
        } else {
          setSaveError('Could not save changes. Please try again.');
        }
      });
      return;
    }

    addTransaction(formData);
    onSaved?.();
    onClose();
    setIsSaving(false);
  };

  const selectedCategory = categories.find(c => c.name === formData.category);

  return (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-surface-container-lowest w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col">
        <div className="px-6 py-4 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container-low">
          <h3 className="text-xl font-bold">{editingTransaction ? 'Edit Transaction' : 'Add Transaction'}</h3>
          <button onClick={onClose} className="p-2 hover:bg-surface-container-high rounded-full transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto max-h-[80vh]">
          {saveError && (
            <div className="p-3 bg-error-container/10 border border-error-container/30 text-error text-xs font-bold rounded-xl">
              {saveError}
            </div>
          )}
          <div className="flex bg-surface-container-low p-1 rounded-xl">
            <button 
              type="button"
              onClick={() => setFormData({...formData, type: 'expense'})}
              className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${formData.type === 'expense' ? 'bg-error text-white shadow-md' : 'text-outline hover:text-on-surface'}`}
            >
              Expense
            </button>
            <button 
              type="button"
              onClick={() => setFormData({...formData, type: 'income'})}
              className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${formData.type === 'income' ? 'bg-secondary text-white shadow-md' : 'text-outline hover:text-on-surface'}`}
            >
              Income
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Amount</label>
              <div className="relative">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center text-outline font-bold">
                  {CURRENCY_SYMBOL}
                </div>
                <input 
                  required
                  type="number" 
                  step="0.01"
                  value={formData.amount || ''}
                  onChange={(e) => setFormData({...formData, amount: parseFloat(e.target.value)})}
                  placeholder="0.00" 
                  className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold" 
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Date</label>
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
                  <input 
                    required
                    type="date" 
                    value={formData.date}
                    onChange={(e) => setFormData({...formData, date: e.target.value})}
                    className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm" 
                  />
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Account</label>
                <select 
                  value={formData.account}
                  onChange={(e) => setFormData({...formData, account: e.target.value})}
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm outline-none"
                >
                  {accounts.length > 0 ? (
                    accounts.map(acc => (
                      <option key={acc.account_id} value={acc.account_id}>{acc.account_name}</option>
                    ))
                  ) : (
                    <>
                      <option value="HDFC Bank">HDFC Bank</option>
                      <option value="ICICI Bank">ICICI Bank</option>
                      <option value="Amex Card">Amex Card</option>
                      <option value="Stripe">Stripe</option>
                    </>
                  )}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Merchant / Source</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
                <input 
                  required
                  type="text" 
                  value={formData.merchant}
                  onChange={(e) => setFormData({...formData, merchant: e.target.value})}
                  placeholder="e.g. Starbucks, Client X" 
                  className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm" 
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Category</label>
                <select 
                  value={formData.category}
                  onChange={(e) => setFormData({...formData, category: e.target.value, subCategory: ''})}
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm outline-none"
                >
                  {categories.map(cat => <option key={cat.id} value={cat.name}>{cat.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Sub-category</label>
                <select 
                  value={formData.subCategory}
                  onChange={(e) => setFormData({...formData, subCategory: e.target.value})}
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm outline-none"
                >
                  <option value="">None</option>
                  {selectedCategory?.subCategories.map(sub => <option key={sub.id} value={sub.name}>{sub.name}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Notes</label>
              <div className="relative">
                <FileText className="absolute left-3 top-3 w-4 h-4 text-outline" />
                <textarea 
                  value={formData.notes}
                  onChange={(e) => setFormData({...formData, notes: e.target.value})}
                  placeholder="Additional details..." 
                  rows={3}
                  className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm"
                ></textarea>
              </div>
            </div>
          </div>

          <div className="pt-4">
            <button 
              type="submit"
              disabled={isSaving}
              className="w-full py-4 bg-primary text-white font-bold rounded-xl shadow-lg hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-60"
            >
              {isSaving ? 'Saving…' : editingTransaction ? 'Save Changes' : 'Create Transaction'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
