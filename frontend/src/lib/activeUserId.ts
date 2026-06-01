/** Resolved Supabase auth user id used for API calls. */
export function activeUserId(
  user: { userId?: string; id?: string } | null | undefined,
): string {
  if (!user) return '';
  return (user.userId || user.id || '').trim();
}
