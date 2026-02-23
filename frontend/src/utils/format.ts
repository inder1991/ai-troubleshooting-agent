/**
 * Safe formatting utilities — handles undefined, NaN, Infinity, and invalid dates.
 */

/** Safely format a number with fixed decimals. Returns fallback for undefined/NaN/Infinity. */
export function safeFixed(value: number | undefined | null, decimals: number = 1, fallback: string = '\u2014'): string {
  if (value == null || !isFinite(value)) return fallback;
  return value.toFixed(decimals);
}

/** Parse a timestamp string to a Date, or null if invalid. */
function parseDate(timestamp: string | undefined | null): Date | null {
  if (!timestamp) return null;
  const d = new Date(timestamp);
  return isNaN(d.getTime()) ? null : d;
}

/** Format a timestamp as HH:mm:ss. Returns fallback for invalid dates. */
export function formatTime(timestamp: string | undefined | null, fallback: string = '\u2014'): string {
  const d = parseDate(timestamp);
  if (!d) return fallback;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** Format a timestamp as "MMM DD, HH:mm". Returns fallback for invalid dates. */
export function formatDateTime(timestamp: string | undefined | null, fallback: string = '\u2014'): string {
  const d = parseDate(timestamp);
  if (!d) return fallback;
  return d.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Format a timestamp as UTC string (for SREs working across zones). */
export function formatUTC(timestamp: string | undefined | null, fallback: string = '\u2014'): string {
  const d = parseDate(timestamp);
  if (!d) return fallback;
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
}

/** Format a timestamp as relative time ("2m ago", "1h ago"). Returns fallback for invalid/future dates. */
export function formatRelative(timestamp: string | undefined | null, fallback: string = '\u2014'): string {
  const d = parseDate(timestamp);
  if (!d) return fallback;
  const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diffSec < 0) return 'just now';
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}d ago`;
}

/** Safely format a date for display — catches 'Invalid Date' and returns fallback. */
export function safeDate(
  timestamp: string | undefined | null,
  format: 'time' | 'datetime' | 'utc' | 'relative' = 'datetime',
  fallback: string = '\u2014',
): string {
  switch (format) {
    case 'time': return formatTime(timestamp, fallback);
    case 'datetime': return formatDateTime(timestamp, fallback);
    case 'utc': return formatUTC(timestamp, fallback);
    case 'relative': return formatRelative(timestamp, fallback);
    default: return formatDateTime(timestamp, fallback);
  }
}
