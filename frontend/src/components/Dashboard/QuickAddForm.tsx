import React, { useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { cn } from '../../lib/utils';
import { Plus, Check, Loader2, ArrowUpRight, ArrowDownLeft } from 'lucide-react';

interface QuickAddFormProps {
  onSuccess?: () => void;
  accounts?: any[];
}

export const QuickAddForm: React.FC<QuickAddFormProps> = ({ onSuccess, accounts }) => {
  const { categories, user } = useAppContext();
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  
  const [formData, setFormData] = useState({
    description: '',
    amount: '',
    type: 'expense',
    mainCategory: '',
    subCategory: 'General',
    accountId: '',
    date: new Date().toISOString().split('T')[0]
  });

  const selectedCategory = categories.find(c => c.name === formData.mainCategory);
  const subCategories = selectedCategory?.subCategories || [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.mainCategory || !formData.accountId || !formData.amount) {
        alert("Please fill in all required fields (Amount, Category, Account)");
        return;
    }

    setLoading(true);
    try {
      const activeUserId = user.id || user.userId || "";
      const response = await fetch('http://localhost:8000/api/transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: activeUserId,
          account_id: formData.accountId,
          amount: Math.abs(parseFloat(formData.amount)),
          transaction_type: formData.type,
          merchant_name: formData.description || 'Quick Add',
          description: formData.description || 'Quick Add',
          main_category: formData.mainCategory,
          category_name: formData.mainCategory,
          sub_category: formData.subCategory || 'General',
          sub_category_name: formData.subCategory || 'General',
          transaction_date: formData.date
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
          date: new Date().toISOString().split('T')[0]
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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h4 className="text-xl font-bold text-on-surface">Quick Add</h4>
          <p className="text-[10px] font-black text-outline uppercase tracking-widest mt-1">Log a new transaction</p>
        </div>
        {success && (
          <div className="flex items-center gap-2 text-secondary bg-secondary/10 px-3 py-1 rounded-full animate-in fade-in zoom-in duration-300">
            <Check className="w-3 h-3" />
            <span className="text-[10px] font-black uppercase tracking-wider">Added!</span>
          </div>
        )}
      </div>

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
    </div>
  );
};
