import React, { useState } from 'react';
import { User, Bell, Shield, CreditCard, Globe, Zap, Flame, Trophy, Smartphone, Lock, Eye, Fingerprint, FileText, Upload, AlertTriangle, Sparkles } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency, CURRENCY_SYMBOL } from '../lib/utils';
import { 
  format, 
  startOfYear, 
  eachDayOfInterval, 
  endOfYear, 
  getDay, 
  startOfMonth, 
  endOfMonth, 
  eachMonthOfInterval 
} from 'date-fns';

import { analyzeStatementFile } from '../lib/statementParser';
import { PdfPasswordModal } from '../components/PdfPasswordModal';
import { apiFetch } from '../lib/api';
import { activeUserId } from '../lib/activeUserId';
import { PageHeader, PageShell, lumio } from '../components/PageShell';

export const Settings: React.FC = () => {
  const { 
    user,
    updateUser,
    heatmapData, 
    categories,
    navigateToAddTransaction,
    loadTransactions,
    setCurrentPage
  } = useAppContext();

  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [passwordModal, setPasswordModal] = useState<{ open: boolean; wrongPassword: boolean }>({ open: false, wrongPassword: false });
  const [uploadStatus, setUploadStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const processFile = async (file: File, password?: string) => {
    setUploadStatus(null);
    try {
      const uid = activeUserId(user);
      const { transactions, summary } = await analyzeStatementFile(file, categories, password, uid || undefined);

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
      setUploadStatus({
        type: 'success',
        message: `✓ Parsed ${transactions.length} transactions — ${summary.totalCategorized} categorized, ${summary.totalUnknown} unknown, ${summary.highAmountAnomalies} anomalies.`,
      });
    } catch (err: any) {
      if (err?.type === 'password_required') {
        setPendingFile(file);
        setPasswordModal({ open: true, wrongPassword: false });
      } else if (err?.type === 'wrong_password') {
        setPasswordModal({ open: true, wrongPassword: true });
      } else {
        setUploadStatus({ type: 'error', message: err?.message || 'Failed to parse the statement.' });
      }
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    processFile(file);
    e.target.value = '';
  };

  // Simple streak calculation (mock or based on heatmapData)
  const currentStreak = 14; 
  const totalDaysActive = heatmapData.filter(d => d.count > 0).length;

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
      <PageShell className="max-w-5xl">
      <PageHeader
        title="Settings & Profile"
        description="Configure your personal assistant and view your financial activity streaks."
      />

      {/* Streak Maintainer Heatmap */}
      <section className="bg-surface-container-lowest p-8 rounded-2xl border border-outline-variant/30 soft-shadow">
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-error-container/20 text-error rounded-xl">
              <Flame className="w-6 h-6 fill-current" />
            </div>
            <div>
              <h3 className="text-xl font-bold">Streak Maintainer</h3>
              <p className="text-xs text-outline font-bold uppercase tracking-widest mt-0.5">Don't miss a day of tracking!</p>
            </div>
          </div>
          <div className="flex gap-8">
            <div className="text-center">
              <p className="text-2xl font-black text-on-surface">{currentStreak}</p>
              <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Current Streak</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-black text-secondary">{totalDaysActive}</p>
              <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Days Logged</p>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex overflow-x-auto pb-6 gap-8 scrollbar-hide">
            {/* Day Labels */}
            <div className="flex flex-col justify-between py-6 text-[9px] font-bold text-outline uppercase tracking-wider h-[84px] sticky left-0 bg-surface-container-lowest pr-2 z-10">
              <span className="h-3 leading-none">Mon</span>
              <span className="h-3 leading-none">Wed</span>
              <span className="h-3 leading-none">Fri</span>
            </div>

            {eachMonthOfInterval({
              start: startOfYear(new Date()),
              end: endOfYear(new Date())
            }).map((month) => {
              const monthStart = startOfMonth(month);
              const monthEnd = endOfMonth(month);
              const monthDays = eachDayOfInterval({ start: monthStart, end: monthEnd });
              const monthLabel = format(month, 'MMM');
              
              // Calculate empty cells for the first week to align days correctly
              const firstDayOffset = (getDay(monthStart) + 6) % 7; // Adjusting to start week on Monday

              return (
                <div key={monthLabel} className="flex flex-col gap-3 min-w-max">
                  <p className="text-[10px] font-bold text-outline uppercase tracking-widest text-center">{monthLabel}</p>
                  <div className="grid grid-rows-7 grid-flow-col gap-1.5 h-[84px]">
                    {/* Empty cells for offset */}
                    {Array.from({ length: firstDayOffset }).map((_, i) => (
                      <div key={`empty-${i}`} className="w-2.5 h-2.5" />
                    ))}
                    
                    {monthDays.map((date) => {
                      const dStr = format(date, 'yyyy-MM-dd');
                      const dayData = heatmapData.find(d => d.date === dStr);
                      const count = dayData ? dayData.count : 0;
                      const level = count === 0 ? 0 : count < 3 ? 1 : count < 6 ? 2 : 3;
                      const isToday = dStr === format(new Date(), 'yyyy-MM-dd');
                      
                      return (
                        <button 
                          key={dStr}
                          onClick={() => navigateToAddTransaction(dStr)}
                          title={`${dStr}: ${count} records`}
                          className={cn(
                            "w-2.5 h-2.5 rounded-sm transition-all hover:ring-2 hover:ring-primary relative",
                            level === 0 ? 'bg-[#EBEDF0]' :
                            level === 1 ? 'bg-[#9BE9A8]' :
                            level === 2 ? 'bg-[#40C463]' : 'bg-[#216E39]',
                            isToday && "ring-2 ring-orange-500 ring-offset-1"
                          )}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          
          <div className="flex items-center justify-center gap-4 text-[10px] font-bold text-outline uppercase tracking-widest pt-4 border-t border-outline-variant/10">
            <span>Less</span>
            <div className="flex gap-1.5 items-center">
              {[0, 1, 2, 3].map((lvl) => (
                <div key={lvl} className="flex items-center gap-1.5">
                  <div className={cn(
                    "w-3 h-3 rounded-sm",
                    lvl === 0 ? 'bg-[#EBEDF0]' :
                    lvl === 1 ? 'bg-[#9BE9A8]' :
                    lvl === 2 ? 'bg-[#40C463]' : 'bg-[#216E39]'
                  )} />
                  <span className="text-[9px] text-outline/60 lowercase">
                    {lvl === 0 ? '0' : lvl === 1 ? '1-2' : lvl === 2 ? '3-5' : '5+'}
                  </span>
                </div>
              ))}
            </div>
            <span>More</span>
          </div>
        </div>
      </section>

       

      {/* Bank Statement Upload Section */}
      <section className="bg-surface-container-lowest p-8 rounded-2xl border border-outline-variant/30 soft-shadow">
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-secondary-container/20 text-secondary rounded-xl">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-xl font-bold">Bank Statement Hub</h3>
              <p className="text-xs text-outline font-bold uppercase tracking-widest mt-0.5">Upload historical data for better forecasting.</p>
            </div>
          </div>
          {user.statementUploaded && (
            <div className="flex items-center gap-2 text-secondary px-4 py-2 bg-secondary/5 rounded-full border border-secondary/10">
              <Sparkles className="w-4 h-4" />
              <span className="text-[10px] font-black uppercase tracking-widest">History Synced</span>
            </div>
          )}
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          <div className="flex-1">
             <div className="bg-surface-container-low p-8 rounded-[32px] border-2 border-dashed border-outline-variant flex flex-col items-center gap-4 group hover:border-primary transition-all relative overflow-hidden text-center">
                <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
                   <Upload className="w-8 h-8" />
                </div>
                <div>
                   <p className="text-sm font-bold">Upload bank statements (2-3 months)</p>
                   <p className="text-[10px] text-outline font-bold uppercase tracking-widest mt-1">PDF or CSV formats only</p>
                </div>
                <input 
                   type="file" 
                   className="absolute inset-0 opacity-0 cursor-pointer" 
                   onChange={handleFileUpload}
                />
             </div>
             {/* Upload status banner */}
             {uploadStatus && (
               <div className={`mt-3 px-4 py-3 rounded-xl text-sm font-bold ${
                 uploadStatus.type === 'success'
                   ? 'bg-secondary/10 border border-secondary/20 text-secondary'
                   : 'bg-error/10 border border-error/20 text-error'
               }`}>
                 {uploadStatus.message}
               </div>
             )}
          </div>
          <div className="lg:w-1/3 flex flex-col justify-center gap-4">
             <div className="flex items-start gap-3 bg-primary/5 p-4 rounded-xl border border-primary/10">
                <AlertTriangle className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                <p className="text-[11px] font-bold text-on-surface-variant leading-relaxed">
                  <span className="text-primary font-black uppercase tracking-wider mr-1">Note:</span> 
                  If not uploaded, forecasting will only work after 2 months of active use. 
                </p>
             </div>
             <p className="text-[10px] text-outline font-bold uppercase tracking-widest leading-relaxed">
               Historical data allows FinAssist AI to analyze your seasonality, recurring bills, and irregular spending spikes from the past.
             </p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {[
          { icon: Bell, label: 'Notifications', desc: 'Spending alert triggers.' },
          { icon: Lock, label: 'App Password', desc: 'Pin based login access.' },
          { icon: Fingerprint, label: 'Fingerprint Lock', desc: 'Biometric security layer.' },
          { icon: CreditCard, label: 'Linked Accounts', desc: 'Plaid & Bank connections.' },
        ].map((item, i) => (
          <button 
            key={i} 
            onClick={() => {
              if (item.label === 'Linked Accounts') {
                setCurrentPage('linked-accounts');
              }
            }}
            className="flex items-center justify-between p-6 bg-surface-container-lowest border border-outline-variant/30 rounded-2xl soft-shadow hover:bg-surface-container-low transition-all group text-left"
          >
            <div className="flex items-center gap-5">
              <div className="w-10 h-10 rounded-xl bg-surface-container-high flex items-center justify-center text-primary group-hover:bg-white transition-colors">
                <item.icon className="w-5 h-5" />
              </div>
              <div>
                <h4 className="font-bold text-on-surface">{item.label}</h4>
                <p className="text-[10px] text-outline font-bold uppercase tracking-widest mt-0.5">{item.desc}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
      </PageShell>
    </>
  );
};
