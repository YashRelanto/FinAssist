
import React, { useMemo, useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { Dashboard } from '../views/Dashboard';
import { Transactions } from '../views/Transactions';
import { AIAssistant } from '../views/AIAssistant';
import { BudgetGoals } from '../views/BudgetGoals';
import { Investments } from '../views/Investments';
import { Reports } from '../views/Reports';
import { Settings } from '../views/Settings';
import { Forecasting } from '../views/Forecasting';
import { AdminPanel } from '../views/AdminPanel';
import { Onboarding } from '../views/Onboarding';
import { Login } from '../views/Login';
import { LinkedAccounts } from '../views/LinkedAccounts';
import { EditProfile } from '../views/EditProfile';
import { MessageSquare } from 'lucide-react';
import { motion } from 'motion/react';
import { useAppContext } from '../context/AppContext';

export const Layout: React.FC = () => {
  const { currentPage, setCurrentPage, user, authReady } = useAppContext();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Must run on every render (before any early return) — Rules of Hooks.
  const pages = useMemo(
    () => [
      { id: 'dashboard', node: <Dashboard /> },
      { id: 'forecasting', node: <Forecasting /> },
      { id: 'transactions', node: <Transactions /> },
      { id: 'ai-assistant', node: <AIAssistant /> },
      { id: 'budget-goals', node: <BudgetGoals /> },
      { id: 'investments', node: <Investments /> },
      { id: 'reports', node: <Reports /> },
      { id: 'settings', node: <Settings /> },
      { id: 'linked-accounts', node: <LinkedAccounts /> },
      { id: 'edit-profile', node: <EditProfile /> },
      { id: 'admin', node: <AdminPanel /> },
    ],
    [],
  );

  if (!authReady) {
    return (
      <div className="min-h-screen bg-surface flex items-center justify-center">
        <div className="text-sm font-medium text-outline">Loading...</div>
      </div>
    );
  }

  if (!user.isAuthenticated) {
    return <Login />;
  }

  if (!user.onboarded) {
    return <Onboarding />;
  }

  return (
    <div className="min-h-screen bg-surface">
      <Sidebar 
        currentPage={currentPage} 
        onNavigate={setCurrentPage} 
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <Header onMenuClick={() => setSidebarOpen(true)} />
      
      <main className="lg:ml-[280px] pt-16 min-h-screen">
        <div className="p-4 lg:p-10 max-w-[1440px] mx-auto">
          {pages.map((page) => {
            const active = page.id === currentPage;
            return (
              <motion.div
                key={page.id}
                initial={false}
                animate={active ? { opacity: 1, y: 0 } : { opacity: 0, y: 0 }}
                transition={{ duration: 0.15 }}
                style={{ display: active ? 'block' : 'none' }}
              >
                {page.node}
              </motion.div>
            );
          })}
        </div>
      </main>

      {/* Global AI FAB */}
      {currentPage !== 'ai-assistant' && (
        <button 
          onClick={() => setCurrentPage('ai-assistant')}
          className="fixed bottom-8 right-8 w-14 h-14 bg-primary text-white rounded-full shadow-lg flex items-center justify-center hover:scale-110 active:scale-95 transition-all group z-50"
        >
          <MessageSquare className="w-6 h-6" />
          <span className="absolute right-full mr-4 bg-on-surface text-white text-xs px-3 py-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
            Ask AI Assistant
          </span>
        </button>
      )}
    </div>
  );
};
