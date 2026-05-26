
export interface UserProfile {
  userId?: string;
  name: string;
  email: string;
  isAuthenticated: boolean;
  onboarded: boolean;
  income: number;
  cityTier: 'Metro' | 'Tier 1' | 'Tier 2' | 'Tier 3';
  fixedRent: number;
  fixedEMI: number;
  biggestCategory: string;
  primaryGoal: string;
  statementUploaded: boolean;
}

export interface SubCategory {
  id: string;
  name: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  subCategories: SubCategory[];
}

export interface Transaction {
  id: string;
  date: string;
  merchant: string;
  category: string;
  subCategory?: string;
  amount: number;
  account: string;
  notes?: string;
  type: 'income' | 'expense';
}

export interface Goal {
  id: string;
  label: string;
  sub: string;
  current: number;
  target: number;
  date: string;
  icon: string;
  color: string;
}

export interface Report {
  id: string;
  title: string;
  date: string;
  size: string;
  type: 'PDF' | 'CSV';
}

export interface HeatmapData {
  date: string;
  count: number; // number of transactions/actions on that day
}
