
import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { Dashboard } from '../views/Dashboard';
import { Transactions } from '../views/Transactions';
import { AIAssistant } from '../views/AIAssistant';
import { BudgetGoals } from '../views/BudgetGoals';
import { Investments } from '../views/Investments';
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
      case 'dashboard':
      default:
        return <Dashboard />;
    }
  };

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
          <motion.div
            key={currentPage}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
          >
            {renderPage()}
          </motion.div>
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
