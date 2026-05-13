import React from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  ArrowUpRight, 
  ArrowDownRight,
  Target,
  CircleCheck,
  Bell,
  Sparkles,
  Receipt,
  IndianRupee,
  CreditCard,
  Building2,
  PlusCircle,
  History
} from 'lucide-react';
import { 
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  ComposedChart
} from 'recharts';
import { useAppContext } from '../context/AppContext';
import { cn, formatCurrency, CURRENCY_SYMBOL } from '../lib/utils';

const chartData = [
  { name: 'Jan', income: 4000, expense: 2400, net: 1600 },
  { name: 'Feb', income: 4500, expense: 2800, net: 1700 },
  { name: 'Mar', income: 4200, expense: 2300, net: 1900 },
  { name: 'Apr', income: 5000, expense: 3000, net: 2000 },
  { name: 'May', income: 5500, expense: 3200, net: 2300 },
  { name: 'Jun', income: 5800, expense: 3300, net: 2500 },
  { name: 'Jul', income: 6000, expense: 3450, net: 2550 },
];

const pieData = [
  { name: 'Housing', value: 1800, color: '#004ac6' },
  { name: 'Food', value: 650, color: '#006c49' },
  { name: 'Transport', value: 400, color: '#784b00' },
  { name: 'Leisure', value: 600, color: '#ba1a1a' },
];

const transactions = [
  { id: 1, date: 'Oct 24, 2023', merchant: 'Starbucks', category: 'Food & Drink', amount: -12.50, method: 'Apple Pay' },
  { id: 2, date: 'Oct 23, 2023', merchant: 'Amazon', category: 'Shopping', amount: -89.99, method: 'Visa *4421' },
  { id: 3, date: 'Oct 21, 2023', merchant: 'Landlord Prop', category: 'Housing', amount: -1800.00, method: 'Bank Transfer' },
  { id: 4, date: 'Oct 20, 2023', merchant: 'Delta Air', category: 'Travel', amount: -450.00, method: 'Amex Platinum' },
  { id: 5, date: 'Oct 19, 2023', merchant: 'Freelance Payment', category: 'Income', amount: 1200.00, method: 'Stripe' },
];

