/**
 * Presentation helpers — pure, framework-free, and unit-tested. Anything that
 * turns domain data into a display string lives here rather than inline in JSX.
 */

/** First 10 characters of a commit SHA, the length the design shows. */
export function shortCommit(sha: string): string {
  return sha.length > 10 ? sha.slice(0, 10) : sha;
}

/** Last `segments` path parts (default 2), for the Inspection Report File column.
 *  The full path is always kept available for tooltip / aria use by the caller. */
export function shortenPath(filePath: string, segments = 2): string {
  const parts = filePath.split('/').filter(Boolean);
  if (parts.length <= segments) return filePath;
  return parts.slice(-segments).join('/');
}

export function fileName(filePath: string): string {
  const parts = filePath.split('/').filter(Boolean);
  return parts[parts.length - 1] ?? filePath;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function lineRange(start: number, end: number | null | undefined): string {
  return end && end !== start ? `${start}–${end}` : String(start);
}

const DATE_FMT = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
});
const DATETIME_FMT = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | null | undefined, fallback = '—'): string {
  const date = parseDate(value);
  return date ? DATE_FMT.format(date) : fallback;
}

export function formatDateTime(value: string | null | undefined, fallback = '—'): string {
  const date = parseDate(value);
  return date ? DATETIME_FMT.format(date) : fallback;
}

const RELATIVE_FMT = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' });
const RELATIVE_DIVISIONS: { amount: number; unit: Intl.RelativeTimeFormatUnit }[] = [
  { amount: 60, unit: 'seconds' },
  { amount: 60, unit: 'minutes' },
  { amount: 24, unit: 'hours' },
  { amount: 7, unit: 'days' },
  { amount: 4.34524, unit: 'weeks' },
  { amount: 12, unit: 'months' },
  { amount: Number.POSITIVE_INFINITY, unit: 'years' },
];

/** "3 days ago" style age, from an ISO timestamp. */
export function formatRelativeTime(value: string | null | undefined, fallback = '—'): string {
  const date = parseDate(value);
  if (!date) return fallback;
  let duration = (date.getTime() - Date.now()) / 1000;
  for (const division of RELATIVE_DIVISIONS) {
    if (Math.abs(duration) < division.amount) {
      return RELATIVE_FMT.format(Math.round(duration), division.unit);
    }
    duration /= division.amount;
  }
  return fallback;
}

/** "1.9s" / "1m 12s" — the design shows compact durations. */
export function formatDuration(ms: number | null | undefined, fallback = '—'): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return fallback;
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = ms / 1000;
  if (totalSeconds < 60) return `${totalSeconds.toFixed(totalSeconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes}m ${seconds}s`;
}

export function formatCount(value: number | null | undefined, fallback = '—'): string {
  return value == null ? fallback : new Intl.NumberFormat('en-US').format(value);
}
