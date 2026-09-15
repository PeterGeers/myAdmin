# Environments & Test Strategy

> How the platform is tested without touching production — the missing environment
> axis behind the roadmap's identity/data work. `mysaas` decides *where code lives*
> (the trunk); this doc decides *which environment code runs against*. Those are
> separate concerns and both must be answered. Companion to `aws-accounts.md`
> (steering) and the identity steps (S2/S3/S4). Analysis + decisions.

## The three environment axes

A full test run of the verify → claim → system-of-record → projection → portal path
touches three resource types. Each has its own isolation mechanism:

| Resource | Test isolation | Status |
| --- | --- | --- |
| **MySQL + admin backend** | Local **Docker** dev/test app (myAdmin) | Have it |
| **DynamoDB** | `test_`-prefixed table names (rule: all test tables prefixed `test_`) | Have it |
| **Cognito** | A **standing test pool** (see below) | New — the one addition |

Two of the three are already solved by existing conventions. The only gap was
identity: Cognito has no local emulator and no name-prefix trick — a pool is a real
cloud resource — so a dedicated test pool is required.

## Decision — standing test Cognito pool

- A **new, permanent Essentials-tier Cognito pool** in the identity (personal)
  account, always available (not spun up per task). Essentials = 10,000 MAU free, so
  a handful of test users costs effectively nothing.
- **Mirrors Pool A** (`eu-west-1_Hdp40eWmu`): same app-client config, claim shapes,
  groups, and the Pre-Token-Generation trigger — so token verification (S2),
  two-pool claims + provisioning (S3), and entitlement projection (S4) are exercised
  against a realistic pool.
- Holds **throwaway test users only** — never real admin/member accounts.
- Recorded in `aws-accounts.md` under the identity-account model.

## The core rule — production is touched only after gated validation

- All identity changes (S2/S3/S4) are validated against the **test pool** +
  **Docker MySQL** + **`test_` DynamoDB** first.
- **Production Pool A (`eu-west-1_Hdp40eWmu`) is changed only after test-pool
  validation, gated** — the same copy/verify/prove discipline the migration plan
  applies to data moves, applied to identity config.
- Rationale: Cognito changes are among the riskiest (a bad app-client or trigger
  change can lock real users out). Working in a clean `mysaas` repo does NOT by
  itself protect production identity — the test pool is what does.

## The always-remote caveat

Local Docker covers MySQL + backend, and `test_` tables cover DynamoDB, but
**Cognito is always a remote call** (no local emulator). So the standard test
pattern is:

> local Docker MySQL/backend + local/`test_` DynamoDB + **remote test Cognito pool**.

The identity verification hop is the one part of the loop that always reaches a real
(test) cloud pool. This is normal and expected.

## Relation to the roadmap

- **Prerequisite for S2/S3 (and S4):** the standing test pool must exist before
  identity work begins, so that work never runs first against production Pool A.
- Fits the existing gating philosophy in `migration_plan.md` (copy → verify → cut
  over → keep old until proven) — here applied to identity config promotion
  (test pool → production pool) rather than data.

## Open sub-items

- Test-pool user seeding: a small fixture set (one per role / per pool-A-like
  claim shape) — scripted, reproducible.
- Whether Pool B also gets a mirrored test pool, or the single test pool covers both
  audiences with test app-clients. (Likely one test pool, two test app-clients.)
- CI: where automated identity tests point (test pool + `test_` tables), and
  ensuring they can never be pointed at production by misconfiguration
  (fail-fast env vars, per the no-dangerous-fallbacks guardrail).
