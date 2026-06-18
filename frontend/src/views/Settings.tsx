import React from 'react';
import { Flame, CreditCard, ChevronRight } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { cn } from '../lib/utils';
import {
  format,
  startOfYear,
  eachDayOfInterval,
  endOfYear,
  getDay,
  startOfMonth,
  endOfMonth,
  eachMonthOfInterval
} from 'date-fns';

import { PageHeader, PageShell } from '../components/PageShell';

export const Settings: React.FC = () => {
  const {
    heatmapData,
    navigateToAddTransaction,
    setCurrentPage
  } = useAppContext();

  // Simple streak calculation (mock or based on heatmapData)
  const currentStreak = 14; 
  const totalDaysActive = heatmapData.filter(d => d.count > 0).length;

  return (
    <PageShell className="max-w-5xl">
      <PageHeader
        title="Settings & Profile"
        description="Configure your personal assistant and view your financial activity streaks."
      />

      {/* Streak Maintainer Heatmap */}
      <section className="bg-surface-container-lowest p-8 rounded-2xl border border-outline-variant/30 soft-shadow">
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-error-container/20 text-error rounded-xl">
              <Flame className="w-6 h-6 fill-current" />
            </div>
            <div>
              <h3 className="text-xl font-bold">Streak Maintainer</h3>
              <p className="text-xs text-outline font-bold uppercase tracking-widest mt-0.5">Don't miss a day of tracking!</p>
            </div>
          </div>
          <div className="flex gap-8">
            <div className="text-center">
              <p className="text-2xl font-black text-on-surface">{currentStreak}</p>
              <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Current Streak</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-black text-secondary">{totalDaysActive}</p>
              <p className="text-[10px] font-bold text-outline uppercase tracking-widest">Days Logged</p>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex overflow-x-auto pb-6 gap-8 scrollbar-hide">
            {/* Day Labels */}
            <div className="flex flex-col justify-between py-6 text-[9px] font-bold text-outline uppercase tracking-wider h-[84px] sticky left-0 bg-surface-container-lowest pr-2 z-10">
              <span className="h-3 leading-none">Mon</span>
              <span className="h-3 leading-none">Wed</span>
              <span className="h-3 leading-none">Fri</span>
            </div>

            {eachMonthOfInterval({
              start: startOfYear(new Date()),
              end: endOfYear(new Date())
            }).map((month) => {
              const monthStart = startOfMonth(month);
              const monthEnd = endOfMonth(month);
              const monthDays = eachDayOfInterval({ start: monthStart, end: monthEnd });
              const monthLabel = format(month, 'MMM');
              
              // Calculate empty cells for the first week to align days correctly
              const firstDayOffset = (getDay(monthStart) + 6) % 7; // Adjusting to start week on Monday

              return (
                <div key={monthLabel} className="flex flex-col gap-3 min-w-max">
                  <p className="text-[10px] font-bold text-outline uppercase tracking-widest text-center">{monthLabel}</p>
                  <div className="grid grid-rows-7 grid-flow-col gap-1.5 h-[84px]">
                    {/* Empty cells for offset */}
                    {Array.from({ length: firstDayOffset }).map((_, i) => (
                      <div key={`empty-${i}`} className="w-2.5 h-2.5" />
                    ))}
                    
                    {monthDays.map((date) => {
                      const dStr = format(date, 'yyyy-MM-dd');
                      const dayData = heatmapData.find(d => d.date === dStr);
                      const count = dayData ? dayData.count : 0;
                      const level = count === 0 ? 0 : count < 3 ? 1 : count < 6 ? 2 : 3;
                      const isToday = dStr === format(new Date(), 'yyyy-MM-dd');
                      
                      return (
                        <button 
                          key={dStr}
                          onClick={() => navigateToAddTransaction(dStr)}
                          title={`${dStr}: ${count} records`}
                          className={cn(
                            "w-2.5 h-2.5 rounded-sm transition-all hover:ring-2 hover:ring-primary relative",
                            level === 0 ? 'bg-[#EBEDF0]' :
                            level === 1 ? 'bg-[#9BE9A8]' :
                            level === 2 ? 'bg-[#40C463]' : 'bg-[#216E39]',
                            isToday && "ring-2 ring-orange-500 ring-offset-1"
                          )}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          
          <div className="flex items-center justify-center gap-4 text-[10px] font-bold text-outline uppercase tracking-widest pt-4 border-t border-outline-variant/10">
            <span>Less</span>
            <div className="flex gap-1.5 items-center">
              {[0, 1, 2, 3].map((lvl) => (
                <div key={lvl} className="flex items-center gap-1.5">
                  <div className={cn(
                    "w-3 h-3 rounded-sm",
                    lvl === 0 ? 'bg-[#EBEDF0]' :
                    lvl === 1 ? 'bg-[#9BE9A8]' :
                    lvl === 2 ? 'bg-[#40C463]' : 'bg-[#216E39]'
                  )} />
                  <span className="text-[9px] text-outline/60 lowercase">
                    {lvl === 0 ? '0' : lvl === 1 ? '1-2' : lvl === 2 ? '3-5' : '5+'}
                  </span>
                </div>
              ))}
            </div>
            <span>More</span>
          </div>
        </div>
      </section>

      {/* Linked Accounts */}
      <section className="bg-surface-container-lowest rounded-2xl border border-outline-variant/30 soft-shadow overflow-hidden">
        <div className="p-6 border-b border-outline-variant/20">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-primary/10 text-primary rounded-xl">
              <CreditCard className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold">Linked Accounts</h3>
              <p className="text-[10px] text-outline font-bold uppercase tracking-widest mt-0.5">Manage your connected bank accounts.</p>
            </div>
          </div>
        </div>
        <button
          onClick={() => setCurrentPage('linked-accounts')}
          className="w-full flex items-center justify-between px-6 py-4 hover:bg-surface-container-low transition-colors group text-left"
        >
          <span className="text-sm font-semibold text-on-surface">View & manage accounts</span>
          <ChevronRight className="w-4 h-4 text-outline group-hover:text-primary transition-colors" />
        </button>
      </section>
    </PageShell>
  );
};
