
import React, { useState, useEffect } from 'react';
import { X, Target, Calendar, Info, Palette } from 'lucide-react';
import { Goal } from '../types';
import { useAppContext } from '../context/AppContext';
import { CURRENCY_SYMBOL } from '../lib/utils';
import { AppModal } from './AppModal';

interface GoalModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingGoal?: Goal;
}

const colors = [
  { name: 'PrimaryBlue', class: 'bg-primary' },
  { name: 'SecondaryGreen', class: 'bg-secondary' },
  { name: 'TertiaryOrange', class: 'bg-tertiary' },
  { name: 'ErrorRed', class: 'bg-error' },
  { name: 'OutlineGrey', class: 'bg-outline' },
];

export const GoalModal: React.FC<GoalModalProps> = ({ isOpen, onClose, editingGoal }) => {
  const { addGoal, updateGoal } = useAppContext();
  const [formData, setFormData] = useState<Omit<Goal, 'id'>>({
    label: '',
    sub: '',
    current: 0,
    target: 0,
    date: new Date().toISOString().split('T')[0],
    icon: 'Target',
    color: 'bg-primary'
  });

  useEffect(() => {
    if (editingGoal) {
      const { id, ...rest } = editingGoal;
      setFormData(rest);
    } else {
      setFormData({
        label: '',
        sub: '',
        current: 0,
        target: 0,
        date: new Date().toISOString().split('T')[0],
        icon: 'Target',
        color: 'bg-primary'
      });
    }
  }, [editingGoal, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingGoal) {
      updateGoal(editingGoal.id, formData);
    } else {
      addGoal(formData);
    }
    onClose();
  };

  return (
    <AppModal isOpen={isOpen} onClose={onClose}>
      <div className="bg-surface-container-lowest w-full rounded-2xl shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col">
        <div className="px-6 py-4 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container-low">
          <h3 className="text-xl font-bold">{editingGoal ? 'Edit Savings Goal' : 'Create New Goal'}</h3>
          <button onClick={onClose} className="p-2 hover:bg-surface-container-high rounded-full transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto max-h-[80vh]">
          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Goal Name</label>
              <div className="relative">
                <Target className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
                <input 
                  required
                  type="text" 
                  value={formData.label}
                  onChange={(e) => setFormData({...formData, label: e.target.value})}
                  placeholder="e.g. New Car, Emergency Fund" 
                  className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold" 
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Description</label>
              <div className="relative">
                <Info className="absolute left-3 top-3 w-4 h-4 text-outline" />
                <textarea 
                  value={formData.sub}
                  onChange={(e) => setFormData({...formData, sub: e.target.value})}
                  placeholder="What is this goal for?" 
                  rows={2}
                  className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm"
                ></textarea>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Target Amount ({CURRENCY_SYMBOL})</label>
                <input 
                  required
                  type="number" 
                  value={formData.target || ''}
                  onChange={(e) => setFormData({...formData, target: parseFloat(e.target.value)})}
                  placeholder="0.00" 
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold" 
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Current Saved ({CURRENCY_SYMBOL})</label>
                <input 
                  required
                  type="number" 
                  value={formData.current || ''}
                  onChange={(e) => setFormData({...formData, current: parseFloat(e.target.value)})}
                  placeholder="0.00" 
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold" 
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Target Date</label>
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
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Theme Color</label>
              <div className="flex gap-3 mt-2">
                {colors.map(c => (
                  <button 
                    key={c.class}
                    type="button"
                    onClick={() => setFormData({...formData, color: c.class})}
                    className={`w-8 h-8 rounded-full ${c.class} border-4 transition-all ${formData.color === c.class ? 'border-primary-container scale-125 shadow-lg' : 'border-transparent opacity-60 hover:opacity-100'}`}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="pt-4">
            <button 
              type="submit"
              className="w-full py-4 bg-primary text-white font-bold rounded-xl shadow-lg hover:brightness-110 active:scale-[0.98] transition-all"
            >
              {editingGoal ? 'Save Changes' : 'Create Goal'}
            </button>
          </div>
        </form>
      </div>
    </AppModal>
  );
};
