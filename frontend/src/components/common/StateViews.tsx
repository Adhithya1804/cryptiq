import type { ReactNode } from 'react';
import type { ApiError } from '@/types/common';
import { Spinner } from './Spinner';
import styles from './StateViews.module.css';

/** Neutral "there is nothing here yet" panel. No fabricated data behind it. */
export function EmptyState({
  title,
  description,
  action,
  kicker,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  kicker?: string;
}) {
  return (
    <div className={styles.wrap}>
      {kicker && <div className={styles.kicker}>{kicker}</div>}
      <div className={styles.title}>{title}</div>
      {description && <p className={styles.body}>{description}</p>}
      {action && <div className={styles.actions}>{action}</div>}
    </div>
  );
}

/** Error panel with a retry affordance. Shows the normalised message only. */
export function ErrorState({
  error,
  onRetry,
  title,
}: {
  error: ApiError;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div className={styles.wrap} role="alert">
      <div className={styles.kicker}>{error.network ? 'Connection error' : 'Error'}</div>
      <div className={styles.title}>{title ?? 'This view could not be loaded'}</div>
      <p className={styles.body}>{error.message}</p>
      {onRetry && (
        <div className={styles.actions}>
          <button type="button" className={styles.retry} onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className={styles.loading} role="status">
      <Spinner size={14} />
      <span>{label}</span>
    </div>
  );
}

export function Skeleton({
  width = '100%',
  height = 14,
  radius,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number | string;
}) {
  return (
    <span
      className={styles.skeleton}
      style={{ display: 'block', width, height, ...(radius != null ? { borderRadius: radius } : {}) }}
      aria-hidden
    />
  );
}
