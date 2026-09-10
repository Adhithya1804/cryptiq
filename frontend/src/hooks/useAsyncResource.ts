/**
 * Load an async resource once per key, with abort-on-unmount, stale-response
 * rejection, and an explicit `reload()`. This is the single data-fetching
 * primitive every screen uses — no screen calls a service inside its own
 * `useEffect`.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { remote, type RemoteData } from '@/types/common';
import { isAbortError, toApiError } from '@/services';

export interface AsyncResource<T> {
  readonly state: RemoteData<T>;
  /** Re-run the loader, showing the loading state again. Safe to pass to onClick. */
  readonly reload: () => void;
  /** Re-run the loader in the background, keeping the current data on screen.
   *  For polling a resource whose value changes over time (e.g. a running scan). */
  readonly refresh: () => void;
}

/**
 * @param loader  receives an AbortSignal; must reject on non-2xx.
 * @param deps    identity list — a change re-runs the loader and discards any
 *                in-flight response.
 */
export function useAsyncResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): AsyncResource<T> {
  const [state, setState] = useState<RemoteData<T>>(remote.loading<T>());
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const runIdRef = useRef(0);

  const run = useCallback((signal: AbortSignal, background = false) => {
    const runId = ++runIdRef.current;
    if (!background) setState(remote.loading<T>());
    loaderRef.current(signal).then(
      (data) => {
        if (runId === runIdRef.current && !signal.aborted) setState(remote.success(data));
      },
      (cause: unknown) => {
        if (runId !== runIdRef.current || signal.aborted || isAbortError(cause)) return;
        // A failed background poll leaves the last good data in place rather
        // than replacing the screen with an error.
        if (!background) setState(remote.error<T>(toApiError(cause)));
      },
    );
  }, []);

  const [reloadNonce, setReloadNonce] = useState(0);
  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);

  const refreshControllerRef = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    refreshControllerRef.current?.abort();
    const controller = new AbortController();
    refreshControllerRef.current = controller;
    run(controller.signal, true);
  }, [run]);

  useEffect(() => {
    const controller = new AbortController();
    run(controller.signal);
    return () => {
      controller.abort();
      refreshControllerRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, reloadNonce, ...deps]);

  return { state, reload, refresh };
}
