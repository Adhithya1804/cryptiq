import { useCallback, useEffect, useState } from 'react';

/**
 * `useState` mirrored to `localStorage`. Every access is guarded — a private
 * window or a storage-blocked context degrades to plain in-memory state.
 */
export function useLocalStorageState<T>(
  key: string,
  initial: T,
  parse: (raw: string) => T | null,
  serialize: (value: T) => string = String,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      if (raw == null) return initial;
      return parse(raw) ?? initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, serialize(value));
    } catch {
      /* storage unavailable — keep in-memory value */
    }
  }, [key, serialize, value]);

  const set = useCallback((next: T) => setValue(next), []);
  return [value, set];
}
