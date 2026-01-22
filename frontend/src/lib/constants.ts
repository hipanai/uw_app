import type { JobStatus } from '@/api/types';

// Status colors matching Slack message formatting
export const STATUS_COLORS: Record<JobStatus, string> = {
  new: 'bg-blue-100 text-blue-800',
  scoring: 'bg-purple-100 text-purple-800',
  extracting: 'bg-indigo-100 text-indigo-800',
  generating: 'bg-cyan-100 text-cyan-800',
  pending_approval: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  submitting: 'bg-orange-100 text-orange-800',
  submitted: 'bg-emerald-100 text-emerald-800',
  submission_failed: 'bg-red-200 text-red-900',
  filtered_out: 'bg-gray-100 text-gray-800',
  error: 'bg-red-200 text-red-900',
};

export const STATUS_LABELS: Record<JobStatus, string> = {
  new: 'New',
  scoring: 'Scoring',
  extracting: 'Extracting',
  generating: 'Generating',
  pending_approval: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  submitting: 'Submitting',
  submitted: 'Submitted',
  submission_failed: 'Failed',
  filtered_out: 'Filtered',
  error: 'Error',
};

// Score colors from Slack formatting
export const getScoreColor = (score: number | null): string => {
  if (score === null) return 'bg-gray-500 text-white';
  if (score >= 85) return 'bg-green-500 text-white';
  if (score >= 70) return 'bg-yellow-500 text-black';
  return 'bg-red-500 text-white';
};

export const getScoreLabel = (score: number | null): string => {
  if (score === null) return 'N/A';
  if (score >= 85) return 'Excellent';
  if (score >= 70) return 'Good';
  return 'Low';
};

// Log level colors
export const LOG_LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-blue-600',
  WARNING: 'text-yellow-600',
  ERROR: 'text-red-600',
  DEBUG: 'text-gray-500',
};
