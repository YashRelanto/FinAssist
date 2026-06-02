
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Transaction, Goal, Category, Report, HeatmapData, UserProfile, Budget } from '../types';
import { format, eachDayOfInterval, startOfYear, endOfYear } from 'date-fns';
import {
  clearAuthSession,
  loadAuthSession,
  saveAuthSession,
  updateStoredUser,
} from '../lib/authSession';
import { apiFetch } from '../lib/api';
import { activeUserId } from '../lib/activeUserId';

interface AppContextType {
  user: UserProfile;
  updateUser: (u: Partial<UserProfile>) => void;
  
  transactions: Transaction[];
  addTransaction: (t: Omit<Transaction, 'id'>) => void;
  addTransactions: (ts: Omit<Transaction, 'id'>[]) => void;
  updateTransaction: (id: string, t: Partial<Transaction>, onComplete?: (success: boolean) => void) => void;
  deleteTransaction: (id: string) => void;
  loadTransactions: () => void;
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
  addCategory: (name: string, icon: string, subCategories?: string[]) => void;
  updateCategory: (id: string, name: string) => void;
  deleteCategory: (id: string) => void;
  addSubCategory: (categoryId: string, name: string) => void;
  deleteSubCategory: (categoryId: string, subId: string) => void;
  
  reports: Report[];
  addReport: (r: Report) => void;
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

}

