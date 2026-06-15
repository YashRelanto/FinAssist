import React, { useState } from 'react';
import { Search, Bell, Menu, User, Settings, LogOut, ChevronDown, RefreshCw } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn } from '../lib/utils';
import { TimeframeSelector } from './TimeframeSelector';

interface HeaderProps {
  onMenuClick: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onMenuClick }) => {
  const { user, setCurrentPage, signOut, analysisPeriod, setAnalysisPeriod, loadDashboardSummary, dashboardSummaryLoading } = useAppContext();
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 lg:left-[280px] right-0 h-16 bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center px-4 lg:px-10 z-30">
      <div className="flex items-center gap-4 flex-1 max-w-xl">
        <button 
          onClick={onMenuClick}
          className="lg:hidden p-2 hover:bg-surface-container-low rounded-lg text-on-surface-variant"
        >
          <Menu className="w-6 h-6" />
        </button>
        
        <div className="relative w-full hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
          <input 
            type="text" 
            placeholder="Search analytics, transactions, or goals..." 
            className="w-full pl-10 pr-4 py-2 bg-surface-container-low border-none rounded-full text-sm focus:ring-2 focus:ring-primary transition-all"
          />
        </div>
      </div>

      <div className="flex items-center gap-2 lg:gap-6">
        <div className="flex items-center gap-2">
          <TimeframeSelector
            value={analysisPeriod}
            onChange={(p) => {
              setAnalysisPeriod(p);
              void loadDashboardSummary({ force: true });
            }}
          />
          {dashboardSummaryLoading && (
            <RefreshCw className="w-4 h-4 text-primary animate-spin" />
          )}
        </div>
        
        <button className="relative p-2 text-on-surface-variant hover:text-primary transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-error rounded-full border-2 border-surface-container-lowest"></span>
        </button>

        <div className="relative pl-4 lg:pl-6 border-l border-outline-variant">
          <button 
            onClick={() => setIsProfileOpen(!isProfileOpen)}
            className="flex items-center gap-3 hover:bg-surface-container-low p-1.5 rounded-xl transition-all"
          >
            <div className="text-right hidden sm:block">
              <p className="text-sm font-bold text-on-surface leading-tight">{user.name}</p>
              <p className="text-[10px] text-outline uppercase tracking-wider font-semibold">Premium Member</p>
            </div>
            <div className="w-8 h-8 lg:w-10 lg:h-10 rounded-full bg-primary-container text-white flex items-center justify-center font-bold border-2 border-primary-container shadow-sm overflow-hidden relative">
              <span className="text-sm lg:text-base">{user.name.charAt(0)}</span>
            </div>
            <ChevronDown className={cn("w-4 h-4 text-outline transition-transform", isProfileOpen && "rotate-180")} />
          </button>

          {/* Profile Dropdown */}
          {isProfileOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setIsProfileOpen(false)}></div>
              <div className="absolute right-0 top-full mt-2 w-72 bg-surface-container-lowest rounded-2xl shadow-2xl border border-outline-variant/30 py-4 z-50 overflow-hidden animate-in fade-in zoom-in duration-200">
                <div className="py-2">
                  <button 
                    onClick={() => { setCurrentPage('edit-profile'); setIsProfileOpen(false); }}
                    className="w-full flex items-center gap-3 px-6 py-3 hover:bg-surface-container-low text-sm font-bold text-on-surface-variant transition-colors"
                  >
                    <User className="w-4 h-4" />
                    Edit Profile
                  </button>
                  <button 
                    onClick={() => { setCurrentPage('settings'); setIsProfileOpen(false); }}
                    className="w-full flex items-center gap-3 px-6 py-3 hover:bg-surface-container-low text-sm font-bold text-on-surface-variant transition-colors"
                  >
                    <Settings className="w-4 h-4" />
                    Settings
                  </button>
                  <button 
                    onClick={() => { signOut(); setIsProfileOpen(false); }}
                    className="w-full flex items-center gap-3 px-6 py-3 hover:bg-error-container/10 text-sm font-bold text-error transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
