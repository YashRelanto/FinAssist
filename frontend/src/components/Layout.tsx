
import React from 'react';
import { MessageSquare } from 'lucide-react';
import { cn } from '../lib/utils';
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

const TAB_PAGES: { id: string; Component: React.FC }[] = [
  { id: 'dashboard', Component: Dashboard },
  { id: 'forecasting', Component: Forecasting },
  { id: 'transactions', Component: Transactions },
  { id: 'ai-assistant', Component: AIAssistant },
  { id: 'budget-goals', Component: BudgetGoals },
  { id: 'investments', Component: Investments },
  { id: 'settings', Component: Settings },
  { id: 'linked-accounts', Component: LinkedAccounts },
  { id: 'edit-profile', Component: EditProfile },
  { id: 'admin', Component: AdminPanel },
  { id: 'reports', Component: Reports },
];

export const Layout: React.FC = () => {
  const { currentPage, setCurrentPage, user, authReady } = useAppContext();

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
        {TAB_PAGES.map(({ id, Component }) => (
          <div
            key={id}
            className={cn(currentPage !== id && 'hidden')}
            aria-hidden={currentPage !== id}
          >
            <Component />
          </div>
        ))}
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