const AppContext = createContext<AppContextType | undefined>(undefined);

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
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>(initialCategories);
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [pendingDate, setPendingDate] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([
    { id: '1', title: 'Monthly Summary', date: 'Sept 2023', size: '2.4 MB', type: 'PDF' },
  ]);
  const updateUser = (u: Partial<UserProfile>) => {
    setUser(prev => {
      const newUser = { ...prev, ...u };
      
      if (newUser.isAuthenticated && (newUser.userId || newUser.id)) {
        updateStoredUser(newUser);
      }

      // If user is logged in, sync changes to the database
      if (newUser.isAuthenticated && newUser.userId) {
        fetch(`http://localhost:8000/api/users/${newUser.userId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: newUser.name,
            email: newUser.email,
            onboarded: newUser.onboarded,
            income: newUser.income,
            city_tier: newUser.cityTier,
            fixed_rent: newUser.fixedRent,
            fixed_emi: newUser.fixedEMI,
            biggest_category: newUser.biggestCategory,
            primary_goal: newUser.primaryGoal
          })
        }).catch(err => console.error("Failed to sync profile changes:", err));
      }
      
      return newUser;
    });
  };

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
    const handleHashAuth = () => {
      const hash = window.location.hash;
      if (hash && hash.includes("access_token=")) {
        const params = new URLSearchParams(hash.substring(1)); // Remove the leading '#'
        const accessToken = params.get("access_token");
        if (accessToken) {
          try {
            const base64Url = accessToken.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            const decoded = JSON.parse(jsonPayload);
            
            if (decoded && decoded.sub && decoded.email) {
              const user_id = decoded.sub;
              const email = decoded.email;
              const full_name = decoded.user_metadata?.full_name || decoded.email.split('@')[0];
              
              fetch('http://localhost:8000/api/oauth-login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id, email, full_name })
              })
              .then(res => res.json())
              .then(data => {
                if (data.success) {
                  // Clear the hash from the URL so it looks clean
                  window.history.replaceState(null, "", window.location.pathname);

                  const restoredUser: UserProfile = {
                    id: user_id,
                    isAuthenticated: true,
                    userId: user_id,
                    name: full_name,
                    email: email,
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

                  saveAuthSession(accessToken, restoredUser);
                  setUser(restoredUser);
                }
              })
              .catch(err => {
                console.error("Backend OAuth login failed:", err);
              });
            }
          } catch (e) {
            console.error("Failed to parse JWT from hash:", e);
          }
        }
      }
    };

    handleHashAuth();
    window.addEventListener("hashchange", handleHashAuth);
    return () => window.removeEventListener("hashchange", handleHashAuth);
  }, []);

  const loadTransactions = useCallback(() => {
    const uid = activeUserId(user);
    if (!uid) {
      setTransactions([]);
      return;
    }

    apiFetch(`/api/transactions?user_id=${encodeURIComponent(uid)}`)
      .then(res => {
        if (!res.ok) throw new Error('Could not load transactions from database');
        return res.json();
      })
      .then(data => {
        const rows = Array.isArray(data?.data) ? data.data : [];
        setTransactions(rows);
      })
      .catch(err => {
        console.warn('Failed to load transactions from database:', err);
        setTransactions([]);
      });
  }, [user]);

  const loadBudgets = useCallback(() => {
    const uid = activeUserId(user);
    if (!uid) {
      setBudgets([]);
      return;
    }

    apiFetch(`/api/budgets?user_id=${encodeURIComponent(uid)}`)
      .then(res => res.json())
      .then(data => {
        if (data.success && Array.isArray(data.data)) {
          setBudgets(data.data);
        } else {
          setBudgets([]);
        }
      })
      .catch(err => console.error('Failed to load budgets:', err));
  }, [user]);

  const loadGoals = useCallback(() => {
    const uid = activeUserId(user);
    if (!uid) {
      setGoals([]);
      return;
    }

    apiFetch(`/api/goals?user_id=${encodeURIComponent(uid)}`)
      .then(res => res.json())
      .then(data => {
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
      })
      .catch(err => console.error('Failed to load goals:', err));
  }, [user]);

  const refreshUserData = useCallback(() => {
    loadTransactions();
    loadBudgets();
    loadGoals();
  }, [loadTransactions, loadBudgets, loadGoals]);

  // Load from database once auth session is restored
  useEffect(() => {
    if (!authReady) return;
    if (user.isAuthenticated && activeUserId(user)) {
      refreshUserData();
    } else {
      setTransactions([]);
      setGoals([]);
      setBudgets([]);
    }
  }, [authReady, user.isAuthenticated, user.userId, user.id, refreshUserData]);

  // Refetch when the tab regains focus (e.g. after editing in Supabase)
  useEffect(() => {
    if (!authReady || !user.isAuthenticated) return;

    const onFocus = () => refreshUserData();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [authReady, user.isAuthenticated, refreshUserData]);

  const addTransaction = (t: Omit<Transaction, 'id'>) => {
    const uid = activeUserId(user);
    if (uid) {
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
        }),
      })
        .then(res => res.json())
        .then(() => loadTransactions())
        .catch(err => console.error('Database save failed:', err));
      return;
    }
  };

  const addTransactions = (_ts: Omit<Transaction, 'id'>[]) => {
    loadTransactions();
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
    };

    apiFetch(`/api/transactions/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (ok && data.success) {
          loadTransactions();
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
    const uid = activeUserId(user);
    if (!uid) return;

    apiFetch(`/api/transactions/${id}`, { method: 'DELETE' })
      .then(res => res.json())
      .then(data => {
        if (data.success) loadTransactions();
      })
      .catch(err => console.error('Failed to delete transaction:', err));
  };

  const addBudget = (b: Omit<Budget, 'id'>) => {
    const uid = activeUserId(user);
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
      .then(saved => {
        loadBudgets();
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
    .then(saved => {
      loadBudgets();
    })
    .catch(err => console.error("Failed to update budget:", err));
  };

  const deleteBudget = (id: string) => {
    apiFetch(`/api/budgets/${id}`, {
      method: 'DELETE'
    })
    .then(res => res.json())
    .then(saved => {
      loadBudgets();
    })
    .catch(err => console.error("Failed to delete budget:", err));
  };

  const addGoal = (g: Omit<Goal, 'id'>) => {
    const uid = activeUserId(user);
    if (uid) {
      apiFetch('/api/goals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: uid,
          goal_name: g.label,
          description: g.sub,
          target_amount: g.target,
          current_amount: g.current,
          target_date: g.date,
          status: 'active'
        })
      })
      .then(res => res.json())
      .then(saved => {
        loadGoals();
      })
      .catch(err => console.error("Failed to add goal:", err));
    }
  };

  const updateGoal = (id: string, g: Partial<Goal>) => {
    apiFetch(`/api/goals/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user.userId || user.id,
        goal_name: g.label || '',
        description: g.sub || '',
        target_amount: g.target || 0,
        current_amount: g.current || 0,
        target_date: g.date || '',
        status: 'active'
      })
    })
    .then(res => res.json())
    .then(saved => {
      loadGoals();
    })
    .catch(err => console.error("Failed to update goal:", err));
  };

  const deleteGoal = (id: string) => {
    apiFetch(`/api/goals/${id}`, {
      method: 'DELETE'
    })
    .then(res => res.json())
    .then(saved => {
      loadGoals();
    })
    .catch(err => console.error("Failed to delete goal:", err));
  };

  const addCategory = (name: string, icon: string, initialSubCategories: string[] = []) => {
    const newId = `cat-${Math.random().toString(36).substr(2, 9)}`;
    const subs = initialSubCategories.map(s => ({ id: `sub-${Math.random().toString(36).substr(2, 9)}`, name: s }));
    setCategories(prev => [...prev, { id: newId, name, icon, subCategories: subs }]);
  };

  const updateCategory = (id: string, name: string) => {
    setCategories(prev => prev.map(c => c.id === id ? { ...c, name } : c));
  };

  const deleteCategory = (id: string) => {
    setCategories(prev => prev.filter(c => c.id !== id));
  };

  const addSubCategory = (categoryId: string, name: string) => {
    setCategories(prev => prev.map(cat => 
      cat.id === categoryId 
        ? { ...cat, subCategories: [...cat.subCategories, { id: `sub-${Math.random()}`, name }] } 
        : cat
    ));
  };

  const deleteSubCategory = (categoryId: string, subId: string) => {
    setCategories(prev => prev.map(cat => 
      cat.id === categoryId 
        ? { ...cat, subCategories: cat.subCategories.filter(s => s.id !== subId) } 
        : cat
    ));
  };

  const navigateToAddTransaction = (date: string) => {
    setPendingDate(date);
    setCurrentPage('transactions');
  };

  const resetPendingDate = () => setPendingDate(null);

  const signOut = () => {
    clearAuthSession();
    setUser(initialUser);
    setTransactions([]);
    setGoals([]);
    setBudgets([]);
    setReports([]);
    setCurrentPage('dashboard');
  };

  const addReport = (r: Report) => setReports(prev => [r, ...prev]);
  
  const uploadReport = async (file: File) => {
    const newReport: Report = {
      id: Math.random().toString(36).substr(2, 9),
      title: file.name,
      date: format(new Date(), 'MMM yyyy'),
      size: `${(file.size / 1024 / 1024).toFixed(1)} MB`,
      type: file.name.endsWith('.csv') ? 'CSV' : 'PDF'
    };
    addReport(newReport);

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
          loadTransactions(); // Refetch transactions to update UI immediately
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
      transactions, addTransaction, addTransactions, updateTransaction, deleteTransaction, loadTransactions,
      budgets, addBudget, updateBudget, deleteBudget, loadBudgets, loadGoals,
      goals, addGoal, updateGoal, deleteGoal,
      categories, addCategory, updateCategory, deleteCategory, addSubCategory, deleteSubCategory,
      reports, addReport, uploadReport,
      heatmapData,
      navigateToAddTransaction, pendingDate, resetPendingDate,
      signOut,
      setCurrentPage, currentPage,
      authReady,
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
