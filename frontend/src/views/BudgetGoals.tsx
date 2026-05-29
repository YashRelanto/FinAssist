import React, { useState } from 'react';
import { Home, Utensils, Car, ShoppingBasket, PlaneTakeoff, Laptop, ShieldCheck, Download, Plus, AlertCircle, Target, Edit2, Trash2 } from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';
import { useAppContext } from '../context/AppContext';
import { GoalModal } from '../components/GoalModal';
import { Goal } from '../types';

export const BudgetGoals: React.FC = () => {
  const { goals, deleteGoal, transactions, user } = useAppContext();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<Goal | undefined>(undefined);

  // 1. Calculate dynamic budget allocations
  const housingSpent = transactions
    .filter(t => t.category === 'Housing' || t.category === 'Housing & Rent' || t.category === 'Housing & Utilities')
    .reduce((acc, t) => acc + Math.abs(t.amount), 0);
  const housingBudget = user.fixedRent || (user.isAuthenticated ? 0 : 2400);

  const diningSpent = transactions
    .filter(t => t.category === 'Food & Drinks' || t.category === 'Food & Dining' || t.category === 'Life & Entertainment')
    .reduce((acc, t) => acc + Math.abs(t.amount), 0);
  const diningBudget = user.isAuthenticated ? 0 : 800;

  const transportSpent = transactions
    .filter(t => t.category === 'Transportation' || t.category === 'Vehicle')
    .reduce((acc, t) => acc + Math.abs(t.amount), 0);
  const transportBudget = user.isAuthenticated ? 0 : 450;

  const grocerySpent = transactions
    .filter(t => t.category === 'Shopping')
    .reduce((acc, t) => acc + Math.abs(t.amount), 0);
  const groceryBudget = user.isAuthenticated ? 0 : 600;

  const budgetItems = [
    { icon: Home, label: 'Housing & Utilities', sub: 'Fixed Monthly', spent: housingSpent, total: housingBudget, color: 'bg-secondary' },
    { 
      icon: Utensils, 
      label: 'Dining & Entertainment', 
      sub: diningSpent >= diningBudget && diningBudget > 0 ? 'Exceeded Limit' : 'Dining & Outing', 
      spent: diningSpent, 
      total: diningBudget, 
      color: diningSpent > diningBudget && diningBudget > 0 ? 'bg-error' : 'bg-secondary', 
      alert: diningBudget > 0 && diningSpent >= diningBudget * 0.9 
    },
    { icon: Car, label: 'Transportation', sub: 'Gas & Maintenance', spent: transportSpent, total: transportBudget, color: 'bg-primary' },
    { icon: ShoppingBasket, label: 'Groceries', sub: 'Household Essentials', spent: grocerySpent, total: groceryBudget, color: 'bg-primary' },
  ].map(item => ({
    ...item,
    status: item.total > 0 ? `${Math.round((item.spent / item.total) * 100)}% Utilized` : '0% Utilized',
    percent: item.total > 0 ? Math.min(100, (item.spent / item.total) * 100) : 0
  }));

  const totalSpent = budgetItems.reduce((acc, item) => acc + item.spent, 0);
  const totalBudget = budgetItems.reduce((acc, item) => acc + item.total, 0);

  // 2. Dynamic trajectory insight
  const isAuthNoData = user.isAuthenticated && transactions.length === 0;
  const trajectoryTitle = isAuthNoData ? "No Trajectory Data Yet" : "Financial Trajectory";
  const trajectoryDesc = isAuthNoData 
    ? "Once you log your income and start recording transactions, we'll project your savings trajectory and growth rates in real-time."
    : "You are saving 18% more than last month. At this rate, your Emergency Fund will be fully funded 2 months ahead of schedule. Your investment portfolio is also showing a strong upward trend.";
  const trajectoryGrowth = isAuthNoData ? "0%" : "75%";
  const strokeOffset = isAuthNoData ? 351.8 : 88;

  const handleEdit = (g: Goal) => {
    setEditingGoal(g);
    setModalOpen(true);
  };

  const handleAdd = () => {
    setEditingGoal(undefined);
    setModalOpen(true);
  };

  return (
    <div className="space-y-10">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6">
        <div>
          <h2 className="text-3xl font-bold text-on-surface">Budget & Goals</h2>
          <p className="text-on-surface-variant mt-2 max-w-2xl text-sm font-medium">Strategic oversight of your financial commitments. Real-time tracking of allocations versus performance benchmarks.</p>
        </div>
        <div className="flex gap-4 w-full md:w-auto">
          <button className="flex-1 md:flex-none px-6 py-2.5 rounded-lg bg-surface-container-highest text-primary font-bold text-sm hover:brightness-95 transition-all">Download Report</button>
          <button 
            onClick={handleAdd}
            className="flex-1 md:flex-none px-6 py-2.5 rounded-lg bg-primary text-white font-bold text-sm hover:brightness-110 shadow-md transition-all flex items-center justify-center gap-2"
          >
            <Plus className="w-4 h-4" /> Create New Goal
          </button>
        </div>
      </div>
      
      {/* Strategic Savings Goals */}
      <section className="space-y-6">
        <div className="flex justify-between items-center">
          <h3 className="text-xl font-bold">Strategic Savings Goals</h3>
          <div className="bg-primary/10 text-primary px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest">
            {goals.length} Active Goals
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {goals.map((goal, i) => {
            const progress = Math.round((goal.current / goal.target) * 100);
            return (
              <div key={goal.id} className="bg-surface-container-lowest rounded-2xl border border-outline-variant/30 soft-shadow p-6 flex flex-col hover-lift h-full group relative">
                <div className="flex justify-between items-start mb-6">
                  <div className={cn("p-2.5 rounded-xl bg-primary/10 text-primary")}>
                    <Target className="w-5 h-5 shadow-sm" />
                  </div>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => handleEdit(goal)}
                      className="p-1.5 text-outline hover:text-primary hover:bg-primary-container/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button 
                      onClick={() => { if(confirm('Delete this goal?')) deleteGoal(goal.id) }}
                      className="p-1.5 text-outline hover:text-error hover:bg-error-container/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <span className={cn("px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider", goal.color.replace('bg-', 'bg-') + '/10', goal.color.replace('bg-', 'text-'))}>
                      {progress}% Complete
                    </span>
                  </div>
                </div>
                <h4 className="text-lg font-bold mb-2">{goal.label}</h4>
                <p className="text-xs text-outline font-medium mb-8 leading-relaxed line-clamp-2">{goal.sub}</p>
                
                <div className="mt-auto space-y-4">
                  <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest">
                    <span className="text-outline">Current Status</span>
                    <span className="text-on-surface">{formatCurrency(goal.current)} / {formatCurrency(goal.target)}</span>
                  </div>
                  <div className="h-1.5 w-full bg-surface-container-high rounded-full overflow-hidden">
                    <div className={cn(goal.color, "h-full transition-all duration-1000")} style={{ width: `${progress}%` }}></div>
                  </div>
                  <div className="flex justify-between items-center pt-2">
                    <div className="flex items-center gap-1.5 text-outline">
                      <AlertCircle className="w-3.5 h-3.5" />
                      <span className="text-[10px] font-bold uppercase tracking-widest">Target: {goal.date}</span>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Monthly Budget Allocations */}
      <section className="bg-surface-container-lowest rounded-2xl soft-shadow p-6 lg:p-8 border border-outline-variant/30">
        <div className="flex justify-between items-center mb-8 border-b border-outline-variant/30 pb-4">
          <h3 className="text-xl font-bold">Monthly Budget Allocations</h3>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-outline uppercase tracking-widest">Spent:</span>
            <span className="text-sm font-bold text-on-surface">{formatCurrency(totalSpent)} / {formatCurrency(totalBudget)}</span>
          </div>
        </div>

        <div className="space-y-8">
          {budgetItems.map((item, i) => (
            <div key={i} className="group">
              <div className="flex justify-between items-center mb-3">
                <div className="flex items-center gap-4">
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center transition-all",
                    item.alert ? "bg-error/10 text-error" : "bg-surface-container-high text-primary"
                  )}>
                    <item.icon className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-on-surface">{item.label}</p>
                    <p className={cn("text-[10px] font-bold uppercase tracking-[0.15em]", item.alert ? "text-error" : "text-outline")}>{item.sub}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-on-surface">{formatCurrency(item.spent)} of {formatCurrency(item.total)}</p>
                  <p className={cn("text-[10px] font-bold uppercase tracking-widest mt-0.5", item.alert ? "text-error" : "text-secondary")}>{item.status}</p>
                </div>
              </div>
              <div className="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
                <div 
                  className={cn(item.color, "h-full transition-all duration-1000 ease-out")} 
                  style={{ width: `${item.percent}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Trajectory Insight */}
      <div className="bg-inverse-surface rounded-2xl p-8 text-white flex flex-col md:flex-row items-center justify-between gap-8 h-full">
          <div className="max-w-2xl">
            <h4 className="text-2xl font-bold mb-3">{trajectoryTitle}</h4>
            <p className="opacity-80 text-sm leading-relaxed font-medium">
              {trajectoryDesc}
            </p>
          </div>
          <div className="relative w-32 h-32 flex items-center justify-center flex-shrink-0">
            <svg className="w-full h-full transform -rotate-90">
              <circle className="text-white/10" cx="64" cy="64" fill="transparent" r="56" stroke="currentColor" strokeWidth="8"></circle>
              <circle className="text-secondary" cx="64" cy="64" fill="transparent" r="56" stroke="currentColor" strokeDasharray="351.8" strokeDashoffset={strokeOffset} strokeWidth="8" strokeLinecap="round"></circle>
            </svg>
            <div className="absolute flex flex-col items-center">
              <span className="text-3xl font-bold">{trajectoryGrowth}</span>
              <span className="text-[8px] font-bold opacity-60 uppercase tracking-widest">Growth</span>
            </div>
          </div>
      </div>

      <GoalModal 
        isOpen={modalOpen} 
        onClose={() => setModalOpen(false)} 
        editingGoal={editingGoal} 
      />
    </div>
  );
};
