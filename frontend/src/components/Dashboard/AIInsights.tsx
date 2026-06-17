import React from 'react';
import { Sparkles } from 'lucide-react';
import { APP_NAME } from '../lib/utils';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export const AIInsights: React.FC = () => {
  return (
    <div className="lg:col-span-7 bg-primary-container text-white p-8 rounded-xl shadow-lg relative overflow-hidden flex flex-col min-h-[300px]">
      <div className="absolute top-0 right-0 w-48 h-48 bg-white/10 rounded-full -mr-20 -mt-20 blur-3xl"></div>
      <div className="flex items-center gap-3 mb-6 relative z-10">
        <Sparkles className="w-6 h-6 animate-pulse" />
        <h4 className="text-xl font-bold">{APP_NAME} Insights</h4>
      </div>
      <ComingSoonPlaceholder message="AI Powered Insights Coming Soon" className="text-white/80" />
    </div>
  );
};
