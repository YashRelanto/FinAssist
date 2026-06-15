import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Plus, Trash2, Tag, ShoppingBag, Utensils, Car, Home, Plane, Heart, Smartphone, Briefcase } from 'lucide-react';
import { Category } from '../types';
import { cn } from '../lib/utils';

interface CategoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (name: string, icon: string, subCategories: string[]) => void;
}

const icons = [
  { name: 'Tag', icon: Tag },
  { name: 'ShoppingBag', icon: ShoppingBag },
  { name: 'Utensils', icon: Utensils },
  { name: 'Car', icon: Car },
  { name: 'Home', icon: Home },
  { name: 'Plane', icon: Plane },
  { name: 'Heart', icon: Heart },
  { name: 'Smartphone', icon: Smartphone },
  { name: 'Briefcase', icon: Briefcase },
];

export const CategoryModal: React.FC<CategoryModalProps> = ({ isOpen, onClose, onAdd }) => {
  const [name, setName] = useState('');
  const [selectedIcon, setSelectedIcon] = useState('Tag');
  const [subCategories, setSubCategories] = useState<string[]>([]);
  const [newSubName, setNewSubName] = useState('');

  const handleAddSub = () => {
    if (newSubName.trim()) {
      setSubCategories(prev => [...prev, newSubName.trim()]);
      setNewSubName('');
    }
  };

  const handleRemoveSub = (index: number) => {
    setSubCategories(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      onAdd(name.trim(), selectedIcon, subCategories);
      setName('');
      setSubCategories([]);
      onClose();
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />
          
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="w-full max-w-lg bg-surface-container-lowest rounded-3xl shadow-2xl relative z-10 overflow-hidden border border-outline-variant/30"
          >
            <div className="p-6 border-b border-outline-variant/30 flex justify-between items-center bg-surface-container-low">
              <div>
                <h3 className="text-xl font-bold">Add Custom Category</h3>
                <p className="text-xs text-outline font-bold uppercase tracking-widest mt-1">Structure your spending your way.</p>
              </div>
              <button onClick={onClose} className="p-2 hover:bg-surface-container-high rounded-full transition-colors">
                <X className="w-5 h-5 text-on-surface-variant" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-8 space-y-8">
              <div className="space-y-3">
                <label className="text-[10px] font-black text-outline uppercase tracking-[0.2em] ml-1">Category Name</label>
                <input
                  autoFocus
                  required
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Transportation, Subscription"
                  className="w-full px-5 py-4 bg-surface-container-low border border-outline-variant rounded-2xl focus:ring-4 focus:ring-primary/10 focus:border-primary outline-none transition-all font-bold text-lg"
                />
              </div>

              <div className="space-y-3">
                <label className="text-[10px] font-black text-outline uppercase tracking-[0.2em] ml-1">Select Icon</label>
                <div className="grid grid-cols-5 gap-3">
                  {icons.map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.name}
                        type="button"
                        onClick={() => setSelectedIcon(item.name)}
                        className={cn(
                          "flex flex-col items-center justify-center p-4 rounded-2xl border transition-all gap-2",
                          selectedIcon === item.name 
                            ? "bg-primary text-white border-primary shadow-lg shadow-primary/20 scale-105" 
                            : "bg-surface-container-low border-outline-variant text-outline hover:border-primary/50"
                        )}
                      >
                        <Icon className="w-6 h-6" />
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-4">
                <label className="text-[10px] font-black text-outline uppercase tracking-[0.2em] ml-1">Initial Subcategories</label>
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={newSubName}
                    onChange={(e) => setNewSubName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddSub())}
                    placeholder="e.g. Bus, Train, Taxi"
                    className="flex-1 px-4 py-3 bg-surface-container-low border border-outline-variant rounded-xl focus:ring-2 focus:ring-primary outline-none transition-all text-sm font-bold"
                  />
                  <button
                    type="button"
                    onClick={handleAddSub}
                    className="p-3 bg-primary text-white rounded-xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-90 transition-all"
                  >
                    <Plus className="w-5 h-5" />
                  </button>
                </div>
                
                <div className="flex flex-wrap gap-2">
                  {subCategories.map((sub, idx) => (
                    <div key={idx} className="flex items-center gap-2 px-3 py-1.5 bg-primary/5 text-primary rounded-lg border border-primary/10 group">
                      <span className="text-[11px] font-black uppercase tracking-tighter">{sub}</span>
                      <button 
                        type="button"
                        onClick={() => handleRemoveSub(idx)}
                        className="text-error hover:scale-125 transition-transform"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                  {subCategories.length === 0 && (
                    <p className="text-[10px] text-outline font-bold uppercase tracking-widest italic opacity-60 ml-1">Optional: Add subcategories later</p>
                  )}
                </div>
              </div>

              <button
                type="submit"
                className="w-full py-5 bg-primary text-white font-black rounded-2xl shadow-xl shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center gap-3 text-sm uppercase tracking-[0.15em] mt-4"
              >
                Create Category
              </button>
            </form>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
