/**
 * The single HTTP boundary. Every network call in the app goes through
 * `request()`; nothing else constructs a `fetch`, a URL, or a header.
 *
 * Responsibilities: base-URL joining, JSON encode/decode, a request timeout,
 * abort propagation, and normalising every failure mode into a typed
 * `ApiError`. Raw response bodies and stack traces never escape this module.
 */

import type { ApiError } from '@/types/common';
import type { ApiErrorBody } from '@/types/api';
import { apiConfig } from './config';
import { HttpError } from './errors';

export { HttpError };

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** JSON-serialisable request body. */
  body?: unknown;
  /** Query parameters; `undefined` / `null` values are dropped. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Caller-supplied abort signal (e.g. from a component effect cleanup). */
  signal?: AbortSignal;
}

const GENERIC_MESSAGE = 'Something went wrong. Please try again.';

const STATUS_MESSAGES: Record<number, string> = {
  400: 'The request was rejected as invalid.',
  401: 'Your session has expired. Sign in again to continue.',
  403: 'You do not have access to this resource.',
  404: 'The requested resource was not found.',
  409: 'This action conflicts with the current state. Refresh and try again.',
  422: 'The request could not be processed as submitted.',
  429: 'Too many requests. Wait a moment and try again.',
};

function buildUrl(path: string, query: RequestOptions['query']): string {
  const base = apiConfig.baseUrl;
  const rel = `${base}${path.startsWith('/') ? path : `/${path}`}`;
  // `base` can be absolute (dev: http://localhost:8000/api/v1), a same-origin
  // path (deployed behind nginx: /api/v1), or empty (no backend). `new URL`
  // rejects a non-absolute second argument, so only pass a base when the
  // combined string isn't already absolute — otherwise resolve against the
  // current origin.
  const url = /^https?:\/\//i.test(rel) ? new URL(rel) : new URL(rel, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function messageFromBody(body: ApiErrorBody | null, status: number): string {
  if (body) {
    if (typeof body.message === 'string' && body.message.trim()) return body.message;
    if (typeof body.error?.message === 'string' && body.error.message.trim()) return body.error.message;
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail;
    if (Array.isArray(body.detail)) {
      const first = body.detail.find((d) => typeof d?.msg === 'string');
      if (first?.msg) return first.msg;
    }
  }
  return STATUS_MESSAGES[status] ?? (status >= 500 ? 'The server encountered an error.' : GENERIC_MESSAGE);
}

/** Cryptiq nests its stable code under `error`; other shapes put it at the top. */
function codeFromBody(body: ApiErrorBody | null): string | undefined {
  return body?.code ?? body?.error?.code ?? undefined;
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody | null> {
  try {
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/json')) return null;
    return (await response.json()) as ApiErrorBody;
  } catch {
    return null;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), apiConfig.timeoutMs);
  const onExternalAbort = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener('abort', onExternalAbort, { once: true });
  }

  const init: RequestInit = {
    method,
    headers: {
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    signal: controller.signal,
    credentials: 'same-origin',
  };
  if (body !== undefined) init.body = JSON.stringify(body);

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), init);
  } catch (cause) {
    if (controller.signal.aborted && (cause as DOMException)?.name === 'TimeoutError') {
      throw new HttpError({ message: 'The request timed out. Please try again.', network: true });
    }
    if ((cause as DOMException)?.name === 'AbortError') {
      throw new HttpError({ message: 'The request was cancelled.', network: true, code: 'aborted' });
    }
    throw new HttpError({
      message: 'Could not reach the Cryptiq service. Check your connection and try again.',
      network: true,
    });
  } finally {
    clearTimeout(timeout);
    if (signal) signal.removeEventListener('abort', onExternalAbort);
  }

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    const code = codeFromBody(errorBody);
    throw new HttpError({
      message: messageFromBody(errorBody, response.status),
      status: response.status,
      ...(code ? { code } : {}),
    });
  }

  if (response.status === 204) return undefined as T;

  try {
    return (await response.json()) as T;
  } catch {
    throw new HttpError({ message: 'The server returned a response the app could not read.', status: response.status });
  }
}

/** Coerce an unknown thrown value into a plain `ApiError` for state storage. */
export function toApiError(cause: unknown): ApiError {
  if (cause instanceof HttpError) {
    return {
      message: cause.message,
      ...(cause.code ? { code: cause.code } : {}),
      ...(cause.status ? { status: cause.status } : {}),
      ...(cause.network ? { network: true } : {}),
    };
  }
  if (cause instanceof Error && cause.message) {
    return { message: cause.message };
  }
  return { message: GENERIC_MESSAGE };
}

/** True for the abort that a component triggers on unmount / dependency change —
 *  callers should swallow it rather than render an error. */
export function isAbortError(cause: unknown): boolean {
  return (
    (cause instanceof HttpError && cause.code === 'aborted') ||
    (cause instanceof DOMException && cause.name === 'AbortError')
  );
}
