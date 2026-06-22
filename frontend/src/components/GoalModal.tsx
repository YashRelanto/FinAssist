
import React, { useState, useEffect, useMemo } from 'react';
import { X, Target, Calendar, Info, Landmark, TrendingUp, PiggyBank, Link2, Check } from 'lucide-react';
import { Goal, FundingSource, FundingSourceType } from '../types';
import { useAppContext } from '../context/AppContext';
import { CURRENCY_SYMBOL, formatCurrency } from '../lib/utils';
import { AppModal } from './AppModal';

interface GoalModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingGoal?: Goal & { funding_sources?: FundingSource[] };
}

const colors = [
  { name: 'PrimaryBlue', class: 'bg-primary' },
  { name: 'SecondaryGreen', class: 'bg-secondary' },
  { name: 'TertiaryOrange', class: 'bg-tertiary' },
  { name: 'ErrorRed', class: 'bg-error' },
  { name: 'OutlineGrey', class: 'bg-outline' },
];

interface SourceOption {
  type: FundingSourceType;
  id: string;
  name: string;
  current_value: number;
  meta?: string;
}

const SOURCE_GROUPS: {
  type: FundingSourceType;
  label: string;
  icon: typeof Landmark;
}[] = [
  { type: 'account', label: 'Bank Accounts', icon: Landmark },
  { type: 'mutual_fund', label: 'Mutual Funds', icon: TrendingUp },
  { type: 'fixed_deposit', label: 'Fixed Deposits', icon: PiggyBank },
];

