# Bugfix Requirements Document

## Introduction

Admin Cognito operations in the Flask backend (`backend/src`) resolve the target user
pool from the legacy single-pool env var `COGNITO_USER_POOL_ID`, which points at the
**prod** pool (`eu-west-1_Hdp40eWmu`) in every environment. In contrast, **token
validation** correctly resolves the pool through the multi-pool issuer→pool registry
(`backend/src/auth/pool_registry.py` + `backend/src/auth/cognito_utils.py`), keyed by
the token's `iss` (TEST pool in dev/test via `COGNITO_POOL_KEYS=TEST`, `PROD_A` in
prod).

The result is a split-brain: in the dev container a user logs in and has their token
validated against the **TEST** pool, but every admin operation (password reset, user
create/get/update/delete, enable/disable, group add/remove, attribute updates,
preferred-language read/write, self-service signup) silently acts on the **PROD**
pool. This is why an in-app password reset for `peter@pgeers.nl` reported success (it
updated the prod account, which exists there) while localhost login kept failing
(the test-pool account had no matching password). The failure class has recurred
because each incident was patched at the symptom, not at the shared pool-resolution
root.

This violates the governing contract (specs s5c/s5d): the pool registry is the single
source of truth and pool selection is "config-not-code, by `iss`". This bugfix routes
**all** admin Cognito operations through one registry-backed pool-resolution helper,
keyed to the target user's pool rather than a global env var, and consolidates the
duplicated admin-Cognito logic onto that helper.

**Source of truth:** `.kiro/specs/myBacklog/rca-cognito-pool-selection-admin-ops.md`
(root cause is not re-derived here). Scope is RCA recommendations **R1** (root fix)
and **R2** (consolidation).

### Blast radius (full untruncated sweep of `backend/src`)

The RCA's blast-radius list was explicitly marked non-exhaustive. A full, untruncated
`grep` sweep of `backend/src` for `COGNITO_USER_POOL_ID` was re-run as part of this
requirements phase. Every site below reads the legacy single-pool var for an admin
operation and therefore targets prod in all environments:

- `backend/src/routes/auth_routes.py` — password reset (`admin_get_user`, `admin_set_user_password`)
- `backend/src/tenant_admin_routes.py` — `admin_list_groups_for_user`
- `backend/src/services/cognito_service.py` — create/get/update/delete user, add/remove group, create/delete group, list users in group, add/remove tenant attribute
- `backend/src/admin_routes.py` — list/create/enable/disable/delete user, groups, attribute updates
- `backend/src/services/user_language_service.py` — get/set `custom:preferred_language`
- `backend/src/services/signup_service.py` — self-service signup (`SIGNUP_COGNITO_USER_POOL_ID` falling back to `COGNITO_USER_POOL_ID`)
- `backend/src/routes/sysadmin_health.py` — sysadmin health/diagnostics admin reads *(not in the RCA list)*
- `backend/src/routes/sysadmin_provisioning.py` — provisioning (`SIGNUP_COGNITO_USER_POOL_ID` falling back to `COGNITO_USER_POOL_ID`) *(not in the RCA list)*
- `backend/src/routes/tenant_admin_users.py` — tenant admin user management *(not in the RCA list)*
- `backend/src/routes/tenant_admin_email.py` — tenant admin email/user lookups (two sites) *(not in the RCA list)*
- `backend/src/routes/sysadmin_helpers.py` — sysadmin helper admin ops *(not in the RCA list)*
- `backend/src/routes/sysadmin_roles.py` — sysadmin role/group admin ops *(not in the RCA list)*

The design phase must treat this list as the authoritative migration surface and
re-run the sweep at fix time to catch any drift.

**Excluded from the migration surface (validation path, intentionally preserved):**
`backend/src/auth/cognito_utils.py` reads `COGNITO_USER_POOL_ID` **only** as the
documented legacy single-pool *fallback for token validation*, used solely when
`COGNITO_POOL_KEYS` is absent. This is the already-correct validation behavior and is
not an admin-op read; it must remain unchanged (see clause 3.4).

### Out of scope (referenced from the RCA, not implemented here)

- **R3** — Frontend hostname→`VITE_APP_ENV` pool selection change.
- **R4** — The Pool B (tenant-scoped webshop users) product decision itself. This
  spec must be *forward-compatible* with a future Pool B but does not decide its model.
- **R5** — CI guardrail lint that fails when a non-registry file reads
  `COGNITO_USER_POOL_ID` for an admin op. May be noted as a follow-up but is not
  implemented here.
- The broader "dev/test environment stability" theme — a separate, larger effort.

## Bug Analysis

### Current Behavior (Defect)

What currently happens: admin Cognito operations resolve their target pool from the
legacy single-pool var `COGNITO_USER_POOL_ID` (prod), independent of the environment
and of the user being operated on, so they diverge from the pool the user's token
validates against.

1.1 WHEN an admin Cognito operation (password reset, user create/get/update/delete, enable/disable, group add/remove, attribute update, preferred-language read/write, or signup) runs THEN the system resolves the target pool from `os.getenv("COGNITO_USER_POOL_ID")` regardless of the environment or the target user.

1.2 WHEN the backend runs in the dev/test container (token validation configured with `COGNITO_POOL_KEYS=TEST`) AND an admin operation runs THEN the system acts on the PROD pool (`COGNITO_USER_POOL_ID`) while login/validation acts on the TEST pool, so the two paths target different pools for the same user.

