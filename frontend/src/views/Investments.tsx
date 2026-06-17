import React, { useState, useEffect } from 'react';
import { useAppContext } from '../context/AppContext';
import { 
  TrendingUp, Verified, History, Download, ArrowUpRight, 
  ArrowDownRight, Plus, Search, Calendar, ChevronRight, 
  Loader2, X, AlertCircle, Trash2, ChevronDown
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from 'recharts';
import { cn, formatCurrency } from '../lib/utils';
import { PageHeader, PageLoading, PageShell, lumio } from '../components/PageShell';

interface Holding {
  ticker: string;
  name: string;
  qty: number;
  invested: number;
  avg_nav: number;
  current_nav: number;
  current_value: number;
  gain: number;
  gain_percent: number;
  day_pnl: number;
  portfolio_share: number;
}

interface RawTransaction {
  investment_id: string;
  user_id: string;
  scheme_code: string;
  scheme_name: string;
  transaction_date: string;
  quantity: number;
  purchase_nav: number;
  current_nav: number;
}

interface ChartPoint {
  name: string;
  dateStr: string;
  invested: number;
  current: number;
}

interface MFSearchResult {
  schemeCode: string;
  schemeName: string;
}

export const Investments: React.FC = () => {
  const { user } = useAppContext();
  
  // Dynamic API State
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [rawTransactions, setRawTransactions] = useState<RawTransaction[]>([]);
  const [summary, setSummary] = useState({
    total_invested: 0,
    current_value: 0,
    total_gain: 0,
    total_gain_percentage: 0,
    portfolio_cagr: '0.0%'
  });
  const [rawChartData, setRawChartData] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Accordion state
  const [expandedHolding, setExpandedHolding] = useState<string | null>(null);
  
  // Filter range
  const [activeFilter, setActiveFilter] = useState<'1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL'>('ALL');
  
  // Add transaction Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MFSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  
  const [selectedFund, setSelectedFund] = useState<MFSearchResult | null>(null);
  const [transactionDate, setTransactionDate] = useState(new Date().toISOString().split('T')[0]);
  const [quantity, setQuantity] = useState('');
  const [purchaseNav, setPurchaseNav] = useState('');
  const [navLoading, setNavLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);

  // Fetch investments data
  const fetchInvestments = async () => {
    if (!user?.id) return;
    try {
      setLoading(true);
      const response = await fetch(`http://localhost:8000/api/investments?user_id=${user.id}`);
      const data = await response.json();
      if (data.success) {
        setHoldings(data.holdings);
        setSummary(data.summary);
        setRawChartData(data.chart_data);
        setRawTransactions(data.raw_transactions || []);
      }
    } catch (error) {
      console.error("Error fetching investments:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvestments();
  }, [user?.id]);

  // Debounced search for mutual funds with smart substring matching
  useEffect(() => {
    if (!searchQuery || searchQuery.trim().length < 3) {
      setSearchResults([]);
      return;
    }

    setSearchLoading(true);
    const delayDebounce = setTimeout(async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/investments/search?q=${encodeURIComponent(searchQuery)}`);
        const data = await response.json();
        if (data.success) {
          setSearchResults(data.data);
        }
      } catch (error) {
        console.error("Error searching funds:", error);
      } finally {
        setSearchLoading(false);
      }
    }, 600); // 600ms debounce delay to feel smooth and responsive

    return () => clearTimeout(delayDebounce);
  }, [searchQuery]);

  // Fetch NAV automatically when selected fund or date changes
  useEffect(() => {
    if (!selectedFund) return;
    
    const fetchNav = async () => {
      setNavLoading(true);
      try {
        const response = await fetch(`http://localhost:8000/api/investments/nav?scheme_code=${selectedFund.schemeCode}&date=${transactionDate}`);
        const data = await response.json();
        if (data.success) {
          setPurchaseNav(data.nav.toString());
        }
      } catch (error) {
        console.error("Error fetching NAV:", error);
      } finally {
        setNavLoading(false);
      }
    };

    fetchNav();
  }, [selectedFund, transactionDate]);

  // Submit transaction
  const handleAddInvestment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFund || !quantity || !purchaseNav) return;

    setSubmitLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/investments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.id,
          scheme_code: selectedFund.schemeCode,
          scheme_name: selectedFund.schemeName,
          transaction_date: transactionDate,
          quantity: parseFloat(quantity),
          purchase_nav: parseFloat(purchaseNav)
        })
      });
      const data = await response.json();
      if (data.success) {
        setModalOpen(false);
        // Reset form
        setSelectedFund(null);
        setSearchQuery('');
        setQuantity('');
        setPurchaseNav('');
        // Refresh dashboard
        fetchInvestments();
      }
    } catch (error) {
      console.error("Error adding investment:", error);
    } finally {
      setSubmitLoading(false);
    }
  };

  // Delete holding transaction
  const handleDeleteTransaction = async (investmentId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Avoid triggering accordion close
    if (!confirm("Are you sure you want to delete this purchase?")) return;

    try {
      const response = await fetch(`http://localhost:8000/api/investments/${investmentId}`, {
        method: 'DELETE'
      });
      const data = await response.json();
      if (data.success) {
        // Refresh
        fetchInvestments();
      }
    } catch (error) {
      console.error("Error deleting transaction:", error);
    }
  };

  // Determine earliest date to validate date ranges
  const oldestDate = React.useMemo(() => {
    if (!rawChartData || rawChartData.length === 0) return new Date();
    const firstPoint = rawChartData[0];
    return new Date(firstPoint.dateStr);
  }, [rawChartData]);

  // Calculate age of data in months
  const ageInMonths = React.useMemo(() => {
    const diffTime = Math.abs(new Date().getTime() - oldestDate.getTime());
    return diffTime / (1000 * 60 * 60 * 24 * 30.43);
  }, [oldestDate]);

  // Dynamic filter lists
  const availableFilters = React.useMemo(() => {
    const list: ('1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL')[] = [];
    if (ageInMonths >= 1) list.push('1M');
    if (ageInMonths >= 3) list.push('3M');
    if (ageInMonths >= 6) list.push('6M');
    if (ageInMonths >= 12) list.push('1Y');
    if (ageInMonths >= 36) list.push('3Y');
    if (ageInMonths >= 60) list.push('5Y');
    list.push('ALL');
    return list;
  }, [ageInMonths]);

  // Filter rawChartData
  const displayChartData = React.useMemo(() => {
    if (!rawChartData || rawChartData.length === 0) return [];
    if (activeFilter === 'ALL') return rawChartData;

    const cutOffDate = new Date();
    if (activeFilter === '1M') cutOffDate.setMonth(cutOffDate.getMonth() - 1);
    else if (activeFilter === '3M') cutOffDate.setMonth(cutOffDate.getMonth() - 3);
    else if (activeFilter === '6M') cutOffDate.setMonth(cutOffDate.getMonth() - 6);
    else if (activeFilter === '1Y') cutOffDate.setFullYear(cutOffDate.getFullYear() - 1);
    else if (activeFilter === '3Y') cutOffDate.setFullYear(cutOffDate.getFullYear() - 3);
    else if (activeFilter === '5Y') cutOffDate.setFullYear(cutOffDate.getFullYear() - 5);

    return rawChartData.filter(pt => new Date(pt.dateStr) >= cutOffDate);
  }, [rawChartData, activeFilter]);

  // Custom X-axis month ticks formatting (Shows only distinct Month Abbreviations to avoid duplication)
  const formatXAxisTick = (tick: string, index: number) => {
    try {
      const d = new Date(tick);
      if (index > 0 && displayChartData[index - 1]) {
        const prevD = new Date(displayChartData[index - 1].dateStr);
        if (prevD.getMonth() === d.getMonth()) {
          return "";
        }
      }
      return d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    } catch {
      return tick;
    }
  };

  return (
    <PageShell>
      <PageHeader
        title="Investments"
        description="Real-time performance metrics and mutual fund portfolio distribution."
        actions={
          <button type="button" onClick={() => setModalOpen(true)} className={lumio.btnPrimary}>
            <Plus className="w-4 h-4" />
            Add Fund
          </button>
        }
      />

      {/* METRIC CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {[
          { label: 'Total Invested', val: formatCurrency(summary.total_invested), icon: History, sub: 'Lifetime contributions', trend: null },
          { label: 'Current Value', val: formatCurrency(summary.current_value), icon: TrendingUp, sub: holdings.length > 0 ? '+2.4% this month' : 'Awaiting portfolio data', trend: holdings.length > 0 ? 'up' : null },
          { label: 'Total Gain', val: summary.total_gain >= 0 ? `+${formatCurrency(summary.total_gain)}` : `-${formatCurrency(Math.abs(summary.total_gain))}`, sub: holdings.length > 0 ? `${summary.total_gain_percentage.toFixed(1)}% Overall` : '0% gain tracked', trend: holdings.length > 0 && summary.total_gain >= 0 ? 'up' : holdings.length > 0 ? 'down' : null, secondary: holdings.length > 0 && summary.total_gain >= 0 },
          { label: 'Portfolio CAGR', val: summary.portfolio_cagr, icon: Verified, sub: 'Annualized benchmark', trend: holdings.length > 0 ? 'up' : null },
        ].map((card, i) => (
          <div key={i} className="bg-surface-container-lowest p-6 rounded-[28px] soft-shadow border border-outline-variant/30 hover:scale-[1.01] transition-transform duration-200">
            <p className="text-[10px] font-black text-outline uppercase tracking-[0.2em] mb-2">{card.label}</p>
            <h3 className={cn("text-2.5xl font-black font-display tracking-tight", card.secondary ? "text-secondary" : "text-on-surface")}>{card.val}</h3>
            <div className={cn("flex items-center gap-1.5 mt-4 text-[10px] font-black uppercase tracking-widest", card.trend === 'up' ? "text-secondary" : card.trend === 'down' ? "text-error" : "text-outline")}>
              {card.icon && <card.icon className="w-3.5 h-3.5" />}
              <span>{card.sub}</span>
            </div>
          </div>
        ))}
      </div>

      {/* LINE CHART & SUMMARY */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-12 bg-surface-container-lowest p-8 rounded-[32px] soft-shadow border border-outline-variant/30">
          <div className="flex flex-col md:flex-row justify-between md:items-center gap-4 mb-8">
            <div>
              <h4 className="text-xl font-bold text-on-surface">Portfolio Value Over Time</h4>
              <div className="flex items-center gap-4 mt-2">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 border-t border-dashed border-outline/70" />
                  <span className="text-[10px] font-bold text-outline uppercase tracking-wider">Invested</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 bg-secondary" />
                  <span className="text-[10px] font-bold text-secondary uppercase tracking-wider">Current</span>
                </div>
              </div>
            </div>
            
            {/* Dynamic filter ranges */}
            {rawChartData.length > 0 && (
              <div className="flex bg-surface-container-low p-1 rounded-xl border border-outline-variant/10 self-start">
                {availableFilters.map(p => (
                  <button 
                    key={p} 
                    onClick={() => setActiveFilter(p)}
                    className={cn(
                      "px-4 py-2 rounded-lg text-[10px] font-black tracking-widest uppercase transition-all", 
                      p === activeFilter 
                        ? "bg-white shadow text-primary font-black" 
                        : "text-outline hover:text-on-surface"
                    )}
                  >
                    {p === 'ALL' ? 'ALL TIME' : p}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="h-[360px] w-full">
            {loading ? (
              <div className="h-full flex flex-col items-center justify-center gap-3">
                <Loader2 className="w-10 h-10 animate-spin text-primary" />
                <p className="text-sm font-bold text-outline uppercase tracking-widest">Loading portfolio history...</p>
              </div>
            ) : displayChartData.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center gap-3 text-outline">
                <AlertCircle className="w-8 h-8 opacity-40" />
                <p className="text-sm font-medium">No investment activity logged. Click the button above to add your first mutual fund transaction.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                 <LineChart data={displayChartData} margin={{ left: 10, right: 10, top: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
                    <XAxis 
                      dataKey="dateStr" 
                      axisLine={false} 
                      tickLine={false} 
                      tick={{ fontSize: 9, fill: '#64748B', fontWeight: 800 }} 
                      dy={10} 
                      tickFormatter={formatXAxisTick}
                    />
                    <YAxis 
                      axisLine={false} 
                      tickLine={false} 
                      tick={{ fontSize: 9, fill: '#64748B', fontWeight: 800 }} 
                      dx={-10}
                      tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                    />
                    <Tooltip 
                      content={({ active, payload }) => {
                        if (active && payload && payload.length >= 2) {
                          const invested = payload[0].value as number;
                          const current = payload[1].value as number;
                          const diff = current - invested;
                          const gainPercent = (diff / invested) * 100;
                          return (
                            <div className="bg-surface-container-lowest p-4 rounded-2xl border border-outline-variant/30 shadow-xl z-50 space-y-2">
                              <p className="text-[9px] font-black text-outline uppercase tracking-widest">{payload[0].payload.dateStr}</p>
                              <div className="flex items-center justify-between gap-6">
                                <span className="text-xs font-bold text-outline">Invested Value:</span>
                                <span className="text-xs font-black text-on-surface">{formatCurrency(invested)}</span>
                              </div>
                              <div className="flex items-center justify-between gap-6">
                                <span className="text-xs font-bold text-secondary">Current Value:</span>
                                <span className="text-xs font-black text-secondary">{formatCurrency(current)}</span>
                              </div>
                              <div className="pt-1.5 border-t border-outline-variant/30 flex items-center justify-between gap-6">
                                <span className="text-[10px] font-black uppercase tracking-widest text-outline">Net Return:</span>
                                <span className={cn("text-xs font-black", diff >= 0 ? "text-secondary" : "text-error")}>
                                  {diff >= 0 ? '+' : ''}{formatCurrency(diff)} ({gainPercent.toFixed(1)}%)
                                </span>
                              </div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="invested" 
                      stroke="#94A3B8" 
                      strokeWidth={2} 
                      strokeDasharray="5 5" 
                      dot={false}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="current" 
                      stroke="#10AC84" 
                      strokeWidth={3} 
                      dot={{ r: 3, stroke: '#10AC84', strokeWidth: 1, fill: '#fff' }}
                      activeDot={{ r: 6, fill: '#10AC84' }}
                    />
                 </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* HOLDINGS SECTION */}
      <div className="bg-surface-container-lowest rounded-3xl soft-shadow border border-outline-variant/30 overflow-hidden">
        <div className="p-6 border-b border-outline-variant/30 flex justify-between items-center">
          <div>
            <h4 className="text-xl font-bold text-on-surface">Current Holdings</h4>
            <p className="text-[10px] text-outline font-black uppercase tracking-widest mt-1">Click a fund to view and delete individual purchase transactions</p>
          </div>
          {holdings.length > 0 && (
            <button className="text-primary text-[10px] font-black uppercase tracking-widest hover:underline flex items-center gap-2 border border-outline-variant/40 px-4 py-2 rounded-xl bg-surface-container-low hover:bg-surface-container-high transition-all">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
               <tr className="bg-surface-container-low/50 text-[9px] font-black text-outline uppercase tracking-[0.2em]">
                 <th className="px-6 py-4">Mutual Fund Scheme</th>
                 <th className="px-6 py-4 text-right">Quantity</th>
                 <th className="px-6 py-4 text-right">Avg Purchase NAV</th>
                 <th className="px-6 py-4 text-right">Current NAV</th>
                 <th className="px-6 py-4 text-right">Total Gain/Loss</th>
                 <th className="px-6 py-4 text-right">Day P&L</th>
                 <th className="px-6 py-4 text-right">Portfolio Share</th>
               </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20">
              {holdings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center text-outline text-sm font-medium">
                    No holdings found in active portfolio. Click the "Add Mutual Fund" button above to log transactions.
                  </td>
                </tr>
              ) : (
                holdings.map((h, i) => {
                  const isExpanded = expandedHolding === h.ticker;
                  const fundTxns = rawTransactions.filter(t => t.scheme_code === h.ticker);
                  
                  return (
                    <React.Fragment key={i}>
                      {/* Main Holding Row */}
                      <tr 
                        onClick={() => setExpandedHolding(isExpanded ? null : h.ticker)}
                        className="hover:bg-surface-container-low transition-colors duration-200 cursor-pointer select-none"
                      >
                        <td className="px-6 py-5 max-w-[280px]">
                          <div className="flex items-center gap-3">
                            {isExpanded ? <ChevronDown className="w-4 h-4 text-primary shrink-0" /> : <ChevronRight className="w-4 h-4 text-outline shrink-0" />}
                            <div className="flex flex-col gap-0.5">
                              <span className="font-bold text-on-surface text-sm line-clamp-1">{h.name}</span>
                              <span className="text-[9px] font-black text-outline uppercase tracking-widest">Scheme Code: {h.ticker}</span>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-5 text-sm text-right font-semibold text-on-surface">{h.qty.toFixed(4)}</td>
                        <td className="px-6 py-5 text-sm text-right text-outline font-medium">₹{h.avg_nav.toFixed(4)}</td>
                        <td className="px-6 py-5 text-sm text-right font-black text-on-surface">₹{h.current_nav.toFixed(4)}</td>
                        <td className="px-6 py-5 text-sm text-right font-black">
                          <div className="flex flex-col items-end">
                            <span className={cn("font-bold text-sm", h.gain >= 0 ? "text-secondary" : "text-error")}>
                              {h.gain >= 0 ? `+${formatCurrency(h.gain)}` : `-${formatCurrency(Math.abs(h.gain))}`}
                            </span>
                            <span className={cn("text-[9px] font-black uppercase flex items-center gap-0.5 mt-0.5", h.gain >= 0 ? "text-secondary" : "text-error")}>
                              {h.gain >= 0 ? <ArrowUpRight className="w-2.5 h-2.5" /> : <ArrowDownRight className="w-2.5 h-2.5" />}
                              {Math.abs(h.gain_percent).toFixed(2)}%
                            </span>
                          </div>
                        </td>
                        <td className={cn("px-6 py-5 text-sm text-right font-black", h.day_pnl >= 0 ? "text-secondary" : "text-error")}>
                          {h.day_pnl >= 0 ? `+₹${h.day_pnl.toFixed(2)}` : `-₹${Math.abs(h.day_pnl).toFixed(2)}`}
                        </td>
                        <td className="px-6 py-5 text-right font-bold">
                          <div className="flex items-center justify-end gap-2.5">
                            <span className="text-xs text-on-surface">{h.portfolio_share.toFixed(1)}%</span>
                            <div className="w-16 bg-surface-container h-1.5 rounded-full overflow-hidden shrink-0">
                              <div className="bg-primary h-full" style={{ width: `${h.portfolio_share}%` }} />
                            </div>
                          </div>
                        </td>
                      </tr>

                      {/* Expandable Individual Transaction Details */}
                      {isExpanded && (
                        <tr className="bg-surface-container-low/30">
                          <td colSpan={7} className="px-12 py-5 border-t border-b border-outline-variant/30">
                            <div className="space-y-4 animate-in fade-in slide-in-from-top-1 duration-200">
                              <div className="flex justify-between items-center">
                                <h5 className="text-[10px] font-black text-primary uppercase tracking-[0.15em]">Individual Purchase Transactions</h5>
                                <span className="text-[9px] font-bold text-outline uppercase">{fundTxns.length} Transactions Logged</span>
                              </div>
                              <div className="overflow-hidden rounded-2xl border border-outline-variant/40 bg-surface-container-lowest">
                                <table className="w-full text-left">
                                  <thead>
                                    <tr className="bg-surface-container-low/40 text-[8px] font-black text-outline uppercase tracking-wider border-b border-outline-variant/30">
                                      <th className="px-5 py-3">Purchase Date</th>
                                      <th className="px-5 py-3 text-right">Quantity (Units)</th>
                                      <th className="px-5 py-3 text-right">Purchase NAV</th>
                                      <th className="px-5 py-3 text-right">Current NAV</th>
                                      <th className="px-5 py-3 text-right">Invested Value</th>
                                      <th className="px-5 py-3 text-right">Current Value</th>
                                      <th className="px-5 py-3 text-right">Net Return</th>
                                      <th className="px-5 py-3 text-center">Action</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-outline-variant/10">
                                    {fundTxns.map((txn, idx) => {
                                      const tInvested = txn.quantity * txn.purchase_nav;
                                      const tCurrent = txn.quantity * txn.current_nav;
                                      const tGain = tCurrent - tInvested;
                                      const tGainPct = tInvested > 0 ? (tGain / tInvested) * 100 : 0;
                                      
                                      return (
                                        <tr key={idx} className="hover:bg-surface-container-low/40 transition-colors">
                                          <td className="px-5 py-3 text-xs font-semibold text-on-surface">{txn.transaction_date}</td>
                                          <td className="px-5 py-3 text-xs text-right font-medium text-on-surface">{txn.quantity.toFixed(4)}</td>
                                          <td className="px-5 py-3 text-xs text-right text-outline">₹{txn.purchase_nav.toFixed(4)}</td>
                                          <td className="px-5 py-3 text-xs text-right text-outline">₹{txn.current_nav.toFixed(4)}</td>
                                          <td className="px-5 py-3 text-xs text-right font-medium">₹{tInvested.toFixed(2)}</td>
                                          <td className="px-5 py-3 text-xs text-right font-semibold text-on-surface">₹{tCurrent.toFixed(2)}</td>
                                          <td className={cn("px-5 py-3 text-xs text-right font-black", tGain >= 0 ? "text-secondary" : "text-error")}>
                                            ₹{tGain.toFixed(2)} ({tGainPct.toFixed(1)}%)
                                          </td>
                                          <td className="px-5 py-3 text-center">
                                            <button 
                                              onClick={(e) => handleDeleteTransaction(txn.investment_id, e)}
                                              className="p-1.5 text-outline hover:text-error hover:bg-error/5 rounded-lg transition-colors inline-flex items-center justify-center"
                                              title="Delete transaction"
                                            >
                                              <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ADD MUTUAL FUND TRANSACTION MODAL */}
      {modalOpen && (
        <div className="fixed inset-0 bg-on-surface/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-surface-container-lowest w-full max-w-[540px] rounded-[32px] border border-outline-variant/30 soft-shadow overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-6 border-b border-outline-variant/20 flex justify-between items-center bg-surface-container-low/40">
              <div>
                <h4 className="text-xl font-bold text-on-surface">Log Mutual Fund Investment</h4>
                <p className="text-[10px] font-black text-outline uppercase tracking-widest mt-1">Direct integration with live NAV data</p>
              </div>
              <button 
                onClick={() => setModalOpen(false)}
                className="p-2 hover:bg-surface-container rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-outline" />
              </button>
            </div>

            {/* Modal Form */}
            <form onSubmit={handleAddInvestment} className="p-6 space-y-5 overflow-y-auto flex-1">
              {/* Mutual Fund Autocomplete */}
              <div className="space-y-1.5 relative">
                <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Search Scheme Name</label>
                <div className="relative">
                  <input 
                    type="text"
                    required={!selectedFund}
                    placeholder="e.g. SBI Bluechip Fund"
                    value={selectedFund ? selectedFund.schemeName : searchQuery}
                    onChange={(e) => {
                      if (selectedFund) setSelectedFund(null);
                      setSearchQuery(e.target.value);
                    }}
                    className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl pl-11 pr-4 py-3.5 text-sm font-semibold focus:ring-2 focus:ring-primary outline-none transition-all placeholder:text-outline/40 text-on-surface"
                  />
                  <Search className="w-4 h-4 text-outline absolute left-4 top-1/2 -translate-y-1/2" />
                  
                  {/* Clean clear selection button */}
                  {selectedFund && (
                    <button 
                      type="button" 
                      onClick={() => {
                        setSelectedFund(null);
                        setSearchQuery('');
                      }} 
                      className="absolute right-4 top-1/2 -translate-y-1/2 p-1 hover:bg-surface-container rounded-full"
                    >
                      <X className="w-3.5 h-3.5 text-outline" />
                    </button>
                  )}
                </div>

                {/* Dropdown Suggestions */}
                {searchLoading && (
                  <div className="absolute top-full left-0 right-0 mt-2 bg-surface-container-lowest rounded-xl border border-outline-variant/30 shadow-lg p-4 flex items-center justify-center gap-2.5 z-50">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    <span className="text-xs font-semibold text-outline">Searching mutual funds...</span>
                  </div>
                )}

                {!searchLoading && searchResults.length > 0 && !selectedFund && (
                  <div className="absolute top-full left-0 right-0 mt-2 bg-surface-container-lowest rounded-2xl border border-outline-variant/30 shadow-2xl max-h-[220px] overflow-y-auto z-50 divide-y divide-outline-variant/10">
                    {searchResults.map((fund, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => {
                          setSelectedFund(fund);
                          setSearchResults([]);
                        }}
                        className="w-full text-left px-5 py-3 hover:bg-surface-container-low transition-colors flex items-center justify-between gap-3 text-xs font-bold text-on-surface"
                      >
                        <span className="line-clamp-2">{fund.schemeName}</span>
                        <ChevronRight className="w-4 h-4 text-outline shrink-0" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Transaction Date */}
              <div className="space-y-1.5">
                <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Transaction Date</label>
                <div className="relative">
                  <input 
                    type="date"
                    required
                    max={new Date().toISOString().split('T')[0]}
                    value={transactionDate}
                    onChange={(e) => setTransactionDate(e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3.5 text-sm font-semibold focus:ring-2 focus:ring-primary outline-none transition-all cursor-pointer text-on-surface"
                  />
                </div>
              </div>

              {/* Quantity Purchased */}
              <div className="space-y-1.5">
                <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em] ml-1">Quantity (Units)</label>
                <input 
                  type="number"
                  step="any"
                  required
                  placeholder="0.0000"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3.5 text-sm font-semibold focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                />
              </div>

              {/* Purchase NAV (Auto populated from date selection) */}
              <div className="space-y-1.5">
                <div className="flex justify-between items-center px-1">
                  <label className="text-[9px] font-black text-outline uppercase tracking-[0.2em]">Purchase NAV</label>
                  {navLoading && (
                    <span className="text-[9px] text-primary font-black uppercase flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" /> Fetching Live NAV...
                    </span>
                  )}
                </div>
                <div className="relative">
                  <input 
                    type="number"
                    step="any"
                    required
                    placeholder="0.0000"
                    value={purchaseNav}
                    onChange={(e) => setPurchaseNav(e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant/50 rounded-xl px-4 py-3.5 text-sm font-black focus:ring-2 focus:ring-primary outline-none transition-all text-on-surface"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-black text-outline">INR</span>
                </div>
                {selectedFund && !navLoading && purchaseNav && (
                  <p className="text-[9px] text-secondary font-bold px-1 mt-1">
                    ✓ Live NAV auto-resolved for this scheme on {transactionDate}
                  </p>
                )}
              </div>

              {/* Submit Buttons */}
              <div className="pt-4 flex gap-4">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="flex-1 py-4 border border-outline-variant text-[10px] font-black uppercase tracking-[0.2em] rounded-xl hover:bg-surface-container-low transition-all"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitLoading || !selectedFund || !quantity || !purchaseNav}
                  className="flex-1 py-4 bg-primary text-white text-[10px] font-black uppercase tracking-[0.2em] rounded-xl shadow-lg shadow-primary/20 hover:brightness-110 active:scale-[0.98] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {submitLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <span>Add Transaction</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </PageShell>
  );
};
