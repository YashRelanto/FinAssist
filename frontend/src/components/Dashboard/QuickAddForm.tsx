import React from 'react';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export const QuickAddForm: React.FC = () => {
  return (
    <div className="lg:col-span-5 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 flex flex-col min-h-[300px]">
      <h4 className="text-lg font-bold mb-6">Quick Add Transaction</h4>
      <ComingSoonPlaceholder />
    </div>
  );
};
