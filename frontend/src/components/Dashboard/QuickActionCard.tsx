import React from 'react';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export const QuickActionCard: React.FC = () => {
  return (
    <div className="lg:col-span-4 bg-primary text-white p-6 rounded-[32px] soft-shadow relative overflow-hidden flex flex-col min-h-[200px]">
       <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full -mr-16 -mt-16 blur-2xl"></div>
       <ComingSoonPlaceholder message="Quick Actions Coming Soon" className="text-white/80" />
    </div>
  );
};
