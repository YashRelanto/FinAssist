import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const CURRENCY_SYMBOL = '₹';
export const APP_NAME = 'FinAssist AI';
export const APP_ADVISOR_GREETING = `Hello! I am your ${APP_NAME} Advisor. I have access to your transactions and our latest financial knowledge base. How can I help you today?`;

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number) {
  return `${CURRENCY_SYMBOL}${Math.abs(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
}
