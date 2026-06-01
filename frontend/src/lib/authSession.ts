import type { UserProfile } from '../types';

const SESSION_KEY = 'finassist_auth_session';
const TOKEN_KEY = 'token';

export interface StoredAuthSession {
  accessToken: string;
  refreshToken?: string;
  user: UserProfile;
}

function normalizeSessionUser(user: UserProfile): UserProfile {
  const userId = user.userId || user.id || '';
  return {
    id: userId,
    userId,
    name: user.name,
    email: user.email,
    role: user.role,
    isAuthenticated: true,
    onboarded: user.onboarded,
    income: user.income,
    cityTier: user.cityTier,
    fixedRent: user.fixedRent,
    fixedEMI: user.fixedEMI,
    biggestCategory: user.biggestCategory,
    primaryGoal: user.primaryGoal,
    statementUploaded: user.statementUploaded,
  };
}

export function saveAuthSession(
  accessToken: string,
  user: UserProfile,
  refreshToken?: string
): void {
  const payload: StoredAuthSession = {
    accessToken,
    refreshToken,
    user: normalizeSessionUser(user),
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(payload));
  localStorage.setItem(TOKEN_KEY, accessToken);
}

export function updateStoredUser(partial: Partial<UserProfile>): void {
  const existing = loadAuthSession();
  if (!existing) return;

  saveAuthSession(
    existing.accessToken,
    { ...existing.user, ...partial },
    existing.refreshToken
  );
}

export function loadAuthSession(): StoredAuthSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw) as StoredAuthSession;
    const userId = parsed?.user?.userId || parsed?.user?.id;
    if (!userId) return null;

    return {
      ...parsed,
      user: normalizeSessionUser(parsed.user),
    };
  } catch {
    return null;
  }
}

export function clearAuthSession(): void {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(TOKEN_KEY);
}
