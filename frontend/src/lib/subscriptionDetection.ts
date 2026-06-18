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

function recurringAmountToMonthly(amount: number, period?: string | null, skips?: number): number {
  const step = Math.max(1, (skips ?? 0) + 1);
  const key = (period || 'monthly').toLowerCase();
  if (key === 'daily') return amount * (30 / step);
  if (key === 'weekly') return amount * (52 / 12 / step);
  if (key === 'yearly') return amount / (12 * step);
  return amount / step;
}

/** Detect OTT / platform subscriptions from expense transactions (keyword match only). */
export function detectSubscriptions(transactions: Transaction[]): DetectedSubscription[] {
  const expenses = transactions.filter((t) => t.type === 'expense' && Math.abs(t.amount) > 0);

  type Group = {
    merchant: string;
    displayName: string;
    amounts: number[];
    dates: string[];
    hasRecurringFlag: boolean;
  };

  const bySubscription = new Map<string, Group>();

  for (const t of expenses) {
    const merchant = (t.merchant || '').trim();
    if (!merchant) continue;

    const displayName = matchKnownSubscription(merchant);
    if (!displayName) continue;

    const key = displayName.toLowerCase();
    const entry = bySubscription.get(key) ?? {
      merchant,
      displayName,
      amounts: [],
      dates: [],
      hasRecurringFlag: false,
    };

    const amount = Math.abs(t.amount);
    if (t.is_recurring) {
      entry.amounts.push(
        recurringAmountToMonthly(amount, t.recurrence_period, t.recurrence_skips),
      );
      entry.hasRecurringFlag = true;
    } else {
      entry.amounts.push(amount);
    }
    entry.dates.push(t.date);
    bySubscription.set(key, entry);
  }

  const results: DetectedSubscription[] = [];

  for (const group of bySubscription.values()) {
    const monthlyAmount = Math.round(
      group.amounts.reduce((s, v) => s + v, 0) / group.amounts.length,
    );
    const lastDate = [...group.dates].sort().pop() ?? '';

    results.push({
      merchant: group.merchant,
      displayName: group.displayName,
      monthlyAmount,
      occurrences: group.amounts.length,
      lastDate,
      source: group.hasRecurringFlag ? 'recurring' : 'known',
    });
  }

  return results.sort((a, b) => b.monthlyAmount - a.monthlyAmount);
}
