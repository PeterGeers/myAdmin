/**
 * Tests for the Frontend Environment_Resolver (src/config/appEnv.ts).
 *
 * Covers (S3 / T1.5 — Requirements 1.3-1.5, 2.3, 3.1-3.6, 8.1-8.2):
 * - resolveAppEnv() returns 'test'/'production' for valid injected values
 * - resolveAppEnv() throws for undefined/invalid values (fail-fast, no default)
 * - resolveConfig() / RESOLVED select the correct per-plane config per environment
 * - Module-load fail-fast: importing with an unset/unknown VITE_APP_ENV throws
 *
 * The RESOLVED/APP_ENV constants are evaluated at MODULE LOAD, so those cases use
 * vi.resetModules() + a fresh dynamic import under a stubbed VITE_APP_ENV.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import fc from 'fast-check';
import {
  PROD_FRONTEND_CONFIG,
  TEST_FRONTEND_CONFIG,
  TEST_POOL_ID,
  TEST_CLIENT_ID,
  PROD_POOL_ID,
} from './environmentDefinition';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

/** Load a fresh copy of the module under a specific VITE_APP_ENV value. */
async function loadWith(raw: string | undefined): Promise<typeof import('./appEnv')> {
  vi.resetModules();
  if (raw === undefined) {
    vi.stubEnv('VITE_APP_ENV', undefined as unknown as string);
  } else {
    vi.stubEnv('VITE_APP_ENV', raw);
  }
  return import('./appEnv');
}

describe('resolveAppEnv', () => {
  it("returns 'test' when VITE_APP_ENV='test'", async () => {
    const mod = await loadWith('test');
    expect(mod.resolveAppEnv()).toBe('test');
  });

  it("returns 'production' when VITE_APP_ENV='production'", async () => {
    const mod = await loadWith('production');
    expect(mod.resolveAppEnv()).toBe('production');
  });

  it('throws when VITE_APP_ENV is unset', async () => {
    // The module itself fails fast at load with no valid value, so build it under a
    // valid value, then exercise the function with the var cleared.
    const mod = await loadWith('test');
    vi.stubEnv('VITE_APP_ENV', undefined as unknown as string);
    expect(() => mod.resolveAppEnv()).toThrow(/VITE_APP_ENV must be one of/);
  });

  it('throws for an unrecognized value', async () => {
    const mod = await loadWith('test');
    vi.stubEnv('VITE_APP_ENV', 'staging');
    expect(() => mod.resolveAppEnv()).toThrow(/got: staging/);
  });

  it("rejects case/whitespace variants (exact match only, e.g. 'Test', ' test ')", async () => {
    const mod = await loadWith('test');
    for (const bad of ['Test', 'TEST', ' test ', 'prod', 'Production']) {
      vi.stubEnv('VITE_APP_ENV', bad);
      expect(() => mod.resolveAppEnv()).toThrow();
    }
  });
});

describe('resolveConfig', () => {
  it("selects TEST_FRONTEND_CONFIG for 'test'", async () => {
    const mod = await loadWith('test');
    // Value equality: a fresh dynamic import pulls a fresh module graph, so compare
    // by value rather than reference identity.
    expect(mod.resolveConfig('test')).toStrictEqual(TEST_FRONTEND_CONFIG);
    expect(mod.resolveConfig('test').cognito.poolId).toBe(TEST_POOL_ID);
    expect(mod.resolveConfig('test').cognito.clientId).toBe(TEST_CLIENT_ID);
    // Test pool has no client secret (Req 8.4).
    expect(mod.resolveConfig('test').cognito.clientSecretRef).toBe('');
  });

  it("selects PROD_FRONTEND_CONFIG for 'production'", async () => {
    const mod = await loadWith('production');
    expect(mod.resolveConfig('production')).toStrictEqual(PROD_FRONTEND_CONFIG);
    expect(mod.resolveConfig('production').cognito.poolId).toBe(PROD_POOL_ID);
  });
});

describe('module-load constants (APP_ENV / RESOLVED)', () => {
  it("resolves RESOLVED to the TEST config when VITE_APP_ENV='test'", async () => {
    const mod = await loadWith('test');
    expect(mod.APP_ENV).toBe('test');
    expect(mod.RESOLVED).toStrictEqual(TEST_FRONTEND_CONFIG);
    expect(mod.RESOLVED.sam.tablePrefix).toBe('test_');
    expect(mod.RESOLVED.cognito.poolId).toBe(TEST_POOL_ID);
    expect(mod.RESOLVED.sam.authorizerPoolId).toBe(TEST_POOL_ID);
  });

  it("resolves RESOLVED to the PROD config when VITE_APP_ENV='production'", async () => {
    const mod = await loadWith('production');
    expect(mod.APP_ENV).toBe('production');
    expect(mod.RESOLVED).toStrictEqual(PROD_FRONTEND_CONFIG);
    expect(mod.RESOLVED.sam.tablePrefix).toBe('');
    expect(mod.RESOLVED.cognito.poolId).toBe(PROD_POOL_ID);
    expect(mod.RESOLVED.sam.authorizerPoolId).toBe(PROD_POOL_ID);
  });

  it('FAILS FAST at module load when VITE_APP_ENV is unset (no silent default)', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_APP_ENV', undefined as unknown as string);
    await expect(import('./appEnv')).rejects.toThrow(/VITE_APP_ENV must be one of/);
  });

  it('FAILS FAST at module load when VITE_APP_ENV is unrecognized', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_APP_ENV', 'dev');
    await expect(import('./appEnv')).rejects.toThrow(/got: dev/);
  });
});

describe('property: resolveConfig is total and correct over valid envs', () => {
  // Validates: Requirements 2.3, 3.1
  it('returns exactly the committed config for the selected env, never crossing wires', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom<'production' | 'test'>('production', 'test'),
        async (env) => {
          const mod = await loadWith(env);
          const resolved = mod.resolveConfig(env);
          const expected = env === 'test' ? TEST_FRONTEND_CONFIG : PROD_FRONTEND_CONFIG;
          expect(resolved).toStrictEqual(expected);
          // The resolved config never points at the OTHER environment's pool.
          const otherPool = env === 'test' ? PROD_POOL_ID : TEST_POOL_ID;
          expect(resolved.cognito.poolId).not.toBe(otherPool);
        },
      ),
      { numRuns: 20 },
    );
  });
});
