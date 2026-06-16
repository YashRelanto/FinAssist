import React, { useState, useMemo } from 'react';
import { 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  Legend, 
  ComposedChart,
  Line
} from 'recharts';
import { ChevronDown } from 'lucide-react';
import { formatCurrency } from '../../lib/utils';
import type { AnalysisPeriod } from '../../lib/analysisPeriod';

interface FinancialPerformanceChartProps {
  data?: any[];
  accounts?: any[];
  transactions?: any[];
  analysisPeriod?: AnalysisPeriod;
}

type ViewMode = 'income_expense' | 'running_balance';

export const FinancialPerformanceChart: React.FC<FinancialPerformanceChartProps> = ({ 
  data, 
  accounts = [],
  transactions = [],
  analysisPeriod = '1m'
}) => {
  const [viewMode, setViewMode] = useState<ViewMode>('income_expense');
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(
    new Set(accounts.slice(0, 1).map((a: any) => a.account_id))
  );

  // Get date range for period
  const getDateRange = (period: AnalysisPeriod) => {
    const now = new Date();
    const start = new Date();
    
    switch (period) {
      case '1m':
        start.setMonth(now.getMonth() - 1);
        break;
      case '3m':
        start.setMonth(now.getMonth() - 3);
        break;
      case '6m':
        start.setMonth(now.getMonth() - 6);
        break;
      case '1y':
        start.setFullYear(now.getFullYear() - 1);
        break;
      case 'all':
        return { start: new Date(0), end: now };
    }
    return { start, end: now };
  };

  // Calculate running balance data
  const runningBalanceData = useMemo(() => {
    if (viewMode !== 'running_balance' || selectedAccounts.size === 0) return [];

    const { start, end } = getDateRange(analysisPeriod);
    const dayMap: { [key: string]: { [key: string]: number } } = {};

    // Initialize all selected accounts for all dates in range
    const filtered = (transactions || []).filter((t: any) => {
      const txDate = new Date(t.date || t.transaction_date);
      return txDate >= start && txDate <= end && selectedAccounts.has(t.account_id);
    });

    // Build day-by-day running balance
    filtered.forEach((tx: any) => {
      const dateKey = new Date(tx.date || tx.transaction_date).toISOString().split('T')[0];
      if (!dayMap[dateKey]) {
        dayMap[dateKey] = {};
        Array.from(selectedAccounts).forEach(accId => {
          dayMap[dateKey][accId] = dayMap[dateKey][accId] ?? 0;
        });
      }
      const accountId = tx.account_id;
      const amount = tx.type === 'expense' ? -(tx.amount || 0) : (tx.amount || 0);
      dayMap[dateKey][accountId] = (dayMap[dateKey][accountId] || 0) + amount;
    });

    return Object.entries(dayMap)
      .sort(([dateA], [dateB]) => dateA.localeCompare(dateB))
      .map(([date, balances]) => ({
        name: new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        date,
        ...balances,
      }));
  }, [viewMode, analysisPeriod, selectedAccounts, transactions]);

  // Get income/expense data
  const incomeExpenseData = useMemo(() => {
    if (viewMode !== 'income_expense') return [];
    
    const { start, end } = getDateRange(analysisPeriod);
    const filtered = (data || []).filter((item: any) => {
      if (!item.month) return true;
      const itemDate = new Date(item.month + '-01');
      return itemDate >= start && itemDate <= end;
    });
    
    return filtered;
  }, [viewMode, analysisPeriod, data]);

  const chartData = viewMode === 'running_balance' ? runningBalanceData : incomeExpenseData;
  const accountColorMap: { [key: string]: string } = {
    [accounts[0]?.account_id]: '#006c49',
    [accounts[1]?.account_id]: '#004ac6',
    [accounts[2]?.account_id]: '#ba1a1a',
  };

  const toggleAccountSelection = (accountId: string) => {
    const newSelected = new Set(selectedAccounts);
    if (newSelected.has(accountId)) {
      newSelected.delete(accountId);
    } else {
      newSelected.add(accountId);
    }
    setSelectedAccounts(newSelected);
  };

  return (
    <div className="lg:col-span-8 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h4 className="text-xl font-bold">Financial Performance</h4>
          <p className="text-xs text-outline mt-1 font-medium">
            {viewMode === 'income_expense' ? 'Income vs Expenses vs Net Savings' : 'Running Account Balance'}
          </p>
        </div>
      </div>

      {/* Dropdowns and Controls */}
      <div className="flex flex-wrap gap-4 mb-6 items-center">
        {/* View Mode Dropdown */}
        <div className="relative">
          <select
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value as ViewMode)}
            className="appearance-none bg-surface-container-low border border-outline-variant/40 rounded-lg px-3 py-2 text-sm font-semibold text-on-surface-variant cursor-pointer pr-8"
          >
            <option value="income_expense">Income & Expense</option>
            <option value="running_balance">Running Balance</option>
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none text-outline" />
        </div>
      </div>

      {/* Account Selection (only show for running balance) */}
      {viewMode === 'running_balance' && accounts.length > 0 && (
        <div className="flex flex-wrap gap-3 mb-6">
          {accounts.map((account: any) => (
            <button
              key={account.account_id}
              onClick={() => toggleAccountSelection(account.account_id)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                selectedAccounts.has(account.account_id)
                  ? 'bg-primary/10 text-primary border-2 border-primary'
                  : 'bg-surface-container-low text-on-surface-variant border border-outline-variant/40'
              }`}
            >
              {account.account_name}
              {selectedAccounts.has(account.account_id) && ' ✓'}
            </button>
          ))}
        </div>
      )}

      {/* Chart */}
      <div className="h-[350px]">
        <ResponsiveContainer width="100%" height="100%">
          {viewMode === 'income_expense' ? (
            <ComposedChart data={chartData || []}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B' }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B' }} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#FFFFFF', 
                  borderRadius: '12px', 
                  border: '1px solid #E2E8F0', 
                  boxShadow: '0 4px 12px -1px rgb(0 0 0 / 0.1)' 
                }} 
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: '10px', fontWeight: 'bold', paddingTop: '20px' }} />
              <Bar dataKey="income" name="Total Income" fill="#006c49" radius={[4, 4, 0, 0]} barSize={20} />
              <Bar dataKey="expense" name="Total Expense" fill="#ba1a1a" radius={[4, 4, 0, 0]} barSize={20} />
              <Line type="monotone" dataKey="net" name="Net Savings" stroke="#004ac6" strokeWidth={3} dot={{ r: 4, fill: '#004ac6' }} />
            </ComposedChart>
          ) : (
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B' }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B' }} />
              <Tooltip 
                formatter={(value: number) => formatCurrency(value)}
                contentStyle={{ 
                  backgroundColor: '#FFFFFF', 
                  borderRadius: '12px', 
                  border: '1px solid #E2E8F0', 
                  boxShadow: '0 4px 12px -1px rgb(0 0 0 / 0.1)' 
                }} 
              />
              <Legend wrapperStyle={{ fontSize: '10px', fontWeight: 'bold', paddingTop: '20px' }} />
              {Array.from(selectedAccounts).map((accountId, idx) => (
                <Line
                  key={accountId}
                  type="monotone"
                  dataKey={accountId}
                  name={accounts.find((a: any) => a.account_id === accountId)?.account_name}
                  stroke={accountColorMap[accountId] || ['#006c49', '#004ac6', '#ba1a1a'][idx % 3]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              ))}
            </ComposedChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
};
