import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { formatCurrency } from '../../lib/utils';

const CATEGORY_COLORS: Record<string, string> = {
  'Food & Drinks': '#FF6B6B',
  Shopping: '#4D96FF',
  Housing: '#6BCB77',
  Transportation: '#FFD93D',
  Vehicle: '#FF9F43',
  'Life & Entertainment': '#A55EEF',
  'Communication/PC': '#48DBFB',
  'Financial Expense': '#546E7A',
  Investments: '#10AC84',
  Others: '#95A5A6',
};

const FALLBACK = ['#FF6B6B', '#4D96FF', '#6BCB77', '#FFD93D', '#A55EEF', '#48DBFB', '#FF9F43'];

interface ShareSlice {
  category: string;
  amount: number;
  pct: number;
}

interface CategoryShareChartProps {
  data: ShareSlice[];
  totalSpend?: number;
  loading?: boolean;
}

export const CategoryShareChart: React.FC<CategoryShareChartProps> = ({
  data,
  totalSpend = 0,
  loading,
}) => {
  const chartData = data.map((d) => ({ name: d.category, value: d.amount, pct: d.pct }));
  const total = totalSpend || data.reduce((s, d) => s + d.amount, 0);

  if (loading) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 animate-pulse h-72" />
    );
  }

  if (!chartData.length) {
    return (
      <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
        <h3 className="text-lg font-black mb-2 tracking-tight">Category Share</h3>
        <p className="text-sm text-outline">No spending data for this period.</p>
      </div>
    );
  }

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
      <h3 className="text-lg font-black mb-6 tracking-tight">Category Share</h3>
      <div className="h-[260px] relative">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={70}
              outerRadius={100}
              paddingAngle={2}
              dataKey="value"
              nameKey="name"
              label={({ name, pct }) => `${name} ${pct}%`}
              labelLine={false}
            >
              {chartData.map((entry, i) => (
                <Cell
                  key={entry.name}
                  fill={CATEGORY_COLORS[entry.name] || FALLBACK[i % FALLBACK.length]}
                />
              ))}
            </Pie>
            <Tooltip formatter={(v: number) => formatCurrency(v)} />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Total</p>
            <p className="text-lg font-black">{formatCurrency(total)}</p>
          </div>
        </div>
      </div>
    </div>
  );
};
