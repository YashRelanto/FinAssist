import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Menu } from 'lucide-react';
import { motion } from 'motion/react';
import { cn } from '../lib/utils';
import { useAppContext } from '../context/AppContext';
import { BrandMark } from './BrandMark';

const BASE_NAV: { id: string; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'forecasting', label: 'Analytics' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'budget-goals', label: 'Goals' },
  { id: 'investments', label: 'Investments' },
  { id: 'linked-accounts', label: 'Accounts' },
];

interface TopNavProps {
  variant?: 'app' | 'landing';
  onAuthClick?: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({ variant = 'app', onAuthClick }) => {
  const {
    currentPage,
    setCurrentPage,
    user,
    signOut,
  } = useAppContext();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const isLanding = variant === 'landing';

  const navItems = useMemo(() => {
    const items = [...BASE_NAV];
    if (user.role === 'admin') {
      items.push({ id: 'admin', label: 'Admin' });
    }
    return items;
  }, [user.role]);

  const navigate = (id: string) => {
    setCurrentPage(id);
    setMenuOpen(false);
  };

  const goHome = () => {
    setCurrentPage('landing');
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <>
      <header className="fixed top-4 md:top-6 left-0 right-0 z-50 flex items-center justify-center px-3 md:px-4 w-full pointer-events-none">
        <div
          className={cn(
            'pointer-events-auto w-full grid grid-cols-[1fr_auto_1fr] items-center gap-2 bg-lumio-black backdrop-blur-xl rounded-full px-2 py-2 shadow-xl border border-white/10 min-h-14',
            isLanding ? 'max-w-[720px]' : 'max-w-[min(100%,1100px)]',
          )}
        >
          <button
            type="button"
            onClick={goHome}
            className="shrink-0 ml-1 justify-self-start hover:opacity-90 transition-opacity"
            aria-label="Home"
          >
            <BrandMark variant="dark" showName showIcon={false} />
          </button>

          {!isLanding && (
            <nav className="hidden lg:flex items-center gap-1 justify-self-center">
              {navItems.map((item) => {
                const isActive = currentPage === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => navigate(item.id)}
                    className={cn(
                      'relative shrink-0 px-3 py-1.5 rounded-full font-label text-[10px] font-bold uppercase tracking-wider whitespace-nowrap transition-colors',
                      isActive
                        ? 'text-lumio-black'
                        : 'text-page-bg/75 hover:text-page-bg hover:bg-white/10',
                    )}
                  >
                    {isActive && (
                      <motion.span
                        layoutId="topnav-active-tab"
                        className="absolute inset-0 rounded-full bg-page-bg"
                        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                      />
                    )}
                    <span className="relative z-10">{item.label}</span>
                  </button>
                );
              })}
            </nav>
          )}

          {isLanding && (
            <nav className="hidden md:flex items-center gap-5 justify-self-center">
              {[
                { href: '#features', label: 'Product' },
                { href: '#manifesto', label: 'Solutions' },
                { href: '#cta', label: 'About' },
              ].map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="font-label text-[11px] font-semibold uppercase tracking-wider text-page-bg/80 hover:text-page-bg transition-colors"
                >
                  {item.label}
                </a>
              ))}
            </nav>
          )}

          <div className="flex items-center gap-1.5 pr-1 shrink-0 justify-self-end">
            {isLanding ? (
              <button
                type="button"
                onClick={onAuthClick}
                className="border border-page-bg/30 text-page-bg font-label rounded-full hover:bg-page-bg hover:text-lumio-black transition-all flex items-center px-4 text-[10px] h-8 font-semibold uppercase tracking-wider"
              >
                Get Started
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="text-page-bg/80 hover:text-page-bg p-1.5 lg:hidden"
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-label="Open menu"
                >
                  <Menu className="w-5 h-5" />
                </button>
                <button
                  type="button"
                  onClick={() => setProfileOpen((v) => !v)}
                  className="w-8 h-8 rounded-full border border-page-bg/30 overflow-hidden bg-white/10 text-page-bg flex items-center justify-center text-xs font-bold"
                  aria-label="Account menu"
                >
                  {user.name.charAt(0)}
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {menuOpen &&
        createPortal(
          <div className="fixed inset-0 z-[100]" onClick={() => setMenuOpen(false)}>
            <div
              className="absolute top-20 left-3 right-3 md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-md bg-lumio-black rounded-2xl border border-white/10 p-3 shadow-2xl max-h-[70vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {(isLanding
                ? [
                    { id: 'features', label: 'Product' },
                    { id: 'manifesto', label: 'Solutions' },
                    { id: 'cta', label: 'About' },
                  ]
                : navItems
              ).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    if (isLanding) {
                      document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth' });
                    } else {
                      navigate(item.id);
                    }
                    setMenuOpen(false);
                  }}
                  className={cn(
                    'w-full text-left py-3 px-3 font-label text-sm rounded-xl transition-colors',
                    !isLanding && currentPage === item.id
                      ? 'bg-page-bg text-lumio-black font-semibold'
                      : 'text-page-bg/90 hover:text-page-bg hover:bg-white/10',
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>,
          document.body,
        )}

      {profileOpen &&
        !isLanding &&
        createPortal(
          <>
            <div className="fixed inset-0 z-[100]" onClick={() => setProfileOpen(false)} />
            <div className="fixed top-20 right-4 z-[110] w-56 bg-white-card rounded-2xl shadow-2xl border border-lumio-line/40 py-2 overflow-hidden">
              <div className="px-4 py-3 border-b border-lumio-line/30">
                <p className="text-sm font-semibold text-lumio-text truncate">{user.name}</p>
                <p className="text-[10px] text-lumio-muted truncate">{user.email}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setCurrentPage('edit-profile');
                  setProfileOpen(false);
                }}
                className="w-full text-left px-4 py-3 text-sm hover:bg-soft-card transition-colors"
              >
                Profile
              </button>
              <button
                type="button"
                onClick={() => {
                  setCurrentPage('settings');
                  setProfileOpen(false);
                }}
                className="w-full text-left px-4 py-3 text-sm hover:bg-soft-card transition-colors"
              >
                Settings
              </button>
              <button
                type="button"
                onClick={() => {
                  signOut();
                  setProfileOpen(false);
                }}
                className="w-full text-left px-4 py-3 text-sm text-error hover:bg-error-container/20 transition-colors border-t border-lumio-line/30"
              >
                Sign Out
              </button>
            </div>
          </>,
          document.body,
        )}
    </>
  );
};
