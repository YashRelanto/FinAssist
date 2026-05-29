import React from 'react';
import { useAppContext } from '../context/AppContext';
import { TrendingUp, Verified, History, Download, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { AreaChart, Area, XAxis, ResponsiveContainer, Tooltip, PieChart, Pie, Cell } from 'recharts';
import { cn, formatCurrency } from '../lib/utils';

const chartData = [
  { name: 'JAN', val: 100000 },
  { name: 'MAR', val: 110000 },
  { name: 'MAY', val: 105000 },
  { name: 'JUL', val: 125000 },
  { name: 'SEP', val: 130000 },
  { name: 'NOV', val: 138000 },
  { name: 'DEC', val: 142350 },
];

const allocationData = [
  { name: 'Stocks', value: 60, color: '#004ac6' },
  { name: 'Bonds', value: 20, color: '#006c49' },
  { name: 'Crypto', value: 10, color: '#784b00' },
  { name: 'Cash', value: 10, color: '#737686' },
];

const holdings = [
  { ticker: 'AAPL', name: 'Apple Inc.', qty: 120, avg: 145.20, price: 189.43, return: 30.46, gain: 5307.60 },
  { ticker: 'MSFT', name: 'Microsoft Corp', qty: 45, avg: 290.10, price: 374.07, return: 28.95, gain: 3778.65 },
  { ticker: 'VOO', name: 'Vanguard S&P 500 ETF', qty: 85, avg: 380.00, price: 421.12, return: 10.82, gain: 3495.20 },
  { ticker: 'TSLA', name: 'Tesla, Inc.', qty: 25, avg: 242.00, price: 193.57, return: -20.01, gain: -1210.75 },
  { ticker: 'BND', name: 'Vanguard Total Bond Market', qty: 300, avg: 75.40, price: 73.12, return: -3.02, gain: -684.00 },
];

export const Investments: React.FC = () => {
  const { user } = useAppContext();
  const isAuth = user.isAuthenticated;

  // Filter or clear mock listings if logged in
  const displayChartData = isAuth ? [] : chartData;
  const displayAllocation = isAuth ? [] : allocationData;
  const displayHoldings = isAuth ? [] : holdings;

  const totalInvested = isAuth ? 0 : 125000;
  const currentValue = isAuth ? 0 : 142350;
  const totalGain = isAuth ? 0 : 17350;
  const portfolioCagr = isAuth ? '0.0%' : '8.2%';

  return (
    <div className="space-y-8">
      <header>
        <h2 className="text-3xl font-bold text-on-surface">Investments</h2>
        <p className="text-on-surface-variant font-medium text-sm mt-1">Real-time performance metrics and asset distribution.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {[
          { label: 'Total Invested', val: formatCurrency(totalInvested), icon: History, sub: 'Lifetime contributions', trend: null },
          { label: 'Current Value', val: formatCurrency(currentValue), icon: TrendingUp, sub: isAuth ? 'Awaiting portfolio data' : '+2.4% this month', trend: isAuth ? null : 'up' },
          { label: 'Total Gain', val: totalGain >= 0 ? `+${formatCurrency(totalGain)}` : `-${formatCurrency(Math.abs(totalGain))}`, sub: isAuth ? '0% gain tracked' : '13.8% Overall', trend: isAuth ? null : 'up', secondary: !isAuth },
          { label: 'Portfolio CAGR', val: portfolioCagr, icon: Verified, sub: 'Annualized benchmark', trend: isAuth ? null : 'up' },
        ].map((card, i) => (
          <div key={i} className="bg-surface-container-lowest p-6 rounded-2xl soft-shadow border border-outline-variant/30 hover-lift">
            <p className="text-[10px] font-bold text-outline uppercase tracking-[0.2em] mb-2">{card.label}</p>
            <h3 className={cn("text-2xl font-bold font-display", card.secondary ? "text-secondary" : "text-on-surface")}>{card.val}</h3>
            <div className={cn("flex items-center gap-1.5 mt-4 text-[10px] font-bold uppercase", card.trend === 'up' ? "text-secondary" : "text-outline")}>
              {card.icon && <card.icon className="w-3.5 h-3.5" />}
              <span>{card.sub}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-surface-container-lowest p-8 rounded-2xl soft-shadow border border-outline-variant/30">
          <div className="flex justify-between items-center mb-8">
            <h4 className="text-xl font-bold">Portfolio Value Over Time</h4>
            <div className="flex bg-surface-container-low p-1 rounded-lg">
              {['1Y', '3Y', '5Y', 'MAX'].map(p => (
                <button key={p} className={cn("px-4 py-1.5 rounded-md text-[10px] font-bold transition-all", p === '1Y' ? "bg-white shadow text-primary" : "text-outline hover:text-on-surface")}>{p}</button>
              ))}
            </div>
          </div>
          <div className="h-[320px]">
            {displayChartData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-outline text-sm font-medium">
                 No investment activity logged. Sync your broker to populate charts.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                 <AreaChart data={displayChartData}>
                    <defs>
                      <linearGradient id="colorVal" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#004ac6" stopOpacity={0.1}/>
                        <stop offset="95%" stopColor="#004ac6" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B', fontWeight: 600 }} dy={10} />
                    <Tooltip 
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                    />
                    <Area type="monotone" dataKey="val" stroke="#004ac6" strokeWidth={3} fillOpacity={1} fill="url(#colorVal)" />
                 </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="lg:col-span-4 bg-surface-container-lowest p-8 rounded-2xl soft-shadow border border-outline-variant/30 flex flex-col">
          <h4 className="text-xl font-bold mb-8">Asset Allocation</h4>
          <div className="relative flex-1 flex flex-col items-center justify-center min-h-[250px]">
             {displayAllocation.length === 0 ? (
               <div className="text-outline text-xs text-center font-medium">
                  No assets to allocate
               </div>
             ) : (
               <>
                 <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                      <Pie
                        data={displayAllocation}
                        cx="50%"
                        cy="50%"
                        innerRadius={70}
                        outerRadius={90}
                        paddingAngle={8}
                        dataKey="value"
                      >
                        {displayAllocation.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                    </PieChart>
                 </ResponsiveContainer>
                 <div className="absolute flex flex-col items-center">
                    <span className="text-3xl font-bold">100%</span>
                    <span className="text-[10px] text-outline font-bold uppercase tracking-widest">Diversified</span>
                 </div>
               </>
             )}
          </div>
          <div className="grid grid-cols-2 gap-4 mt-8">
            {displayAllocation.map((item, i) => (
              <div key={i} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }}></div>
                  <span className="text-xs font-bold text-outline uppercase tracking-widest">{item.name}</span>
                </div>
                <span className="text-sm font-bold pl-4.5">{item.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-surface-container-lowest rounded-2xl soft-shadow border border-outline-variant/30 overflow-hidden">
        <div className="p-6 border-b border-outline-variant/30 flex justify-between items-center">
          <h4 className="text-xl font-bold">Current Holdings</h4>
          <button className="text-primary text-[10px] font-bold uppercase tracking-widest hover:underline flex items-center gap-2">
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
               <tr className="bg-surface-container-low/50 text-[10px] font-bold text-outline uppercase tracking-[0.2em]">
                 <th className="px-6 py-4">Ticker</th>
                 <th className="px-6 py-4">Name</th>
                 <th className="px-6 py-4 text-right">Quantity</th>
                 <th className="px-6 py-4 text-right">Avg Cost</th>
                 <th className="px-6 py-4 text-right">Current Price</th>
                 <th className="px-6 py-4 text-right">Total Return %</th>
                 <th className="px-6 py-4 text-right">Gain/Loss</th>
               </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20">
              {displayHoldings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-outline text-sm font-medium">
                    No holdings found in active portfolio. Sync your statements under Settings to import transactions.
                  </td>
                </tr>
              ) : (
                displayHoldings.map((stock, i) => (
                  <tr key={i} className="hover:bg-surface-container-low transition-colors duration-200">
                    <td className="px-6 py-5 font-bold text-primary text-sm">{stock.ticker}</td>
                    <td className="px-6 py-5 text-sm font-medium text-on-surface">{stock.name}</td>
                    <td className="px-6 py-5 text-sm text-right font-medium">{stock.qty.toFixed(2)}</td>
                    <td className="px-6 py-5 text-sm text-right text-outline font-medium">{formatCurrency(stock.avg)}</td>
                    <td className="px-6 py-5 text-sm text-right font-bold text-on-surface">{formatCurrency(stock.price)}</td>
                    <td className={cn("px-6 py-5 text-sm text-right font-bold flex items-center justify-end gap-1", stock.return > 0 ? "text-secondary" : "text-error")}>
                      {stock.return > 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      {Math.abs(stock.return).toFixed(2)}%
                    </td>
                    <td className={cn("px-6 py-5 text-sm text-right font-bold", stock.gain > 0 ? "text-secondary" : "text-error")}>
                      {stock.gain > 0 ? `+${formatCurrency(stock.gain)}` : `-${formatCurrency(Math.abs(stock.gain))}`}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
