export const API_BASE = 'http://localhost:8000';

export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

/** Always fetch fresh data — no browser HTTP cache. */
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set('Cache-Control', 'no-cache');
  headers.set('Pragma', 'no-cache');

  return fetch(apiUrl(path), {
    ...init,
    cache: 'no-store',
    headers,
  });
}
