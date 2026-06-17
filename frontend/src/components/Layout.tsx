
import React from 'react';
import { MessageSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppContext } from '../context/AppContext';
import { APP_NAME } from '../lib/utils';
import { TopNav } from './TopNav';
import { Landing } from '../views/Landing';
import { Dashboard } from '../views/Dashboard';
import { Transactions } from '../views/Transactions';
import { AIAssistant } from '../views/AIAssistant';
import { BudgetGoals } from '../views/BudgetGoals';
import { Investments } from '../views/Investments';
import { Settings } from '../views/Settings';
import { Forecasting } from '../views/Forecasting';
import { AdminPanel } from '../views/AdminPanel';
import { Onboarding } from '../views/Onboarding';
import { LinkedAccounts } from '../views/LinkedAccounts';
import { EditProfile } from '../views/EditProfile';
import { Reports } from '../views/Reports';

export const Layout: React.FC = () => {
  const { currentPage, setCurrentPage, user, authReady } = useAppContext();

  const renderPage = () => {
    switch (currentPage) {
      case 'forecasting':
        return <Forecasting />;
      case 'transactions':
        return <Transactions />;
      case 'ai-assistant':
        return <AIAssistant />;
      case 'budget-goals':
        return <BudgetGoals />;
      case 'investments':
        return <Investments />;
      case 'settings':
        return <Settings />;
      case 'linked-accounts':
        return <LinkedAccounts />;
      case 'edit-profile':
        return <EditProfile />;
      case 'admin':
        return <AdminPanel />;
      case 'reports':
        return <Reports />;
      case 'dashboard':
      default:
        return <Dashboard />;
    }
  };

  if (!authReady) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-sm font-medium text-lumio-muted">Loading...</div>
      </div>
    );
  }

  if (!user.isAuthenticated) {
    return <Landing />;
  }

  if (!user.onboarded) {
    return <Onboarding />;
  }

  if (currentPage === 'landing') {
    return <Landing />;
  }

  return (
    <div className="min-h-screen text-lumio-text lumio-app">
      <TopNav variant="app" />

      <main className="flex-1 flex flex-col pt-24 md:pt-28 pb-16 px-4 md:px-margin w-full max-w-[1440px] mx-auto relative z-10">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentPage}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            {renderPage()}
          </motion.div>
        </AnimatePresence>
      </main>

      {currentPage !== 'ai-assistant' && (
        <button
          type="button"
          onClick={() => setCurrentPage('ai-assistant')}
          className="fixed bottom-8 right-8 w-14 h-14 bg-lumio-black text-white rounded-full shadow-lg flex items-center justify-center hover:scale-110 active:scale-95 transition-all group z-50"
        >
          <MessageSquare className="w-6 h-6" />
          <span className="absolute right-full mr-4 bg-lumio-black text-white text-xs px-3 py-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
            Ask {APP_NAME}
          </span>
        </button>
      )}
    </div>
  );
};
