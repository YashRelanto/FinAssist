import { loadAuthSession, saveAuthSession } from './authSession';

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

function getStoredToken(): string | null {
  try {
    const session = loadAuthSession();
    if (session?.accessToken) return session.accessToken;
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

let _refreshPromise: Promise<string | null> | null = null;

/** Exchange the stored refresh token for a new access token via our backend. */
async function refreshAccessToken(): Promise<string | null> {
  // Deduplicate concurrent refresh attempts
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const session = loadAuthSession();
      const refreshToken = session?.refreshToken;
      if (!refreshToken) return null;

      const res = await fetch(apiUrl('/api/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!res.ok) return null;

      const data = await res.json();
      const newAccessToken: string = data.access_token;
      const newRefreshToken: string = data.refresh_token || refreshToken;

      if (!newAccessToken) return null;

      // Persist refreshed tokens so all subsequent calls use the new token
      if (session?.user) {
        saveAuthSession(newAccessToken, session.user, newRefreshToken);
      } else {
        localStorage.setItem('token', newAccessToken);
      }

      return newAccessToken;
    } catch {
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

/** Fetch with automatic JWT injection and one-time token refresh on 401. */
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const makeHeaders = (token: string | null) => {
    const headers = new Headers(init.headers);
    headers.set('Cache-Control', 'no-cache');
    headers.set('Pragma', 'no-cache');
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    return headers;
  };

  const token = getStoredToken();
  const res = await fetch(apiUrl(path), {
    ...init,
    cache: 'no-store',
    headers: makeHeaders(token),
  });

  // On 401, attempt one silent token refresh then retry once
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return fetch(apiUrl(path), {
        ...init,
        cache: 'no-store',
        headers: makeHeaders(newToken),
      });
    }
  }

  return res;
}
