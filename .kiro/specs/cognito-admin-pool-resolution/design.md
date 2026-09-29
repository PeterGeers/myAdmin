# Cognito Admin Pool Resolution Bugfix Design

## Overview

Admin Cognito operations in the Flask backend resolve their target user pool from the
legacy single-pool env var `COGNITO_USER_POOL_ID` (which points at the PROD pool in
every environment), while **token validation** correctly resolves the pool through the
issuer→pool registry (`auth/pool_registry.py` + `auth/cognito_utils.py`) keyed by the
token's `iss`. The result is a split-brain: a dev/test user logs in against the TEST
pool but every admin op (password reset, user CRUD, enable/disable, group membership,
attribute updates, preferred-language, signup) silently acts on the PROD pool.

The fix introduces **one shared registry-backed pool-resolution helper** that every
admin Cognito operation calls to obtain its target `user_pool_id`, and migrates the 12
admin-op files off their direct `os.getenv("COGNITO_USER_POOL_ID")` reads onto that
helper. The helper resolves the target pool the same way validation does — from the
registry, keyed to the user's pool — with two entry modes: **token-based** (resolve by
the caller's token `iss`, mirroring validation) and **email-based** (resolve which
registered pool a user belongs to, for tokenless flows like forgot-password).

The strategy is deliberately minimal and behavior-preserving: the validation path
(`cognito_utils.py` + `pool_registry.py`) is untouched, and in the existing production
single-pool configuration (`COGNITO_POOL_KEYS=PROD_A`) admin operations continue to act
on exactly the same pool (`eu-west-1_Hdp40eWmu`) they act on today. The change is
forward-compatible with a future `PROD_B` webshop pool without a code change (config-
not-code, N pools).

**Source of truth for the root cause:**
`.kiro/specs/myBacklog/rca-cognito-pool-selection-admin-ops.md` (root cause is settled
and not re-derived here). Scope is RCA recommendations R1 (root fix) + R2
(consolidation).

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — the pool that
  `COGNITO_USER_POOL_ID` points at differs from the pool the target user actually
  belongs to / validates against, so an admin op acts on the wrong pool.
- **Property (P)**: The desired behavior — every admin op resolves and acts on the
  target user's *registry-resolved* pool, and reads no legacy var directly.
- **Preservation**: Existing behavior that must remain unchanged — the token
  validation path, the production single-pool behavior, every admin request/response
  contract, and the registry-absent legacy fallback semantics.
- **Registry**: The issuer→pool map built by `load_pool_registry()` in
  `auth/pool_registry.py`, keyed by the token issuer (`iss`), declared by the
  `COGNITO_POOL_KEYS` env var. Single source of truth for "which pools exist".
- **PoolConfig**: A registry entry (`auth/test_pool_config.py`) —
  `{ iss, jwks_uri, audience, pool_label }`. Note: it has **no** `user_pool_id`
  field; the pool id is the trailing path segment of `iss`
  (`https://cognito-idp.{region}.amazonaws.com/{user_pool_id}`).
- **Admin op**: Any AWS Cognito Identity Provider `admin_*` / group / user operation
  performed server-side against a pool id (e.g. `admin_get_user`,
  `admin_set_user_password`, `admin_create_user`, `admin_add_user_to_group`,
  `list_users`, `list_groups`, `admin_update_user_attributes`).
- **resolve_pool_id (the helper)**: The new shared resolver
  (`auth/admin_pool_resolver.py`) that returns the target `user_pool_id` for an admin
  op, in token mode or email mode. The ONE code path all admin ops use.
- **PROD_A / PROD_B / TEST**: Registered pool keys. PROD_A =
  `eu-west-1_Hdp40eWmu` (current production). TEST = `eu-west-1_xyrlzfqbl`. PROD_B =
  future tenant-scoped webshop pool (not decided here; the helper must not break when
  it is added).
- **F**: The current (unfixed) admin-op code — resolves the pool from
  `COGNITO_USER_POOL_ID`.
- **F'**: The fixed admin-op code — resolves the pool via `resolve_pool_id`.

## Bug Details

### Bug Condition

