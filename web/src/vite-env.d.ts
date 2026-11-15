/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" makes the API client answer from built-in fixtures instead of the server. */
  readonly VITE_USE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
