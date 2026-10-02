/**
 * Tests for AWS Amplify Configuration (src/aws-exports.ts).
 *
 * Covers (T5 — Requirements 1.4, 1.5, 2.3, 5.3, 8.1-8.2, 8.5):
 * - The Cognito pool/client are selected from the resolved APP_ENV (RESOLVED), NOT
 *   from window.location.hostname.
 * - APP_ENV=test resolves the test pool; APP_ENV=production resolves Pool A.
 * - The Amplify config object shape is preserved (Auth.Cognito + OAuth block) so
 *   consumers are unaffected.
 * - Property 3 (resolution ignores incidental signals): for a fixed VITE_APP_ENV the
 *   selected pool is invariant across arbitrary window.location.hostname values.
 *
 * The resolved config is evaluated at MODULE LOAD (via ./config/appEnv), so each case
 * stubs VITE_APP_ENV, resets modules, and dynamically re-imports aws-exports — the
 * same pattern used by src/config/appEnv.test.ts.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import fc from 'fast-check';
import {
  TEST_POOL_ID,
  TEST_CLIENT_ID,
  PROD_POOL_ID,
  PROD_CLIENT_ID,
} from './config/environmentDefinition';

/** The default hostname jsdom provides; restored after each test. */
const DEFAULT_HREF = 'http://localhost:3000/';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  // Restore the jsdom location after any per-test hostname override.
  window.history.pushState({}, '', DEFAULT_HREF);
});

/** Set the browser hostname jsdom reports (an incidental signal that MUST be ignored). */
function setHostname(hostname: string): void {
  // jsdom forbids assigning window.location.hostname directly; redefine the getter.
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, hostname, href: `http://${hostname}:3000/`, port: '3000' },
  });
}

/** Load a fresh copy of aws-exports under a specific VITE_APP_ENV value. */
async function loadWith(raw: string | undefined): Promise<typeof import('./aws-exports')> {
  vi.resetModules();
  if (raw === undefined) {
    vi.stubEnv('VITE_APP_ENV', undefined as unknown as string);
  } else {
    vi.stubEnv('VITE_APP_ENV', raw);
  }
  return import('./aws-exports');
}

describe('AWS Amplify Configuration — shape', () => {
  it('has an Auth.Cognito block with pool id, client id and OAuth config', async () => {
    const { default: awsconfig } = await loadWith('test');
    expect(awsconfig).toBeDefined();
    expect(awsconfig.Auth).toBeDefined();
    expect(awsconfig.Auth.Cognito).toBeDefined();
    expect(awsconfig.Auth.Cognito.userPoolId).toBeDefined();
    expect(awsconfig.Auth.Cognito.userPoolClientId).toBeDefined();

    const oauth = awsconfig.Auth.Cognito.loginWith.oauth;
    expect(oauth).toBeDefined();
    expect(typeof oauth.domain).toBe('string');
    expect(oauth.scopes).toEqual(expect.arrayContaining(['openid', 'email', 'profile']));
    expect(Array.isArray(oauth.redirectSignIn)).toBe(true);
    expect(oauth.redirectSignIn.length).toBeGreaterThan(0);
    expect(Array.isArray(oauth.redirectSignOut)).toBe(true);
    expect(oauth.redirectSignOut.length).toBeGreaterThan(0);
    expect(oauth.responseType).toBe('code');
  });
});

describe('AWS Amplify Configuration — pool selected from resolved APP_ENV', () => {
  it("resolves the TEST pool when VITE_APP_ENV='test'", async () => {
    const { default: awsconfig } = await loadWith('test');
    expect(awsconfig.Auth.Cognito.userPoolId).toBe(TEST_POOL_ID);
    expect(awsconfig.Auth.Cognito.userPoolClientId).toBe(TEST_CLIENT_ID);
  });

  it("resolves Pool A when VITE_APP_ENV='production'", async () => {
    const { default: awsconfig } = await loadWith('production');
    expect(awsconfig.Auth.Cognito.userPoolId).toBe(PROD_POOL_ID);
    expect(awsconfig.Auth.Cognito.userPoolClientId).toBe(PROD_CLIENT_ID);
  });

  it('never selects the OTHER environment pool', async () => {
    const { default: testConfig } = await loadWith('test');
    expect(testConfig.Auth.Cognito.userPoolId).not.toBe(PROD_POOL_ID);

    const { default: prodConfig } = await loadWith('production');
    expect(prodConfig.Auth.Cognito.userPoolId).not.toBe(TEST_POOL_ID);
  });

  it('fails fast at module load when VITE_APP_ENV is unset (no silent default)', async () => {
    await expect(loadWith(undefined)).rejects.toThrow(/VITE_APP_ENV must be one of/);
  });
});

describe('Property 3: resolution ignores incidental signals', () => {
  // Validates: Requirements 1.3, 1.5
  // For a FIXED VITE_APP_ENV, the selected Cognito pool is invariant across arbitrary
  // window.location.hostname values (and port). Changing an incidental signal never
  // changes the resolved pool — the output is a function of APP_ENV only.
  beforeEach(() => {
    vi.resetModules();
  });

  it('selected pool is invariant across arbitrary hostnames for APP_ENV=test', async () => {
    await fc.assert(
      fc.asyncProperty(fc.domain(), async (hostname) => {
        setHostname(hostname);
        const { default: awsconfig } = await loadWith('test');
        // Hostname is incidental: the pool is always the TEST pool.
        expect(awsconfig.Auth.Cognito.userPoolId).toBe(TEST_POOL_ID);
        expect(awsconfig.Auth.Cognito.userPoolClientId).toBe(TEST_CLIENT_ID);
      }),
      { numRuns: 25 },
    );
  });

  it('selected pool is invariant across arbitrary hostnames for APP_ENV=production', async () => {
    await fc.assert(
      fc.asyncProperty(fc.domain(), async (hostname) => {
        setHostname(hostname);
        const { default: awsconfig } = await loadWith('production');
        expect(awsconfig.Auth.Cognito.userPoolId).toBe(PROD_POOL_ID);
        expect(awsconfig.Auth.Cognito.userPoolClientId).toBe(PROD_CLIENT_ID);
      }),
      { numRuns: 25 },
    );
  });

  it("the 'localhost' hostname does NOT force the test pool when APP_ENV=production", async () => {
    // Direct regression guard against the removed hostname switch: localhost used to
    // force the test pool; now APP_ENV alone decides.
    setHostname('localhost');
    const { default: awsconfig } = await loadWith('production');
    expect(awsconfig.Auth.Cognito.userPoolId).toBe(PROD_POOL_ID);
    expect(awsconfig.Auth.Cognito.userPoolId).not.toBe(TEST_POOL_ID);
  });
});
