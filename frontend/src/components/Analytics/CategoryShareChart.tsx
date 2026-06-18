import React, { useState, useMemo } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { ChevronLeft } from 'lucide-react';
import { formatCurrency, cn } from '../../lib/utils';

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

const SUB_COLORS = [
  '#FF8787', '#6BABFF', '#8BD98F', '#FFE566', '#BA7EF7',
  '#6DE5FF', '#FFB76B', '#7A9BA8', '#3DC59A', '#A8B4B8',
  '#FF9F9F', '#8CC1FF', '#A3E5AB', '#FFED8A', '#CCA0F9',
];

interface SubcategorySlice {
  sub_category: string;
  amount: number;
  pct: number;
}

interface ShareSlice {
  category: string;
  amount: number;
  pct: number;
  subcategories?: SubcategorySlice[];
}

interface CategoryShareChartProps {
  data: ShareSlice[];
  totalSpend?: number;
  loading?: boolean;
}

function getColor(name: string, index: number): string {
  return CATEGORY_COLORS[name] || FALLBACK[index % FALLBACK.length];
}



export const CategoryShareChart: React.FC<CategoryShareChartProps> = ({
  data,
  totalSpend = 0,
  loading,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const chartData = useMemo(
    () => data.map((d) => ({ name: d.category, value: d.amount, pct: d.pct })),
    [data],
  );
  const total = totalSpend || data.reduce((s, d) => s + d.amount, 0);

  const selectedSlice = useMemo(
    () => data.find((d) => d.category === selectedCategory),
    [data, selectedCategory],
  );

  const subChartData = useMemo(() => {
    if (!selectedSlice?.subcategories?.length) return [];
    return selectedSlice.subcategories
      .filter((s) => s.amount > 0)
      .map((s) => ({
        name: s.sub_category,
        value: s.amount,
        pct: s.pct,
      }));
  }, [selectedSlice]);

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

  const handleSliceClick = (_: any, index: number) => {
    const cat = data[index];
    if (cat?.subcategories?.length) {
      setSelectedCategory(cat.category);
    }
  };

  return (
    <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
      <h3 className="text-lg font-black mb-6 tracking-tight">Category Share</h3>

      <div className={cn(
        "grid gap-6 transition-all",
        selectedCategory ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1",
      )}>
        {/* Main Pie */}
        <div>
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
                  onClick={handleSliceClick}
                  style={{ cursor: 'pointer' }}
                >
                  {chartData.map((entry, i) => (
                    <Cell
                      key={entry.name}
                      fill={getColor(entry.name, i)}
                      stroke={selectedCategory === entry.name ? '#1a1a2e' : 'transparent'}
                      strokeWidth={selectedCategory === entry.name ? 2 : 0}
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => formatCurrency(v)}
                  contentStyle={{
                    borderRadius: '12px',
                    border: 'none',
                    fontSize: '11px',
                    boxShadow: '0 4px 12px rgb(0 0 0 / 0.08)',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center">
                <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Total</p>
                <p className="text-lg font-black">{formatCurrency(total)}</p>
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 justify-center">
            {chartData.map((entry, i) => (
              <button
                key={entry.name}
                type="button"
                onClick={() => {
                  const cat = data[i];
                  if (cat?.subcategories?.length) {
                    setSelectedCategory(
                      selectedCategory === entry.name ? null : entry.name,
                    );
                  }
                }}
                className={cn(
                  "flex items-center gap-1.5 text-xs font-semibold transition-all hover:opacity-100",
                  selectedCategory && selectedCategory !== entry.name
                    ? "opacity-40"
                    : "opacity-90",
                )}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: getColor(entry.name, i) }}
                />
                <span className="truncate max-w-[120px]">{entry.name}</span>
                <span className="text-outline">{entry.pct}%</span>
              </button>
            ))}
          </div>
        </div>

        {/* Subcategory Drill-Down */}
        {selectedCategory && subChartData.length > 0 && (
          <div className="animate-in fade-in slide-in-from-right-4 duration-300">
            <div className="flex items-center gap-2 mb-3">
              <button
                type="button"
                onClick={() => setSelectedCategory(null)}
                className="p-1 rounded-lg hover:bg-surface-container-low transition-colors"
              >
                <ChevronLeft className="w-4 h-4 text-outline" />
              </button>
              <div>
                <p className="text-sm font-black text-on-surface">{selectedCategory}</p>
                <p className="text-[10px] text-outline font-bold uppercase tracking-widest">
                  Subcategory Breakdown
                </p>
              </div>
            </div>

            <div className="h-[200px] relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={subChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                  >
                    {subChartData.map((entry, i) => (
                      <Cell key={entry.name} fill={SUB_COLORS[i % SUB_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v: number) => formatCurrency(v)}
                    contentStyle={{
                      borderRadius: '12px',
                      border: 'none',
                      fontSize: '11px',
                      boxShadow: '0 4px 12px rgb(0 0 0 / 0.08)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="text-center">
                  <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Cat Total</p>
                  <p className="text-sm font-black">{formatCurrency(selectedSlice?.amount || 0)}</p>
                </div>
              </div>
            </div>

            {/* Sub-category legend */}
            <div className="mt-3 space-y-1.5">
              {subChartData.map((entry, i) => (
                <div key={entry.name} className="flex items-center justify-between px-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: SUB_COLORS[i % SUB_COLORS.length] }}
                    />
                    <span className="text-xs font-semibold text-on-surface/80 truncate max-w-[140px]">
                      {entry.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-on-surface">{formatCurrency(entry.value)}</span>
                    <span className="text-[10px] text-outline font-bold">{entry.pct}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {!selectedCategory && (
        <p className="text-[10px] text-outline font-medium mt-4 text-center">
          Click a category to see subcategory breakdown
        </p>
      )}
    </div>
  );
};
