import React, { useState, useEffect, useMemo } from 'react';
import { 
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend 
} from 'recharts';
import { Calendar, ChevronLeft, Filter, Loader2 } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { activeUserId } from '../../lib/activeUserId';
import { apiFetch } from '../../lib/api';
import { cn, formatCurrency } from '../../lib/utils';
import { type AnalysisPeriod, resolveAnalysisWindow } from '../../lib/analysisPeriod';

const CATEGORY_COLORS: Record<string, string> = {
  'Food & Drinks': '#FF6B6B',
  'Shopping': '#4D96FF',
  'Housing': '#6BCB77',
  'Transportation': '#FFD93D',
  'Vehicle': '#FF9F43',
  'Life & Entertainment': '#A55EEF',
  'Communication/PC': '#48DBFB',
  'Financial Expense': '#546E7A',
  'Investments': '#10AC84',
  'Income': '#2ECC71',
  'others': '#95A5A6',
};

const SUB_COLORS = [
  '#FF6B6B', '#4D96FF', '#6BCB77', '#FFD93D', '#A55EEF', 
  '#48DBFB', '#FF9F43', '#10AC84', '#546E7A', '#FF4757',
  '#2F3542', '#747D8C', '#70A1FF', '#7BED9F', '#ECCC68'
];

type RangeType = AnalysisPeriod;

interface BreakdownSlice {
  name: string;
  value: number;
}

interface ExpenseBreakdownProps {
  analysisPeriod: AnalysisPeriod;
}

