import React, { useState, useEffect } from 'react';
import { useAppContext } from '../../context/AppContext';
import { activeUserId } from '../../lib/activeUserId';
import { apiFetch } from '../../lib/api';
import { cn, formatCurrency } from '../../lib/utils';
import { Plus, Check, Loader2, ArrowUpRight, ArrowDownLeft, Calendar } from 'lucide-react';

interface QuickAddFormProps {
  onSuccess?: () => void;
  accounts?: any[];
}

export const QuickAddForm: React.FC<QuickAddFormProps> = ({ onSuccess, accounts }) => {
  const { categories, user } = useAppContext();
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [activeTab, setActiveTab] = useState<'add' | 'upcoming'>('add');
  const [upcomingPayments, setUpcomingPayments] = useState<any[]>([]);
  const [loadingUpcoming, setLoadingUpcoming] = useState(false);
  
  const [formData, setFormData] = useState({
    description: '',
    amount: '',
    type: 'expense',
    mainCategory: '',
    subCategory: 'General',
    accountId: '',
    date: new Date().toISOString().split('T')[0],
    isRecurring: false,
    recurrencePeriod: 'monthly',
    recurrenceSkips: '0'
  });

  const selectedCategory = categories.find(c => c.name === formData.mainCategory);
  const subCategories = selectedCategory?.subCategories || [];

  const fetchUpcomingPayments = async () => {
    const uid = activeUserId(user);
    if (!uid) return;
    setLoadingUpcoming(true);
    try {
      const res = await apiFetch(`/api/upcoming-payments`);
      const data = await res.json();
      if (res.ok && data.success) {
        setUpcomingPayments(data.data || []);
      }
    } catch (err) {
      console.error("Failed to fetch upcoming payments", err);
    } finally {
      setLoadingUpcoming(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'upcoming') {
      fetchUpcomingPayments();
    }
  }, [activeTab]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.mainCategory || !formData.accountId || !formData.amount) {
        alert("Please fill in all required fields (Amount, Category, Account)");
        return;
    }

    setLoading(true);
    try {
      const uid = activeUserId(user);
      if (!uid) {
        alert('Please sign in again.');
        return;
      }
      const response = await apiFetch('/api/transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: formData.accountId,
          amount: Math.abs(parseFloat(formData.amount)),
          transaction_type: formData.type,
          merchant_name: formData.description || 'Quick Add',
          description: formData.description || 'Quick Add',
          main_category: formData.mainCategory,
          category_name: formData.mainCategory,
          sub_category: formData.subCategory || 'General',
          sub_category_name: formData.subCategory || 'General',
          transaction_date: formData.date,
          is_recurring: formData.isRecurring,
          recurrence_period: formData.isRecurring ? formData.recurrencePeriod : null,
          recurrence_skips: formData.isRecurring ? parseInt(formData.recurrenceSkips || '0') : 0
        })
      });

      const data = await response.json();
      if (response.ok || data.success) {
        setSuccess(true);
        setFormData({
          description: '',
          amount: '',
          type: 'expense',
          mainCategory: '',
          subCategory: 'General',
          accountId: '',
          date: new Date().toISOString().split('T')[0],
          isRecurring: false,
          recurrencePeriod: 'monthly',
          recurrenceSkips: '0'
        });
        if (onSuccess) onSuccess();
        setTimeout(() => setSuccess(false), 3000);
      } else {
        const errorDetail = data.detail 
          ? (typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail) 
          : "Failed to add transaction";
        alert(errorDetail);
      }
    } catch (error: any) {
      console.error("Failed to add transaction", error);
      alert(error.message || "Error connecting to backend");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="lg:col-span-5 bg-surface-container-lowest p-6 rounded-[24px] border border-outline-variant/30 soft-shadow flex flex-col h-full">
      <div className="flex items-center justify-between mb-6 border-b border-outline-variant/20 pb-3">
        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => setActiveTab('add')}
            className={cn(
              "text-lg font-black uppercase tracking-widest pb-1 transition-all",
              activeTab === 'add'
                ? "text-primary border-b-2 border-primary"
                : "text-outline hover:text-on-surface"
            )}
          >
            Quick Add
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('upcoming')}
            className={cn(
              "text-lg font-black uppercase tracking-widest pb-1 transition-all",
              activeTab === 'upcoming'
                ? "text-primary border-b-2 border-primary"
                : "text-outline hover:text-on-surface"
            )}
          >
            Upcoming
          </button>
        </div>
        {success && activeTab === 'add' && (
          <div className="flex items-center gap-2 text-secondary bg-secondary/10 px-3 py-1 rounded-full animate-in fade-in zoom-in duration-300">
            <Check className="w-3 h-3" />
            <span className="text-[10px] font-black uppercase tracking-wider">Added!</span>
          </div>
        )}
      </div>

      {activeTab === 'add' ? (
        <form onSubmit={handleSubmit} className="space-y-4 flex-1 flex flex-col">
          {/* Type Selector */}
          <div className="flex p-1 bg-surface-container-low rounded-xl gap-1">
            <button
              type="button"
              onClick={() => setFormData({ ...formData, type: 'expense' })}
              className={cn(
                "flex-1 py-2 rounded-lg flex items-center justify-center gap-2 transition-all",
                formData.type === 'expense' 
                  ? "bg-white text-error shadow-sm" 
                  : "text-outline hover:text-on-surface"
              )}
            >
              <ArrowDownLeft className="w-4 h-4" />
              <span className="text-[10px] font-black uppercase tracking-widest">Expense</span>
            </button>
            <button
              type="button"
              onClick={() => setFormData({ ...formData, type: 'income' })}
              className={cn(
                "flex-1 py-2 rounded-lg flex items-center justify-center gap-2 transition-all",
                formData.type === 'income' 
                  ? "bg-white text-secondary shadow-sm" 
                  : "text-outline hover:text-on-surface"
              )}
            >
              <ArrowUpRight className="w-4 h-4" />
              <span className="text-[10px] font-black uppercase tracking-widest">Income</span>
            </button>
          </div>

          {/* Amount & Description */}
          <div className="grid grid-cols-1 gap-4">
            <div className="space-y-1.5">
              <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Amount</label>
              <input 
                required
                type="number" 
                placeholder="0.00"
                value={formData.amount}
                onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3 text-lg font-black focus:ring-2 focus:ring-primary outline-none transition-all placeholder:text-outline/30"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Merchant / Note</label>
              <input 
                type="text" 
                placeholder="Where did you spend?"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3 text-sm font-bold focus:ring-2 focus:ring-primary outline-none transition-all placeholder:text-outline/30"
              />
            </div>
          </div>

          {/* Categories */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Category</label>
              <select 
                required
                value={formData.mainCategory}
                onChange={(e) => setFormData({ ...formData, mainCategory: e.target.value, subCategory: 'General' })}
                className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3 text-xs font-bold focus:ring-2 focus:ring-primary outline-none transition-all appearance-none cursor-pointer"
              >
                <option value="" disabled>Select</option>
                {categories.map(cat => (
                  <option key={cat.id} value={cat.name}>{cat.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Sub Category</label>
              <select 
                value={formData.subCategory}
                onChange={(e) => setFormData({ ...formData, subCategory: e.target.value })}
                className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3 text-xs font-bold focus:ring-2 focus:ring-primary outline-none transition-all appearance-none cursor-pointer"
              >
                <option value="General">General</option>
                {subCategories.filter(s => s.name !== 'General').map(sub => (
                  <option key={sub.id} value={sub.name}>{sub.name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Account & Date */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Account</label>
              <select 
                required
                value={formData.accountId}
                onChange={(e) => setFormData({ ...formData, accountId: e.target.value })}
                className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3 text-xs font-bold focus:ring-2 focus:ring-primary outline-none transition-all appearance-none cursor-pointer"
              >
                <option value="" disabled>Select</option>
                {accounts?.map(acc => (
                  <option key={acc.account_id} value={acc.account_id}>{acc.account_name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Date</label>
              <input 
                type="date" 
                value={formData.date}
                onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3 text-xs font-bold focus:ring-2 focus:ring-primary outline-none transition-all cursor-pointer"
              />
            </div>
          </div>

          {/* Recurring Options */}
          <div className="bg-surface-container-low p-4 rounded-xl space-y-3 border border-outline-variant/20">
            <div className="flex items-center gap-2">
              <input 
                type="checkbox"
                id="isRecurring"
                checked={formData.isRecurring}
                onChange={(e) => setFormData({ ...formData, isRecurring: e.target.checked })}
                className="w-4 h-4 rounded text-primary focus:ring-primary cursor-pointer"
              />
              <label htmlFor="isRecurring" className="text-xs font-black text-on-surface uppercase tracking-widest cursor-pointer select-none">
                Make Recurring Payment
              </label>
            </div>

            {formData.isRecurring && (
              <div className="grid grid-cols-2 gap-4 pt-1 animate-in fade-in slide-in-from-top-1 duration-200">
                <div className="space-y-1">
                  <label className="text-[8px] font-black text-outline uppercase tracking-[0.2em] ml-0.5">Period</label>
                  <select
                    value={formData.recurrencePeriod}
                    onChange={(e) => setFormData({ ...formData, recurrencePeriod: e.target.value })}
                    className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-lg px-2 py-1.5 text-xs font-bold focus:ring-2 focus:ring-primary outline-none transition-all"
                  >
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="yearly">Yearly</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-[8px] font-black text-outline uppercase tracking-[0.2em] ml-0.5">Skips (Skip count)</label>
                  <input
                    type="number"
                    min="0"
                    placeholder="0"
                    value={formData.recurrenceSkips}
                    onChange={(e) => setFormData({ ...formData, recurrenceSkips: e.target.value })}
                    className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-lg px-2 py-1 text-xs font-bold focus:ring-2 focus:ring-primary outline-none transition-all"
                  />
                </div>
              </div>
            )}
          </div>

          <button 
            type="submit"
            disabled={loading}
            className="w-full mt-auto py-4 bg-primary text-white font-black rounded-xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <>
                <span className="uppercase tracking-[0.2em] text-[10px]">Add Transaction</span>
                <Plus className="w-4 h-4 group-hover:rotate-90 transition-transform" />
              </>
            )}
          </button>
        </form>
      ) : (
        <div className="flex-1 flex flex-col overflow-y-auto space-y-3 pb-2 scrollbar-hide max-h-[360px]">
          {loadingUpcoming ? (
            <div className="flex-1 flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          ) : upcomingPayments.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-20 px-4">
              <Calendar className="w-10 h-10 text-outline/40 mb-3" />
              <p className="text-xs font-black text-outline uppercase tracking-wider">No upcoming payments</p>
              <p className="text-[10px] text-outline/60 mt-1">Add a recurring transaction to schedule payments.</p>
            </div>
          ) : (
            upcomingPayments.map((payment) => (
              <div 
                key={payment.id} 
                className="bg-surface-container-low border border-outline-variant/20 rounded-2xl p-4 flex items-center justify-between hover:bg-surface-container-high transition-colors"
              >
                <div className="space-y-1">
                  <p className="text-sm font-bold text-on-surface">{payment.merchant}</p>
                  <div className="flex flex-wrap gap-2 items-center text-[9px] font-black uppercase tracking-wider text-outline">
                    <span className="bg-surface-container-lowest px-2 py-0.5 rounded border border-outline-variant/10">{payment.category}</span>
                    <span>•</span>
                    <span>{payment.account}</span>
                  </div>
                  <p className="text-[9px] font-bold text-primary uppercase tracking-widest pt-1">
                    Next: {payment.next_date} ({payment.recurrence_period}
                    {payment.recurrence_skips > 0 ? `, skip ${payment.recurrence_skips}` : ''})
                  </p>
                </div>
                <div className="text-right">
                  <span className={cn(
                    "text-sm font-black",
                    payment.type === 'income' ? "text-secondary" : "text-error"
                  )}>
                    {payment.type === 'income' ? '+' : '-'}{formatCurrency(payment.amount)}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
