import React from 'react';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export const ExpenseBreakdown: React.FC = () => {
  return (
    <div className="lg:col-span-4 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 flex flex-col min-h-[300px]">
      <h4 className="text-xl font-bold mb-6">Expense Breakdown</h4>
      <ComingSoonPlaceholder />
    </div>
  );
};
