import React from 'react';
import { useAppContext } from '../context/AppContext';
import { SummaryCards } from '../components/Dashboard/SummaryCards';
import { FinancialPerformanceChart } from '../components/Dashboard/FinancialPerformanceChart';
import { LinkedAccounts } from '../components/Dashboard/LinkedAccounts';
import { QuickActionCard } from '../components/Dashboard/QuickActionCard';
import { ExpenseBreakdown } from '../components/Dashboard/ExpenseBreakdown';
import { BudgetUtilization } from '../components/Dashboard/BudgetUtilization';
import { RecentTransactions } from '../components/Dashboard/RecentTransactions';
import { QuickAddForm } from '../components/Dashboard/QuickAddForm';
import { AIInsights } from '../components/Dashboard/AIInsights';

export const Dashboard: React.FC = () => {
  const { user } = useAppContext();
  const [dashboardData, setDashboardData] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(true);
  
  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const response = await fetch(`http://localhost:8000/api/dashboard-summary?user_id=${user?.id}`);
      const data = await response.json();
      if (data.success) {
        setDashboardData(data);
      }
    } catch (error) {
      console.error("Failed to connect to backend dashboard API", error);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    if (user?.isAuthenticated) fetchDashboardData();
  }, [user]);
  
  if (loading && !dashboardData) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-10">
      {/* Summary Cards - Live */}
      <SummaryCards data={dashboardData?.summary} />

      {/* Linked Accounts & Quick Actions - Placeholders */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-12">
          <div className="flex items-center justify-between mb-4">
             <h3 className="text-sm font-black text-outline uppercase tracking-[0.2em] px-2">Your Financial Hub</h3>
             <button className="text-[10px] font-black text-primary uppercase tracking-widest hover:underline">Manage Accounts</button>
          </div>
        </div>

        {/* Linked Accounts Card */}
        <LinkedAccounts accounts={dashboardData?.accounts} />

        {/* Quick Add Action Card */}
        <QuickActionCard />
      </div>

      {/* Main Charts area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Financial Performance - Live */}
        <FinancialPerformanceChart data={dashboardData?.chart_data} />

        {/* Expense Breakdown - Placeholder */}
        <ExpenseBreakdown />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Budget Utilization - Placeholder */}
        <BudgetUtilization />

        {/* Recent Transactions - Live */}
        <RecentTransactions transactions={dashboardData?.recent_transactions} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
         {/* Quick Add Form - Live */}
         <QuickAddForm 
            onSuccess={fetchDashboardData} 
            accounts={dashboardData?.accounts}
         />

        {/* AI Insights Card - Placeholder */}
        <AIInsights />
      </div>
    </div>
  );
};