export const Dashboard: React.FC = () => {
  const { transactions, addTransaction, categories, navigateToAddTransaction, user } = useAppContext();
  
  React.useEffect(() => {
    // Basic endpoint integration check
    const checkConnection = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/dashboard-summary?user_id=${user?.id}`);
        const data = await response.json();
        if (data.success) {
          console.log("Backend integration success:", data.message);
          // We can show a toast or alert if needed, but console is less intrusive for now
          // alert("Dashboard data synced with backend successfully!");
        }
      } catch (error) {
        console.error("Failed to connect to backend dashboard API");
      }
    };
    if (user?.isAuthenticated) checkConnection();
  }, [user]);
  
  const handleQuickAdd = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const amount = parseFloat(formData.get('amount') as string);
    const merchant = formData.get('merchant') as string;
    const category = formData.get('category') as string;
    
    if (!amount || !merchant) return;

    addTransaction({
      amount: -amount,
      merchant,
      category,
      date: new Date().toISOString().split('T')[0],
      account: 'HDFC Bank',
      type: 'expense'
    });
    
    e.currentTarget.reset();
  };

  return (
    <div className="space-y-8 pb-10">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
        {[
          { label: 'Total Balance', value: formatCurrency(42500), trend: '+2.4%', up: true, desc: 'vs last mo' },
          { label: 'Monthly Income', value: `+${formatCurrency(8200)}`, trend: '12 trans', up: null, desc: 'Average flow', color: 'text-secondary' },
          { label: 'Monthly Expenses', value: `-${formatCurrency(3450)}`, trend: '+12%', up: false, desc: 'spending spike', color: 'text-error' },
          { label: 'Net Savings', value: `+${formatCurrency(4750)}`, trend: 'Active', up: true, desc: 'Auto-transfers' },
          { label: 'Savings Rate', value: '58%', trend: 'Goal: 60%', up: true, desc: 'On track', progress: 58 },
        ].map((stat, i) => (
          <div key={i} className="bg-surface-container-lowest p-6 rounded-[32px] soft-shadow border border-outline-variant/30 flex flex-col justify-between min-h-[160px]">
            <div>
              <p className="text-[10px] text-outline font-black uppercase tracking-[0.15em] mb-3">{stat.label}</p>
              <h3 className={cn(
                "text-2xl font-black font-display tracking-tight",
                stat.color ? stat.color : "text-on-surface"
              )}>
                {stat.value}
              </h3>
            </div>
            
            <div className="mt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {stat.up !== null && stat.label !== 'Net Savings' && (
                    stat.up ? <ArrowUpRight className="w-3.5 h-3.5 text-secondary" /> : <ArrowDownRight className="w-3.5 h-3.5 text-error" />
                  )}
                  {stat.label === 'Net Savings' && <Sparkles className="w-3.5 h-3.5 text-secondary" />}
                  <span className={cn(
                    "text-[11px] font-black tracking-tight",
                    stat.up === true ? "text-secondary" : stat.up === false ? "text-error" : "text-on-surface"
                  )}>
                    {stat.trend}
                  </span>
                </div>
                <span className="text-[10px] text-outline font-bold text-right leading-tight max-w-[60px]">
                  {stat.desc}
                </span>
              </div>
              {stat.progress && (
                <div className="w-full bg-surface-container h-1.5 rounded-full mt-3 overflow-hidden">
                  <div className="bg-primary h-full transition-all duration-1000" style={{ width: `${stat.progress}%` }}></div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Linked Accounts & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-12">
          <div className="flex items-center justify-between mb-4">
             <h3 className="text-sm font-black text-outline uppercase tracking-[0.2em] px-2">Your Financial Hub</h3>
             <button className="text-[10px] font-black text-primary uppercase tracking-widest hover:underline">Manage Accounts</button>
          </div>
        </div>

        {/* Linked Accounts Card */}
        <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-3 gap-6">
           {[
             { name: 'HDFC Bank', type: 'Savings', balance: 24500, icon: Building2, color: 'text-blue-600', bg: 'bg-blue-50' },
             { name: 'ICICI Bank', type: 'Checking', balance: 12000, icon: Building2, color: 'text-orange-600', bg: 'bg-orange-50' },
             { name: 'Amex Card', type: 'Credit', balance: 6000, icon: CreditCard, color: 'text-teal-600', bg: 'bg-teal-50' },
           ].map((bank, i) => (
             <div key={i} className="bg-surface-container-lowest p-6 rounded-[24px] border border-outline-variant/30 soft-shadow group hover:border-primary transition-all cursor-pointer">
                <div className="flex justify-between items-start mb-4">
                   <div className={cn("p-2.5 rounded-xl", bank.bg, bank.color)}>
                      <bank.icon className="w-5 h-5" />
                   </div>
                   <div className="w-2 h-2 rounded-full bg-secondary animate-pulse" title="Synced"></div>
                </div>
                <p className="text-[10px] font-black text-outline uppercase tracking-widest leading-none">{bank.type}</p>
                <h4 className="font-bold text-on-surface mt-1">{bank.name}</h4>
                <p className="text-xl font-black text-on-surface mt-4 tracking-tighter">{formatCurrency(bank.balance)}</p>
                <div className="flex items-center gap-1.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                   <History className="w-3 h-3 text-outline" />
                   <span className="text-[10px] font-bold text-outline uppercase tracking-widest">Last Sync: 5m ago</span>
                </div>
             </div>
           ))}
        </div>

        {/* Quick Add Action Card */}
        <div className="lg:col-span-4 bg-primary text-white p-6 rounded-[32px] soft-shadow relative overflow-hidden group">
           <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16 blur-2xl group-hover:scale-110 transition-transform"></div>
           <div className="relative z-10 h-full flex flex-col">
              <div className="flex items-center gap-3 mb-4">
                 <div className="p-2 bg-white/20 rounded-lg backdrop-blur-sm">
                    <PlusCircle className="w-5 h-5" />
                 </div>
                 <h4 className="text-lg font-black tracking-tight">Quick Action</h4>
              </div>
              <p className="text-xs font-medium opacity-90 mb-6 leading-relaxed">Add a new expense instantly. We'll categorize it using our AI engine.</p>
              
              <button 
                onClick={() => navigateToAddTransaction(new Date().toISOString().split('T')[0])}
                className="w-full bg-white text-primary font-black py-4 rounded-xl shadow-lg hover:shadow-xl active:scale-95 transition-all text-xs tracking-[0.15em] uppercase mt-auto"
              >
                Snap Transaction
              </button>
           </div>
        </div>
      </div>

      {/* Main Charts area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h4 className="text-xl font-bold">Financial Performance</h4>
              <p className="text-xs text-outline mt-1 font-medium">Income vs Expenses vs Net Savings</p>
            </div>
          </div>
          <div className="h-[350px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
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
            </ResponsiveContainer>
          </div>
        </div>

        {/* ... Breakdown area ... */}

        <div className="lg:col-span-4 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 flex flex-col">
          <h4 className="text-xl font-bold mb-6">Expense Breakdown</h4>
          <div className="flex-1 flex items-center justify-center min-h-[250px]">
             <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
             </ResponsiveContainer>
             <div className="absolute text-center">
                <p className="text-[10px] text-outline font-bold uppercase">Total</p>
                <p className="text-2xl font-bold">{formatCurrency(3450)}</p>
             </div>
          </div>
          <div className="space-y-3 mt-6">
            {pieData.map((item, i) => (
              <div key={i} className="flex justify-between items-center text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }}></div>
                  <span className="text-on-surface-variant">{item.name}</span>
                </div>
                <span className="font-bold">{formatCurrency(item.value)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Budget Utilization */}
        <div className="lg:col-span-4 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 space-y-6">
          <h4 className="text-lg font-bold">Budget Utilization</h4>
          <div className="space-y-6">
            {[
              { label: 'Housing', spent: 1800, total: 2000, color: 'bg-primary' },
              { label: 'Entertainment', spent: 845, total: 800, color: 'bg-error', over: 45 },
              { label: 'Grocery', spent: 450, total: 1000, color: 'bg-secondary' },
            ].map((item, i) => {
              const percent = Math.min(100, (item.spent / item.total) * 100);
              return (
                <div key={i}>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-bold">{item.label}</span>
                    <span className={cn("text-sm font-bold", item.over ? "text-error" : "text-outline")}>
                      {Math.round((item.spent / item.total) * 100)}%
                    </span>
                  </div>
                  <div className="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
                    <div className={cn(item.color, "h-full rounded-full transition-all duration-1000")} style={{ width: `${percent}%` }}></div>
                  </div>
                  <div className="flex justify-between mt-2">
                    <span className="text-[10px] text-outline font-medium">{formatCurrency(item.spent)} / {formatCurrency(item.total)}</span>
                    {item.over && <span className="text-[10px] text-error font-bold uppercase tracking-widest">Exceeded by {formatCurrency(item.over)}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Transactions Table */}
        <div className="lg:col-span-8 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30">
          <div className="flex justify-between items-center mb-6">
            <h4 className="text-lg font-bold">Recent Transactions</h4>
            <button className="text-primary text-xs font-bold hover:underline tracking-widest uppercase">View All</button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-b border-outline-variant/30">
                <tr className="text-[10px] text-outline font-bold uppercase tracking-widest">
                  <th className="pb-3 px-2">Date</th>
                  <th className="pb-3 px-2">Merchant</th>
                  <th className="pb-3 px-2">Category</th>
                  <th className="pb-3 px-2 text-right">Amount</th>
                  <th className="pb-3 px-2">Method</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20">
                {transactions.slice(0, 5).map((t) => (
                  <tr key={t.id} className="group hover:bg-surface-container-low transition-colors duration-200">
                    <td className="py-4 px-2 text-sm text-on-surface-variant font-medium">{t.date}</td>
                    <td className="py-4 px-2 text-sm font-bold text-on-surface">{t.merchant}</td>
                    <td className="py-4 px-2">
                      <span className={cn(
                        "px-2 py-1 rounded text-[10px] font-bold uppercase tracking-widest",
                        t.type === 'income' ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"
                      )}>
                        {t.category}
                      </span>
                    </td>
                    <td className={cn(
                      "py-4 px-2 text-sm text-right font-bold",
                      t.type === 'income' ? "text-secondary" : "text-on-surface"
                    )}>
                      {t.type === 'income' ? `+${formatCurrency(t.amount)}` : `-${formatCurrency(Math.abs(t.amount))}`}
                    </td>
                    <td className="py-4 px-2 text-sm text-outline font-medium">{t.account}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
         {/* Quick Add Form */}
         <div className="lg:col-span-5 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30">
          <h4 className="text-lg font-bold mb-6">Quick Add Transaction</h4>
          <form onSubmit={handleQuickAdd} className="space-y-4">
            <div>
              <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Amount</label>
              <div className="relative">
                <div className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center text-outline font-bold">
                  {CURRENCY_SYMBOL}
                </div>
                <input required name="amount" type="number" step="0.01" placeholder="0.00" className="w-full pl-10 pr-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm outline-none" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Category</label>
                <select name="category" className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm outline-none">
                  {categories.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Merchant</label>
                <input required name="merchant" type="text" placeholder="e.g. Starbucks" className="w-full px-4 py-3 bg-surface-container-low rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary transition-all text-sm outline-none" />
              </div>
            </div>
            <button type="submit" className="w-full py-4 bg-primary text-white font-bold rounded-lg hover:bg-primary-container active:scale-[0.98] transition-all shadow-md mt-2">
              Add Transaction
            </button>
          </form>
        </div>

        {/* AI Insights Card */}
        <div className="lg:col-span-7 bg-primary-container text-white p-8 rounded-xl shadow-lg relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-48 h-48 bg-white/10 rounded-full -mr-20 -mt-20 blur-3xl group-hover:bg-white/20 transition-all"></div>
          <div className="flex items-center gap-3 mb-6 relative z-10">
            <Sparkles className="w-6 h-6 animate-pulse" />
            <h4 className="text-xl font-bold">FinAssist AI Insights</h4>
          </div>
          <div className="space-y-4 relative z-10">
            {[
              { icon: TrendingUp, title: 'Spending Pattern Alert', desc: 'Spending increased in Dining by 24% this month. Consider checking your entertainment budget.' },
              { icon: CircleCheck, title: 'Goal Achievement Progress', desc: 'Excellent work! You are currently on track for your Vacation goal set for December.' },
              { icon: Receipt, title: 'Recurring Charges Detected', desc: '3 new recurring subscriptions detected this week. Review them in the Subscriptions tab.' },
            ].map((insight, i) => {
              const Icon = insight.icon;
              return (
                <div key={i} className="flex items-start gap-4 p-4 bg-white/10 rounded-xl backdrop-blur-sm border border-white/10 hover:bg-white/15 transition-all">
                  <Icon className="w-5 h-5 mt-0.5 shrink-0" />
                  <div>
                    <h5 className="text-sm font-bold">{insight.title}</h5>
                    <p className="text-xs opacity-90 mt-1">{insight.desc}</p>
                  </div>
                </div>
              )
            })}
          </div>
          <button className="mt-8 text-[10px] font-bold uppercase tracking-[0.2em] flex items-center gap-2 hover:translate-x-1 transition-all">
            Generate Detailed Report <ArrowUpRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
};
