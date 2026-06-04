import React, { useMemo, useRef, useState } from 'react';
import { Search, Download, Upload, Plus, Edit2, Trash2 } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { TransactionModal } from '../components/TransactionModal';
import { BulkUploadModal } from '../components/BulkUploadModal';
import { cn, formatCurrency } from '../lib/utils';
import { Transaction } from '../types';
import { apiFetch } from '../lib/api';
import { activeUserId } from '../lib/activeUserId';
import { analyzeStatementFile } from '../lib/statementParser';
import { isWithinAnalysisWindow } from '../lib/analysisPeriod';

export const Transactions: React.FC = () => {
  const {
    user,
    authReady,
    analysisPeriod,
    updateTransaction,
    deleteTransaction,
    categories,
    pendingDate,
    loadTransactions,
    transactions,
    accounts,
    dbCategories,
    loadAccounts,
    loadDbCategories,
  } = useAppContext();
  const [modalOpen, setModalOpen] = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | undefined>(undefined);
  const [search, setSearch] = useState('');
  const [selectedAccount, setSelectedAccount] = useState('All Accounts');
  const [selectedCategory, setSelectedCategory] = useState('All Categories');
  const [selectedType, setSelectedType] = useState('All Types');

  // Bulk statement upload states
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [passwordModal, setPasswordModal] = useState<{ open: boolean; wrongPassword: boolean }>({ open: false, wrongPassword: false });
  const [uploadError, setUploadError] = useState<string | null>(null);

  React.useEffect(() => {
    if (authReady && user?.isAuthenticated && activeUserId(user)) {
      loadTransactions();
      loadAccounts();
      loadDbCategories();
    }
  }, [authReady, user?.isAuthenticated, user?.userId, user?.id, loadTransactions, loadAccounts, loadDbCategories]);

  const handleUpdateCategory = async (trans: any, newMainCat: string) => {
    try {
      const response = await apiFetch(`/api/transactions/${trans.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: activeUserId(user),
          account_id: trans.account_id,
          amount: trans.amount,
          transaction_type: trans.type,
          merchant_name: trans.merchant,
          description: trans.notes || '',
          main_category: newMainCat,
          sub_category: 'General',
          transaction_date: trans.date
        })
      });
      const data = await response.json();
      if (data.success) {
        loadTransactions();
      }
    } catch (error) {
      console.error("Failed to update category", error);
    }
  };

  const handleEdit = (t: Transaction) => {
    setEditingTransaction(t);
    setModalOpen(true);
  };

  const handleAdd = () => {
    setEditingTransaction(undefined);
    setModalOpen(true);
  };

  React.useEffect(() => {
    if (pendingDate) {
      setEditingTransaction(undefined);
      setModalOpen(true);
    }
  }, [pendingDate]);

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this transaction?')) return;
    try {
      await deleteTransaction(id);
    } catch (error) {
      console.error("Failed to delete transaction", error);
    }
  };

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
        // Refresh centralized caches
        loadTransactions();
        loadAccounts();
      }

      setPendingFile(null);
      setPasswordModal({ open: false, wrongPassword: false });
      alert("Statement successfully uploaded and transactions imported!");
    } catch (err: any) {
      if (err?.type === 'password_required') {
        setPendingFile(file);
        setPasswordModal({ open: true, wrongPassword: false });
      } else if (err?.type === 'wrong_password') {
        setPasswordModal({ open: true, wrongPassword: true });
      } else {
        setUploadError(err?.message || 'Failed to parse the statement. Please try again.');
        alert(err?.message || 'Failed to parse the statement. Please try again.');
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

  const handleExportCSV = () => {
    if (filtered.length === 0) {
      alert('No transactions to export.');
      return;
    }
    const headers = ['Date', 'Merchant', 'Category', 'SubCategory', 'Account', 'Amount', 'Type', 'Notes'];
    const rows = filtered.map(t => [
      t.date,
      `"${t.merchant.replace(/"/g, '""')}"`,
      t.category,
      t.subCategory || '',
      t.account,
      t.amount,
      t.type,
      t.notes ? `"${t.notes.replace(/"/g, '""')}"` : ''
    ]);
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `FinAssist_Transactions_${new Date().toISOString().slice(0, 10)}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filtered = useMemo(() => transactions.filter(t => {
    const matchesSearch =
      t.merchant.toLowerCase().includes(search.toLowerCase()) ||
      t.category.toLowerCase().includes(search.toLowerCase()) ||
      (t.notes && t.notes.toLowerCase().includes(search.toLowerCase()));

    const matchesAccount =
      selectedAccount === 'All Accounts' ||
      t.account.toLowerCase() === selectedAccount.toLowerCase();

    const matchesCategory =
      selectedCategory === 'All Categories' ||
      t.category.toLowerCase() === selectedCategory.toLowerCase();

    const matchesType =
      selectedType === 'All Types' ||
      t.type.toLowerCase() === selectedType.toLowerCase();

    const matchesPeriod = isWithinAnalysisWindow(t.date, analysisPeriod);

    return (
      matchesSearch && matchesAccount && matchesCategory && matchesType && matchesPeriod
    );
  }), [transactions, search, selectedAccount, selectedCategory, selectedType, analysisPeriod]);

  if (!transactions.length && authReady && user?.isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <h2 className="text-3xl font-bold text-on-surface">Transactions</h2>
          <p className="text-on-surface-variant mt-1 text-sm font-medium">Manage and review your detailed financial ledger.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setBulkUploadOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-on-surface-variant bg-surface-container-lowest border border-outline-variant hover:bg-surface-container-low transition-all"
          >
            <Upload className="w-4 h-4" /> Bulk Upload
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".pdf,.csv,.xls,.xlsx"
            style={{ display: 'none' }}
          />
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-on-surface-variant bg-surface-container-lowest border border-outline-variant hover:bg-surface-container-low transition-all"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button
            onClick={handleAdd}
            className="flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold bg-primary text-white hover:bg-primary-container shadow-md transition-all"
          >
            <Plus className="w-4 h-4" /> Add Transaction
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant/30 soft-shadow">
        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-5 gap-6 items-end">
          <div className="space-y-2 lg:col-span-2">
            <label className="text-[10px] font-bold text-outline ml-1 uppercase tracking-widest">Search</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search merchant, category..."
                className="w-full pl-10 pr-4 py-2.5 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary outline-none transition-all"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-outline ml-1 uppercase tracking-widest">Account</label>
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-primary transition-all outline-none appearance-none font-bold"
            >
              <option value="All Accounts">All Accounts</option>
              {accounts.map((acc, idx) => (
                <option key={idx} value={acc.account_name}>{acc.account_name}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-outline ml-1 uppercase tracking-widest">Category</label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-primary transition-all outline-none appearance-none font-bold"
            >
              <option value="All Categories">All Categories</option>
              {(dbCategories.length > 0 ? dbCategories : categories.map(c => c.name)).map((cat, idx) => (
                <option key={idx} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-outline ml-1 uppercase tracking-widest">Type</label>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-primary transition-all outline-none appearance-none font-bold"
            >
              <option value="All Types">All Types</option>
              <option value="expense">Expense</option>
              <option value="income">Income</option>
            </select>
          </div>
        </div>
      </div>

      {/* Categorize Unknown Section */}
      {transactions.filter(t => t.category === 'Uncategorized').length > 0 && (
        <section className="bg-primary/5 border-2 border-primary/20 rounded-2xl p-6 lg:p-8 space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-xl font-bold flex items-center gap-2">
                Action Required: Categorize the Unknown <span className="px-2 py-0.5 bg-primary text-white text-[10px] rounded-full">{transactions.filter(t => t.category === 'Uncategorized').length}</span>
              </h3>
              <p className="text-sm text-outline font-medium mt-1">Our AI identified transactions that need your classification or validation. High-amount anomalies are highlighted.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {transactions.filter(t => t.category === 'Uncategorized').map(t => {
              const isAnomaly = Math.abs(t.amount) > 5000 || t.notes?.includes('anomaly');
              return (
                <div key={t.id} className={cn(
                  "bg-white p-6 rounded-2xl border transition-all group relative overflow-hidden",
                  isAnomaly ? "border-error/30 shadow-error/5" : "border-outline-variant/30 shadow-sm"
                )}>
                  {isAnomaly && <div className="absolute top-0 right-0 w-16 h-16 bg-error/5 rounded-bl-full -mr-4 -mt-4"></div>}
                  <div className="flex justify-between items-start mb-4">
                    <div className="overflow-hidden">
                      <p className="text-sm font-bold truncate">{t.merchant}</p>
                      <p className="text-[10px] text-outline font-bold uppercase tracking-widest mt-1">{t.date}</p>
                    </div>
                    <span className={cn(
                      "text-lg font-black",
                      isAnomaly ? "text-error" : "text-on-surface"
                    )}>
                      {formatCurrency(t.amount)}
                    </span>
                  </div>
                  {isAnomaly && (
                    <div className="mb-4 px-3 py-1.5 bg-error/10 text-error text-[10px] font-bold rounded-lg flex items-center gap-2 border border-error/5">
                      <span className="w-1.5 h-1.5 bg-error rounded-full animate-pulse"></span>
                      High Amount Anomaly Detected
                    </div>
                  )}
                  <div className="space-y-3">
                    <label className="text-[9px] font-bold text-outline uppercase tracking-widest pl-1">Assign Category</label>
                    <select
                      onChange={(e) => handleUpdateCategory(t, e.target.value)}
                      className="w-full px-4 py-2.5 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary outline-none appearance-none font-bold"
                    >
                      <option value="Uncategorized">Select Category...</option>
                      {categories.map(cat => <option key={cat.id} value={cat.name}>{cat.name}</option>)}
                    </select>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Main Transactions Table */}
      <div className="bg-surface-container-lowest rounded-xl soft-shadow border border-outline-variant/30 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-surface-container-low/50 border-b border-outline-variant/30">
              <tr className="text-[10px] text-outline font-bold uppercase tracking-widest">
                <th className="px-6 py-4">Date</th>
                <th className="px-6 py-4">Merchant</th>
                <th className="px-6 py-4">Category</th>
                <th className="px-6 py-4">Account</th>
                <th className="px-6 py-4 text-right">Amount</th>
                <th className="px-6 py-4 text-right">Running Balance</th>
                <th className="px-6 py-4 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20">
              {filtered.map((row) => (
                <tr key={row.id} className="hover:bg-surface-container-low transition-colors duration-200 group">
                  <td className="px-6 py-4 text-sm font-medium text-on-surface-variant">{row.date}</td>
                  <td className="px-6 py-4 text-sm font-bold text-on-surface">{row.merchant}</td>
                  <td className="px-6 py-4">
                    <span className="px-2.5 py-1 rounded bg-primary-container/10 text-primary text-[10px] font-bold uppercase tracking-widest">
                      {row.category}
                    </span>
                    {row.subCategory && <span className="block text-[8px] text-outline mt-1 uppercase font-bold">{row.subCategory}</span>}
                  </td>
                  <td className="px-6 py-4 text-sm text-outline font-medium">{row.account}</td>
                  <td className={`px-6 py-4 text-sm text-right font-bold ${row.type === 'income' ? 'text-secondary' : 'text-error'}`}>
                    {row.type === 'income' ? `+${formatCurrency(row.amount)}` : `-${formatCurrency(row.amount)}`}
                  </td>
                  <td className="px-6 py-4 text-sm text-right font-medium text-on-surface-variant/80">
                    {row.runningBalance !== undefined && row.runningBalance !== null ? formatCurrency(row.runningBalance) : '—'}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-center gap-2">
                      <button
                        onClick={() => handleEdit(row)}
                        className="p-1.5 text-outline hover:text-primary transition-colors hover:bg-primary-container/10 rounded"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(row.id)}
                        className="p-1.5 text-outline hover:text-error transition-colors hover:bg-error-container/10 rounded"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Pagination placeholder */}
        <div className="px-6 py-4 border-t border-outline-variant/30 flex items-center justify-between bg-surface-container-low/30">
          <span className="text-xs text-outline font-medium">Showing {filtered.length} transactions</span>
        </div>
      </div>

      <TransactionModal
        isOpen={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingTransaction(undefined);
          loadTransactions();
        }}
        editingTransaction={editingTransaction}
        accounts={accounts}
        onSaved={() => {
          loadTransactions();
        }}
      />

      <BulkUploadModal
        isOpen={bulkUploadOpen}
        onClose={() => setBulkUploadOpen(false)}
        onSuccess={() => {
          loadTransactions();
        }}
      />
    </div>
  );
};
