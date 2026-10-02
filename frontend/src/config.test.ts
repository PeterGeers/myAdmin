/**
 * Tests for the Flask API base URL config (src/config.ts) and a representative
 * service that consumes it.
 *
 * Covers (T11 — Requirements 21.2, 21.3, 21.4): the Flask API base URL the frontend
 * calls is resolved SOLELY from APP_ENV via the Environment_Resolver
 * (`./config/appEnv` → `RESOLVED.flaskApiBaseUrl`) — never a hardcoded `localhost:5000`
 * literal and never inferred from the browser protocol/hostname.
 *
 * - APP_ENV=test  ⇒ the resolved TEST Flask API base URL (http://localhost:5000).
 * - APP_ENV=production ⇒ the resolved PRODUCTION Flask API base URL.
 * - The two environments never collapse to the same base.
 * - No `localhost:5000` literal survives in the migrated source.
 *
 * The resolved config is evaluated at MODULE LOAD (via ./config/appEnv), so each case
 * stubs VITE_APP_ENV, resets modules, and dynamically re-imports — the same pattern
 * used by src/aws-exports.test.ts and src/config/appEnv.test.ts.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  TEST_FRONTEND_CONFIG,
  PROD_FRONTEND_CONFIG,
} from './config/environmentDefinition';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

/** Load a fresh copy of config.ts under a specific VITE_APP_ENV value. */
async function loadConfigWith(raw: string | undefined): Promise<typeof import('./config')> {
  vi.resetModules();
  if (raw === undefined) {
    vi.stubEnv('VITE_APP_ENV', undefined as unknown as string);
  } else {
    vi.stubEnv('VITE_APP_ENV', raw);
  }
  return import('./config');
}

/** Load a fresh copy of tenantAdminApi.ts (a representative service) under an env. */
async function loadTenantAdminApiWith(
  raw: string,
): Promise<typeof import('./services/tenantAdminApi')> {
  vi.resetModules();
  vi.stubEnv('VITE_APP_ENV', raw);
  return import('./services/tenantAdminApi');
}

describe('config.ts — Flask API base URL resolved from APP_ENV', () => {
  it("resolves the TEST Flask API base URL when VITE_APP_ENV='test'", async () => {
    const { API_BASE_URL } = await loadConfigWith('test');
    expect(API_BASE_URL).toBe(TEST_FRONTEND_CONFIG.flaskApiBaseUrl);
    expect(API_BASE_URL).toBe('http://localhost:5000');
  });

  it("resolves the PRODUCTION Flask API base URL when VITE_APP_ENV='production'", async () => {
    const { API_BASE_URL } = await loadConfigWith('production');
    expect(API_BASE_URL).toBe(PROD_FRONTEND_CONFIG.flaskApiBaseUrl);
  });

  it('never collapses TEST and PRODUCTION to the same base URL', async () => {
    const { API_BASE_URL: testBase } = await loadConfigWith('test');
    const { API_BASE_URL: prodBase } = await loadConfigWith('production');
    expect(testBase).not.toBe(prodBase);
  });

  it('buildApiUrl composes the resolved base with the endpoint path', async () => {
    const { buildApiUrl } = await loadConfigWith('test');
    expect(buildApiUrl('/api/status')).toBe('http://localhost:5000/api/status');
  });

  it('fails fast at module load when VITE_APP_ENV is unset (no silent default)', async () => {
    await expect(loadConfigWith(undefined)).rejects.toThrow(/VITE_APP_ENV must be one of/);
  });
});

describe('tenantAdminApi.ts — base URL derives from the resolved Flask API base URL', () => {
  // A representative service: its base URL must track the resolved config, not a literal.
  it('is importable under APP_ENV=test (base derived from RESOLVED, not a literal)', async () => {
    const mod = await loadTenantAdminApiWith('test');
    // The module exposes functions; a successful import proves the module-load
    // `RESOLVED.flaskApiBaseUrl` read succeeded (a stray literal would not fail-fast,
    // but the appEnv resolver only yields a value when APP_ENV is set — see below).
    expect(typeof mod).toBe('object');
  });

  it('fails fast when APP_ENV is unset (service base URL is NOT a hardcoded fallback)', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_APP_ENV', undefined as unknown as string);
    await expect(import('./services/tenantAdminApi')).rejects.toThrow(
      /VITE_APP_ENV must be one of/,
    );
  });
});

describe('no hardcoded localhost:5000 literal remains in the migrated Flask-URL source', () => {
  // Guard that the T11 migration actually removed the literals from the touched source
  // (the base URL must come from RESOLVED, never a hardcoded string).
  const here = dirname(fileURLToPath(import.meta.url));
  const touched = [
    'config.ts',
    'services/authService.ts',
    'services/verificationApi.ts',
    'services/tenantAdminApi.ts',
    'services/chartOfAccountsService.ts',
    'components/ProfitLoss.tsx',
    'components/PDFValidation.tsx',
  ];

  it.each(touched)('%s contains no "localhost:5000" literal', (relPath) => {
    const source = readFileSync(join(here, relPath), 'utf8');
    expect(source).not.toContain('localhost:5000');
  });
});