1.3 WHEN a password reset is requested on localhost for a user that exists only in the PROD pool THEN the system reports the reset as successful (updating the prod account) while subsequent login against the TEST pool continues to fail, giving a misleading "reset succeeded but login still fails" outcome.

1.4 WHEN each admin operation site independently reads `COGNITO_USER_POOL_ID` (duplicated pool-resolution logic across at least the 12 files listed in the blast radius) THEN there is no single shared resolution path, so new admin code copies the legacy pattern and the defect recurs.

### Expected Behavior (Correct)

What should happen instead: every admin Cognito operation resolves its target pool
through the registry, keyed to the target user's pool, consistent with the pool the
user's token validates against, via one shared helper.

2.1 WHEN any admin Cognito operation runs THEN the system SHALL resolve the target user pool through the issuer→pool registry (`pool_registry.py`), keyed to the target user's pool, rather than from `COGNITO_USER_POOL_ID`.

2.2 WHEN an admin operation runs in dev/test (registry configured with the TEST pool) THEN the system SHALL act on the TEST pool; WHEN it runs in prod (registry configured with `PROD_A`) THEN the system SHALL act on `PROD_A`; and the resolution SHALL remain correct without code changes when a future `PROD_B` pool is added to the registry (config-not-code, N pools).

2.3 WHEN an admin operation starts from a token (the caller's own pool is known via `iss`) THEN the system SHALL resolve the target pool to the pool identified by that token's issuer, consistent with how token validation resolves it.

2.4 WHEN every admin Cognito operation resolves its pool THEN the system SHALL do so exclusively through ONE shared registry-backed resolution helper, and NO admin-operation code path SHALL read `COGNITO_USER_POOL_ID` directly.

2.5 WHEN an admin operation starts from an email (no token, e.g. forgot-password) THEN the system SHALL resolve which registered pool the user belongs to via a deterministic rule (the specific mechanism — resolve across registered pools, or a stored user→pool mapping — is chosen in design), not an implicit or environment-based guess.

2.6 WHEN an email could resolve to more than one registered pool (same email present in multiple pools) THEN the system SHALL apply an explicit, documented disambiguation rule and SHALL NOT silently pick the first match.

2.7 WHEN an admin operation targets a user (by email) that is not found in any registered pool THEN the system SHALL return a clear, non-500 error for operations that already surface not-found, EXCEPT that the existing anti-enumeration behavior of the password-reset (forgot-password) path SHALL be preserved (it SHALL continue to report success without revealing whether the account exists).

### Unchanged Behavior (Regression Prevention)

Existing behavior that must be preserved.

3.1 WHEN a token is validated THEN the system SHALL CONTINUE TO use the existing issuer→pool registry validation path (`cognito_utils.py` + `pool_registry.py`, selected by `iss`) unchanged — this path is already correct and is not modified by this fix.

3.2 WHEN the backend runs in prod with the current single-pool configuration (`COGNITO_POOL_KEYS=PROD_A`) THEN admin operations SHALL CONTINUE TO act on the same prod pool (`PROD_A` = `eu-west-1_Hdp40eWmu`) they act on today, i.e. the fix is behavior-preserving for the existing production environment.

3.3 WHEN admin operations run against a correctly configured registry THEN the system SHALL CONTINUE TO perform the same Cognito actions (create/get/update/delete user, enable/disable, group add/remove, attribute and preferred-language updates, signup) with the same request/response contracts — only the pool-resolution source changes.

3.4 WHEN `COGNITO_POOL_KEYS` is absent THEN the system SHALL CONTINUE TO permit the legacy single-pool var as a fallback, mirroring exactly how the validation path already falls back to `COGNITO_USER_POOL_ID` only when the registry is not configured; the legacy var SHALL be used only as this registry-absent fallback and never as the primary source when the registry is present.

3.5 WHEN the forgot-password endpoint is called for a non-existent or absent user THEN the system SHALL CONTINUE TO return success (anti-enumeration), consistent with clause 2.7.

## Bug Condition (derived)

**Definitions**
- **F**: current admin-op code — resolves the pool from `COGNITO_USER_POOL_ID`.
- **F'**: fixed admin-op code — resolves the pool via the shared registry-backed helper, keyed to the target user's pool.

**Bug Condition** — identifies inputs that trigger the bug:

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type AdminCognitoOperation   // { op, targetUser, callerToken?, env }
  OUTPUT: boolean

  // The bug triggers whenever the pool that COGNITO_USER_POOL_ID points at
  // differs from the pool the target user actually belongs to / validates against.
  RETURN poolFrom(COGNITO_USER_POOL_ID) <> registryPoolFor(X.targetUser)
END FUNCTION
```

**Property — Fix Checking** (desired behavior for buggy inputs):

```pascal
// For every admin op where the legacy var and the user's real pool diverge,
// the fixed code must act on the user's real (registry-resolved) pool.
FOR ALL X WHERE isBugCondition(X) DO
  targetPool ← resolvePoolViaRegistry(X.targetUser)   // the ONE shared helper
  result ← F'(X) using targetPool
  ASSERT actedOnPool(result) = registryPoolFor(X.targetUser)
  ASSERT reads_COGNITO_USER_POOL_ID(F') = FALSE        // no direct legacy read in admin path
END FOR
```

**Property — Preservation Checking** (non-buggy inputs unchanged):

```pascal
// Where the legacy var already agrees with the user's real pool (e.g. prod with
// COGNITO_POOL_KEYS=PROD_A, or registry-absent single-pool config), behavior is identical.
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```