The bug manifests whenever an admin Cognito operation runs and the pool that the legacy
`COGNITO_USER_POOL_ID` var points at is **not** the pool the target user actually
belongs to (or the pool the caller's token validates against). The admin-op code
resolves the target pool from the legacy env var instead of from the registry keyed to
the target user, so the operation acts on the wrong pool. This is systemic: at least 12
files independently read the legacy var, so there is no single shared resolution path.

**Formal Specification:**
```
FUNCTION isBugCondition(X)
  INPUT: X of type AdminCognitoOperation   // { op, targetUser, callerToken?, env }
  OUTPUT: boolean

  // The bug triggers whenever the pool COGNITO_USER_POOL_ID points at differs from
  // the pool the target user actually belongs to / validates against.
  RETURN poolFrom(COGNITO_USER_POOL_ID) <> registryPoolFor(X.targetUser)
END FUNCTION
```

### Examples

- **Password reset, dev container (TEST validation, PROD legacy var):**
  `forgot-password` for `peter@pgeers.nl` — legacy var = PROD (`eu-west-1_Hdp40eWmu`),
  registry pool (by TEST config) = TEST (`eu-west-1_xyrlzfqbl`). Expected: reset acts
  on the TEST-pool account so localhost login succeeds. Actual: `admin_get_user` /
  `admin_set_user_password` update the PROD account; the endpoint reports success
  (anti-enumeration) but localhost login keeps failing.
- **User create, dev container:** admin creates a user "in the app" — legacy var =
  PROD, so the user lands in the PROD pool. Expected: created in the TEST pool the app
  validates against. Actual: created in PROD, invisible to dev login.
- **Group add/remove, dev container:** `admin_add_user_to_group` for a role change —
  legacy var = PROD, so the group membership is written to the PROD account, not the
  TEST account whose token the UI carries.
- **Edge case — prod, single-pool config (`COGNITO_POOL_KEYS=PROD_A`):** legacy var =
  PROD_A = registry pool = PROD_A. `isBugCondition` is FALSE — behavior is already
  correct and must be preserved unchanged.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Token validation continues to use the existing issuer→pool registry path
  (`cognito_utils.py` + `pool_registry.py`, selected by `iss`) with no modification
  (3.1).
- In the existing production single-pool configuration (`COGNITO_POOL_KEYS=PROD_A`),
  admin operations continue to act on the same prod pool (`PROD_A` =
  `eu-west-1_Hdp40eWmu`) they act on today (3.2).
- Every admin operation continues to perform the same Cognito actions with the same
  request/response contracts — only the pool-resolution *source* changes (3.3).
- When `COGNITO_POOL_KEYS` is absent, the legacy single-pool var continues to be
  permitted as a fallback, mirroring exactly how the validation path already falls
  back to `COGNITO_USER_POOL_ID` only when the registry is not configured (3.4).
- The forgot-password endpoint continues to return success for a non-existent/absent
  user (anti-enumeration) (3.5 / 2.7).

**Scope:**
All inputs where `isBugCondition` is FALSE — i.e. where the legacy var already agrees
with the target user's registry-resolved pool — must be completely unaffected by this
fix. This includes:
- Production running with `COGNITO_POOL_KEYS=PROD_A` (legacy var == PROD_A).
- Any registry-absent single-pool deployment (helper falls back to the legacy var,
  same pool as before).
- The token validation code path entirely (it is not an admin-op path).

**Note:** The actual expected correct behavior for buggy inputs is defined in the
Correctness Properties section (Property 1). This section focuses on what must NOT
change.

## Hypothesized Root Cause

Root cause is settled in the RCA and is not re-derived. Summarized for design context:

1. **Two divergent pool-resolution code paths.** Validation resolves the pool via the
   registry keyed by `iss`; admin ops resolve it from `os.getenv("COGNITO_USER_POOL_ID")`.
   The two paths target different pools for the same user in any environment where the
   legacy var and the registry disagree (dev/test).

2. **Duplicated legacy reads.** At least 12 files independently read the legacy var
   (module-level constants and, in `cognito_service.py`, `self.user_pool_id`), so there
   is no single shared resolution point to fix — new admin code copies the nearest
   legacy example and the defect recurs.

3. **`PoolConfig` carries no `user_pool_id`.** The registry keys on `iss`; the pool id
   must be derived from the issuer URL. The absence of a first-class "pool id" accessor
   is part of why admin code reached for the flat env var instead of the registry.

4. **Anti-enumeration hid the mismatch.** The reset path returns success even when the
   user is absent from the target pool, so the wrong-pool write surfaced only as
   "reset succeeded but login still fails".

## Correctness Properties

Property 1: Bug Condition — Admin ops act on the target user's registry-resolved pool

_For any_ admin Cognito operation `X` where the bug condition holds (`isBugCondition(X)`
is true — the legacy var and the target user's registry pool diverge), the fixed code
SHALL resolve the target pool through the ONE shared registry-backed helper
(`resolve_pool_id`) keyed to the target user's pool, act on that registry-resolved pool
(not the pool `COGNITO_USER_POOL_ID` points at), and read no `COGNITO_USER_POOL_ID`
value directly in the admin path. In token mode the resolved pool SHALL match the pool
identified by the caller token's `iss` (consistent with validation); in email mode it
SHALL be the registered pool the user belongs to, chosen by the documented
disambiguation rule.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Property 2: Preservation — Non-buggy inputs unchanged

_For any_ admin operation `X` where the bug condition does NOT hold
(`isBugCondition(X)` is false — the legacy var already agrees with the target user's
registry pool, e.g. production with `COGNITO_POOL_KEYS=PROD_A`, or a registry-absent
single-pool deployment), the fixed code `F'(X)` SHALL produce exactly the same result
as the original code `F(X)`: same pool acted on, same Cognito actions, same
request/response contracts, and the same anti-enumeration behavior for forgot-password.
The token validation path SHALL remain byte-for-byte unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### New shared helper — `backend/src/auth/admin_pool_resolver.py`

A single module that all admin ops call to obtain the target `user_pool_id`. It is the
admin-side mirror of how `cognito_utils` resolves the validation pool, and it reuses
`load_pool_registry()` / `PoolRegistry` unchanged.

**Public surface (proposed):**

```
# --- pool-id derivation (shared) ---
FUNCTION pool_id_from_issuer(iss) -> str
  # iss = "https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
  # PoolConfig has no user_pool_id field; derive it from the issuer's last segment.
  RETURN iss.rstrip("/").rsplit("/", 1)[-1]
END FUNCTION

# --- registry access, mirroring cognito_utils selection order ---
FUNCTION _registry_or_none() -> PoolRegistry | None
  # Mirror cognito_utils._get_jwt_verifier step (1)/(2) EXACTLY:
  #   COGNITO_POOL_KEYS present & non-blank -> load_pool_registry()
  #     (PoolRegistryError -> raise PoolResolutionError, never a silent legacy read)
  #   else -> None  (registry absent -> caller uses legacy fallback)
END FUNCTION

# --- TOKEN MODE (2.3) ---
FUNCTION resolve_pool_id_for_token(jwt_token) -> str
  registry = _registry_or_none()
  IF registry is None:
      RETURN _legacy_pool_id_or_raise()          # 3.4 registry-absent fallback
  iss = verified_issuer(jwt_token)               # reuse the SAME verification as validation
  pool = registry.require(iss)                   # UnknownIssuerError -> reject
  RETURN pool_id_from_issuer(pool.iss)
END FUNCTION

# --- EMAIL MODE (2.5/2.6/2.7) ---
FUNCTION resolve_pool_id_for_email(email, *, anti_enumeration=False)
        -> str | None
  registry = _registry_or_none()
  IF registry is None:
      RETURN _legacy_pool_id_or_raise()          # 3.4 registry-absent fallback
  candidate_pool_ids = [pool_id_from_issuer(p.iss)
                        for p in registry.entries_in_declared_order()]
  hits = [pid for pid in candidate_pool_ids if admin_user_exists(pid, email)]
  IF len(hits) == 0:
      IF anti_enumeration: RETURN None           # 2.7 forgot-password: no signal
      RAISE UserPoolNotFoundError(email)         # 2.7 clear non-500 for not-found ops
  IF len(hits) > 1:
      RETURN disambiguate(hits, registry)        # 2.6 explicit rule, never silent first
  RETURN hits[0]
END FUNCTION
```

- `verified_issuer(jwt_token)` reuses the existing `JWTVerifier` (built over the same
  `load_pool_registry()`), so token mode resolves the pool from the SAME cryptographically
  verified `iss` that validation uses — no second, weaker code path (2.3, mirrors 3.1).
- `entries_in_declared_order()` is a small read-only accessor added to `PoolRegistry`
  that returns the `PoolConfig` entries in `COGNITO_POOL_KEYS` declaration order. This
  is additive and does not change any existing `PoolRegistry` behavior used by
  validation (get/require/issuers are untouched).
- `admin_user_exists(pool_id, email)` performs `admin_get_user` and returns
  `True`/`False` (`UserNotFoundException` → `False`), never leaking the result to a
  caller.

### Email-mode mechanism — recommendation and justification (2.5)

**Recommended: probe `admin_get_user` across registered pools in declared order.**

Considered alternatives:
- **(A) Probe across registered pools in declared order, first-consistent hit.**
  Zero new persistent state, always consistent with the registry (the single source of
  truth), and requires no backfill for existing users. Cost is up to N `admin_get_user`
  calls (N = number of registered pools: 1 in prod today, 2 in dev). N is tiny and
  bounded by config.
- **(B) A stored `user → pool` mapping (new table).** Needs a migration, a backfill of
  every existing Cognito user, and a write on every user create/delete/move to stay in
  sync — a second source of truth that can drift from the registry and reintroduces
  exactly the "two divergent paths" failure mode this bug is about.

**Recommendation: (A).** It is minimal, has no drift surface, and is naturally
forward-compatible: adding PROD_B is a config change (append the key to
`COGNITO_POOL_KEYS`) and the probe automatically includes it — no code change (2.2).
For the anti-enumeration constraint, the probe result is never surfaced to the caller
in the forgot-password path (`anti_enumeration=True` returns `None`, and the endpoint
still reports success), so probing does not create an enumeration oracle. When PROD_B
arrives with its own product rules (e.g. email uniqueness across pools, or per-pool
reset UX), the disambiguation rule below is the single place that decision is encoded
(RCA R4 forward-compatibility) — the mechanism itself does not need to change.

### Disambiguation rule when an email exists in more than one pool (2.6)

`disambiguate(hits, registry)` applies an **explicit, documented** rule — never a
silent first-match:

1. **Token context wins when available.** If the operation also carries a caller token
   (e.g. an authenticated admin acting on a user), and the token's registry pool is
   among `hits`, resolve to that pool. This keeps admin ops consistent with the pool
   the caller is authenticated against.
2. **Otherwise, ambiguity is an error, not a guess.** For tokenless ops
   (forgot-password, tokenless lookups) where more than one registered pool contains
   the email and there is no token to disambiguate, the resolver RAISES
   `AmbiguousUserPoolError(email, hits)` rather than picking the first. Callers map it
   as follows:
   - **forgot-password (anti-enumeration):** treat as the "cannot safely act" case —
     the endpoint still returns success without acting or revealing anything (3.5,
     2.7). It does not silently reset a password in an arbitrary pool.
   - **not-found-surfacing ops:** return a clear, non-500 error (HTTP 409 Conflict —
     "account exists in multiple pools; contact an administrator") (2.7).

Today (single prod pool, or TEST+PROD with distinct user sets) `len(hits) > 1` does not
occur; the rule exists so the multi-pool PROD_B future is handled deterministically and
is documented up front.

### Not-found handling (2.7)

- **Ops that already surface not-found** (admin user lookup by email, tenant-admin
  user management, enable/disable/delete by email): `resolve_pool_id_for_email` raises
  `UserPoolNotFoundError`, which the route maps to a clear non-500 (HTTP 404) — never a
  500 and never an accidental action on the legacy/prod pool.
- **forgot-password (anti-enumeration preserved):** the endpoint calls
  `resolve_pool_id_for_email(email, anti_enumeration=True)`. `None` (not found in any
  pool) is handled exactly like today's `UserNotFoundException` branch: log internally
  and return the same success message. The account's existence is never revealed
  (3.5).

### Registry-absent fallback (3.4)

`_legacy_pool_id_or_raise()` returns `os.getenv("COGNITO_USER_POOL_ID")` **only** when
`_registry_or_none()` returned `None` (i.e. `COGNITO_POOL_KEYS` is absent/blank),
mirroring `cognito_utils._get_jwt_verifier` step (2) exactly. The legacy var is:
- **never** consulted when the registry is present (registry-first, not legacy-first);
- used **only** as the registry-absent fallback;
- if it too is unset in that fallback, raise `PoolResolutionError` (no silent
  wrong-pool action — consistent with the "no dangerous fallbacks" guardrail the
  validation path uses).

### Migration of the 12 admin-op files (R2 consolidation, 3.3)

Each file replaces its direct legacy read with a call to the helper, resolving in token
mode when the request carries an authenticated caller token and in email mode when the
op starts from an email. **Every request/response contract is preserved** — only the
value passed as `UserPoolId=...` changes from a module constant to a helper result.

| File | Current legacy read | Migration |
|---|---|---|
| `services/cognito_service.py` | `self.user_pool_id = os.getenv("COGNITO_USER_POOL_ID")` in `__init__`, used by ~12 `admin_*`/group calls as `UserPoolId=self.user_pool_id` | Stop resolving in `__init__`. Add a `user_pool_id` parameter to the service entry points (or a per-call resolver hook) so callers pass the helper-resolved pool id; internally every `UserPoolId=self.user_pool_id` becomes `UserPoolId=<resolved pool id>`. Method signatures/return shapes unchanged. |
| `routes/auth_routes.py` | module `USER_POOL_ID`; `admin_get_user`, `admin_set_user_password` | forgot-password / confirm-reset resolve via `resolve_pool_id_for_email(email, anti_enumeration=True)`; use the result as `UserPoolId`. Preserve anti-enumeration success responses. |
| `tenant_admin_routes.py` | module `USER_POOL_ID`; `admin_list_groups_for_user` | token mode from the authenticated caller token; email mode where the op is by email. |
| `admin_routes.py` | module `USER_POOL_ID`; list/create/enable/disable/delete user, groups, attribute updates | token mode (admin-authenticated routes carry a token); replace the `USER_POOL_ID not configured` 500 guard with the helper's `PoolResolutionError` mapping. |
| `services/user_language_service.py` | `os.getenv("COGNITO_USER_POOL_ID")` in get/set | resolve per target user (token mode if a token is in scope, else email mode); preserve the current `"nl"` default / `False` return contracts on failure. |
| `services/signup_service.py` | `os.getenv("SIGNUP_COGNITO_USER_POOL_ID", os.getenv("COGNITO_USER_POOL_ID"))` | Preserve the explicit `SIGNUP_COGNITO_USER_POOL_ID` override when set (dedicated signup pool). When it is unset, replace the `os.getenv("COGNITO_USER_POOL_ID")` fallback with the helper (email mode for the self-service email), so signup targets the registry pool instead of the flat prod var. |
| `routes/sysadmin_provisioning.py` | `os.getenv("SIGNUP_COGNITO_USER_POOL_ID", os.getenv("COGNITO_USER_POOL_ID"))` | Same as signup_service: keep the `SIGNUP_COGNITO_USER_POOL_ID` override; replace the legacy fallback with the helper. |
| `routes/sysadmin_health.py` | module `USER_POOL_ID`; health/diagnostics reads | token mode (sysadmin routes carry a token). Diagnostics that report "configured pool" report the resolved pool. |
| `routes/tenant_admin_users.py` | module `USER_POOL_ID`; user management | token mode from the caller token; email mode for by-email lookups. |
| `routes/tenant_admin_email.py` | two `os.getenv("COGNITO_USER_POOL_ID")` sites; `admin_get_user`, password set | email mode for the user-lookup site; token or email mode for the password-set site. Preserve response shapes. |
| `routes/sysadmin_helpers.py` | module `USER_POOL_ID`; helper admin ops | token mode from the caller token. |
| `routes/sysadmin_roles.py` | module `USER_POOL_ID`; role/group admin ops | token mode from the caller token. |

**Two `SIGNUP_COGNITO_USER_POOL_ID` sites** (`signup_service.py`,
`sysadmin_provisioning.py`): the `SIGNUP_COGNITO_USER_POOL_ID` **override is preserved**
(it names an explicit dedicated signup pool). Only the *fallback* — the nested
`os.getenv("COGNITO_USER_POOL_ID")` — is replaced by the helper, so an unset override
resolves via the registry rather than the flat prod var.

**Re-run the sweep at fix time.** The requirements list is the authoritative migration
surface; a fresh `grep -rn "COGNITO_USER_POOL_ID" backend/src` is run at implementation
time to catch drift, and `auth/cognito_utils.py` is explicitly **excluded** (its read
is the validation fallback, not an admin op).

### Validation path and prod single-pool behavior untouched (3.1, 3.2)

- `auth/cognito_utils.py` and `auth/pool_registry.py` are **not modified** for
  resolution behavior (the only registry addition is the additive read-only
  `entries_in_declared_order()` accessor, which no validation code calls). Token
  validation continues to select the pool by `iss` exactly as today (3.1).
- In prod with `COGNITO_POOL_KEYS=PROD_A`, `resolve_pool_id_*` resolves to PROD_A =
  `eu-west-1_Hdp40eWmu` — the same pool the legacy var points at today — so every admin
  op acts on the identical pool (3.2). `isBugCondition` is false there, so F' ≡ F.

## Testing Strategy

Tests run under the Flask backend pytest per workspace steering:
`cd backend && source .venv/bin/activate && pytest ... ` with `TEST_MODE`/`testfinance`
where a DB is touched. Unit tests use the isolation fixtures (`mock_env`,
`mock_cognito`); no real Cognito or MySQL connection is opened. The registry is driven
by injecting env vars via `mock_env` / `patch.dict` and, where useful,
`load_pool_registry(environ=...)`.

### Validation Approach

Two phases: first surface counterexamples that demonstrate the bug on the UNFIXED code
(prove the wrong-pool resolution), then verify the fix resolves via the registry and
preserves every non-buggy behavior — framed as Bug-Condition / Fix / Preservation from
requirements.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples demonstrating the bug BEFORE the fix; confirm the
settled root cause (admin ops resolve from the legacy var, not the registry). If a test
does not fail on unfixed code, re-examine the assumption for that op.

**Test Plan**: Configure the registry for the TEST pool (`COGNITO_POOL_KEYS=TEST`,
`TEST_COGNITO_*` set) while `COGNITO_USER_POOL_ID` points at PROD — the dev-container
split. Assert which pool id each admin op passes as `UserPoolId=...` (via a mocked
`cognito-idp` client capturing kwargs).

**Test Cases**:
1. **forgot-password targets wrong pool** — assert `admin_get_user`/
   `admin_set_user_password` are called with the PROD pool id on unfixed code (will
   fail against the desired TEST-pool expectation).
2. **create_user targets wrong pool** — `admin_create_user` called with PROD id.
3. **group add targets wrong pool** — `admin_add_user_to_group` called with PROD id.
4. **preferred-language read targets wrong pool** — `admin_get_user` called with PROD
   id.

**Expected Counterexamples**: each admin op passes `UserPoolId = <PROD>` while the
registry (TEST) says the user's pool is `<TEST>` — i.e. `poolFrom(legacy) ≠
registryPoolFor(user)`.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed helper resolves — and
each admin op acts on — the target user's registry-resolved pool, with no direct legacy
read.

**Pseudocode:**
```
FOR ALL X WHERE isBugCondition(X) DO
  targetPool := resolve_pool_id(X.targetUser)        // the ONE shared helper
  result := F'(X) using targetPool
  ASSERT actedOnPool(result) = registryPoolFor(X.targetUser)
  ASSERT reads_COGNITO_USER_POOL_ID(F') = FALSE
END FOR
```

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed code produces
the same result as the original.

**Pseudocode:**
```
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation because it
generates many op/pool/user combinations automatically, catches edge cases manual tests
miss, and gives strong guarantees that behavior is unchanged across the non-buggy input
domain (prod single-pool, registry-absent single-pool). Observe behavior on the UNFIXED
code first (prod-equivalent config: legacy var == PROD_A == registry pool), then assert
F' matches.

**Test Plan / Test Cases**:
1. **Prod single-pool preservation** — with `COGNITO_POOL_KEYS=PROD_A` and legacy var =
   PROD_A, every migrated op passes the SAME pool id after the fix as before (per-file).
2. **Registry-absent fallback preservation** — with `COGNITO_POOL_KEYS` unset and legacy
   var set, the helper returns the legacy var and ops act on the same pool as today.
3. **Contract preservation** — each migrated route/service returns the same
   status/response shape for success and error paths.
4. **Anti-enumeration preservation** — forgot-password returns the same success message
   for existent, non-existent, and absent-in-all-pools emails.

### Unit Tests

Resolver (`auth/admin_pool_resolver.py`):
- `pool_id_from_issuer` extracts the trailing segment from a Cognito issuer URL.
- **Token mode**: verified `iss` → correct pool id; unknown issuer → reject
  (`UnknownIssuerError` surfaced as the resolver's error).
- **Email mode**: single-pool hit → that pool id; found in none →
  `UserPoolNotFoundError` (or `None` when `anti_enumeration=True`).
- **Multi-pool disambiguation (2.6)**: email in >1 pool with a caller token whose pool
  is among hits → that pool; tokenless multi-hit → `AmbiguousUserPoolError` (never
  first-match); forgot-password multi-hit → success without acting.
- **Not-found (2.7)**: not-found-surfacing op → non-500; forgot-password → success.
- **Registry-absent fallback (3.4)**: `COGNITO_POOL_KEYS` unset → returns legacy var;
  legacy var also unset → `PoolResolutionError`. Registry present → legacy var never
  read.

### Property-Based Tests

- Generate registry configurations (1..N pools, declared order) and target users;
  assert token mode always returns the pool for the token's `iss`.
- Generate non-buggy inputs (legacy var == registry pool) and assert `F(X) == F'(X)`
  for pool id and response shape (preservation).
- Generate email-mode inputs across pool memberships and assert the disambiguation rule
  is deterministic (no first-match) and anti-enumeration holds for forgot-password.

### Integration Tests

- Full forgot-password → confirm-reset flow in a TEST-pool-configured registry resolves
  to the TEST pool end to end (mocked Cognito), and preserves anti-enumeration.
- Per-file preservation: with prod-equivalent config (`COGNITO_POOL_KEYS=PROD_A`), each
  migrated admin route acts on PROD_A and returns unchanged contracts.
- Registry-absent single-pool run: admin ops act on the legacy-var pool exactly as
  before the fix.

## Requirements Traceability

| Requirement | Summary | Design section(s) |
|---|---|---|
| 1.1 | Admin ops resolve pool from `COGNITO_USER_POOL_ID` regardless of env/user | Overview; Bug Details → Bug Condition; Hypothesized Root Cause (1,2) |
| 1.2 | Dev/test: admin acts on PROD while validation acts on TEST | Bug Details → Examples; Exploratory Bug Condition Checking |
| 1.3 | "Reset succeeded but login fails" misleading outcome | Bug Details → Examples; Hypothesized Root Cause (4) |
| 1.4 | Duplicated legacy reads across ≥12 files, no shared path | Hypothesized Root Cause (2); Fix Implementation → Migration table |
| 2.1 | Resolve target pool via registry, keyed to target user | Fix Implementation → New shared helper; Correctness Property 1 |
| 2.2 | Correct in TEST/PROD_A and future PROD_B without code change | Fix Implementation → email-mode recommendation; Validation-untouched (3.2); Correctness Property 1 |
| 2.3 | Token-start ops resolve to the token issuer's pool | Fix Implementation → `resolve_pool_id_for_token` (token mode); Correctness Property 1 |
| 2.4 | Exactly ONE shared helper; no admin path reads legacy var directly | Overview; Fix Implementation → New shared helper + Migration table; Fix Checking |
| 2.5 | Email-start ops resolve pool via a deterministic rule | Fix Implementation → email-mode mechanism recommendation; Correctness Property 1 |
| 2.6 | Explicit disambiguation when email in >1 pool; no silent first-match | Fix Implementation → Disambiguation rule; Unit + PBT (disambiguation) |
| 2.7 | Not-found: clear non-500; forgot-password preserves anti-enumeration | Fix Implementation → Not-found handling; Preservation/Unit tests |
| 3.1 | Token validation path unchanged | Fix Implementation → Validation path untouched; Correctness Property 2 |
| 3.2 | Prod single-pool (`PROD_A`) admin behavior preserved | Fix Implementation → Validation-untouched (3.2); Preservation Checking |
| 3.3 | Same Cognito actions and request/response contracts | Fix Implementation → Migration table; Preservation/Integration tests; Correctness Property 2 |
| 3.4 | Registry-absent legacy fallback, mirroring validation; never legacy-first | Fix Implementation → Registry-absent fallback; Unit tests (fallback) |
| 3.5 | Forgot-password returns success for non-existent/absent user | Fix Implementation → Not-found handling; Anti-enumeration preservation tests |
