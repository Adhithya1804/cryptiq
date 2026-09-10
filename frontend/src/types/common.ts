/**
 * Shared, domain-agnostic types.
 */

/** A normalised error every layer of the app can reason about. */
export interface ApiError {
  /** Human-readable, safe to show to a user. Never a raw stack trace. */
  message: string;
  /** Machine-readable code where the backend provides one. */
  code?: string;
  /** HTTP status, when the failure came from a response. */
  status?: number;
  /** True when the request never completed (offline, DNS, timeout, abort). */
  network?: boolean;
}

/** Discriminated remote-data state used by every data-driven screen. */
export type RemoteData<T> =
  | { readonly status: 'idle' }
  | { readonly status: 'loading' }
  | { readonly status: 'success'; readonly data: T }
  | { readonly status: 'error'; readonly error: ApiError };

export const remote = {
  idle: <T>(): RemoteData<T> => ({ status: 'idle' }),
  loading: <T>(): RemoteData<T> => ({ status: 'loading' }),
  success: <T>(data: T): RemoteData<T> => ({ status: 'success', data }),
  error: <T>(error: ApiError): RemoteData<T> => ({ status: 'error', error }),
};
