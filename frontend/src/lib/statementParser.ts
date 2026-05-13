
import { Transaction, Category } from '../types';

interface AnalysisResult {
  transactions: Omit<Transaction, 'id'>[];
  summary: {
    totalCategorized: number;
    totalUnknown: number;
    highAmountAnomalies: number;
  };
}

const KNOWN_MERCHANTS: Record<string, { category: string; subCategory: string }> = {
  'Starbucks': { category: 'Food & Drinks', subCategory: 'bar-cafe' },
  'Amazon': { category: 'Shopping', subCategory: 'Electronics' },
  'Flipkart': { category: 'Shopping', subCategory: 'General' },
  'Uber': { category: 'Transportation', subCategory: 'Taxi' },
  'Netflix': { category: 'Life & Entertainment', subCategory: 'TV/Streaming' },
  'Zomato': { category: 'Food & Drinks', subCategory: 'Restaurant' },
  'HDFC Home Loan': { category: 'Housing', subCategory: 'Mortgage' },
  'Jio Fiber': { category: 'Communication/PC', subCategory: 'Internet' },
};

const HIGH_AMOUNT_THRESHOLD = 5000;

export const analyzeStatement = (fileName: string, categories: Category[]): AnalysisResult => {
  // Simulate statement analysis
  // In a real app, this would be an API call to a backend model
  
  const simulationMerchants = [
    'Starbucks', 'Amazon', 'Unknown Merchant #12', 'Uber', 'Big High Price Store',
    'Zomato', 'Netflix', 'Jio Fiber', 'Suspicious Vendor', 'HDFC Home Loan'
  ];

  const transactions: Omit<Transaction, 'id'>[] = simulationMerchants.map(merchant => {
    const isKnown = !!KNOWN_MERCHANTS[merchant];
    const amount = merchant === 'HDFC Home Loan' ? -25000 : merchant === 'Big High Price Store' ? -12000 : -(Math.random() * 2000 + 50);
    const date = new Date(Date.now() - Math.floor(Math.random() * 60) * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    
    // Anomaly logic: amount is high or merchant is unknown
    const isHighAmount = Math.abs(amount) > HIGH_AMOUNT_THRESHOLD;
    
    return {
      date,
      merchant,
      category: isKnown ? KNOWN_MERCHANTS[merchant].category : 'Uncategorized',
      subCategory: isKnown ? KNOWN_MERCHANTS[merchant].subCategory : undefined,
      amount,
      account: 'Statement Upload',
      type: 'expense',
      notes: isHighAmount ? 'High amount anomaly detected. Please verify.' : undefined
    };
  });

  const summary = {
    totalCategorized: transactions.filter(t => t.category !== 'Uncategorized').length,
    totalUnknown: transactions.filter(t => t.category === 'Uncategorized').length,
    highAmountAnomalies: transactions.filter(t => Math.abs(t.amount) > HIGH_AMOUNT_THRESHOLD).length
  };

  return { transactions, summary };
};
