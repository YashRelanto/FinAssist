
import React, { createContext, useContext, useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { Transaction, Goal, Category, Report, HeatmapData, UserProfile, Budget } from '../types';
import {
  buildFundedSnapshot,
  toGoalWithProgress,
  type GoalWithProgress,
} from '../lib/budgetGoalsApi';
import { format, eachDayOfInterval, startOfYear, endOfYear } from 'date-fns';
import {
  clearAuthSession,
  loadAuthSession,
  saveAuthSession,
  updateStoredUser,
} from '../lib/authSession';
import { apiFetch } from '../lib/api';
import { APP_ADVISOR_GREETING } from '../lib/utils';
import { activeUserId } from '../lib/activeUserId';
import {
  type AnalysisPeriod,
  DEFAULT_ANALYSIS_PERIOD,
  loadStoredAnalysisPeriod,
  storeAnalysisPeriod,
} from '../lib/analysisPeriod';

interface AppContextType {
  user: UserProfile;
  updateUser: (u: Partial<UserProfile>, options?: { syncNow?: boolean }) => void;
  
  transactions: Transaction[];
  accounts: any[];
  dbCategories: string[];
  dashboardSummary: any | null;
  dashboardSummaryLoading: boolean;
  budgetGoalsSummary: any | null;
  addTransaction: (t: Omit<Transaction, 'id'>) => void;
  updateTransaction: (id: string, t: Partial<Transaction>, onComplete?: (success: boolean) => void) => void;
  deleteTransaction: (id: string) => void;
  loadTransactions: (options?: { force?: boolean }) => Promise<void>;
  prependTransaction: (t: Transaction) => void;
  refreshAfterTransactionChange: () => void;
  loadAccounts: (options?: { force?: boolean }) => void;
  upsertAccount: (account: Record<string, unknown>) => void;
  loadDbCategories: () => void;
  analysisPeriod: AnalysisPeriod;
  setAnalysisPeriod: (period: AnalysisPeriod) => void;
  loadDashboardSummary: (options?: { force?: boolean }) => Promise<void>;
  loadBudgetGoalsSummary: (options?: { force?: boolean }) => Promise<void>;
  patchLinkedGoalProgress: (accountPatch?: Record<string, unknown>) => void;
  investmentsData: any | null;
  fixedDepositsData: any | null;
  loadInvestments: (options?: { force?: boolean }) => Promise<any | null>;
  loadFixedDeposits: (options?: { force?: boolean }) => Promise<any | null>;
  loadForecast: (params: {
    period?: AnalysisPeriod;
    accountId?: string;
    categoryId?: string;
    merchant?: string;
    force?: boolean;
  }) => Promise<any | null>;
  loadSpendingAnalytics: (params: {
    period?: AnalysisPeriod;
    accountId?: string;
    categoryId?: string;
    merchant?: string;
    force?: boolean;
  }) => Promise<any | null>;
  loadFinancialInsights: (params: {
    period?: AnalysisPeriod;
    accountId?: string;
    categoryId?: string;
    merchant?: string;
    force?: boolean;
    llm?: boolean;
  }) => Promise<any | null>;
  loadFinancialHealthInsights: (options?: { force?: boolean; llm?: boolean }) => Promise<any | null>;
  accountHubAnalysis: any | null;
  accountHubAnalysisLoading: boolean;
  loadAccountHubAnalysis: (options?: { force?: boolean }) => Promise<any | null>;
  budgets: Budget[];
  addBudget: (b: Omit<Budget, 'id'>) => void;
  updateBudget: (id: string, b: Partial<Budget>) => void;
  deleteBudget: (id: string) => void;
  loadBudgets: () => void;
  loadGoals: () => void;

  goals: Goal[];
  addGoal: (g: Omit<Goal, 'id'>) => void;
  updateGoal: (id: string, g: Partial<Goal>) => void;
  deleteGoal: (id: string) => void;
  
  categories: Category[];
  
  reports: Report[];
  uploadReport: (file: File) => void;
  
  heatmapData: HeatmapData[];
  
  // Navigation helper for heatmap -> add trans
  navigateToAddTransaction: (date: string) => void;
  pendingDate: string | null;
  resetPendingDate: () => void;
  signOut: () => void;
  setCurrentPage: (page: string) => void;
  currentPage: string;
  authReady: boolean;
  authError: string | null;
  clearAuthError: () => void;
  chatMessages: any[];
  setChatMessages: React.Dispatch<React.SetStateAction<any[]>>;
}


const AppContext = createContext<AppContextType | undefined>(undefined);

const TTL = {
  transactionsMs: 30_000,
  accountsMs: 60_000,
  budgetsMs: 60_000,
  goalsMs: 60_000,
  dbCategoriesMs: 5 * 60_000,
  dashboardSummaryMs: 30_000,
  budgetGoalsSummaryMs: 30_000,
  investmentsMs: 60_000,
  fixedDepositsMs: 60_000,
  forecastMs: 30_000,
  spendingAnalyticsMs: 30_000,
  financialInsightsMs: 30_000,
  financialHealthInsightsMs: 60_000,
};

const initialUser: UserProfile = {
  id: '',
  name: 'Guest User',
  email: '',
  isAuthenticated: false,
  userId: '',
  onboarded: false,
  income: 0,
  cityTier: 'Metro',
  fixedRent: 0,
  fixedEMI: 0,
  biggestCategory: '',
  primaryGoal: '',
  statementUploaded: false
};

const initialCategories: Category[] = [
  { id: 'cat-0', name: 'Uncategorized', icon: 'HelpCircle', subCategories: [] },
  { 
    id: 'cat-1', name: 'Food & Drinks', icon: 'Utensils', 
    subCategories: [
      { id: 'sub-fd1', name: 'General' }, { id: 'sub-fd2', name: 'bar-cafe' }, 
      { id: 'sub-fd3', name: 'Groceries' }, { id: 'sub-fd4', name: 'Restaurant' }, 
      { id: 'sub-fd5', name: 'fast food' }
    ] 
  },
  { 
    id: 'cat-2', name: 'Shopping', icon: 'ShoppingBag', 
    subCategories: [
      { id: 'sub-sh1', name: 'General' }, { id: 'sub-sh2', name: 'Clothes & store' }, 
      { id: 'sub-sh3', name: 'Drug-store/chemist' }, { id: 'sub-sh4', name: 'Electronics' }, 
      { id: 'sub-sh5', name: 'accessories' }, { id: 'sub-sh6', name: 'free time' }, 
      { id: 'sub-sh7', name: 'Gifts' }, { id: 'sub-sh8', name: 'health and beauty' }, 
      { id: 'sub-sh9', name: 'home' }, { id: 'sub-sh10', name: 'garden' }, 
      { id: 'sub-sh11', name: 'jewels' }, { id: 'sub-sh12', name: 'kids' }, 
      { id: 'sub-sh13', name: 'pets' }, { id: 'sub-sh14', name: 'stationary' }, 
      { id: 'sub-sh15', name: 'tools' }
    ] 
  },
  { 
    id: 'cat-3', name: 'Housing', icon: 'Home', 
    subCategories: [
      { id: 'sub-ho1', name: 'General' }, { id: 'sub-ho2', name: 'Energy' }, 
      { id: 'sub-ho3', name: 'utilities' }, { id: 'sub-ho4', name: 'maintenance/repairs' }, 
      { id: 'sub-ho5', name: 'Mortgage' }, { id: 'sub-ho6', name: 'Property Insurance' }, 
      { id: 'sub-ho7', name: 'Rent' }, { id: 'sub-ho8', name: 'Services' }
    ] 
  },
  { 
    id: 'cat-4', name: 'Transportation', icon: 'Bus', 
    subCategories: [
      { id: 'sub-tr1', name: 'General' }, { id: 'sub-tr2', name: 'Business Trip' }, 
      { id: 'sub-tr3', name: 'Public Transport' }, { id: 'sub-tr4', name: 'Taxi' }, 
      { id: 'sub-tr5', name: 'Flight' }, { id: 'sub-tr6', name: 'Train' }
    ] 
  },
  { 
    id: 'cat-5', name: 'Vehicle', icon: 'Car', 
    subCategories: [
      { id: 'sub-ve1', name: 'General' }, { id: 'sub-ve2', name: 'Fuel' }, 
      { id: 'sub-ve3', name: 'Leasing' }, { id: 'sub-ve4', name: 'Parking' }, 
      { id: 'sub-ve5', name: 'Rentals' }, { id: 'sub-ve6', name: 'Vehicle Insurance' }, 
      { id: 'sub-ve7', name: 'Vehicle Maintenance' }
    ] 
  },
  { 
    id: 'cat-6', name: 'Life & Entertainment', icon: 'Gamepad2', 
    subCategories: [
      { id: 'sub-le1', name: 'General' }, { id: 'sub-le2', name: 'Sports' }, 
      { id: 'sub-le3', name: 'Fitness' }, { id: 'sub-le4', name: 'Alcohol/tobacco' }, 
      { id: 'sub-le5', name: 'Books' }, { id: 'sub-le6', name: 'Subscriptions' }, 
      { id: 'sub-le7', name: 'Charity' }, { id: 'sub-le8', name: 'Gifts' }, 
      { id: 'sub-le9', name: 'Cultural Events' }, { id: 'sub-le10', name: 'Education/development' }, 
      { id: 'sub-le11', name: 'healthcare/doctor' }, { id: 'sub-le12', name: 'Hobbies' }, 
      { id: 'sub-le13', name: 'Holiday Trip/Hotels' }, { id: 'sub-le14', name: 'Life Events' }, 
      { id: 'sub-le15', name: 'Lottery/Gambling' }, { id: 'sub-le16', name: 'TV/Streaming' }, 
      { id: 'sub-le17', name: 'Wellness/Beauty' }
    ] 
  },
  { 
    id: 'cat-7', name: 'Communication/PC', icon: 'Laptop', 
    subCategories: [
      { id: 'sub-cp1', name: 'General' }, { id: 'sub-cp2', name: 'Internet' }, 
      { id: 'sub-cp3', name: 'Phone' }, { id: 'sub-cp4', name: 'Postal Service' }, 
      { id: 'sub-cp5', name: 'Software/apps/games' }
    ] 
  },
  { 
    id: 'cat-8', name: 'Financial Expense', icon: 'CreditCard', 
    subCategories: [
      { id: 'sub-fe1', name: 'General' }, { id: 'sub-fe2', name: 'Advisory' }, 
      { id: 'sub-fe3', name: 'Charges/Fees' }, { id: 'sub-fe4', name: 'Child Support' }, 
      { id: 'sub-fe5', name: 'Fines' }, { id: 'sub-fe6', name: 'Insurances' }, 
      { id: 'sub-fe7', name: 'loans/interests' }, { id: 'sub-fe8', name: 'taxes' }
    ] 
  },
  { 
    id: 'cat-9', name: 'Investments', icon: 'TrendingUp', 
    subCategories: [
      { id: 'sub-in1', name: 'General' }, { id: 'sub-in2', name: 'Collections' }, 
      { id: 'sub-in3', name: 'Financial Insvestments' }, { id: 'sub-in4', name: 'realty' }, 
      { id: 'sub-in5', name: 'savings' }, { id: 'sub-in6', name: 'Vehicles/chattels' }
    ] 
  },
  { 
    id: 'cat-10', name: 'Income', icon: 'DollarSign', 
    subCategories: [
      { id: 'sub-ic1', name: 'General' }, { id: 'sub-ic2', name: 'Checks/coupons' }, 
      { id: 'sub-ic3', name: 'Child Support' }, { id: 'sub-ic4', name: 'Dues and Grants' }, 
      { id: 'sub-ic5', name: 'Gifts' }, { id: 'sub-ic6', name: 'Interests/Dividends' }, 
      { id: 'sub-ic7', name: 'Lending/renting' }, { id: 'sub-ic8', name: 'Lottery/gambling' }, 
      { id: 'sub-ic9', name: 'Refunds (tax, purchase)' }, { id: 'sub-ic10', name: 'Rental Income' }, 
      { id: 'sub-ic11', name: 'Sale' }, { id: 'sub-ic12', name: 'Wage/invoices' }
    ] 
  },
  { 
    id: 'cat-11', name: 'others', icon: 'MoreHorizontal', 
    subCategories: [
      { id: 'sub-ot1', name: 'General' }, { id: 'sub-ot2', name: 'Missing' }
    ] 
  },
];

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile>(initialUser);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const profileSyncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearAuthError = useCallback(() => setAuthError(null), []);

  const syncProfileToServer = useCallback((profile: UserProfile) => {
    const userId = profile.userId || profile.id;
    if (!profile.isAuthenticated || !userId) return;

    apiFetch(`/api/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: profile.name,
        email: profile.email,
        onboarded: profile.onboarded,
        income: profile.income,
        city_tier: profile.cityTier,
        fixed_rent: profile.fixedRent,
        fixed_emi: profile.fixedEMI,
        biggest_category: profile.biggestCategory,
        primary_goal: profile.primaryGoal,
      }),
    }).catch((err) => console.error('Failed to sync profile changes:', err));
  }, []);

  const updateUser = useCallback((u: Partial<UserProfile>, options?: { syncNow?: boolean }) => {
    setUser((prev) => {
      const newUser = { ...prev, ...u };

      if (newUser.isAuthenticated && (newUser.userId || newUser.id)) {
        updateStoredUser(newUser);
      }

      if (newUser.isAuthenticated && newUser.userId) {
        if (profileSyncTimerRef.current) clearTimeout(profileSyncTimerRef.current);
        if (options?.syncNow) {
          syncProfileToServer(newUser);
        } else {
          profileSyncTimerRef.current = setTimeout(() => syncProfileToServer(newUser), 800);
        }
      }

      return newUser;
    });
  }, [syncProfileToServer]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [dbCategories, setDbCategories] = useState<string[]>([]);
  const [dashboardSummary, setDashboardSummary] = useState<any | null>(null);
  const [dashboardSummaryLoading, setDashboardSummaryLoading] = useState(false);
  const [budgetGoalsSummary, setBudgetGoalsSummary] = useState<any | null>(null);
  const [investmentsData, setInvestmentsData] = useState<any | null>(null);
  const [fixedDepositsData, setFixedDepositsData] = useState<any | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const categories = initialCategories;
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [chatMessages, setChatMessages] = useState<any[]>(() => [
    { 
      id: 1, 
      role: 'ai', 
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), 
      text: APP_ADVISOR_GREETING,
      type: 'text' 
    }
  ]);
  const [analysisPeriod, setAnalysisPeriodState] = useState<AnalysisPeriod>(

    () => loadStoredAnalysisPeriod(),
  );
  const [pendingDate, setPendingDate] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([
    { id: '1', title: 'Monthly Summary', date: 'Sept 2023', size: '2.4 MB', type: 'PDF' },
  ]);
  const [accountHubAnalysis, setAccountHubAnalysis] = useState<any | null>(null);
  const [accountHubAnalysisLoading, setAccountHubAnalysisLoading] = useState(false);
  const uid = useMemo(() => activeUserId(user), [user]);
  const isAuthed = !!(authReady && user.isAuthenticated && uid);

  const lastLoadedRef = useRef({
    transactions: 0,
    accounts: 0,
    budgets: 0,
    goals: 0,
    dbCategories: 0,
    dashboardSummary: 0,
    budgetGoalsSummary: 0,
    investments: 0,
    fixedDeposits: 0,
  });

  const inflightRef = useRef<{
    transactions?: Promise<void>;
    accounts?: Promise<void>;
    budgets?: Promise<void>;
    goals?: Promise<void>;
    dbCategories?: Promise<void>;
    dashboardSummary?: Promise<void>;
    budgetGoalsSummary?: Promise<void>;
    investments?: Promise<any | null>;
    fixedDeposits?: Promise<any | null>;
    forecast?: Map<string, Promise<any | null>>;
    spendingAnalytics?: Map<string, Promise<any | null>>;
    financialInsights?: Map<string, Promise<any | null>>;
    financialHealthInsights?: Map<string, Promise<any | null>>;
    accountHubAnalysis?: Promise<any | null>;
  }>({ forecast: new Map(), spendingAnalytics: new Map(), financialInsights: new Map(), financialHealthInsights: new Map() });

  const accountHubAnalysisRef = useRef<any | null>(null);
  const accountHubLoadedRef = useRef(false);
  const investmentsDataRef = useRef<any | null>(null);
  const fixedDepositsDataRef = useRef<any | null>(null);

  const forecastCacheRef = useRef<
    Map<string, { ts: number; data: any }>
  >(new Map());
  const spendingAnalyticsCacheRef = useRef<
    Map<string, { ts: number; data: any }>
  >(new Map());
  const financialInsightsCacheRef = useRef<
    Map<string, { ts: number; data: any }>
  >(new Map());
  const financialHealthInsightsCacheRef = useRef<
    Map<string, { ts: number; data: any }>
  >(new Map());

  const invalidateDerivedCaches = useCallback(() => {
    forecastCacheRef.current.clear();
    spendingAnalyticsCacheRef.current.clear();
    financialInsightsCacheRef.current.clear();
    financialHealthInsightsCacheRef.current.clear();
    inflightRef.current.forecast?.clear();
    inflightRef.current.spendingAnalytics?.clear();
    inflightRef.current.financialInsights?.clear();
    inflightRef.current.financialHealthInsights?.clear();
  }, []);

  const setAnalysisPeriod = useCallback((period: AnalysisPeriod) => {
    setAnalysisPeriodState(period);
    storeAnalysisPeriod(period);
    forecastCacheRef.current.clear();
    spendingAnalyticsCacheRef.current.clear();
    financialInsightsCacheRef.current.clear();
  }, []);

  // Restore persisted auth session on reload
  useEffect(() => {
    const session = loadAuthSession();
    if (session?.user) {
      setUser(session.user);
    }
    setAuthReady(true);
  }, []);

  // Check for Supabase OAuth redirect parameters in URL hash
  useEffect(() => {
    const handleHashAuth = async () => {
      const hash = window.location.hash;
      if (!hash) return;

      const params = new URLSearchParams(hash.substring(1));
      const oauthError = params.get('error_description') || params.get('error');
      if (oauthError) {
        window.history.replaceState(null, '', window.location.pathname);
        setAuthError(oauthError);
        return;
      }

      if (!hash.includes('access_token=')) return;

      const accessToken = params.get('access_token');
      const refreshToken = params.get('refresh_token');
      if (!accessToken) return;

      try {
        const base64Url = accessToken.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(
          atob(base64)
            .split('')
            .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
            .join('')
        );
        const decoded = JSON.parse(jsonPayload);

        if (!decoded?.sub || !decoded?.email) {
          setAuthError('OAuth sign-in did not return a valid user profile.');
          window.history.replaceState(null, '', window.location.pathname);
          return;
        }

        const user_id = decoded.sub as string;
        const email = decoded.email as string;
        const full_name =
          (decoded.user_metadata?.full_name as string | undefined) ||
          email.split('@')[0];

        const res = await apiFetch('/api/oauth-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id, email, full_name }),
        });
        const data = await res.json();

        window.history.replaceState(null, '', window.location.pathname);

        if (!res.ok || !data.success) {
          setAuthError(data.detail || data.message || 'OAuth sign-in failed');
          return;
        }

        const restoredUser: UserProfile = {
          id: user_id,
          isAuthenticated: true,
          userId: user_id,
          name: full_name,
          email,
          onboarded: data.user.onboarded || false,
          income: data.user.income || 0,
          cityTier: data.user.city_tier || 'Metro',
          fixedRent: data.user.fixed_rent || 0,
          fixedEMI: data.user.fixed_emi || 0,
          biggestCategory: data.user.biggest_category || '',
          primaryGoal: data.user.primary_goal || '',
          statementUploaded: false,
          role: data.user.role === 'admin' ? 'admin' : 'user',
        };

        saveAuthSession(accessToken, restoredUser, refreshToken || undefined);
        setUser(restoredUser);
        setAuthError(null);
      } catch (e) {
        console.error('Failed to complete OAuth sign-in:', e);
        window.history.replaceState(null, '', window.location.pathname);
        setAuthError('Failed to complete Google sign-in. Please try again.');
      }
    };

    handleHashAuth();
    window.addEventListener('hashchange', handleHashAuth);
    return () => window.removeEventListener('hashchange', handleHashAuth);
  }, []);

  const loadTransactions = useCallback((options?: { force?: boolean }): Promise<void> => {
    if (!isAuthed || !uid) {
      setTransactions([]);
      return Promise.resolve();
    }

    const now = Date.now();
    if (options?.force) {
      lastLoadedRef.current.transactions = 0;
    }
    if (!options?.force && now - lastLoadedRef.current.transactions < TTL.transactionsMs) {
      return Promise.resolve();
    }
    if (inflightRef.current.transactions) {
      return inflightRef.current.transactions;
    }

    const promise = apiFetch(
      `/api/transactions`
    )
      .then((res) => {
        if (!res.ok) throw new Error('Could not load transactions from database');
        return res.json();
      })
      .then((data) => {
        const rows = Array.isArray(data?.data) ? data.data : [];
        setTransactions(rows);
        lastLoadedRef.current.transactions = Date.now();
      })
      .catch((err) => {
        console.warn('Failed to load transactions from database:', err);
        setTransactions([]);
      })
      .finally(() => {
        inflightRef.current.transactions = undefined;
      });

    inflightRef.current.transactions = promise;
    return promise;
  }, [isAuthed, uid]);

  const loadAccounts = useCallback((options?: { force?: boolean }) => {
    if (!isAuthed || !uid) {
      setAccounts([]);
      return;
    }
    const now = Date.now();
    if (!options?.force) {
      if (now - lastLoadedRef.current.accounts < TTL.accountsMs) return;
      if (inflightRef.current.accounts) return;
    } else {
      lastLoadedRef.current.accounts = 0;
    }

    inflightRef.current.accounts = apiFetch(
      `/api/accounts`
    )
      .then((res) => res.json())
      .then((data) => {
        if (data.success && Array.isArray(data.data)) {
          setAccounts(data.data);
        } else {
          setAccounts([]);
        }
        lastLoadedRef.current.accounts = Date.now();
      })
      .catch((err) => {
        console.warn('Failed to load accounts:', err);
        setAccounts([]);
      })
      .finally(() => {
        inflightRef.current.accounts = undefined;
      });
  }, [isAuthed, uid]);

  const upsertAccount = useCallback((account: Record<string, unknown>) => {
    const id = account.account_id;
    if (!id) return;
    setAccounts((prev) => {
      const idx = prev.findIndex((a) => a.account_id === id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = { ...next[idx], ...account };
        return next;
      }
      return [...prev, account];
    });
  }, []);

  // Shared investments / fixed-deposit data, fetched once and reused across
  // the Investments tab and the goal money-source picker.
  const loadInvestments = useCallback(
    async (options?: { force?: boolean }) => {
      if (!isAuthed || !uid) {
        setInvestmentsData(null);
        investmentsDataRef.current = null;
        return null;
      }
      const now = Date.now();
      if (!options?.force) {
        if (
          now - lastLoadedRef.current.investments < TTL.investmentsMs &&
          investmentsDataRef.current
        )
          return investmentsDataRef.current;
        if (inflightRef.current.investments) return inflightRef.current.investments;
      } else {
        lastLoadedRef.current.investments = 0;
      }

      const promise = apiFetch('/api/investments')
        .then((res) => res.json())
        .then((data) => {
          if (data?.success) {
            setInvestmentsData(data);
            investmentsDataRef.current = data;
            lastLoadedRef.current.investments = Date.now();
            return data;
          }
          return investmentsDataRef.current;
        })
        .catch((err) => {
          console.warn('Failed to load investments:', err);
          return investmentsDataRef.current;
        })
        .finally(() => {
          inflightRef.current.investments = undefined;
        });

      inflightRef.current.investments = promise;
      return promise;
    },
    [isAuthed, uid],
  );

  const loadFixedDeposits = useCallback(
    async (options?: { force?: boolean }) => {
      if (!isAuthed || !uid) {
        setFixedDepositsData(null);
        fixedDepositsDataRef.current = null;
        return null;
      }
      const now = Date.now();
      if (!options?.force) {
        if (
          now - lastLoadedRef.current.fixedDeposits < TTL.fixedDepositsMs &&
          fixedDepositsDataRef.current
        )
          return fixedDepositsDataRef.current;
        if (inflightRef.current.fixedDeposits) return inflightRef.current.fixedDeposits;
      } else {
        lastLoadedRef.current.fixedDeposits = 0;
      }

      const promise = apiFetch('/api/fixed-deposits')
        .then((res) => res.json())
        .then((data) => {
          if (data?.success) {
            setFixedDepositsData(data);
            fixedDepositsDataRef.current = data;
            lastLoadedRef.current.fixedDeposits = Date.now();
            return data;
          }
          return fixedDepositsDataRef.current;
        })
        .catch((err) => {
          console.warn('Failed to load fixed deposits:', err);
          return fixedDepositsDataRef.current;
        })
        .finally(() => {
          inflightRef.current.fixedDeposits = undefined;
        });

      inflightRef.current.fixedDeposits = promise;
      return promise;
    },
    [isAuthed, uid],
  );

  const loadDbCategories = useCallback(() => {
    if (!authReady) return;
    const now = Date.now();
    if (now - lastLoadedRef.current.dbCategories < TTL.dbCategoriesMs) return;
    if (inflightRef.current.dbCategories) return;

    inflightRef.current.dbCategories = apiFetch('/api/categories')
      .then((res) => res.json())
      .then((data) => {
        if (data.success && Array.isArray(data.data)) {
          setDbCategories(data.data);
        } else {
          setDbCategories([]);
        }
        lastLoadedRef.current.dbCategories = Date.now();
      })
      .catch((err) => {
        console.warn('Failed to load categories:', err);
      })
      .finally(() => {
        inflightRef.current.dbCategories = undefined;
      });
  }, [authReady]);

  const loadBudgets = useCallback(() => {
    if (!isAuthed || !uid) {
      setBudgets([]);
      return;
    }

    const now = Date.now();
    if (now - lastLoadedRef.current.budgets < TTL.budgetsMs) return;
    if (inflightRef.current.budgets) return;

    inflightRef.current.budgets = apiFetch(
      `/api/budgets`
    )
      .then((res) => res.json())
      .then((data) => {
        if (data.success && Array.isArray(data.data)) {
          setBudgets(data.data);
        } else {
          setBudgets([]);
        }
        lastLoadedRef.current.budgets = Date.now();
      })
      .catch((err) => console.error('Failed to load budgets:', err))
      .finally(() => {
        inflightRef.current.budgets = undefined;
      });
  }, [isAuthed, uid]);

  const loadGoals = useCallback(() => {
    if (!isAuthed || !uid) {
      setGoals([]);
      return;
    }

    const now = Date.now();
    if (now - lastLoadedRef.current.goals < TTL.goalsMs) return;
    if (inflightRef.current.goals) return;

    inflightRef.current.goals = apiFetch(
      `/api/goals`
    )
      .then((res) => res.json())
      .then((data) => {
        if (data.success && Array.isArray(data.data)) {
          const icons = ['Target', 'ShieldCheck', 'PlaneTakeoff', 'Laptop'];
          const colors = ['bg-primary', 'bg-secondary', 'bg-tertiary', 'bg-outline'];
          const mapped = data.data.map((g: Goal, index: number) => ({
            ...g,
            icon: icons[index % icons.length],
            color: colors[index % colors.length],
          }));
          setGoals(mapped);
        } else {
          setGoals([]);
        }
        lastLoadedRef.current.goals = Date.now();
      })
      .catch((err) => console.error('Failed to load goals:', err))
      .finally(() => {
        inflightRef.current.goals = undefined;
      });
  }, [isAuthed, uid]);

  const loadDashboardSummary = useCallback(
    async (options?: { force?: boolean }) => {
      if (!isAuthed || !uid) {
        setDashboardSummary(null);
        return;
      }

      const now = Date.now();
      if (!options?.force) {
        if (now - lastLoadedRef.current.dashboardSummary < TTL.dashboardSummaryMs) return;
        if (inflightRef.current.dashboardSummary) return inflightRef.current.dashboardSummary;
      }

      setDashboardSummaryLoading(true);
      inflightRef.current.dashboardSummary = apiFetch(
        `/api/dashboard-summary?period=${encodeURIComponent(analysisPeriod)}`,
      )
        .then((res) => res.json())
        .then((data) => {
          if (data?.success) {
            setDashboardSummary(data);
            lastLoadedRef.current.dashboardSummary = Date.now();
          }
        })
        .catch((err) => {
          console.warn('Failed to load dashboard summary:', err);
        })
        .finally(() => {
          setDashboardSummaryLoading(false);
          inflightRef.current.dashboardSummary = undefined;
        });

      return inflightRef.current.dashboardSummary;
    },
    [isAuthed, uid, analysisPeriod],
  );

  const loadAccountHubAnalysis = useCallback(
    async (options?: { force?: boolean }) => {
      if (!isAuthed || !uid) {
        setAccountHubAnalysis(null);
        return null;
      }

      if (options?.force) {
        accountHubLoadedRef.current = false;
      }

      if (!options?.force && accountHubLoadedRef.current) {
        return accountHubAnalysisRef.current;
      }
      if (inflightRef.current.accountHubAnalysis) {
        return inflightRef.current.accountHubAnalysis;
      }

      setAccountHubAnalysisLoading(true);
      inflightRef.current.accountHubAnalysis = apiFetch(
        `/api/spending-analytics`,
      )
        .then((res) => res.json())
        .then((data) => {
          if (data?.success) {
            setAccountHubAnalysis(data);
            accountHubAnalysisRef.current = data;
            accountHubLoadedRef.current = true;
            return data;
          }
          return null;
        })
        .catch((err) => {
          console.warn('Failed to load account hub analysis:', err);
          return null;
        })
        .finally(() => {
          setAccountHubAnalysisLoading(false);
          inflightRef.current.accountHubAnalysis = undefined;
        });

      return inflightRef.current.accountHubAnalysis;
    },
    [isAuthed, uid],
  );

  const refreshUserData = useCallback(() => {
    loadTransactions();
    loadAccounts();
    loadBudgets();
    loadGoals();
    loadDbCategories();
    void loadDashboardSummary();
  }, [loadTransactions, loadAccounts, loadBudgets, loadGoals, loadDbCategories, loadDashboardSummary]);

  useEffect(() => {
    if (!authReady || !isAuthed) return;
    void loadDashboardSummary();
  }, [authReady, isAuthed, loadDashboardSummary]);

  const loadBudgetGoalsSummary = useCallback(
    async (options?: { force?: boolean }) => {
      if (!isAuthed || !uid) {
        setBudgetGoalsSummary(null);
        return;
      }
      const now = Date.now();
      if (options?.force) {
        lastLoadedRef.current.budgetGoalsSummary = 0;
        inflightRef.current.budgetGoalsSummary = undefined;
      }
      if (!options?.force) {
        if (
          now - lastLoadedRef.current.budgetGoalsSummary < TTL.budgetGoalsSummaryMs
        )
          return;
        if (inflightRef.current.budgetGoalsSummary) {
          return inflightRef.current.budgetGoalsSummary;
        }
      }

      inflightRef.current.budgetGoalsSummary = apiFetch(
        `/api/budget-goals-summary`
      )
        .then((res) => res.json())
        .then((data) => {
          if (data?.success) {
            setBudgetGoalsSummary(data);
            lastLoadedRef.current.budgetGoalsSummary = Date.now();
          }
        })
        .catch((err) => {
          console.warn('Failed to load budget goals summary:', err);
        })
        .finally(() => {
          inflightRef.current.budgetGoalsSummary = undefined;
        });

      return inflightRef.current.budgetGoalsSummary;
    },
    [isAuthed, uid],
  );

  const refreshAfterTransactionChange = useCallback(() => {
    lastLoadedRef.current.transactions = 0;
    lastLoadedRef.current.dashboardSummary = 0;
    lastLoadedRef.current.budgetGoalsSummary = 0;
    void loadTransactions({ force: true });
    void loadDashboardSummary({ force: true });
    void loadBudgetGoalsSummary({ force: true });
    invalidateDerivedCaches();
  }, [loadTransactions, loadDashboardSummary, loadBudgetGoalsSummary]);

  const patchLinkedGoalProgress = useCallback(
    (accountPatch?: Record<string, unknown>) => {
      const accountList =
        accountPatch?.account_id != null
          ? accounts.map((a) =>
              a.account_id === accountPatch.account_id
                ? { ...a, ...accountPatch }
                : a,
            )
          : accounts;
      const invData = investmentsDataRef.current ?? investmentsData;
      const fdData = fixedDepositsDataRef.current ?? fixedDepositsData;
      setBudgetGoalsSummary((prev) => {
        if (!prev?.goals?.length) return prev;
        const nextGoals = (prev.goals as GoalWithProgress[]).map((goal) => {
          const fundingSources =
            goal.fundingSources ?? goal.funding_sources ?? [];
          if (!fundingSources.length) return goal;
          const funded = buildFundedSnapshot(
            fundingSources,
            accountList,
            invData,
            fdData,
          );
          return toGoalWithProgress(goal, funded, fundingSources);
        });
        return { ...prev, goals: nextGoals };
      });
    },
    [accounts, investmentsData, fixedDepositsData],
  );

  const loadForecast = useCallback(
    async (params: {
      period?: AnalysisPeriod;
      accountId?: string;
      categoryId?: string;
      merchant?: string;
      force?: boolean;
    }): Promise<any | null> => {
      if (!isAuthed || !uid) return null;
      const period = params.period ?? analysisPeriod;

      const key = JSON.stringify({
        uid,
        period,
        accountId: params.accountId || '',
        categoryId: params.categoryId || '',
        merchant: params.merchant || '',
      });

      const now = Date.now();
      const cached = forecastCacheRef.current.get(key);
      if (!params.force && cached && now - cached.ts < TTL.forecastMs) {
        return cached.data;
      }

      const inflightMap = inflightRef.current.forecast!;
      const existing = inflightMap.get(key);
      if (existing) return existing;

      const query = new URLSearchParams({
        user_id: uid,
        period,
      });
      if (params.accountId) query.set('account_id', params.accountId);
      if (params.categoryId) query.set('category_id', params.categoryId);
      if (params.merchant) query.set('merchant', params.merchant);

      const p = apiFetch(`/api/forecast?${query.toString()}`)
        .then((res) => res.json())
        .then((data) => {
          forecastCacheRef.current.set(key, { ts: Date.now(), data });
          return data as any;
        })
        .catch((err) => {
          console.warn('Failed to load forecast:', err);
          return null;
        })
        .finally(() => {
          inflightMap.delete(key);
        });

      inflightMap.set(key, p);
      return p;
    },
    [isAuthed, uid, analysisPeriod],
  );

  const buildAnalyticsQueryKey = (
    endpoint: string,
    params: {
      period?: AnalysisPeriod;
      accountId?: string;
      categoryId?: string;
      merchant?: string;
    },
  ) =>
    JSON.stringify({
      endpoint,
      uid,
      period: params.period ?? '3m',
      accountId: params.accountId || '',
      categoryId: params.categoryId || '',
      merchant: params.merchant || '',
    });

  const loadSpendingAnalytics = useCallback(
    async (params: {
      period?: AnalysisPeriod;
      accountId?: string;
      categoryId?: string;
      merchant?: string;
      force?: boolean;
    }): Promise<any | null> => {
      if (!isAuthed || !uid) return null;
      const period = params.period ?? '3m';
      const key = buildAnalyticsQueryKey('spending', { ...params, period });
      const now = Date.now();
      const cached = spendingAnalyticsCacheRef.current.get(key);
      if (!params.force && cached && now - cached.ts < TTL.spendingAnalyticsMs) {
        return cached.data;
      }
      const inflightMap = inflightRef.current.spendingAnalytics!;
      const existing = inflightMap.get(key);
      if (existing) return existing;

      const query = new URLSearchParams({ period });
      if (params.accountId) query.set('account_id', params.accountId);
      if (params.categoryId) query.set('category_id', params.categoryId);
      if (params.merchant) query.set('merchant', params.merchant);

      const p = apiFetch(`/api/spending-analytics?${query.toString()}`)
        .then((res) => res.json())
        .then((data) => {
          spendingAnalyticsCacheRef.current.set(key, { ts: Date.now(), data });
          return data;
        })
        .catch((err) => {
          console.warn('Failed to load spending analytics:', err);
          return null;
        })
        .finally(() => inflightMap.delete(key));

      inflightMap.set(key, p);
      return p;
    },
    [isAuthed, uid],
  );

  const loadFinancialInsights = useCallback(
    async (params: {
      period?: AnalysisPeriod;
      accountId?: string;
      categoryId?: string;
      merchant?: string;
      force?: boolean;
      llm?: boolean;
    }): Promise<any | null> => {
      if (!isAuthed || !uid) return null;
      const period = params.period ?? '3m';
      const key = buildAnalyticsQueryKey('insights', { ...params, period });
      const cacheKey = `${key}:${params.llm ? 'llm' : 'instant'}`;
      const now = Date.now();
      const cached = financialInsightsCacheRef.current.get(cacheKey);
      if (!params.force && cached && now - cached.ts < TTL.financialInsightsMs) {
        return cached.data;
      }
      const inflightMap = inflightRef.current.financialInsights!;
      const existing = inflightMap.get(cacheKey);
      if (existing) return existing;

      const query = new URLSearchParams({ user_id: uid, period });
      if (params.accountId) query.set('account_id', params.accountId);
      if (params.categoryId) query.set('category_id', params.categoryId);
      if (params.merchant) query.set('merchant', params.merchant);
      if (params.llm) query.set('llm', '1');

      const p = apiFetch(`/api/financial-insights?${query.toString()}`)
        .then((res) => res.json())
        .then((data) => {
          financialInsightsCacheRef.current.set(cacheKey, { ts: Date.now(), data });
          return data;
        })
        .catch((err) => {
          console.warn('Failed to load financial insights:', err);
          return null;
        })
        .finally(() => inflightMap.delete(cacheKey));

      inflightMap.set(cacheKey, p);
      return p;
    },
    [isAuthed, uid],
  );

  const loadFinancialHealthInsights = useCallback(
    async (options?: { force?: boolean; llm?: boolean }): Promise<any | null> => {
      if (!isAuthed || !uid) return null;
      const cacheKey = options?.llm ? 'llm' : 'instant';
      const now = Date.now();
      const cached = financialHealthInsightsCacheRef.current.get(cacheKey);
      if (!options?.force && cached && now - cached.ts < TTL.financialHealthInsightsMs) {
        return cached.data;
      }
      const inflightMap = inflightRef.current.financialHealthInsights!;
      const existing = inflightMap.get(cacheKey);
      if (existing) return existing;

      const query = new URLSearchParams({ user_id: uid });
      if (options?.llm) query.set('llm', '1');

      const p = apiFetch(`/api/financial-health-insights?${query.toString()}`)
        .then((res) => res.json())
        .then((data) => {
          financialHealthInsightsCacheRef.current.set(cacheKey, { ts: Date.now(), data });
          return data;
        })
        .catch((err) => {
          console.warn('Failed to load financial health insights:', err);
          return null;
        })
        .finally(() => inflightMap.delete(cacheKey));

      inflightMap.set(cacheKey, p);
      return p;
    },
    [isAuthed, uid],
  );

  // Load from database once auth session is restored
  useEffect(() => {
    if (!authReady) return;
    if (user.isAuthenticated && activeUserId(user)) {
      refreshUserData();
    } else {
      setTransactions([]);
      setAccounts([]);
      setGoals([]);
      setBudgets([]);
      setDashboardSummary(null);
      setBudgetGoalsSummary(null);
    }
  }, [authReady, user.isAuthenticated, user.userId, user.id, refreshUserData]);

  // NOTE: tab-focus refetch was REMOVED intentionally. It called refreshUserData() (which reloads
  // the dashboard summary and re-runs the financial-health compute) whenever the window regained
  // focus and a cache was stale — read by users as "random" API calls. Data now loads only on mount
  // (page reload) and on explicit user actions (add/edit transaction, the refresh button, etc.).

  const prependTransaction = (t: Transaction) => {
    setTransactions((prev) => [t, ...prev]);
  };

  const addTransaction = (t: Omit<Transaction, 'id'>) => {
    if (uid) {
      // Optimistic UI update (instant list refresh).
      const optimistic: Transaction = {
        ...(t as any),
        id: `optimistic-${Date.now()}`,
      };
      setTransactions((prev) => [optimistic, ...prev]);
      lastLoadedRef.current.transactions = Date.now();

      apiFetch('/api/transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: uid,
          account_id: t.account || 'Primary Checking',
          amount: Math.abs(t.amount),
          transaction_type: t.type,
          merchant_name: t.merchant,
          description: t.notes || '',
          main_category: t.category,
          category_name: t.category,
          sub_category: t.subCategory || 'General',
          sub_category_name: t.subCategory || 'General',
          transaction_date: t.date,
          is_recurring: Boolean((t as Transaction).is_recurring),
          recurrence_period: (t as Transaction).is_recurring
            ? (t as Transaction).recurrence_period ?? 'monthly'
            : null,
          recurrence_skips: (t as Transaction).is_recurring
            ? (t as Transaction).recurrence_skips ?? 0
            : 0,
        }),
      })
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ ok }) => {
          if (!ok) throw new Error('Database save failed');
          refreshAfterTransactionChange();
        })
        .catch((err) => {
          console.error('Database save failed:', err);
          // Rollback optimistic insert on failure.
          setTransactions((prev) => prev.filter((x) => x.id !== optimistic.id));
        });
      return;
    }
  };

  const updateTransaction = (
    id: string,
    t: Partial<Transaction>,
    onComplete?: (success: boolean) => void,
  ) => {
    const uid = activeUserId(user);
    if (!uid) {
      onComplete?.(false);
      return;
    }

    const existing = transactions.find((item) => item.id === id);
    const existingWithAccount = existing as (Transaction & { account_id?: string }) | undefined;

    const accountId =
      t.account ||
      existingWithAccount?.account_id ||
      existing?.account ||
      '';

    const payload = {
      user_id: uid,
      account_id: accountId,
      amount: Math.abs(t.amount ?? existing?.amount ?? 0),
      transaction_type: t.type ?? existing?.type ?? 'expense',
      merchant_name: t.merchant ?? existing?.merchant ?? '',
      description: t.notes ?? existing?.notes ?? '',
      main_category: t.category ?? existing?.category ?? 'Others',
      sub_category: t.subCategory || existing?.subCategory || 'General',
      transaction_date: t.date ?? existing?.date ?? new Date().toISOString().split('T')[0],
      is_recurring: Boolean(
        (t as Transaction & { is_recurring?: boolean }).is_recurring ??
          existing?.is_recurring ??
          false,
      ),
      recurrence_period:
        (t as Transaction & { recurrence_period?: string | null }).recurrence_period ??
        existing?.recurrence_period ??
        null,
      recurrence_skips:
        (t as Transaction & { recurrence_skips?: number }).recurrence_skips ??
        existing?.recurrence_skips ??
        0,
    };

    apiFetch(`/api/transactions/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success) {
          refreshAfterTransactionChange();
          onComplete?.(true);
        } else {
          console.error('Failed to update transaction:', data.detail ?? data);
          onComplete?.(false);
        }
      })
      .catch((err) => {
        console.error('Failed to update transaction:', err);
        onComplete?.(false);
      });
  };

  const deleteTransaction = (id: string) => {
    if (!uid) return;

    apiFetch(`/api/transactions/${id}`, { method: 'DELETE' })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setTransactions((prev) => prev.filter((t) => t.id !== id));
          refreshAfterTransactionChange();
        }
      })
      .catch(err => console.error('Failed to delete transaction:', err));
  };

  const addBudget = (b: Omit<Budget, 'id'>) => {
    if (uid) {
      apiFetch('/api/budgets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: uid,
          category_name: b.categoryName,
          budget_name: b.budgetName,
          amount: b.amount,
          period: b.period || 'monthly',
          start_date: b.startDate || null,
          end_date: b.endDate || null,
          alert_threshold: b.alertThreshold || 80.0
        })
      })
      .then(res => res.json())
      .then(() => {
        lastLoadedRef.current.budgets = 0;
        loadBudgets();
        lastLoadedRef.current.budgetGoalsSummary = 0;
        void loadBudgetGoalsSummary({ force: true });
        lastLoadedRef.current.dashboardSummary = 0;
        void loadDashboardSummary({ force: true });
      })
      .catch(err => console.error("Failed to add budget:", err));
    }
  };

  const updateBudget = (id: string, b: Partial<Budget>) => {
    apiFetch(`/api/budgets/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user.userId || user.id,
        category_name: b.categoryName || 'Others',
        budget_name: b.budgetName || '',
        amount: b.amount || 0,
        period: b.period || 'monthly',
        start_date: b.startDate || null,
        end_date: b.endDate || null,
        alert_threshold: b.alertThreshold || 80.0
      })
    })
    .then(res => res.json())
    .then(() => {
      lastLoadedRef.current.budgets = 0;
      loadBudgets();
      lastLoadedRef.current.budgetGoalsSummary = 0;
      void loadBudgetGoalsSummary({ force: true });
      lastLoadedRef.current.dashboardSummary = 0;
      void loadDashboardSummary({ force: true });
    })
    .catch(err => console.error("Failed to update budget:", err));
  };

  const deleteBudget = (id: string) => {
    apiFetch(`/api/budgets/${id}`, {
      method: 'DELETE'
    })
    .then(res => res.json())
    .then(() => {
      lastLoadedRef.current.budgets = 0;
      loadBudgets();
      lastLoadedRef.current.budgetGoalsSummary = 0;
      void loadBudgetGoalsSummary({ force: true });
      lastLoadedRef.current.dashboardSummary = 0;
      void loadDashboardSummary({ force: true });
    })
    .catch(err => console.error("Failed to delete budget:", err));
  };

  const addGoal = (g: Omit<Goal, 'id'>) => {
    if (!uid) return;

    const tempId = `temp-${Date.now()}`;
    const fundingSources = g.fundingSources || [];
    const funded = buildFundedSnapshot(
      fundingSources,
      accounts,
      investmentsDataRef.current ?? investmentsData,
      fixedDepositsDataRef.current ?? fixedDepositsData,
    );
    const optimistic = toGoalWithProgress(
      { ...g, id: tempId, icon: g.icon || 'Target', color: g.color || 'bg-primary' },
      funded,
      fundingSources,
    );

    setGoals((prev) => [...prev, optimistic]);
    setBudgetGoalsSummary((prev) =>
      prev ? { ...prev, goals: [...(prev.goals || []), optimistic] } : prev,
    );

    apiFetch('/api/goals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: uid,
        goal_name: g.label,
        description: g.sub,
        target_amount: g.target,
        current_amount: optimistic.current,
        target_date: g.date,
        status: 'active',
        color: g.color || 'bg-primary',
        funding_sources: fundingSources,
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data?.success) throw new Error(data?.detail || 'Failed to create goal');
        const realId = data.data?.goal_id;
        if (!realId) return;
        const applyRealId = (goal: GoalWithProgress) =>
          goal.id === tempId ? { ...goal, id: realId } : goal;
        setGoals((prev) => prev.map(applyRealId));
        setBudgetGoalsSummary((prev) =>
          prev
            ? { ...prev, goals: (prev.goals || []).map(applyRealId) }
            : prev,
        );
      })
      .catch((err) => {
        console.error('Failed to add goal:', err);
        setGoals((prev) => prev.filter((x) => x.id !== tempId));
        setBudgetGoalsSummary((prev) =>
          prev
            ? {
                ...prev,
                goals: (prev.goals || []).filter((x: GoalWithProgress) => x.id !== tempId),
              }
            : prev,
        );
      });
  };

  const updateGoal = (id: string, g: Partial<Goal>) => {
    const existing =
      ((budgetGoalsSummary?.goals as GoalWithProgress[] | undefined)?.find(
        (x) => x.id === id,
      ) as GoalWithProgress | undefined) ||
      (goals.find((x) => x.id === id) as GoalWithProgress | undefined);
    if (!existing) return;

    const fundingSources =
      g.fundingSources ??
      existing.fundingSources ??
      existing.funding_sources ??
      [];
    const funded = buildFundedSnapshot(
      fundingSources,
      accounts,
      investmentsDataRef.current ?? investmentsData,
      fixedDepositsDataRef.current ?? fixedDepositsData,
    );
    const merged = toGoalWithProgress(
      {
        ...existing,
        label: g.label ?? existing.label,
        sub: g.sub ?? existing.sub,
        target: g.target ?? existing.target,
        date: g.date ?? existing.date,
        icon: g.icon ?? existing.icon,
        color: g.color ?? existing.color,
        fundingSources,
      },
      funded,
      fundingSources,
    );

    let goalsBefore: Goal[] = [];
    let summaryGoalsBefore: GoalWithProgress[] = [];

    setGoals((prev) => {
      goalsBefore = prev;
      return prev.map((goal) => (goal.id === id ? merged : goal));
    });
    setBudgetGoalsSummary((prev) => {
      if (!prev) return prev;
      summaryGoalsBefore = (prev.goals || []) as GoalWithProgress[];
      return {
        ...prev,
        goals: summaryGoalsBefore.map((goal) => (goal.id === id ? merged : goal)),
      };
    });

    apiFetch(`/api/goals/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user.userId || user.id,
        goal_name: merged.label,
        description: merged.sub,
        target_amount: merged.target,
        current_amount: merged.current,
        target_date: merged.date,
        status: 'active',
        color: merged.color || 'bg-primary',
        funding_sources: fundingSources,
      }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data?.success) throw new Error(data?.detail || 'Failed to update goal');
      })
      .catch((err) => {
        console.error('Failed to update goal:', err);
        setGoals(goalsBefore);
        setBudgetGoalsSummary((prev) =>
          prev ? { ...prev, goals: summaryGoalsBefore } : prev,
        );
      });
  };

  const deleteGoal = (id: string) => {
    let goalsBefore: Goal[] = [];
    let summaryGoalsBefore: GoalWithProgress[] = [];

    setGoals((prev) => {
      goalsBefore = prev;
      return prev.filter((goal) => goal.id !== id);
    });
    setBudgetGoalsSummary((prev) => {
      if (!prev) return prev;
      summaryGoalsBefore = (prev.goals || []) as GoalWithProgress[];
      return {
        ...prev,
        goals: summaryGoalsBefore.filter((goal) => goal.id !== id),
      };
    });

    apiFetch(`/api/goals/${id}`, { method: 'DELETE' })
      .then((res) => res.json())
      .then((data) => {
        if (!data?.success) throw new Error(data?.detail || 'Failed to delete goal');
      })
      .catch((err) => {
        console.error('Failed to delete goal:', err);
        setGoals(goalsBefore);
        setBudgetGoalsSummary((prev) =>
          prev ? { ...prev, goals: summaryGoalsBefore } : prev,
        );
      });
  };

  const navigateToAddTransaction = (date: string) => {
    setPendingDate(date);
    setCurrentPage('transactions');
  };

  const resetPendingDate = () => setPendingDate(null);

  const signOut = () => {
    clearAuthSession();
    setAuthError(null);
    setUser(initialUser);
    setTransactions([]);
    setGoals([]);
    setBudgets([]);
    setReports([]);
    setCurrentPage('dashboard');
    setChatMessages([
      { 
        id: 1, 
        role: 'ai', 
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), 
        text: APP_ADVISOR_GREETING,
        type: 'text' 
      }
    ]);
  };


  const uploadReport = async (file: File) => {
    const newReport: Report = {
      id: Math.random().toString(36).substr(2, 9),
      title: file.name,
      date: format(new Date(), 'MMM yyyy'),
      size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
      type: file.name.endsWith('.csv') ? 'CSV' : 'PDF'
    };
    setReports(prev => [newReport, ...prev]);

    if (user.userId) {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("user_id", user.userId);
      formData.append("account_name", "Primary Checking");

      try {
        const response = await apiFetch('/api/statement/upload', {
          method: 'POST',
          body: formData,
        });
        if (response.ok) {
          console.log("Statement successfully uploaded and parsed.");
          refreshAfterTransactionChange();
        } else {
          console.error("Backend failed to parse the statement.");
        }
      } catch (err) {
        console.error("Failed to connect to backend:", err);
      }
    }
  };

  // Generate heatmap data based on transaction dates
  const heatmapData: HeatmapData[] = eachDayOfInterval({
    start: startOfYear(new Date()),
    end: endOfYear(new Date())
  }).map(date => {
    const dStr = format(date, 'yyyy-MM-dd');
    const count = transactions.filter(t => t.date === dStr).length;
    return { date: dStr, count };
  });

  return (
    <AppContext.Provider value={{
      user, updateUser,
      transactions,
      accounts,
      dbCategories,
      dashboardSummary,
      dashboardSummaryLoading,
      budgetGoalsSummary,
      analysisPeriod,
      setAnalysisPeriod,
      addTransaction, updateTransaction, deleteTransaction, loadTransactions, prependTransaction,
      refreshAfterTransactionChange,
      loadAccounts,
      upsertAccount,
      loadDbCategories,
      loadDashboardSummary,
      loadBudgetGoalsSummary,
      patchLinkedGoalProgress,
      investmentsData,
      fixedDepositsData,
      loadInvestments,
      loadFixedDeposits,
      loadForecast,
      loadSpendingAnalytics,
      loadFinancialInsights,
      loadFinancialHealthInsights,
      accountHubAnalysis, accountHubAnalysisLoading, loadAccountHubAnalysis,
      budgets, addBudget, updateBudget, deleteBudget, loadBudgets, loadGoals,
      goals, addGoal, updateGoal, deleteGoal,
      categories,
      reports, uploadReport,
      heatmapData,
      navigateToAddTransaction, pendingDate, resetPendingDate,
      signOut,
      setCurrentPage, currentPage,
      authReady,
      authError,
      clearAuthError,
      chatMessages, setChatMessages,
    }}>

      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
};
