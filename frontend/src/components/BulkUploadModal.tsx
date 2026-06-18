import React, { useState } from 'react';
import { X, Upload, FileText, AlertTriangle, CheckCircle2, ChevronRight, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { analyzeStatementFile, AnalysisResult } from '../lib/statementParser';
import { PdfPasswordModal } from './PdfPasswordModal';
import { AppModal } from './AppModal';
import { apiFetch } from '../lib/api';
import { cn, formatCurrency } from '../lib/utils';
import { activeUserId } from '../lib/activeUserId';

interface BulkUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const BulkUploadModal: React.FC<BulkUploadModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const { user, categories } = useAppContext();
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [passwordModal, setPasswordModal] = useState<{ open: boolean; wrongPassword: boolean }>({ open: false, wrongPassword: false });
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [accountName, setAccountName] = useState('Bank Statement');

  if (!isOpen) return null;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPendingFile(file);
    processFile(file);
    e.target.value = ''; // Reset file input
  };

  const processFile = async (file: File, password?: string) => {
    setIsAnalyzing(true);
    setUploadError(null);
    try {
      const result = await analyzeStatementFile(file, categories, password);
      setAnalysisResult(result);
      if (result.bankName) {
        const shortNum = result.accountNumber && result.accountNumber !== 'UNKNOWN' && result.accountNumber !== 'XXXXXX'
          ? ` *${result.accountNumber.slice(-4)}`
          : '';
        setAccountName(`${result.bankName}${shortNum}`);
      }
      setPasswordModal({ open: false, wrongPassword: false });
    } catch (err: any) {
      if (err?.type === 'password_required') {
        setPasswordModal({ open: true, wrongPassword: false });
      } else if (err?.type === 'wrong_password') {
        setPasswordModal({ open: true, wrongPassword: true });
      } else {
        setUploadError(err?.message || 'Failed to parse the statement. Please try again.');
        setPendingFile(null);
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleIngest = async () => {
    if (!analysisResult) return;
    setIsIngesting(true);
    setUploadError(null);

    const uid = activeUserId(user);
    if (!uid) {
      setUploadError("Authentication required.");
      setIsIngesting(false);
      return;
    }

    try {
      const ingestRes = await apiFetch('/api/statement/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: uid,
          account_name: accountName,
          bank_name: analysisResult.bankName,
          account_number: analysisResult.accountNumber,
          account_holder: analysisResult.accountHolder,
          ifsc: analysisResult.ifsc,
          transactions: analysisResult.transactions.map((t) => ({
            transaction_date: t.date,
            amount: Math.abs(t.amount),
            transaction_type: t.type === 'income' ? 'Credit' : 'Debit',
            merchant_name: t.merchant,
            description: t.merchant,
            running_balance: t.runningBalance,
            category: t.category,
            sub_category: t.subCategory,
          })),
        }),
      });

      const resData = await ingestRes.json();
      if (!ingestRes.ok || !resData.success) {
        throw new Error(resData.detail || 'Failed to save statement transactions to the database');
      }

      onSuccess();
      handleClose();
    } catch (err: any) {
      setUploadError(err?.message || 'Failed to import transactions. Please try again.');
    } finally {
      setIsIngesting(false);
    }
  };

  const handleClose = () => {
    setPendingFile(null);
    setAnalysisResult(null);
    setUploadError(null);
    setPasswordModal({ open: false, wrongPassword: false });
    onClose();
  };

  // Calculate totals for preview dashboard
  const totalTransactions = analysisResult?.transactions.length || 0;
  const totalCredits = analysisResult?.transactions.filter(t => t.type === 'income').reduce((acc, t) => acc + Math.abs(t.amount), 0) || 0;
  const totalDebits = analysisResult?.transactions.filter(t => t.type === 'expense').reduce((acc, t) => acc + Math.abs(t.amount), 0) || 0;
  const netFlow = totalCredits - totalDebits;

  return (
    <>
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

      <AppModal isOpen={isOpen} onClose={handleClose} className={cn(analysisResult ? 'max-w-3xl' : 'max-w-md')}>
        <div className={cn(
          "bg-surface-container-lowest w-full rounded-[28px] shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col transform transition-all scale-100",
          analysisResult ? "max-h-[85vh]" : ""
        )}>
          {/* Header */}
          <div className="px-8 py-5 border-b border-outline-variant/20 flex justify-between items-center bg-surface-container-low">
            <div>
              <h3 className="text-xl font-black text-on-surface tracking-tight">Bulk Statement Upload</h3>
              <p className="text-[10px] text-outline font-bold uppercase tracking-wider mt-0.5">
                {analysisResult ? `Previewing parsed file: ${pendingFile?.name}` : 'Instantly ingest months of transaction history'}
              </p>
            </div>
            <button 
              onClick={handleClose} 
              className="p-2 hover:bg-surface-container-high rounded-full text-outline hover:text-on-surface transition-all active:scale-90"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Error Banner */}
          {uploadError && (
            <div className="mx-8 mt-6 p-4 bg-error-container/10 border border-error-container/30 text-error text-xs font-bold rounded-xl flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}

          {/* Modal Body */}
          <div className="p-8 overflow-y-auto flex-1">
            {!analysisResult ? (
              // Step 1: Upload Dropzone
              <div className="space-y-6">
                {isAnalyzing ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-4">
                    <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
                    <div className="text-center space-y-1">
                      <p className="text-sm font-bold text-primary">Analyzing bank statement...</p>
                      <p className="text-[10px] text-outline font-bold uppercase tracking-widest">Running optical character recognition & parsing engines</p>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="bg-surface-container-low p-10 rounded-[32px] border-2 border-dashed border-outline-variant flex flex-col items-center gap-6 group hover:border-primary transition-all relative overflow-hidden">
                      <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
                        <Upload className="w-10 h-10" />
                      </div>
                      <div className="space-y-1 text-center">
                        <p className="text-sm font-bold">Click to upload or drag & drop bank statement</p>
                        <p className="text-[10px] text-outline font-bold uppercase tracking-widest">Supports PDF and CSV bank formats</p>
                      </div>
                      <input 
                        type="file" 
                        accept=".pdf,.csv"
                        className="absolute inset-0 opacity-0 cursor-pointer" 
                        onChange={handleFileUpload}
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="block text-[10px] font-black text-outline uppercase tracking-widest px-1">Import into Account Name</label>
                      <input 
                        type="text" 
                        value={accountName}
                        onChange={(e) => setAccountName(e.target.value)}
                        placeholder="e.g. Chase Statement, HDFC Bank" 
                        className="w-full px-5 py-4 bg-surface-container-low rounded-2xl border border-outline-variant/50 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all text-sm font-bold text-on-surface" 
                      />
                    </div>

                    <div className="flex items-start gap-3 bg-primary/5 p-4 rounded-xl border border-primary/10">
                      <AlertTriangle className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                      <p className="text-[11px] font-bold text-on-surface-variant leading-relaxed">
                        <span className="text-primary font-black uppercase tracking-wider mr-1">Smart Engine:</span> 
                        FinAssist AI automatically parses transactional columns, auto-categorizes merchant descriptions, and screens for anomalies dynamically.
                      </p>
                    </div>
                  </>
                )}
              </div>
            ) : (
              // Step 2: Live Statement Preview Dashboard
              <div className="space-y-6">
                {/* Stats Dashboard */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-surface-container-low p-5 rounded-2xl border border-outline-variant/20 flex flex-col justify-between">
                    <span className="text-[9px] font-bold text-outline uppercase tracking-widest">Transactions</span>
                    <span className="text-2xl font-black text-on-surface mt-2">{totalTransactions}</span>
                  </div>

                  <div className="bg-surface-container-low p-5 rounded-2xl border border-outline-variant/20 flex flex-col justify-between">
                    <span className="text-[9px] font-bold text-outline uppercase tracking-widest">Total Credits</span>
                    <span className="text-2xl font-black text-success mt-2 flex items-center gap-1">
                      <TrendingUp className="w-5 h-5 shrink-0" />
                      {formatCurrency(totalCredits)}
                    </span>
                  </div>

                  <div className="bg-surface-container-low p-5 rounded-2xl border border-outline-variant/20 flex flex-col justify-between">
                    <span className="text-[9px] font-bold text-outline uppercase tracking-widest">Total Debits</span>
                    <span className="text-2xl font-black text-error mt-2 flex items-center gap-1">
                      <TrendingDown className="w-5 h-5 shrink-0" />
                      {formatCurrency(totalDebits)}
                    </span>
                  </div>

                  <div className="bg-surface-container-low p-5 rounded-2xl border border-outline-variant/20 flex flex-col justify-between">
                    <span className="text-[9px] font-bold text-outline uppercase tracking-widest">Net Flow</span>
                    <span className={cn(
                      "text-2xl font-black mt-2",
                      netFlow >= 0 ? "text-success" : "text-error"
                    )}>
                      {netFlow >= 0 ? '+' : ''}{formatCurrency(netFlow)}
                    </span>
                  </div>
                </div>

                {/* Summary Alert banner */}
                {analysisResult.summary.highAmountAnomalies > 0 && (
                  <div className="bg-error/5 p-4 rounded-xl border border-error/20 flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 text-error shrink-0" />
                    <p className="text-xs font-bold text-on-surface-variant">
                      Detected <span className="text-error font-extrabold">{analysisResult.summary.highAmountAnomalies} large transactions</span> exceeding {formatCurrency(5000)}. These are flagged with warning icons in the list below.
                    </p>
                  </div>
                )}

                {/* Table Preview */}
                <div className="border border-outline-variant/30 rounded-2xl overflow-hidden bg-surface-container-low">
                  <div className="max-h-[200px] overflow-y-auto">
                    <table className="w-full text-left border-collapse">
                      <thead className="sticky top-0 bg-surface-container-high border-b border-outline-variant/30">
                        <tr className="text-[9px] text-outline font-bold uppercase tracking-widest">
                          <th className="px-5 py-3">Date</th>
                          <th className="px-5 py-3">Merchant / Description</th>
                          <th className="px-5 py-3">Suggested Category</th>
                          <th className="px-5 py-3 text-right">Amount</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant/20">
                        {analysisResult.transactions.map((tx, idx) => {
                          const isHigh = Math.abs(tx.amount) > 5000;
                          return (
                            <tr key={idx} className="hover:bg-surface-container-high/40 transition-colors duration-150">
                              <td className="px-5 py-3 text-xs font-semibold text-on-surface-variant">{tx.date}</td>
                              <td className="px-5 py-3 text-xs font-bold text-on-surface">
                                <div className="flex items-center gap-2">
                                  {isHigh && <AlertTriangle className="w-3.5 h-3.5 text-error shrink-0" title="High Amount Anomaly" />}
                                  <span className="truncate max-w-[200px] sm:max-w-xs">{tx.merchant}</span>
                                </div>
                              </td>
                              <td className="px-5 py-3">
                                <span className={cn(
                                  "px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-widest",
                                  tx.category === 'Uncategorized' 
                                    ? "bg-outline-variant/25 text-outline" 
                                    : "bg-primary-container/10 text-primary"
                                )}>
                                  {tx.category}
                                </span>
                              </td>
                              <td className={cn(
                                "px-5 py-3 text-xs font-extrabold text-right",
                                tx.type === 'income' ? 'text-success' : 'text-error'
                              )}>
                                {tx.type === 'income' ? '+' : '-'}{formatCurrency(Math.abs(tx.amount))}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="px-8 py-5 border-t border-outline-variant/20 flex justify-between gap-4 bg-surface-container-low">
            {analysisResult ? (
              <>
                <button
                  type="button"
                  onClick={() => setAnalysisResult(null)}
                  disabled={isIngesting}
                  className="px-6 py-3.5 bg-surface-container-high hover:brightness-95 text-on-surface font-extrabold rounded-2xl text-xs uppercase tracking-widest transition-all active:scale-[0.98] disabled:opacity-50"
                >
                  Start Over
                </button>
                <button
                  type="button"
                  onClick={handleIngest}
                  disabled={isIngesting}
                  className="flex-1 max-w-xs py-3.5 bg-primary text-white font-extrabold rounded-2xl text-xs uppercase tracking-widest shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2 ml-auto"
                >
                  {isIngesting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Ingesting Ledger...</span>
                    </>
                  ) : (
                    <>
                      <span>Import {totalTransactions} Transactions</span>
                      <ChevronRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={handleClose}
                className="w-full py-4 bg-surface-container-high hover:brightness-95 text-on-surface font-bold rounded-2xl transition-all active:scale-[0.98]"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      </AppModal>
    </>
  );
};
