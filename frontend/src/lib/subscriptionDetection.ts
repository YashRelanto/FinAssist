import { Transaction } from '../types';

export interface DetectedSubscription {
  merchant: string;
  displayName: string;
  monthlyAmount: number;
  occurrences: number;
  lastDate: string;
  source: 'known' | 'recurring';
}

const KNOWN_SUBSCRIPTIONS: { displayName: string; patterns: RegExp[] }[] = [
  { displayName: 'Spotify', patterns: [/spotify/i] },
  { displayName: 'Netflix', patterns: [/netflix/i] },
  { displayName: 'Amazon Prime', patterns: [/amazon\s*prime|prime\s*video/i] },
  { displayName: 'Jio Hotstar', patterns: [/jio\s*hotstar|hotstar|disney\+?\s*hotstar/i] },
  { displayName: 'YouTube Premium', patterns: [/youtube\s*premium|google\s*youtube/i] },
  { displayName: 'Apple Services', patterns: [/apple\.com|icloud|apple\s*music|apple\s*tv/i] },
  { displayName: 'Microsoft 365', patterns: [/microsoft|office\s*365|xbox\s*game/i] },
  { displayName: 'Adobe', patterns: [/adobe/i] },
  { displayName: 'LinkedIn Premium', patterns: [/linkedin/i] },
  { displayName: 'Zee5', patterns: [/zee5/i] },
  { displayName: 'SonyLIV', patterns: [/sonyliv/i] },
  { displayName: 'Swiggy One', patterns: [/swiggy\s*one|swiggy\s*super/i] },
  { displayName: 'Zomato Gold', patterns: [/zomato\s*gold|zomato\s*pro/i] },
  { displayName: 'Gym / Fitness', patterns: [/cult\.fit|gold'?s?\s*gym|fitness/i] },
];

function matchKnownSubscription(merchant: string): string | null {
  for (const sub of KNOWN_SUBSCRIPTIONS) {
    if (sub.patterns.some((p) => p.test(merchant))) {
      return sub.displayName;
    }
  }
  return null;
}

function daysBetween(a: string, b: string): number {
  const da = new Date(`${a}T00:00:00`);
  const db = new Date(`${b}T00:00:00`);
  return Math.abs((db.getTime() - da.getTime()) / (1000 * 60 * 60 * 24));
}

function isRecurringMonthly(amounts: number[], dates: string[]): boolean {
  if (amounts.length < 2 || dates.length < 2) return false;
  const avg = amounts.reduce((s, v) => s + v, 0) / amounts.length;
  const amountConsistent = amounts.every((a) => Math.abs(a - avg) / avg <= 0.15);
  if (!amountConsistent) return false;

  const sortedDates = [...dates].sort();
  const gaps: number[] = [];
  for (let i = 1; i < sortedDates.length; i++) {
    gaps.push(daysBetween(sortedDates[i - 1], sortedDates[i]));
  }
  const monthlyGaps = gaps.filter((g) => g >= 25 && g <= 35);
  return monthlyGaps.length >= 1;
}

/** Detect subscriptions from expense transactions using known brands + recurring patterns. */
export function detectSubscriptions(transactions: Transaction[]): DetectedSubscription[] {
  const expenses = transactions.filter((t) => t.type === 'expense' && Math.abs(t.amount) > 0);
  const byMerchant = new Map<string, { amounts: number[]; dates: string[] }>();

  for (const t of expenses) {
    const merchant = (t.merchant || '').trim();
    if (!merchant) continue;
    const key = merchant.toLowerCase();
    const entry = byMerchant.get(key) ?? { amounts: [], dates: [] };
    entry.amounts.push(Math.abs(t.amount));
    entry.dates.push(t.date);
    byMerchant.set(key, entry);
  }

  const results: DetectedSubscription[] = [];
  const seen = new Set<string>();

  for (const [key, data] of byMerchant) {
    const merchant = expenses.find((t) => t.merchant.toLowerCase() === key)?.merchant ?? key;
    const known = matchKnownSubscription(merchant);
    const recurring = isRecurringMonthly(data.amounts, data.dates);
    if (!known && !recurring) continue;

    const displayName = known ?? merchant;
    const dedupeKey = displayName.toLowerCase();
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const avgAmount = data.amounts.reduce((s, v) => s + v, 0) / data.amounts.length;
    const lastDate = [...data.dates].sort().pop() ?? '';

    results.push({
      merchant,
      displayName,
      monthlyAmount: Math.round(avgAmount),
      occurrences: data.amounts.length,
      lastDate,
      source: known ? 'known' : 'recurring',
    });
  }

  return results.sort((a, b) => b.monthlyAmount - a.monthlyAmount);
}