export const ExpenseBreakdown: React.FC<ExpenseBreakdownProps> = ({ analysisPeriod }) => {
  const { user } = useAppContext();
  const [loading, setLoading] = useState(false);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [drillDown, setDrillDown] = useState<string | null>(null);

  const fetchTransactions = async (startDate: string, endDate: string) => {
    setLoading(true);
    try {
      const uid = activeUserId(user);
      const response = await apiFetch(
        `/api/transactions?start_date=${startDate}&end_date=${endDate}`,
      );
      const data = await response.json();
      if (data.success) {
        setTransactions(data.data.filter((t: any) => t.type === 'expense'));
      }
    } catch (error) {
      console.error("Failed to fetch transactions for breakdown", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const uid = activeUserId(user);
    if (!uid) return;

    const { startDate, endDate } = resolveAnalysisWindow(analysisPeriod);
    if (!startDate) {
      fetchTransactions('2000-01-01', endDate);
      return;
    }
    fetchTransactions(startDate, endDate);
  }, [analysisPeriod, user]);

  const chartData = useMemo(() => {
    const groups: Record<string, number> = {};
    
    transactions.forEach(t => {
      const key = drillDown ? t.subCategory : t.category;
      if (drillDown && t.category !== drillDown) return;
      
      groups[key] = (groups[key] || 0) + Math.abs(t.amount);
    });

    return Object.entries(groups)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [transactions, drillDown]);

  const totalExpense = useMemo(() => chartData.reduce((sum, item) => sum + item.value, 0), [chartData]);

  const onPieClick = (data: any) => {
    if (!drillDown) {
      setDrillDown(data.name);
    }
  };

  return (
    <div className="lg:col-span-4 bg-surface-container-lowest p-6 rounded-[24px] soft-shadow border border-outline-variant/30 flex flex-col h-full min-h-[550px]">
      <div className="flex flex-col gap-4 mb-2 h-[80px]">
        <div className="flex items-center justify-between">
          <h4 className="text-xl font-bold text-on-surface truncate pr-2">Expense Breakdown</h4>
          {drillDown && (
            <button 
              onClick={() => setDrillDown(null)}
              className="flex items-center gap-1 text-[10px] font-black text-primary uppercase tracking-widest hover:underline shrink-0"
            >
              <ChevronLeft className="w-3 h-3" /> Back
            </button>
          )}
        </div>

        <div className="h-[42px] flex items-center">
          <div className="flex items-center gap-2 w-full px-4 py-2.5 bg-surface-container-low border border-outline-variant/30 rounded-2xl">
            <Filter className="w-3.5 h-3.5 text-outline shrink-0" />
            <p className="text-[11px] font-black uppercase tracking-widest text-outline truncate">
              {resolveAnalysisWindow(analysisPeriod).periodLabel}
            </p>
            <Calendar className="w-3.5 h-3.5 text-outline/40 ml-auto shrink-0" />
          </div>
        </div>
      </div>

      <div className="flex-1 relative min-h-[350px]">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-primary opacity-20" />
          </div>
        ) : chartData.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6">
            <div className="w-16 h-16 bg-surface-container-low rounded-full flex items-center justify-center mb-4 text-outline/30">
              <Calendar className="w-8 h-8" />
            </div>
            <p className="text-xs font-bold text-outline uppercase tracking-widest">No data for this period</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
              <Pie
                data={chartData}
                cx="50%"
                cy="45%"
                startAngle={90}
                endAngle={-270}
                innerRadius={55}
                outerRadius={75}
                paddingAngle={4}
                dataKey="value"
                onClick={onPieClick}
                stroke="none"
                animationBegin={0}
                animationDuration={800}
              >
                {chartData.map((entry, index) => (
                  <Cell 
                    key={`cell-${index}`} 
                    fill={drillDown ? SUB_COLORS[index % SUB_COLORS.length] : CATEGORY_COLORS[entry.name] || '#95A5A6'} 
                    className="hover:opacity-80 transition-opacity cursor-pointer outline-none"
                  />
                ))}
              </Pie>
              <Tooltip 
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    return (
                      <div className="bg-surface-container-lowest p-3 rounded-xl border border-outline-variant/30 shadow-xl z-50">
                        <p className="text-[10px] font-black uppercase tracking-widest text-outline mb-1">{payload[0].name}</p>
                        <p className="text-sm font-black text-on-surface">{formatCurrency(payload[0].value as number)}</p>
                        <p className="text-[9px] font-bold text-primary mt-1">
                          {((payload[0].value as number) / totalExpense * 100).toFixed(1)}% of total
                        </p>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Legend 
                verticalAlign="bottom" 
                align="center"
                content={({ payload }) => (
                  <div className="flex flex-col items-center mt-4">
                    {/* Total Summary - Positioned between chart and legend */}
                    <div className="text-center mb-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
                      <p className="text-[9px] font-black text-outline opacity-70 uppercase tracking-[0.25em] leading-none">Total Expense</p>
                      <div className="flex items-center justify-center gap-2 mt-1.5">
                        <span className="text-base font-black text-on-surface tracking-tight">{formatCurrency(totalExpense)}</span>
                      </div>
                      {drillDown && (
                        <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/5 border border-primary/10 rounded-full mt-2">
                          <div className="w-1 h-1 rounded-full bg-primary animate-pulse" />
                          <p className="text-[8px] font-black text-primary uppercase tracking-widest">{drillDown}</p>
                        </div>
                      )}
                    </div>

                    {/* 2-Column Category Grid */}
                    <div className="grid grid-cols-2 gap-x-10 gap-y-3.5 max-h-[140px] overflow-y-auto px-4 w-full scrollbar-hide">
                      {payload?.map((entry: any, index: number) => (
                        <div key={index} className="flex items-center gap-2.5 group">
                          <div className="w-2 h-2 rounded-full shrink-0 shadow-sm transition-transform group-hover:scale-125" style={{ backgroundColor: entry.color }} />
                          <div className="flex flex-col min-w-0">
                            <span className="text-[8px] font-black text-outline uppercase tracking-wider leading-tight truncate group-hover:text-on-surface transition-colors">{entry.value}</span>
                            <span className="text-[10px] font-black text-on-surface-variant leading-none mt-0.5">
                              {((entry.payload.value / totalExpense) * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        )}
      </div>
      
      {!drillDown && chartData.length > 0 && (
        <div className="mt-auto pt-4">
          <p className="text-[9px] text-center text-outline font-bold uppercase tracking-tighter opacity-40">
            Click a segment to explore sub-categories
          </p>
        </div>
      )}
    </div>
  );
};
