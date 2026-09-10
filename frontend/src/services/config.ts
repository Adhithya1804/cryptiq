/**
 * Runtime configuration for the API layer, read once from Vite's build-time
 * environment. Only public values live here — no secrets are ever shipped to the
 * browser (see .env.example).
 */

import { HttpError } from './errors';

/**
 * The backend base URL, read from the build-time environment. `VITE_API_BASE_URL`
 * is the primary name; `NEXT_PUBLIC_API_URL` is accepted as an alias so the same
 * `.env` works if the shell already exports one. In development,
 * `.env.development.local` supplies `http://localhost:8000/api/v1`.
 *
 * Left blank the app runs in "no backend connected" mode (see below) — this is a
 * deliberate offline state, not an error.
 */
function readBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.NEXT_PUBLIC_API_URL;
  if (typeof raw !== 'string') return '';
  return raw.trim().replace(/\/+$/, '');
}

function readTimeout(): number {
  const raw = import.meta.env.VITE_API_TIMEOUT_MS;
  const parsed = typeof raw === 'string' ? Number.parseInt(raw, 10) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 20_000;
}

export const apiConfig = {
  baseUrl: readBaseUrl(),
  timeoutMs: readTimeout(),
} as const;

/** True when a backend has been configured for this build. When false, the app
 *  runs in "no backend connected" mode: reads yield empty collections and the
 *  inspection submit reports a connection error rather than fabricating a
 *  result — matching the design's data-service boundary. */
export function isBackendConfigured(): boolean {
  return apiConfig.baseUrl.length > 0;
}

export const NO_BACKEND_MESSAGE =
  'Unable to reach the Cryptiq inspection service. No backend is connected in this environment.';

/** Guard for endpoints that cannot degrade to an empty collection (detail reads,
 *  writes). Throws the same error a real connection failure would produce. */
export function assertBackendConfigured(): void {
  if (!isBackendConfigured()) {
    throw new HttpError({ message: NO_BACKEND_MESSAGE, network: true });
  }
}
