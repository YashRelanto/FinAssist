import React from 'react';
import { 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  Legend, 
  ComposedChart,
  Line
} from 'recharts';

interface FinancialPerformanceChartProps {
  data?: any[];
}

export const FinancialPerformanceChart: React.FC<FinancialPerformanceChartProps> = ({ data }) => {
  return (
    <div className="lg:col-span-8 bg-surface-container-lowest p-6 rounded-xl soft-shadow border border-outline-variant/30">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h4 className="text-xl font-bold">Financial Performance</h4>
          <p className="text-xs text-outline mt-1 font-medium">Income vs Expenses vs Net Savings</p>
        </div>
      </div>
      <div className="h-[350px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data || []}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B' }} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748B' }} />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#FFFFFF', 
                borderRadius: '12px', 
                border: '1px solid #E2E8F0', 
                boxShadow: '0 4px 12px -1px rgb(0 0 0 / 0.1)' 
              }} 
            />
            <Legend iconType="circle" wrapperStyle={{ fontSize: '10px', fontWeight: 'bold', paddingTop: '20px' }} />
            <Bar dataKey="income" name="Total Income" fill="#006c49" radius={[4, 4, 0, 0]} barSize={20} />
            <Bar dataKey="expense" name="Total Expense" fill="#ba1a1a" radius={[4, 4, 0, 0]} barSize={20} />
            <Line type="monotone" dataKey="net" name="Net Savings" stroke="#004ac6" strokeWidth={3} dot={{ r: 4, fill: '#004ac6' }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
