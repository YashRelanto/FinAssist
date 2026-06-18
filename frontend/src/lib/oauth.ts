/** Supabase project URL for browser OAuth (set VITE_SUPABASE_URL in frontend env). */
export const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL as string | undefined)?.replace(/\/$/, '') || '';

export function getGoogleOAuthUrl(): string | null {
  if (!SUPABASE_URL) return null;
  const redirectTo = encodeURIComponent(window.location.origin);
  return `${SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to=${redirectTo}`;
}
