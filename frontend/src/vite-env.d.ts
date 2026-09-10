/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Cryptiq backend v1 API. Empty string when unconfigured. */
  readonly VITE_API_BASE_URL?: string;
  /** Alias for VITE_API_BASE_URL, accepted so a pre-exported env var also works. */
  readonly NEXT_PUBLIC_API_URL?: string;
  /** Request timeout in milliseconds. */
  readonly VITE_API_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
