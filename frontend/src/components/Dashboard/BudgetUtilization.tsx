import React from 'react';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export const BudgetUtilization: React.FC = () => {
  return (
    <div className="lg:col-span-4 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 space-y-6 flex flex-col min-h-[300px]">
      <h4 className="text-lg font-bold">Budget Utilization</h4>
      <ComingSoonPlaceholder />
    </div>
  );
};
