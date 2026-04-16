import type { Status } from '../../../types';

export const STATUS_BADGE_CLASSES: Record<Status, string> = {
  running: 'bg-amber-500 animate-pulse',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
  skipped: 'bg-neutral-400',
};

export const STATUS_DOT_CLASSES: Record<Status, string> = {
  running: 'bg-amber-500',
  pending: 'bg-neutral-500',
  cancelling: 'bg-slate-400',
  cancelled: 'bg-slate-500',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
  skipped: 'bg-neutral-400',
};

export const TERMINAL_STATUSES: ReadonlySet<Status> = new Set([
  'success', 'failed', 'cancelled',
]);

export function isTerminal(status: Status): boolean {
  return TERMINAL_STATUSES.has(status);
}