export const GoalModal: React.FC<GoalModalProps> = ({ isOpen, onClose, editingGoal }) => {
  const {
    addGoal,
    updateGoal,
    accounts,
    loadAccounts,
    investmentsData,
    fixedDepositsData,
    loadInvestments,
    loadFixedDeposits,
  } = useAppContext();
  const [formData, setFormData] = useState<Omit<Goal, 'id'>>({
    label: '',
    sub: '',
    current: 0,
    target: 0,
    date: new Date().toISOString().split('T')[0],
    icon: 'Target',
    color: 'bg-primary',
    fundingSources: [],
  });

  // Load goal being edited (supports both camelCase and the API's snake_case field)
  useEffect(() => {
    if (editingGoal) {
      const linked =
        editingGoal.fundingSources || editingGoal.funding_sources || [];
      setFormData({
        label: editingGoal.label,
        sub: editingGoal.sub,
        current: editingGoal.current,
        target: editingGoal.target,
        date: editingGoal.date,
        icon: editingGoal.icon,
        color: editingGoal.color,
        fundingSources: linked.map((s) => ({ type: s.type, id: s.id, name: s.name })),
      });
    } else {
      setFormData({
        label: '',
        sub: '',
        current: 0,
        target: 0,
        date: new Date().toISOString().split('T')[0],
        icon: 'Target',
        color: 'bg-primary',
        fundingSources: [],
      });
    }
  }, [editingGoal, isOpen]);

  // Reuse the app-wide cached money sources; only triggers a network call if the
  // cache is empty/stale (e.g. the user hasn't opened the Investments tab yet).
  useEffect(() => {
    if (!isOpen) return;
    loadAccounts();
    void loadInvestments();
    void loadFixedDeposits();
  }, [isOpen, loadAccounts, loadInvestments, loadFixedDeposits]);

  const mfOptions: SourceOption[] = useMemo(() => {
    const holdings = investmentsData?.holdings;
    if (!Array.isArray(holdings)) return [];
    return holdings.map((h: any) => ({
      type: 'mutual_fund' as const,
      id: String(h.ticker),
      name: h.name || String(h.ticker),
      current_value: Number(h.current_value) || 0,
      meta: `NAV ${formatCurrency(Number(h.current_nav) || 0)}`,
    }));
  }, [investmentsData]);

  const fdOptions: SourceOption[] = useMemo(() => {
    const list = fixedDepositsData?.fixed_deposits;
    if (!Array.isArray(list)) return [];
    return list.map((f: any) => ({
      type: 'fixed_deposit' as const,
      id: String(f.fd_id),
      name: f.label || f.bank_name || 'Fixed Deposit',
      current_value: Number(f.current_value) || 0,
      meta: f.bank_name && f.label ? f.bank_name : undefined,
    }));
  }, [fixedDepositsData]);

  const accountOptions: SourceOption[] = useMemo(
    () =>
      (accounts || [])
        .filter((a: any) => a.account_type !== 'credit_card')
        .map((a: any) => ({
          type: 'account' as const,
          id: String(a.account_id),
          name: a.account_name || 'Account',
          current_value: Number(a.current_balance) || 0,
          meta: a.bank_name || a.account_type,
        })),
    [accounts],
  );

  const optionsByType: Record<FundingSourceType, SourceOption[]> = {
    account: accountOptions,
    mutual_fund: mfOptions,
    fixed_deposit: fdOptions,
  };

  // Only show the loading state on a true cold start (nothing cached yet).
  const sourcesLoading =
    investmentsData === null &&
    fixedDepositsData === null &&
    (accounts?.length ?? 0) === 0;

  const selected = formData.fundingSources || [];
  const isSelected = (type: FundingSourceType, id: string) =>
    selected.some((s) => s.type === type && s.id === id);

  const toggleSource = (opt: SourceOption) => {
    setFormData((prev) => {
      const list = prev.fundingSources || [];
      const exists = list.some((s) => s.type === opt.type && s.id === opt.id);
      const next = exists
        ? list.filter((s) => !(s.type === opt.type && s.id === opt.id))
        : [...list, { type: opt.type, id: opt.id, name: opt.name }];
      return { ...prev, fundingSources: next };
    });
  };

  const linkedTotal = useMemo(() => {
    if (!selected.length) return 0;
    let total = 0;
    for (const s of selected) {
      const opt = optionsByType[s.type]?.find((o) => o.id === s.id);
      if (opt) total += opt.current_value;
    }
    return total;
  }, [selected, accountOptions, mfOptions, fdOptions]);

  const hasLinks = selected.length > 0;

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: Omit<Goal, 'id'> = {
      ...formData,
      // Linked goals derive their saved amount from live source values (computed server-side).
      current: hasLinks ? linkedTotal : formData.current,
    };
    if (editingGoal) {
      updateGoal(editingGoal.id, payload);
    } else {
      addGoal(payload);
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
                  required={!hasLinks}
                  disabled={hasLinks}
                  type="number" 
                  value={hasLinks ? Number(linkedTotal.toFixed(2)) : (formData.current || '')}
                  onChange={(e) => setFormData({...formData, current: parseFloat(e.target.value)})}
                  placeholder="0.00" 
                  className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm font-bold disabled:opacity-70 disabled:cursor-not-allowed" 
                />
                {hasLinks && (
                  <p className="text-[9px] text-secondary font-bold uppercase tracking-wider mt-1">
                    Auto-updated from linked sources
                  </p>
                )}
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

            {/* ── Funding sources ─────────────────────────────────────────── */}
            <div className="pt-1">
              <div className="flex items-center justify-between mb-2">
                <label className="flex items-center gap-1.5 text-[10px] font-bold text-outline uppercase tracking-widest">
                  <Link2 className="w-3.5 h-3.5" /> Money Sources (optional)
                </label>
                {hasLinks && (
                  <span className="text-[10px] font-bold text-primary">
                    {selected.length} linked · {formatCurrency(linkedTotal)}
                  </span>
                )}
              </div>
              <p className="text-[10px] text-outline font-medium mb-3 leading-relaxed">
                Link accounts, mutual funds, or FDs and this goal's progress tracks
                their live value automatically.
              </p>

              {sourcesLoading ? (
                <div className="py-6 text-center text-xs text-outline font-medium">
                  Loading your money sources…
                </div>
              ) : (
                <div className="space-y-4">
                  {SOURCE_GROUPS.map((group) => {
                    const opts = optionsByType[group.type];
                    const GroupIcon = group.icon;
                    return (
                      <div key={group.type}>
                        <div className="flex items-center gap-1.5 mb-2">
                          <GroupIcon className="w-3.5 h-3.5 text-primary" />
                          <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">
                            {group.label}
                          </span>
                        </div>
                        {opts.length === 0 ? (
                          <p className="text-[10px] text-outline/70 font-medium pl-5 pb-1">
                            None added yet.
                          </p>
                        ) : (
                          <div className="space-y-1.5">
                            {opts.map((opt) => {
                              const checked = isSelected(opt.type, opt.id);
                              return (
                                <button
                                  type="button"
                                  key={`${opt.type}-${opt.id}`}
                                  onClick={() => toggleSource(opt)}
                                  className={`w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border-2 text-left transition-all ${
                                    checked
                                      ? 'border-primary bg-primary/5'
                                      : 'border-outline-variant/40 hover:border-primary/40'
                                  }`}
                                >
                                  <div className="flex items-center gap-3 min-w-0">
                                    <div
                                      className={`w-5 h-5 rounded-md flex items-center justify-center shrink-0 transition-all ${
                                        checked
                                          ? 'bg-primary text-white'
                                          : 'bg-surface-container-high text-transparent'
                                      }`}
                                    >
                                      <Check className="w-3.5 h-3.5" />
                                    </div>
                                    <div className="min-w-0">
                                      <p className="text-xs font-bold text-on-surface truncate">
                                        {opt.name}
                                      </p>
                                      {opt.meta && (
                                        <p className="text-[10px] text-outline font-medium truncate">
                                          {opt.meta}
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                  <span className="text-xs font-bold text-on-surface shrink-0 font-tabular">
                                    {formatCurrency(opt.current_value)}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
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
