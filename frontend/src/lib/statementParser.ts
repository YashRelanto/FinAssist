import { Transaction, Category } from '../types';

export interface AnalysisResult {
  transactions: Omit<Transaction, 'id'>[];
  summary: {
    totalCategorized: number;
    totalUnknown: number;
    highAmountAnomalies: number;
  };
}

export interface ParseError extends Error {
  type: 'password_required' | 'wrong_password' | 'general';
}

const HIGH_AMOUNT_THRESHOLD = 5000;

export const analyzeStatementFile = async (
  file: File,
  categories: Category[],
  password?: string
): Promise<AnalysisResult> => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (password) {
      formData.append('password', password);
    }

    const response = await fetch('http://localhost:8000/api/statement/parse-file', {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      // Check if it's a password error from backend
      const detail = data.detail;
      if (detail && typeof detail === 'object' && (detail.type === 'password_required' || detail.type === 'wrong_password')) {
        const error = new Error(detail.message || 'Password authentication required') as ParseError;
        error.type = detail.type;
        throw error;
      }
      
      // Handle standard detail string
      if (typeof detail === 'string') {
        if (detail.includes('password') || detail.includes('encrypted')) {
          const error = new Error(detail) as ParseError;
          error.type = password ? 'wrong_password' : 'password_required';
          throw error;
        }
      }

      const error = new Error(data.detail || 'Failed to parse statement') as ParseError;
      error.type = 'general';
      throw error;
    }

    // Now we map the parsed transactions to the frontend structure
    const backendTxs = data.transactions || [];
    
    const transactions: Omit<Transaction, 'id'>[] = backendTxs.map((t: any) => {
      // Map main category and subcategory from backend or categorize locally
      // Try to match description to a category
      let matchedCategory = 'Uncategorized';
      let matchedSubCategory: string | undefined = undefined;

      const desc = (t.description || '').toLowerCase();
      
      // Simple frontend categorization matching keywords
      for (const cat of categories) {
        if (desc.includes(cat.name.toLowerCase())) {
          matchedCategory = cat.name;
          if (cat.subCategories && cat.subCategories.length > 0) {
            matchedSubCategory = cat.subCategories[0].name;
          }
          break;
        }
        for (const sub of cat.subCategories || []) {
          if (desc.includes(sub.name.toLowerCase())) {
            matchedCategory = cat.name;
            matchedSubCategory = sub.name;
            break;
          }
        }
        if (matchedCategory !== 'Uncategorized') break;
      }

      // Check transaction type to set correct sign for amount
      // In frontend, expenses are negative, incomes are positive
      const dbType = t.transaction_type.toLowerCase();
      const type: 'income' | 'expense' = (dbType === 'credit' || dbType === 'income') ? 'income' : 'expense';
      const rawAmount = Math.abs(t.amount);
      const amount = type === 'income' ? rawAmount : -rawAmount;

      const isHighAmount = Math.abs(amount) > HIGH_AMOUNT_THRESHOLD;

      return {
        date: t.transaction_date,
        merchant: t.merchant_name || t.description || 'Transaction',
        category: matchedCategory,
        subCategory: matchedSubCategory,
        amount,
        account: 'Statement Upload',
        type,
        notes: isHighAmount ? 'High amount anomaly detected. Please verify.' : undefined,
        runningBalance: t.running_balance
      };
    });

    const summary = {
      totalCategorized: transactions.filter(t => t.category !== 'Uncategorized').length,
      totalUnknown: transactions.filter(t => t.category === 'Uncategorized').length,
      highAmountAnomalies: transactions.filter(t => Math.abs(t.amount) > HIGH_AMOUNT_THRESHOLD).length
    };

    return { transactions, summary };
  } catch (err: any) {
    if (err.type) {
      throw err;
    }
    const error = new Error(err.message || 'An error occurred during file upload') as ParseError;
    error.type = 'general';
    throw error;
  }
};
