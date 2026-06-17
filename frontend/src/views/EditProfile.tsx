import React, { useState } from 'react';
import { User, Mail, ArrowLeft, Loader2, CheckCircle2, Shield, DollarSign, Building, Home, CreditCard, Compass, Sparkles } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { apiFetch } from '../lib/api';

export const EditProfile: React.FC = () => {
  const { user, updateUser, setCurrentPage } = useAppContext();

  // Local Form state pre-populated with context user data
  const [formData, setFormData] = useState({
    name: user.name || '',
    email: user.email || '',
    income: user.income || 0,
    cityTier: user.cityTier || 'Metro',
    fixedRent: user.fixedRent || 0,
    fixedEMI: user.fixedEMI || 0,
    biggestCategory: user.biggestCategory || '',
    primaryGoal: user.primaryGoal || '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatus(null);

    // Basic Validation
    if (!formData.name.trim() || !formData.email.trim()) {
      setStatus({ type: 'error', message: 'Name and Email are required.' });
      setIsSubmitting(false);
      return;
    }

    try {
      if (user.userId) {
        // Sync with Backend database
        const res = await apiFetch(`/api/users/${user.userId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: formData.name,
            email: formData.email,
            income: Number(formData.income),
            city_tier: formData.cityTier,
            fixed_rent: Number(formData.fixedRent),
            fixed_emi: Number(formData.fixedEMI),
            biggest_category: formData.biggestCategory,
            primary_goal: formData.primaryGoal,
          }),
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
          throw new Error(data.detail || 'Failed to update profile on server.');
        }
      }

      // Sync React App State Context
      updateUser({
        name: formData.name,
        email: formData.email,
        income: Number(formData.income),
        cityTier: formData.cityTier as any,
        fixedRent: Number(formData.fixedRent),
        fixedEMI: Number(formData.fixedEMI),
        biggestCategory: formData.biggestCategory,
        primaryGoal: formData.primaryGoal,
      });

      setStatus({ type: 'success', message: 'Profile updated successfully!' });
    } catch (err: any) {
      console.error(err);
      setStatus({ type: 'error', message: err.message || 'Something went wrong. Please try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8 pb-20">
      <header>
        <button 
          onClick={() => setCurrentPage('dashboard')}
          className="flex items-center gap-2 text-xs font-black text-primary uppercase tracking-widest hover:underline mb-2 transition-all active:scale-95"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Dashboard
        </button>
        <h2 className="text-3xl font-bold text-on-surface">Edit Profile</h2>
        <p className="text-on-surface-variant font-medium text-sm mt-1">Manage your public credentials and financial settings securely connected to your ledger database.</p>
      </header>

      {status && (
        <div className={`p-4 rounded-2xl border text-xs font-bold flex items-center gap-3 animate-in fade-in duration-300 ${
          status.type === 'success'
            ? 'bg-secondary/10 border-secondary/20 text-secondary'
            : 'bg-error/10 border-error/20 text-error'
        }`}>
          {status.type === 'success' && <CheckCircle2 className="w-5 h-5 shrink-0" />}
          <span>{status.message}</span>
        </div>
      )}

      <section className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 soft-shadow">
        <form onSubmit={handleSubmit} className="space-y-8">
          
          {/* Section 1: Basic Info */}
          <div className="space-y-4">
            <h3 className="text-xs font-black text-primary uppercase tracking-widest">Personal Details</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Full Name</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <User className="w-4 h-4" />
                  </span>
                  <input 
                    required
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. Alex Thompson"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Email Address</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <Mail className="w-4 h-4" />
                  </span>
                  <input 
                    required
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. alex@example.com"
                  />
                </div>
              </div>
            </div>
          </div>

          <hr className="border-outline-variant/30" />

          {/* Section 2: Financial Metrics */}
          <div className="space-y-4">
            <h3 className="text-xs font-black text-primary uppercase tracking-widest">Financial Configuration</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Monthly Income ($)</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <DollarSign className="w-4 h-4" />
                  </span>
                  <input 
                    type="number"
                    value={formData.income}
                    onChange={(e) => setFormData({ ...formData, income: Number(e.target.value) })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. 5000"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">City Tier</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <Building className="w-4 h-4" />
                  </span>
                  <select 
                    value={formData.cityTier}
                    onChange={(e) => setFormData({ ...formData, cityTier: e.target.value })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface appearance-none"
                  >
                    <option value="Metro">Metro</option>
                    <option value="Tier 1">Tier 1</option>
                    <option value="Tier 2">Tier 2</option>
                    <option value="Tier 3">Tier 3</option>
                  </select>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Fixed Monthly Rent ($)</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <Home className="w-4 h-4" />
                  </span>
                  <input 
                    type="number"
                    value={formData.fixedRent}
                    onChange={(e) => setFormData({ ...formData, fixedRent: Number(e.target.value) })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. 1200"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Fixed Monthly EMIs ($)</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <CreditCard className="w-4 h-4" />
                  </span>
                  <input 
                    type="number"
                    value={formData.fixedEMI}
                    onChange={(e) => setFormData({ ...formData, fixedEMI: Number(e.target.value) })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. 400"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Biggest Expense Category</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <Compass className="w-4 h-4" />
                  </span>
                  <input 
                    type="text"
                    value={formData.biggestCategory}
                    onChange={(e) => setFormData({ ...formData, biggestCategory: e.target.value })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. Shopping or Food"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1 block">Primary Goal</label>
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-outline">
                    <Sparkles className="w-4 h-4" />
                  </span>
                  <input 
                    type="text"
                    value={formData.primaryGoal}
                    onChange={(e) => setFormData({ ...formData, primaryGoal: e.target.value })}
                    className="w-full pl-12 pr-4 py-3.5 bg-surface-container-low border border-outline-variant/50 rounded-xl font-bold text-sm focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                    placeholder="e.g. Save Emergency Fund"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="p-4 bg-primary/5 rounded-2xl border border-primary/10 flex items-start gap-3">
            <Shield className="w-5 h-5 text-primary shrink-0 mt-0.5" />
            <p className="text-[10px] text-outline font-bold uppercase tracking-wider leading-relaxed">
              Updating your personal & financial metrics keeps your recommendations customized. Settings are encrypted & private.
            </p>
          </div>

          <div className="pt-4 border-t border-outline-variant/20 flex gap-4">
            <button
              type="button"
              onClick={() => setCurrentPage('dashboard')}
              className="flex-1 py-3.5 bg-surface-container-low hover:bg-surface-container-high text-on-surface font-extrabold text-xs rounded-2xl active:scale-[0.98] transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 py-3.5 bg-primary text-white font-extrabold text-xs rounded-2xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                'Save Changes'
              )}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
};
