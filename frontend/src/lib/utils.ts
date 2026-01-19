import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBudget(
  budgetType: string | null,
  budgetMin: number | null,
  budgetMax: number | null
): string {
  if (!budgetType || budgetType === 'unknown') {
    return 'Not specified';
  }

  if (budgetType === 'fixed') {
    if (budgetMin === budgetMax) {
      return `$${budgetMin?.toLocaleString() ?? '?'}`;
    }
    return `$${budgetMin?.toLocaleString() ?? '?'} - $${budgetMax?.toLocaleString() ?? '?'}`;
  }

  if (budgetType === 'hourly') {
    return `$${budgetMin ?? '?'} - $${budgetMax ?? '?'}/hr`;
  }

  return 'Not specified';
}

export function formatDate(dateString: string | null): string {
  if (!dateString) return '-';
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}

export function formatClientSpent(spent: number | null): string {
  if (spent === null) return 'N/A';
  if (spent >= 1000000) {
    return `$${(spent / 1000000).toFixed(1)}M`;
  }
  if (spent >= 1000) {
    return `$${(spent / 1000).toFixed(1)}k`;
  }
  return `$${spent.toFixed(0)}`;
}
