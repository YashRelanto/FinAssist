import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const CURRENCY_SYMBOL = '₹';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number) {
  return `${CURRENCY_SYMBOL}${Math.abs(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
}
