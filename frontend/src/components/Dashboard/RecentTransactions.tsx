import React from 'react';
import { ComingSoonPlaceholder } from './ComingSoonPlaceholder';

export const RecentTransactions: React.FC = () => {
  return (
    <div className="lg:col-span-8 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30 flex flex-col min-h-[300px]">
      <div className="flex justify-between items-center mb-6">
        <h4 className="text-lg font-bold">Recent Transactions</h4>
      </div>
      <ComingSoonPlaceholder />
    </div>
  );
};
