/// <reference types="vite/client" />
/// <reference types="vitest" />

interface ImportMetaEnv {
  // Single authoritative environment selector (Environment_Resolver). Injected at
  // build time; recognized values are 'production' | 'test'. Unset/unknown fails fast
  // at module load in src/config/appEnv.ts (no silent default).
  readonly VITE_APP_ENV: string;
  readonly VITE_COGNITO_USER_POOL_ID: string;
  readonly VITE_COGNITO_CLIENT_ID: string;
  readonly VITE_TEST_COGNITO_USER_POOL_ID: string;
  readonly VITE_TEST_COGNITO_CLIENT_ID: string;
  readonly VITE_COGNITO_DOMAIN: string;
  readonly VITE_AWS_REGION: string;
  readonly VITE_API_URL: string;
  readonly VITE_REDIRECT_SIGN_IN: string;
  readonly VITE_REDIRECT_SIGN_OUT: string;
  readonly VITE_DOCS_URL: string;
  readonly BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
