import React, { useState } from 'react';
import { Search, Filter, Download, Upload, Plus, Edit2, Trash2 } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { TransactionModal } from '../components/TransactionModal';
import { cn, formatCurrency } from '../lib/utils';
import { Transaction } from '../types';
import { apiFetch } from '../lib/api';
import { activeUserId } from '../lib/activeUserId';

export const Transactions: React.FC = () => {
  const { user, authReady, updateTransaction, deleteTransaction, categories, pendingDate, loadTransactions } = useAppContext();
  const [realTransactions, setRealTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [dbCategories, setDbCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | undefined>(undefined);
  const [search, setSearch] = useState('');
  const [selectedAccount, setSelectedAccount] = useState('All Accounts');
  const [selectedCategory, setSelectedCategory] = useState('All Categories');
  const [selectedType, setSelectedType] = useState('All Types');

  const fetchTransactions = async () => {
    const uid = activeUserId(user);
    if (!uid) return;
    try {
      setLoading(true);
      const response = await apiFetch(`/api/transactions?user_id=${encodeURIComponent(uid)}`);
      const data = await response.json();
      if (data.success) {
        setRealTransactions(data.data);
      } else {
        setRealTransactions([]);
      }
    } catch (error) {
      console.error('Failed to fetch transactions', error);
      setRealTransactions([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAccounts = async () => {
    const uid = activeUserId(user);
    if (!uid) return;
    try {
      const response = await apiFetch(`/api/accounts?user_id=${encodeURIComponent(uid)}`);
      const data = await response.json();
      if (data.success && Array.isArray(data.data)) {
        setAccounts(data.data);
      }
    } catch (error) {
      console.error('Failed to fetch accounts', error);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await apiFetch('/api/categories');
      const data = await response.json();
      if (data.success && Array.isArray(data.data)) {
        setDbCategories(data.data);
      }
    } catch (error) {
      console.error('Failed to fetch categories', error);
    }
  };

  React.useEffect(() => {
    if (authReady && user?.isAuthenticated && activeUserId(user)) {
      fetchTransactions();
      fetchAccounts();
      fetchCategories();
    }
  }, [authReady, user?.isAuthenticated, user?.userId, user?.id]);

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
        fetchTransactions();
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
      const response = await apiFetch(`/api/transactions/${id}`, {
        method: 'DELETE'
      });
      const data = await response.json();
      if (data.success) {
        fetchTransactions();
        loadTransactions();
      }
    } catch (error) {
      console.error("Failed to delete transaction", error);
    }
  };

  const filtered = realTransactions.filter(t => {
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

    return matchesSearch && matchesAccount && matchesCategory && matchesType;
  });

  if (loading && realTransactions.length === 0) {
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
          <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-on-surface-variant bg-surface-container-lowest border border-outline-variant hover:bg-surface-container-low transition-all">
            <Upload className="w-4 h-4" /> Bulk Upload
          </button>
          <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-on-surface-variant bg-surface-container-lowest border border-outline-variant hover:bg-surface-container-low transition-all">
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
      {realTransactions.filter(t => t.category === 'Uncategorized').length > 0 && (
        <section className="bg-primary/5 border-2 border-primary/20 rounded-2xl p-6 lg:p-8 space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-xl font-bold flex items-center gap-2">
                Action Required: Categorize the Unknown <span className="px-2 py-0.5 bg-primary text-white text-[10px] rounded-full">{realTransactions.filter(t => t.category === 'Uncategorized').length}</span>
              </h3>
              <p className="text-sm text-outline font-medium mt-1">Our AI identified transactions that need your classification or validation. High-amount anomalies are highlighted.</p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {realTransactions.filter(t => t.category === 'Uncategorized').map(t => {
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
          fetchTransactions();
        }} 
        editingTransaction={editingTransaction}
        accounts={accounts}
      />
    </div>
  );
};
