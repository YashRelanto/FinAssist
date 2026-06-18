import React, { useState, useEffect } from 'react';
import { X, PiggyBank, Calendar, Info, ShieldAlert } from 'lucide-react';
import { Budget } from '../types';
import { useAppContext } from '../context/AppContext';
import { CURRENCY_SYMBOL } from '../lib/utils';
import { defaultBudgetPeriodDates } from '../lib/budgetPeriod';
import { AppModal } from './AppModal';

interface BudgetModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingBudget?: Budget;
}

const mainCategories = [
  'Food & Drinks',
  'Shopping',
  'Housing',
  'Transportation',
  'Vehicle',
  'Life & Entertainment',
  'Communication/PC',
  'Financial Expense',
  'Investments',
  'Income',
  'Others'
];

export const BudgetModal: React.FC<BudgetModalProps> = ({ isOpen, onClose, editingBudget }) => {
  const { addBudget, updateBudget } = useAppContext();
  const initialPeriodDates = defaultBudgetPeriodDates('monthly');
  const [formData, setFormData] = useState<Omit<Budget, 'id' | 'userId' | 'categoryId'>>({
    categoryName: 'Food & Drinks',
    budgetName: '',
    amount: 0,
    period: 'monthly',
    startDate: initialPeriodDates.startDate,
    endDate: initialPeriodDates.endDate,
    alertThreshold: 80
  });

  useEffect(() => {
    if (editingBudget) {
      setFormData({
        categoryName: editingBudget.categoryName,
        budgetName: editingBudget.budgetName,
        amount: editingBudget.amount,
        period: editingBudget.period,
        startDate: editingBudget.startDate ? editingBudget.startDate.split('T')[0] : new Date().toISOString().split('T')[0],
        endDate: editingBudget.endDate ? editingBudget.endDate.split('T')[0] : new Date(new Date().setMonth(new Date().getMonth() + 1)).toISOString().split('T')[0],
        alertThreshold: editingBudget.alertThreshold
      });
    } else {
      const dates = defaultBudgetPeriodDates('monthly');
      setFormData({
        categoryName: 'Food & Drinks',
        budgetName: '',
        amount: 0,
        period: 'monthly',
        startDate: dates.startDate,
        endDate: dates.endDate,
        alertThreshold: 80
      });
    }
  }, [editingBudget, isOpen]);

  const handlePeriodChange = (period: string) => {
    const dates = defaultBudgetPeriodDates(period);
    setFormData((prev) => ({
      ...prev,
      period,
      startDate: dates.startDate,
      endDate: dates.endDate,
    }));
  };

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingBudget) {
      updateBudget(editingBudget.id, formData);
    } else {
      addBudget(formData);
    }
    onClose();
  };

  return (
    <AppModal isOpen={isOpen} onClose={onClose}>
      <div className="bg-surface-container-lowest w-full rounded-2xl shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col">
        <div className="px-6 py-4 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container-low">
          <h3 className="text-xl font-bold">{editingBudget ? 'Edit Category Budget' : 'Create New Category Budget'}</h3>
          <button onClick={onClose} className="p-2 hover:bg-surface-container-high rounded-full transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto max-h-[80vh]">
          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Budget Name</label>
              <div className="relative">
                <PiggyBank className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
                <input 
                  required
                  type="text" 
                  value={formData.budgetName}
                  onChange={(e) => setFormData({...formData, budgetName: e.target.value})}
                  placeholder="e.g. Dining Out, Monthly Fuel" 
                  className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold" 
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Category</label>
              <select 
                value={formData.categoryName}
                onChange={(e) => setFormData({...formData, categoryName: e.target.value})}
                className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold text-on-surface"
              >
                {mainCategories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Limit Amount ({CURRENCY_SYMBOL})</label>
                <input 
                  required
                  type="number" 
                  value={formData.amount || ''}
                  onChange={(e) => setFormData({...formData, amount: parseFloat(e.target.value)})}
                  placeholder="0.00" 
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Period</label>
                <select 
                  value={formData.period}
                  onChange={(e) => handlePeriodChange(e.target.value)}
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold text-on-surface"
                >
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="yearly">Yearly</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Start Date</label>
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
                  <input 
                    required
                    type="date" 
                    value={formData.startDate}
                    onChange={(e) => setFormData({...formData, startDate: e.target.value})}
                    className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm" 
                  />
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">End Date</label>
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
                  <input 
                    required
                    type="date" 
                    value={formData.endDate}
                    onChange={(e) => setFormData({...formData, endDate: e.target.value})}
                    className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm" 
                  />
                </div>
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest">Alert Threshold ({formData.alertThreshold}%)</label>
                <ShieldAlert className="w-4 h-4 text-secondary" />
              </div>
              <input 
                type="range" 
                min="50" 
                max="100" 
                value={formData.alertThreshold}
                onChange={(e) => setFormData({...formData, alertThreshold: parseInt(e.target.value)})}
                className="w-full h-2 bg-surface-container-high rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <p className="text-[10px] text-outline mt-1 font-medium">We will flag alert notifications when your category spending reaches this limit.</p>
            </div>
          </div>

          <div className="pt-4">
            <button 
              type="submit"
              className="w-full py-4 bg-primary text-white font-bold rounded-xl shadow-lg hover:brightness-110 active:scale-[0.98] transition-all"
            >
              {editingBudget ? 'Save Changes' : 'Set Budget'}
            </button>
          </div>
        </form>
      </div>
    </AppModal>
  );
};
