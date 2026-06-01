
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  IndianRupee, 
  MapPin, 
  Home, 
  CreditCard, 
  ShoppingBag, 
  TrendingUp, 
  CheckCircle2, 
  ChevronRight, 
  ChevronLeft,
  Search,
  Target,
  Upload,
  AlertTriangle,
  FileText
} from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency, CURRENCY_SYMBOL } from '../lib/utils';

import { analyzeStatementFile, AnalysisResult, ParseError } from '../lib/statementParser';
import { PdfPasswordModal } from '../components/PdfPasswordModal';
import { apiFetch } from '../lib/api';
import { activeUserId } from '../lib/activeUserId';

export const Onboarding: React.FC = () => {
  const { user, updateUser, categories, loadTransactions } = useAppContext();
  const [step, setStep] = useState(1);
  const totalSteps = 6;
  const [isUploading, setIsUploading] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [passwordModal, setPasswordModal] = useState<{ open: boolean; wrongPassword: boolean }>({ open: false, wrongPassword: false });
  const [uploadError, setUploadError] = useState<string | null>(null);

  const processFile = async (file: File, password?: string) => {
    setIsUploading(true);
    setUploadError(null);
    try {
      const { transactions } = await analyzeStatementFile(file, categories, password);

      const uid = activeUserId(user);
      if (uid) {
        const ingestRes = await apiFetch('/api/statement/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: uid,
            transactions: transactions.map((t) => ({
              transaction_date: t.date,
              amount: Math.abs(t.amount),
              transaction_type: t.type === 'income' ? 'Credit' : 'Debit',
              merchant_name: t.merchant,
              description: t.merchant,
              running_balance: null,
            })),
          }),
        });
        if (!ingestRes.ok) {
          throw new Error('Failed to save statement transactions to the database');
        }
        loadTransactions();
      }

      updateUser({ statementUploaded: true });

      setPendingFile(null);
      setPasswordModal({ open: false, wrongPassword: false });
      handleNext();
    } catch (err: any) {
      if (err?.type === 'password_required') {
        setPendingFile(file);
        setPasswordModal({ open: true, wrongPassword: false });
      } else if (err?.type === 'wrong_password') {
        setPasswordModal({ open: true, wrongPassword: true });
      } else {
        setUploadError(err?.message || 'Failed to parse the statement. Please try again.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
    e.target.value = '';
  };


  const handleNext = () => {
    if (step < totalSteps) setStep(step + 1);
    else updateUser({ onboarded: true });
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <motion.div 
            initial={{ opacity: 0, x: 20 }} 
            animate={{ opacity: 1, x: 0 }} 
            className="space-y-8"
          >
            <div className="space-y-2">
              <h2 className="text-3xl font-bold">What's your monthly income?</h2>
              <p className="text-outline">Help us calibrate your budget benchmarks.</p>
            </div>
            <div className="space-y-6">
              <div className="bg-surface-container-low p-8 rounded-2xl border border-outline-variant/30 flex flex-col items-center gap-6">
                <span className="text-5xl font-black text-primary">{formatCurrency(user.income)}</span>
                <input 
                  type="range" 
                  min="0" 
                  max="500000" 
                  step="1000"
                  value={user.income}
                  onChange={(e) => updateUser({ income: parseInt(e.target.value) })}
                  className="w-full h-3 bg-surface-container-high rounded-lg appearance-none cursor-pointer accent-primary"
                />
              </div>
              <div className="relative">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-outline font-bold">
                  {CURRENCY_SYMBOL}
                </div>
                <input 
                  type="number"
                  value={user.income || ''}
                  onChange={(e) => updateUser({ income: parseInt(e.target.value) || 0 })}
                  className="w-full pl-12 pr-4 py-4 bg-surface-container-lowest border border-outline-variant rounded-xl font-bold text-lg"
                  placeholder="Enter custom amount"
                />
              </div>
            </div>
          </motion.div>
        );
      case 2:
        return (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold">Which city tier do you live in?</h2>
              <p className="text-outline">Cost of living varies significantly by location.</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {['Metro', 'Tier 1', 'Tier 2', 'Tier 3'].map((tier) => (
                <button
                  key={tier}
                  onClick={() => updateUser({ cityTier: tier as any })}
                  className={cn(
                    "p-6 rounded-2xl border-2 transition-all text-left",
                    user.cityTier === tier 
                      ? "border-primary bg-primary/5 shadow-md" 
                      : "border-outline-variant hover:border-primary/50"
                  )}
                >
                  <MapPin className={cn("w-6 h-6 mb-3", user.cityTier === tier ? "text-primary" : "text-outline")} />
                  <span className="font-bold block">{tier}</span>
                  <span className="text-[10px] text-outline uppercase font-bold tracking-widest mt-1">
                    {tier === 'Metro' ? 'Highest Cost' : tier === 'Tier 1' ? 'Major City' : 'Developing'}
                  </span>
                </button>
              ))}
            </div>
          </motion.div>
        );
      case 3:
        return (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold">Fixed commitments?</h2>
              <p className="text-outline">Enter your monthly rent and overall debt/EMI payments.</p>
            </div>
            <div className="space-y-4">
              <div className="bg-surface-container-low p-6 rounded-2xl space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-outline uppercase tracking-widest px-1">Monthly Rent</label>
                  <div className="relative">
                    <div className="absolute left-4 top-1/2 -translate-y-1/2 text-outline font-bold">
                      {CURRENCY_SYMBOL}
                    </div>
                    <input 
                      type="number"
                      value={user.fixedRent || ''}
                      onChange={(e) => updateUser({ fixedRent: parseInt(e.target.value) || 0 })}
                      className="w-full pl-12 pr-4 py-4 bg-white border border-outline-variant rounded-xl font-bold"
                      placeholder="0.00"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-outline uppercase tracking-widest px-1">Active EMIs / Loans</label>
                  <div className="relative">
                    <div className="absolute left-4 top-1/2 -translate-y-1/2 text-outline font-bold">
                      {CURRENCY_SYMBOL}
                    </div>
                    <input 
                      type="number"
                      value={user.fixedEMI || ''}
                      onChange={(e) => updateUser({ fixedEMI: parseInt(e.target.value) || 0 })}
                      className="w-full pl-12 pr-4 py-4 bg-white border border-outline-variant rounded-xl font-bold"
                      placeholder="0.00"
                    />
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        );
      case 4:
        return (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold">Biggest spending category?</h2>
              <p className="text-outline">Where does most of your discretionary income go?</p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {[
                { name: 'Shopping', icon: ShoppingBag },
                { name: 'Travel', icon: Search },
                { name: 'Investments', icon: TrendingUp },
                { name: 'Food & Dining', icon: CheckCircle2 },
                { name: 'Entertainment', icon: Target },
                { name: 'Other', icon: ChevronRight },
              ].map((cat) => (
                <button
                  key={cat.name}
                  onClick={() => updateUser({ biggestCategory: cat.name })}
                  className={cn(
                    "p-6 rounded-2xl border-2 transition-all flex flex-col items-center gap-3",
                    user.biggestCategory === cat.name 
                      ? "border-primary bg-primary/5 shadow-md" 
                      : "border-outline-variant hover:border-primary/50"
                  )}
                >
                  <cat.icon className={cn("w-6 h-6", user.biggestCategory === cat.name ? "text-primary" : "text-outline")} />
                  <span className="font-bold text-sm">{cat.name}</span>
                </button>
              ))}
            </div>
          </motion.div>
        );
      case 5:
        return (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold">What's your primary goal?</h2>
              <p className="text-outline">Select the objective we should prioritize for you.</p>
            </div>
            <div className="space-y-3">
              {[
                'Save More Money',
                'Track Detailed Spending',
                'Reach a Specific Goal',
                'Optimize Investments'
              ].map((goal) => (
                <button
                  key={goal}
                  onClick={() => updateUser({ primaryGoal: goal })}
                  className={cn(
                    "w-full p-5 rounded-2xl border-2 transition-all text-left flex items-center justify-between",
                    user.primaryGoal === goal 
                      ? "border-primary bg-primary/5 shadow-sm" 
                      : "border-outline-variant hover:border-primary/50"
                  )}
                >
                  <span className="font-bold">{goal}</span>
                  {user.primaryGoal === goal && <CheckCircle2 className="text-primary w-5 h-5" />}
                </button>
              ))}
            </div>
          </motion.div>
        );
      case 6:
        return (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8 text-center">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold">Deepen your insights?</h2>
              <p className="text-outline">Upload your past 2-3 months of bank statements to unlock predictive forecasting immediately.</p>
            </div>
            
            <div className="bg-surface-container-low p-10 rounded-[32px] border-2 border-dashed border-outline-variant flex flex-col items-center gap-6 group hover:border-primary transition-all relative overflow-hidden">
               {isUploading ? (
                 <div className="flex flex-col items-center gap-4 py-8">
                   <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                   <p className="text-sm font-bold text-primary">Analyzing statements...</p>
                 </div>
               ) : (
                 <>
                   <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
                      <FileText className="w-10 h-10" />
                   </div>
                   <div className="space-y-1">
                      <p className="text-sm font-bold">Click to upload or drag & drop</p>
                      <p className="text-[10px] text-outline font-bold uppercase tracking-widest">PDF, CSV, or Excel files</p>
                   </div>
                   <input 
                      type="file" 
                      className="absolute inset-0 opacity-0 cursor-pointer" 
                      onChange={handleFileUpload}
                   />
                 </>
               )}
            </div>

            <div className="flex items-start gap-3 bg-primary/5 p-4 rounded-xl border border-primary/10 text-left">
               <AlertTriangle className="w-5 h-5 text-primary shrink-0 mt-0.5" />
               <p className="text-[11px] font-bold text-on-surface-variant leading-relaxed italic">
                 <span className="text-primary font-black uppercase tracking-wider mr-1">Disclaimer:</span> 
                 If statements are not uploaded, forecasting and deep insights will only be fully functional after we analyze 2 months of your ongoing transaction history.
               </p>
            </div>

            <button 
              onClick={handleNext}
              className="text-xs font-black text-outline uppercase tracking-widest hover:text-primary transition-colors"
            >
              Skip for now, I'll do it later
            </button>
          </motion.div>
        );
      default:
        return null;
    }
  };

  return (
    <>
      {/* Password modal for encrypted PDFs */}
      {passwordModal.open && pendingFile && (
        <PdfPasswordModal
          fileName={pendingFile.name}
          isWrongPassword={passwordModal.wrongPassword}
          onSubmit={(pw) => processFile(pendingFile, pw)}
          onCancel={() => {
            setPasswordModal({ open: false, wrongPassword: false });
            setPendingFile(null);
          }}
        />
      )}

      <div className="min-h-screen bg-surface flex items-center justify-center p-4">
        <div className="w-full max-w-xl bg-surface-container-lowest rounded-3xl shadow-2xl border border-outline-variant/30 overflow-hidden flex flex-col">
          {/* Progress Bar */}
          <div className="h-2 bg-surface-container-high flex">
            {Array.from({ length: totalSteps }).map((_, i) => (
              <div 
                key={i} 
                className={cn(
                  "flex-1 h-full transition-all duration-500",
                  i + 1 <= step ? "bg-primary" : "bg-transparent"
                )} 
              />
            ))}
          </div>

          <div className="p-10 flex-1">
            <div className="mb-12 flex justify-between items-center text-[10px] font-bold text-outline uppercase tracking-[0.2em]">
              <span>Step {step} of 5</span>
              <span className="text-primary tracking-normal font-black">FinAssist Setup</span>
            </div>

            {/* Upload error banner */}
            {uploadError && (
              <div className="mb-4 flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-xl text-error text-sm font-bold">
                {uploadError}
              </div>
            )}

            <div className="min-h-[400px]">
               {renderStep()}
            </div>
            
            <div className="flex gap-4 mt-12">
              {step > 1 && (
                <button 
                  onClick={handleBack}
                  className="flex-[0.5] flex items-center justify-center gap-2 py-4 bg-surface-container-high text-on-surface font-bold rounded-xl hover:brightness-95 transition-all"
                >
                  <ChevronLeft className="w-5 h-5" /> Back
                </button>
              )}
              <button 
                onClick={handleNext}
                disabled={step === 1 && user.income === 0}
                className="flex-1 flex items-center justify-center gap-2 py-4 bg-primary text-white font-bold rounded-xl shadow-lg hover:brightness-110 active:scale-95 transition-all disabled:opacity-50 disabled:grayscale"
              >
                {step === totalSteps ? 'Finish Setup' : 'Continue'} <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
