export const API_BASE = 'http://localhost:8000';

export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

function getStoredToken(): string | null {
  try {
    const raw = localStorage.getItem('finassist_auth_session');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.accessToken) return parsed.accessToken;
    }
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

/** Always fetch fresh data — no browser HTTP cache. Attaches JWT automatically. */
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('Cache-Control', 'no-cache');
  headers.set('Pragma', 'no-cache');

  const token = getStoredToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  return fetch(apiUrl(path), {
    ...init,
    cache: 'no-store',
    headers,
  });
}
