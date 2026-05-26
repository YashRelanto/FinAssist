import React, { useState } from 'react';
import { User, Mail, ArrowLeft, Loader2, CheckCircle2, Shield } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

export const EditProfile: React.FC = () => {
  const { user, updateUser, setCurrentPage } = useAppContext();

  // Local Form state pre-populated with context user data
  const [formData, setFormData] = useState({
    name: user.name || '',
    email: user.email || '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatus(null);

    // Basic Validation
    if (!formData.name.trim() || !formData.email.trim()) {
      setStatus({ type: 'error', message: 'All fields are required.' });
      setIsSubmitting(false);
      return;
    }

    try {
      if (user.userId) {
        // Sync with Backend database
        const res = await fetch(`http://localhost:8000/api/users/${user.userId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            full_name: formData.name,
            email: formData.email,
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
    <div className="max-w-xl mx-auto space-y-8 pb-20">
      <header>
        <button 
          onClick={() => setCurrentPage('dashboard')}
          className="flex items-center gap-2 text-xs font-black text-primary uppercase tracking-widest hover:underline mb-2 transition-all active:scale-95"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Dashboard
        </button>
        <h2 className="text-3xl font-bold text-on-surface">Edit Profile</h2>
        <p className="text-on-surface-variant font-medium text-sm mt-1">Manage your public name and credentials securely connected to your ledger database.</p>
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
        <form onSubmit={handleSubmit} className="space-y-6">
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

          <div className="p-4 bg-primary/5 rounded-2xl border border-primary/10 flex items-start gap-3">
            <Shield className="w-5 h-5 text-primary shrink-0 mt-0.5" />
            <p className="text-[10px] text-outline font-bold uppercase tracking-wider leading-relaxed">
              Updating your email will keep your credentials synchronized. Authentication settings can be managed under settings menu.
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
