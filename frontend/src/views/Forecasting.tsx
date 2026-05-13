
import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  ArrowUpRight, 
  ArrowDownRight,
  Filter,
  Search,
  Bell,
  Sparkles,
  Zap,
  LayoutDashboard,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Activity,
  AlertCircle,
  Eye,
  RefreshCcw
} from 'lucide-react';
import { 
  BarChart,
  Bar,
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Cell
} from 'recharts';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency } from '../lib/utils';

const weeklyData = [
  { name: 'Week 1', value: 3200 },
  { name: 'Week 2', value: 4500 },
  { name: 'Week 3', value: 1800 },
  { name: 'Week 4', value: 2982 },
];

const merchantData = [
  { name: 'Amazon Corporate', value: 1842, total: 2000, color: 'bg-primary' },
  { name: 'Whole Foods Market', value: 1250, total: 2000, color: 'bg-secondary' },
  { name: 'Apple Inc.', value: 980, total: 2000, color: 'bg-outline' },
];

const heatmapColors = ['bg-blue-50', 'bg-blue-100', 'bg-blue-200', 'bg-blue-300', 'bg-blue-500', 'bg-blue-700'];

export const Forecasting: React.FC = () => {
  const { user } = useAppContext();

  return (
    <div className="space-y-8 pb-20">
      {/* Dynamic Notification */}
      <div className="bg-error/5 border border-error/20 p-4 rounded-2xl flex items-center justify-between group">
         <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-error/10 rounded-full flex items-center justify-center text-error">
               <AlertCircle className="w-5 h-5" />
            </div>
            <div>
               <p className="text-sm font-black text-on-surface tracking-tight">Spending is high likely to exceed budget</p>
               <p className="text-[10px] font-bold text-error uppercase tracking-widest mt-0.5">Unusual pattern detected in "Dining & Entertainment"</p>
            </div>
         </div>
         <button className="px-4 py-2 bg-on-surface text-white text-[10px] font-black uppercase tracking-widest rounded-lg hover:brightness-110 transition-all">
            Take Action
         </button>
      </div>

      {/* Header Filters */}
      <div className="flex flex-col md:flex-row gap-4 items-end md:items-center bg-surface-container-lowest p-6 rounded-3xl border border-outline-variant/30">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 flex-1">
          <div className="space-y-1.5">
            <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">Account</label>
            <select className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none">
              <option>All Accounts</option>
              <option>Chase Checking</option>
              <option>Amex Platinum</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">Category</label>
            <select className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none">
              <option>All Categories</option>
              <option>Food & Drink</option>
              <option>Shopping</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">Merchant</label>
            <select className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none">
              <option>All Merchants</option>
              <option>Amazon</option>
              <option>Apple</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-black text-outline uppercase tracking-widest pl-1">Payment Method</label>
            <select className="w-full bg-surface-container-low border border-outline-variant rounded-xl px-3 py-2 text-xs font-bold focus:ring-2 focus:ring-primary outline-none">
              <option>All Methods</option>
              <option>Visa</option>
              <option>Apple Pay</option>
            </select>
          </div>
        </div>
        <button className="bg-primary text-white px-8 py-3 rounded-xl font-bold text-sm shadow-lg shadow-primary/20 hover:brightness-110 active:scale-95 transition-all">
          Apply Filters
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-8 space-y-8">
          {/* Main Spending Metric */}
          <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 relative overflow-hidden">
             <div className="absolute top-0 left-0 w-2 h-full bg-secondary"></div>
             <div className="flex justify-between items-start">
                <div>
                  <p className="text-[10px] font-black text-outline uppercase tracking-[0.2em] mb-2">Total Analyzed Spending</p>
                  <h2 className="text-5xl font-black text-on-surface">{formatCurrency(12482.50)}</h2>
                </div>
                <div className="text-right">
                   <div className="flex items-center justify-end gap-1 text-secondary font-black">
                      <TrendingDown className="w-5 h-5" />
                      <span className="text-xl">12%</span>
                   </div>
                   <p className="text-[10px] font-bold text-outline uppercase tracking-widest mt-1">lower than previous 30-day period</p>
                </div>
             </div>
          </div>

          {/* Bar Chart */}
          <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
            <h3 className="text-lg font-black mb-8 px-2 tracking-tight">Category Spending Over Time</h3>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weeklyData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" opacity={0.5} />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B', fontWeight: 600 }} />
                  <YAxis hide />
                  <Tooltip 
                    cursor={{ fill: '#F1F5F9' }}
                    contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                  />
                  <Bar dataKey="value" radius={[8, 8, 8, 8]} barSize={60}>
                    {weeklyData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={['#d1e4ff', '#004ac6', '#ffdad6', '#e2e2e6'][index % 4]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-8 mt-6">
               <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#d1e4ff]"></div>
                  <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Housing</span>
               </div>
               <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#004ac6]"></div>
                  <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Food & Dining</span>
               </div>
               <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#ffdad6]"></div>
                  <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Transport</span>
               </div>
            </div>
          </div>

          {/* Small widgets row */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
             <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
                <h3 className="text-sm font-black mb-6 tracking-tight uppercase">Merchant Comparison</h3>
                <div className="space-y-6">
                   {merchantData.map((m, i) => (
                     <div key={i} className="space-y-2">
                        <div className="flex justify-between items-center">
                           <span className="text-xs font-bold text-on-surface">{m.name}</span>
                           <span className="text-xs font-black">{formatCurrency(m.value)}</span>
                        </div>
                        <div className="w-full bg-surface-container h-2 rounded-full overflow-hidden">
                           <div className={cn(m.color, "h-full rounded-full")} style={{ width: `${(m.value/m.total)*100}%` }}></div>
                        </div>
                     </div>
                   ))}
                </div>
             </div>

             <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
                <h3 className="text-sm font-black mb-6 tracking-tight uppercase">Spending Heatmap</h3>
                <div className="grid grid-cols-7 gap-1">
                   {Array.from({ length: 35 }).map((_, i) => (
                     <div 
                        key={i} 
                        className={cn(
                          "aspect-square rounded-md",
                          heatmapColors[Math.floor(Math.random() * heatmapColors.length)]
                        )}
                     />
                   ))}
                </div>
                <div className="flex justify-between mt-4 items-center">
                   <span className="text-[10px] font-bold text-outline uppercase">Less</span>
                   <div className="flex gap-1">
                      {heatmapColors.map((c, i) => <div key={i} className={cn("w-2 h-2 rounded-sm", c)} />)}
                   </div>
                   <span className="text-[10px] font-bold text-outline uppercase">More</span>
                </div>
             </div>
          </div>

          {/* Flow Analysis */}
          <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30">
             <h3 className="text-sm font-black mb-8 tracking-tight uppercase">Flow Analysis</h3>
             <div className="flex items-center justify-between relative px-4">
                <div className="bg-primary/5 p-4 rounded-xl border border-primary/10 text-center w-28">
                   <p className="text-[10px] font-black text-primary uppercase mb-1">Accounts</p>
                   <p className="text-sm font-black">{formatCurrency(12400)}</p>
                </div>
                <div className="flex-1 h-[2px] bg-primary/20 relative mx-4">
                   <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-4 h-4 bg-primary rounded-full flex items-center justify-center">
                      <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
                   </div>
                </div>
                <div className="bg-secondary/5 p-4 rounded-xl border border-secondary/10 text-center w-28">
                   <p className="text-[10px] font-black text-secondary uppercase mb-1">Categories</p>
                   <p className="text-sm font-black">12 Active</p>
                </div>
                <div className="flex-1 h-[2px] bg-secondary/20 relative mx-4"></div>
                <div className="bg-outline/5 p-4 rounded-xl border border-outline/10 text-center w-28">
                   <p className="text-[10px] font-black text-outline uppercase mb-1">Merchants</p>
                   <p className="text-sm font-black">48 Identified</p>
                </div>
             </div>
          </div>
        </div>

        {/* Sidebar Insights */}
        <div className="lg:col-span-4 space-y-8">
          <div className="bg-surface-container-lowest p-8 rounded-[32px] border border-outline-variant/30 space-y-8 h-full">
            <div className="flex items-center gap-3">
               <Eye className="w-5 h-5 text-primary" />
               <h3 className="text-lg font-black tracking-tight">Deep Insights</h3>
            </div>

            <div className="space-y-6">
               <div className="bg-primary/5 p-6 rounded-2xl border border-primary/10 group cursor-pointer hover:bg-primary/10 transition-all">
                  <p className="text-[10px] font-black text-primary uppercase tracking-widest mb-2">Outlier Detected</p>
                  <p className="text-xs font-bold leading-relaxed">Single transaction of {formatCurrency(1200)} identified in Electronics at Best Buy.</p>
                  <button className="text-[10px] font-black uppercase text-primary border-b border-primary mt-4 group-hover:tracking-wider transition-all">Review Transaction</button>
               </div>

               <div className="bg-secondary/5 p-6 rounded-2xl border border-secondary/10 group cursor-pointer hover:bg-secondary/10 transition-all">
                  <p className="text-[10px] font-black text-secondary uppercase tracking-widest mb-2">Recurring Analysis</p>
                  <p className="text-xs font-bold leading-relaxed">12 recurring subscriptions found, totaling {formatCurrency(450)}/month. 2 show a price increase.</p>
                  <button className="text-[10px] font-black uppercase text-secondary border-b border-secondary mt-4 group-hover:tracking-wider transition-all">View Subscriptions</button>
               </div>

               <div className="bg-secondary/5 p-6 rounded-2xl border border-secondary/10 group cursor-pointer hover:bg-secondary/10 transition-all">
                  <p className="text-[10px] font-black text-secondary uppercase tracking-widest mb-2">Goal Trajectory</p>
                  <p className="text-xs font-bold leading-relaxed">Based on current savings, you are likely to crack your {user.primaryGoal || 'Emergency Fund'} goal 12 days early.</p>
                  <button className="text-[10px] font-black uppercase text-secondary border-b border-secondary mt-4 group-hover:tracking-wider transition-all">View Goal Timeline</button>
               </div>

               <div className="bg-error/5 p-6 rounded-2xl border border-error/10 group cursor-pointer hover:bg-error/10 transition-all">
                  <p className="text-[10px] font-black text-error uppercase tracking-widest mb-2">Optimization Goal</p>
                  <p className="text-xs font-bold leading-relaxed">Moving {formatCurrency(1200)} from checking to High-Yield Savings could earn {formatCurrency(54)} annually.</p>
                  <button className="text-[10px] font-black uppercase text-error border-b border-error mt-4 group-hover:tracking-wider transition-all">Transfer Now</button>
               </div>
            </div>

            <div className="pt-12 mt-auto">
               <div className="flex items-center justify-between mb-4">
                  <p className="text-[10px] font-black text-outline uppercase">Data Accuracy</p>
                  <RefreshCcw className="w-3 h-3 text-outline" />
               </div>
               <div className="flex flex-col items-center justify-center p-8 bg-surface-container-low rounded-3xl relative overflow-hidden">
                  <div className="relative w-24 h-24 flex items-center justify-center">
                     <svg className="w-full h-full -rotate-90">
                        <circle cx="48" cy="48" r="40" fill="none" stroke="currentColor" strokeWidth="8" className="text-primary/10" />
                        <circle cx="48" cy="48" r="40" fill="none" stroke="currentColor" strokeWidth="8" strokeDasharray="251.2" strokeDashoffset="15" className="text-secondary" />
                     </svg>
                     <span className="absolute text-xl font-black">94%</span>
                  </div>
                  <p className="text-[10px] font-bold text-outline uppercase tracking-widest mt-6">All accounts synced 2 mins ago.</p>
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
