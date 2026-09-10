import type { ReactNode } from 'react';
import type { RemoteData } from '@/types/common';
import { ErrorState, LoadingState } from './StateViews';

export interface AsyncBoundaryProps<T> {
  state: RemoteData<T>;
  /** Re-run the loader. Wired into the error and (optionally) empty states. */
  onRetry?: () => void;
  /** Custom loading view (e.g. a table skeleton). Defaults to a spinner row. */
  loading?: ReactNode;
  errorTitle?: string;
  /** Treats a successful-but-blank result as "empty". */
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}

/**
 * Renders exactly one of loading / error / empty / success for a `RemoteData`
 * value. Every data-driven screen goes through this so the four states are
 * handled the same way everywhere (master prompt §7).
 */
export function AsyncBoundary<T>({
  state,
  onRetry,
  loading,
  errorTitle,
  isEmpty,
  empty,
  children,
}: AsyncBoundaryProps<T>) {
  if (state.status === 'idle' || state.status === 'loading') {
    return <>{loading ?? <LoadingState />}</>;
  }
  if (state.status === 'error') {
    return <ErrorState error={state.error} {...(onRetry ? { onRetry } : {})} {...(errorTitle ? { title: errorTitle } : {})} />;
  }
  if (empty && isEmpty?.(state.data)) {
    return <>{empty}</>;
  }
  return <>{children(state.data)}</>;
}
