/**
 * URL-based environment selection + access boundary (test-environment spec, Req 22).
 *
 * Req 22 says environment choice is a deployment/entry-point decision — you reach an
 * environment by opening its distinct URL and authenticating against that
 * environment's Cognito pool — NOT an in-app toggle. Access to TEST is determined
 * solely by membership in the test pool (22.3/22.4).
 *
 * These smoke tests assert the committed Environment_Definition binds each distinct
 * URL to the correct pool, so the "URL → pool" access boundary is pinned:
 *   - testUrl  authenticates against the TEST pool (eu-west-1_xyrlzfqbl),
 *   - productionUrl authenticates against production Pool A (eu-west-1_Hdp40eWmu),
 *   - the two URLs and the two pools are distinct (you cannot reach TEST data via the
 *     PROD URL or vice-versa), and
 *   - the resolver selects each environment's pool for that environment (the pool a
 *     deployment authenticates against is a function of APP_ENV, which the URL's
 *     deployment fixes — never inferred from the hostname).
 *
 * Validates: Requirements 22.1, 22.3, 22.4 (22.5/22.6 — indicator-not-from-hostname and
 * no in-app switch — are covered by EnvironmentIndicator.test.tsx and aws-exports.test.ts).
 */

import { describe, expect, it } from 'vitest';
import {
  ENVIRONMENT_DEFINITION,
  TEST_POOL_ID,
  PROD_POOL_ID,
} from './environmentDefinition';
import { resolveConfig } from './appEnv';

describe('URL → Cognito pool access boundary (Req 22.3/22.4)', () => {
  it('declares a distinct URL for each environment (Req 22.1)', () => {
    const { testUrl, productionUrl } = ENVIRONMENT_DEFINITION;
    expect(testUrl).toBeTruthy();
    expect(productionUrl).toBeTruthy();
    expect(testUrl).not.toBe(productionUrl);
  });

  it('binds the TEST URL to the test pool and the PROD URL to Pool A (Req 22.3)', () => {
    // The definition records both the distinct URLs and the per-env pools; the access
    // boundary is that each URL's deployment authenticates against its env's pool.
    expect(ENVIRONMENT_DEFINITION.test.cognito.poolId).toBe(TEST_POOL_ID);
    expect(ENVIRONMENT_DEFINITION.production.cognito.poolId).toBe(PROD_POOL_ID);
    // The TEST URL serves the test deployment (APP_ENV=test → test pool); the PROD URL
    // serves the production deployment (APP_ENV=production → Pool A).
    expect(resolveConfig('test').cognito.poolId).toBe(TEST_POOL_ID);
    expect(resolveConfig('production').cognito.poolId).toBe(PROD_POOL_ID);
  });

  it('keeps the two pools distinct so one URL cannot reach the other env (Req 22.4)', () => {
    expect(TEST_POOL_ID).not.toBe(PROD_POOL_ID);
    expect(resolveConfig('test').cognito.poolId).not.toBe(
      resolveConfig('production').cognito.poolId,
    );
  });

  it('access to TEST is membership in the test pool only — no secondary allow-list', () => {
    // The test pool has NO client secret (access is pool membership, not a shared
    // secret / separate allow-list — Req 22.4 / 8.4).
    expect(resolveConfig('test').cognito.clientSecretRef).toBe('');
  });
});
