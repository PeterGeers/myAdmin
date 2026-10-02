/**
 * Environment_Resolver — Frontend realization (TypeScript equivalent of the backend
 * `backend/src/environment/app_env.py` + `resolver.py`).
 *
 * S3 / T1.5 — The single environment decision point for the frontend. It reads the
 * authoritative deploy-level selector APP_ENV (injected as `VITE_APP_ENV` at build time,
 * or `window.__APP_ENV__` at runtime) and derives the resolved per-plane configuration
 * from the committed Environment_Definition.
 *
 * Invariants carried from the design
 * (`.kiro/specs/Common/test-environment/first-draft/design.md`):
 *
 * 1. Fail-fast, no dangerous default (Req 1.3, 1.5). An unset or unrecognized
 *    VITE_APP_ENV throws AT MODULE LOAD — surfaced as a build/boot error — never a
 *    silent production (or test) default. This parallels the backend `parse_app_env`
 *    and `pool_registry` discipline (missing var ⇒ raise, never a silent fallback).
 * 2. Never inferred from incidental signals (Req 1.4, 1.5). The resolver reads only the
 *    explicit injected variable — never `window.location.hostname`. (The hostname-based
 *    switch in `aws-exports.ts` is replaced in later tasks 5.x; this module just
 *    provides the resolver + RESOLVED config.)
 * 3. One decision, many consumers (Req 2.1-2.4). This is the single place that maps
 *    APP_ENV to concrete per-plane values; consumers read `RESOLVED`, not raw env/host.
 */

import {
  EnvironmentDefinition,
  FrontendPlaneDef,
  ENVIRONMENT_DEFINITION,
  TEST_FRONTEND_CONFIG,
  PROD_FRONTEND_CONFIG,
} from './environmentDefinition';

/** The closed set of recognized environment values (mirrors the backend AppEnv enum). */
export type AppEnv = 'production' | 'test';

/** The recognized APP_ENV values, for error messages and validation. */
export const RECOGNIZED_APP_ENVS: readonly AppEnv[] = ['production', 'test'] as const;

/**
 * Read and validate the active APP_ENV for the frontend.
 *
 * Source precedence: the build-time injected `import.meta.env.VITE_APP_ENV`, falling
 * back to a served runtime value `window.__APP_ENV__`. The active environment is NEVER
 * inferred from the hostname or any other incidental signal (Req 1.4, 1.5).
 *
 * Fail-fast: if the resolved raw value is not exactly `'production'` or `'test'`, this
 * throws (no default is ever substituted — Req 1.3).
 *
 * @returns The validated AppEnv (`'production'` or `'test'`).
 * @throws Error if VITE_APP_ENV / window.__APP_ENV__ is unset or unrecognized.
 */
export function resolveAppEnv(): AppEnv {
  const fromBuild =
    typeof import.meta !== 'undefined' ? import.meta.env?.VITE_APP_ENV : undefined;
  const fromRuntime =
    typeof window !== 'undefined'
      ? (window as unknown as { __APP_ENV__?: unknown }).__APP_ENV__
      : undefined;

  const raw = fromBuild ?? fromRuntime;

  if (raw !== 'production' && raw !== 'test') {
    throw new Error(
      `VITE_APP_ENV must be one of: ${RECOGNIZED_APP_ENVS.map((v) => `'${v}'`).join(
        ', ',
      )}, got: ${String(raw)}. There is no default (no-dangerous-fallbacks).`,
    );
  }

  return raw;
}

/**
 * Select the resolved per-plane configuration for a given AppEnv from the committed
 * Environment_Definition. This is the frontend analogue of the backend `resolve()`.
 *
 * @param env The active AppEnv.
 * @param definition The Environment_Definition to read from (defaults to the committed one).
 * @returns The TEST or PRODUCTION FrontendPlaneDef.
 */
export function resolveConfig(
  env: AppEnv,
  definition: EnvironmentDefinition = ENVIRONMENT_DEFINITION,
): FrontendPlaneDef {
  return env === 'test' ? definition.test : definition.production;
}

/**
 * The active AppEnv, resolved once at module load. Importing this module in a unit
 * built/served without a valid VITE_APP_ENV fails fast (Req 1.3).
 */
export const APP_ENV: AppEnv = resolveAppEnv();

/**
 * The resolved per-plane configuration for the active environment — the single value
 * frontend consumers read instead of raw env vars or the browser hostname.
 */
export const RESOLVED: FrontendPlaneDef =
  APP_ENV === 'test' ? TEST_FRONTEND_CONFIG : PROD_FRONTEND_CONFIG;
