import React, { useState } from 'react';
import { Home, Utensils, Car, ShoppingBasket, PlaneTakeoff, Laptop, ShieldCheck, Download, Plus, AlertCircle, Target, Edit2, Trash2 } from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';
import { useAppContext } from '../context/AppContext';
import { GoalModal } from '../components/GoalModal';
import { Goal } from '../types';

export const BudgetGoals: React.FC = () => {
  const { goals, deleteGoal } = useAppContext();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<Goal | undefined>(undefined);

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
            <span className="text-sm font-bold text-on-surface">{formatCurrency(4850)} / {formatCurrency(6200)}</span>
          </div>
        </div>

        <div className="space-y-8">
          {[
            { icon: Home, label: 'Housing & Utilities', sub: 'Fixed Monthly', spent: 2400, total: 2400, status: '100% Utilized', color: 'bg-secondary' },
            { icon: Utensils, label: 'Dining & Entertainment', sub: 'Nearing Budget Limit', spent: 760, total: 800, status: '95% Utilized', color: 'bg-error', alert: true },
            { icon: Car, label: 'Transportation', sub: 'Gas & Maintenance', spent: 240, total: 450, status: '53% Utilized', color: 'bg-primary' },
            { icon: ShoppingBasket, label: 'Groceries', sub: 'Household Essentials', spent: 415, total: 600, status: '69% Utilized', color: 'bg-primary' },
          ].map((item, i) => (
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
                  style={{ width: `${(item.spent / item.total) * 100}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Trajectory Insight */}
      <div className="bg-inverse-surface rounded-2xl p-8 text-white flex flex-col md:flex-row items-center justify-between gap-8 h-full">
          <div className="max-w-2xl">
            <h4 className="text-2xl font-bold mb-3">Financial Trajectory</h4>
            <p className="opacity-80 text-sm leading-relaxed font-medium">
              You are saving 18% more than last month. At this rate, your Emergency Fund will be fully funded 2 months ahead of schedule. Your investment portfolio is also showing a strong upward trend.
            </p>
          </div>
          <div className="relative w-32 h-32 flex items-center justify-center flex-shrink-0">
            <svg className="w-full h-full transform -rotate-90">
              <circle className="text-white/10" cx="64" cy="64" fill="transparent" r="56" stroke="currentColor" strokeWidth="8"></circle>
              <circle className="text-secondary" cx="64" cy="64" fill="transparent" r="56" stroke="currentColor" strokeDasharray="351.8" strokeDashoffset="88" strokeWidth="8" strokeLinecap="round"></circle>
            </svg>
            <div className="absolute flex flex-col items-center">
              <span className="text-3xl font-bold">75%</span>
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
