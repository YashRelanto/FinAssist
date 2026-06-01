import React from 'react';
import { 
  LayoutDashboard, 
  BarChart2, 
  Receipt, 
  PiggyBank, 
  TrendingUp, 
  FileText, 
  Bot, 
  Settings,
  Shield,
  LogOut,
  ChevronRight,
  TrendingUp as TrendingIcon,
  Target,
  Zap
} from 'lucide-react';
import { cn, formatCurrency } from '../lib/utils';
import { useAppContext } from '../context/AppContext';

interface SidebarProps {
  currentPage: string;
  onNavigate: (page: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'forecasting', label: 'Forecasting', icon: Zap },
  { id: 'transactions', label: 'Transactions', icon: Receipt },
  { id: 'budget-goals', label: 'Budget & Goals', icon: PiggyBank },
  { id: 'investments', label: 'Investments', icon: TrendingUp },
  { id: 'reports', label: 'Reports', icon: FileText },
  { id: 'ai-assistant', label: 'AI Assistant', icon: Bot },
];

export const Sidebar: React.FC<SidebarProps> = ({ currentPage, onNavigate, isOpen, onClose }) => {
  const { user, signOut } = useAppContext();
  const adminNav =
    user.role === 'admin'
      ? [{ id: 'admin', label: 'Model Admin', icon: Shield }]
      : [];

  return (
    <>
      {/* Mobile Overlay */}
      <div 
        className={cn(
          "fixed inset-0 bg-black/50 z-40 lg:hidden transition-opacity duration-300",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
      />
      
      <aside className={cn(
        "fixed left-0 top-0 h-screen w-[280px] bg-surface-container-lowest shadow-md flex flex-col py-8 px-4 z-50 transition-transform duration-300 lg:translate-x-0",
        isOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="mb-8 px-2">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-primary tracking-tight">FinAssist</h1>
              <p className="text-sm text-on-surface-variant font-medium">Premium Finance</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          {[...navItems, ...adminNav].map((item) => {
            const Icon = item.icon;
            const isActive = currentPage === item.id;
            
            return (
              <button
                key={item.id}
                onClick={() => {
                  onNavigate(item.id);
                  onClose();
                }}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 group text-left",
                isActive 
                  ? "bg-surface-container-high text-primary font-bold border-r-4 border-primary" 
                  : "text-on-surface-variant hover:bg-surface-container-low hover:text-primary"
              )}
            >
              <Icon className={cn("w-5 h-5", isActive ? "text-primary" : "text-on-surface-variant group-hover:text-primary")} />
              <span className="flex-1">{item.label}</span>
              {isActive && <ChevronRight className="w-4 h-4 text-primary" />}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-outline-variant pt-4">
        <button 
          onClick={() => { signOut(); onClose(); }}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-error-container/10 hover:text-error transition-all duration-200 group"
        >
          <LogOut className="w-5 h-5" />
          <span>Logout</span>
        </button>
      </div>
    </aside>
  </>
  );
};
