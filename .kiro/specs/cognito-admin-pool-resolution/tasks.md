# Implementation Plan

## Overview

This plan fixes the Cognito admin-pool split-brain by introducing one shared,
registry-backed pool-resolution helper (`backend/src/auth/admin_pool_resolver.py`) and
migrating the 12 admin-op files off their direct `COGNITO_USER_POOL_ID` reads onto that
helper, exactly as specified in `design.md`. The root cause is settled in the RCA and
is **not** re-derived here.

The plan follows the exploratory bugfix order strictly:

1. **Exploration / Bug-Condition tests** (Property 1) — written FIRST and expected to
   **FAIL on unfixed code**, surfacing counterexamples that prove `poolFrom(legacy) ≠
   registryPoolFor(user)` for representative admin ops (Refs 1.1–1.4).
2. **Preservation tests** (Property 2) — written next and expected to **PASS on unfixed
   code**, capturing the non-buggy behavior that must survive the fix (Refs 3.1–3.5).
3. **Implementation** — the shared helper, the additive `PoolRegistry` accessor, and
   the per-file migration of all 12 admin-op files (Refs 2.1–2.7, 3.3, 3.4).
4. **Fix-checking + Preservation re-run** — re-run the Property 1 tests (now PASS) and
   the Property 2 tests (still PASS).
5. **Final checkpoint** — full backend pytest green and a fresh grep confirming no
   admin-op file reads `COGNITO_USER_POOL_ID` directly (`cognito_utils.py` validation
   fallback excluded).

**Test execution (workspace steering):**
`cd backend && source .venv/bin/activate && pytest ...`. Unit/PBT tests use the
isolation fixtures (`mock_env`, `mock_cognito`) — no real Cognito or MySQL. Use
`TEST_MODE=true` / `testfinance` only where a task actually touches a DB. Judge success
from pytest output only; do NOT use diagnostics tooling.

**Registry configs used by tests:**
- **Buggy (dev-container split):** `COGNITO_POOL_KEYS=TEST`, `TEST_COGNITO_*` set,
  `COGNITO_USER_POOL_ID=eu-west-1_Hdp40eWmu` (PROD). Here `poolFrom(legacy)=PROD` but
  `registryPoolFor(user)=TEST` → `isBugCondition` TRUE.
- **Non-buggy prod single-pool:** `COGNITO_POOL_KEYS=PROD_A`, legacy var == PROD_A ==
  `eu-west-1_Hdp40eWmu` → `isBugCondition` FALSE.
- **Registry-absent fallback:** `COGNITO_POOL_KEYS` unset, legacy var set → helper
  falls back to the legacy var.

## Task Dependency Graph

Tasks 1 and 2 (exploration + preservation, both against UNFIXED code) are independent
and form wave 1. Task 3 (implementation) depends on both. Task 3.1 (helper) and 3.2
(registry accessor) precede the per-file migrations (3.3.*), which are mutually
independent and can proceed in parallel once the helper exists. Fix-checking (4) and
preservation re-run (5) depend on the migration being complete; the final checkpoint
(6) depends on everything.

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write exploration (fail) and preservation (pass) tests against UNFIXED code."
    },
    {
      "wave": 2,
      "tasks": ["3.1", "3.2"],
      "description": "Build the shared resolver and the additive PoolRegistry accessor."
    },
    {
      "wave": 3,
      "tasks": ["3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5", "3.3.6", "3.3.7", "3.3.8", "3.3.9", "3.3.10", "3.3.11", "3.3.12"],
      "description": "Migrate the 12 admin-op files onto the helper (independent, parallelizable)."
    },
    {
      "wave": 4,
      "tasks": ["4", "5"],
      "description": "Fix-checking (Property 1 now passes) and preservation re-run (Property 2 still passes)."
    },
    {
      "wave": 5,
      "tasks": ["6"],
      "description": "Final checkpoint: full pytest green + fresh grep confirms no direct legacy reads in admin paths."
    }
  ]
}
```

## Tasks

- [x] 1. Write bug-condition exploration tests (BEFORE implementing the fix)
  - **Property 1: Bug Condition** - Admin ops target the wrong (legacy/PROD) pool under the dev-container split
  - **CRITICAL**: These tests MUST FAIL on unfixed code — failure confirms the bug exists.
  - **DO NOT attempt to fix the tests or the code when they fail.**
  - **NOTE**: These tests encode the expected behavior — they will validate the fix when they pass after implementation.
  - **GOAL**: Surface counterexamples demonstrating `poolFrom(legacy) ≠ registryPoolFor(user)`.
  - **Scoped PBT approach**: the bug is deterministic, so scope the property to the concrete failing config — registry configured for TEST (`COGNITO_POOL_KEYS=TEST`, `TEST_COGNITO_*`) while `COGNITO_USER_POOL_ID` points at PROD (`eu-west-1_Hdp40eWmu`). Assert across representative admin ops.
  - Create `backend/tests/unit/test_admin_pool_resolution_bug.py` using `mock_env` + `mock_cognito`, with a mocked `cognito-idp` client that captures the `UserPoolId=...` kwarg passed to each admin call.
  - Case 1 — **forgot-password** targets wrong pool: drive the password-reset path; assert `admin_get_user` / `admin_set_user_password` are invoked with `UserPoolId = <TEST pool id>` (`eu-west-1_xyrlzfqbl`). On unfixed code they use the PROD id → test FAILS.
  - Case 2 — **create_user** targets wrong pool: drive user creation; assert `admin_create_user` is called with the TEST pool id. On unfixed code it uses PROD → FAILS.
  - Case 3 — **group add** targets wrong pool: drive `admin_add_user_to_group`; assert it is called with the TEST pool id. On unfixed code it uses PROD → FAILS.
  - Case 4 — **preferred-language read** targets wrong pool: drive `user_language_service` get; assert `admin_get_user` is called with the TEST pool id. On unfixed code it uses PROD → FAILS.
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_admin_pool_resolution_bug.py -v`
  - **EXPECTED OUTCOME**: All four cases FAIL on unfixed code (they observe `UserPoolId = <PROD>` while asserting `<TEST>`).
  - Document each counterexample (e.g. "forgot-password called admin_get_user with eu-west-1_Hdp40eWmu; expected eu-west-1_xyrlzfqbl").
  - Mark complete when the tests are written, run, and the failures are documented.
  - _Bug_Condition: isBugCondition(X) = poolFrom(COGNITO_USER_POOL_ID) <> registryPoolFor(X.targetUser)_
  - _Expected_Behavior: each admin op passes UserPoolId = registryPoolFor(targetUser)_
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing the fix)
  - **Property 2: Preservation** - Non-buggy inputs (prod single-pool, registry-absent, contracts, anti-enumeration) unchanged
  - **IMPORTANT**: Follow the observation-first methodology — run the UNFIXED code first, record the actual outputs, then assert them.
  - Property-based testing is recommended: generate op/pool/user combinations and assert `F(X) == F'(X)` for pool id and response shape across the non-buggy domain.
  - Create `backend/tests/unit/test_admin_pool_resolution_preservation.py` using `mock_env` + `mock_cognito`.
  - **Observe (prod single-pool):** with `COGNITO_POOL_KEYS=PROD_A` and legacy var == PROD_A (`eu-west-1_Hdp40eWmu`), record the `UserPoolId` each representative op passes on unfixed code (it is PROD_A). Write a property asserting every op passes that SAME pool id (3.2). _Refs 3.1, 3.2._
  - **Observe (registry-absent fallback):** with `COGNITO_POOL_KEYS` unset and `COGNITO_USER_POOL_ID` set, record that ops act on the legacy-var pool. Write a property asserting the resolved pool equals the legacy var, mirroring the validation fallback (3.4). _Refs 3.4._
  - **Response-contract preservation:** for each representative migrated route/service, record the success and error status/response shape on unfixed code (prod-equivalent config) and assert they are unchanged (3.3). _Refs 3.3._
  - **Forgot-password anti-enumeration:** record that forgot-password returns the same success message for existent, non-existent, and absent-in-all-pools emails on unfixed code; assert that response is unchanged (3.5). _Refs 3.5._
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_admin_pool_resolution_preservation.py -v`
  - **EXPECTED OUTCOME**: All preservation tests PASS on unfixed code (this is the baseline to preserve).
  - Mark complete when the tests are written, run, and passing on unfixed code.
  - _Preservation: For all X where NOT isBugCondition(X), F(X) = F'(X) — same pool, same actions, same contracts, same anti-enumeration_
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix the admin-pool split-brain via one shared registry-backed helper

  - [x] 3.1 Implement the shared resolver `backend/src/auth/admin_pool_resolver.py`
    - Add `pool_id_from_issuer(iss) -> str`: return the trailing path segment of the issuer URL (`iss.rstrip("/").rsplit("/", 1)[-1]`), since `PoolConfig` has no `user_pool_id` field.
    - Add `_registry_or_none() -> PoolRegistry | None`: mirror `cognito_utils` selection order EXACTLY — if `COGNITO_POOL_KEYS` is present and non-blank, `load_pool_registry()` (a `PoolRegistryError` surfaces as `PoolResolutionError`, never a silent legacy read); otherwise return `None`.
    - Add `resolve_pool_id_for_token(jwt_token) -> str` (token mode): if registry is `None`, return `_legacy_pool_id_or_raise()`; else resolve the verified `iss` reusing the SAME `JWTVerifier`/verification as validation, `registry.require(iss)`, and return `pool_id_from_issuer(pool.iss)`.
    - Add `resolve_pool_id_for_email(email, *, anti_enumeration=False) -> str | None` (email mode): if registry is `None`, return `_legacy_pool_id_or_raise()`; else probe `admin_get_user` across `entries_in_declared_order()` pool ids; 0 hits → `None` when `anti_enumeration` else raise `UserPoolNotFoundError`; >1 hits → `disambiguate(hits, registry)`; else return the single hit.
    - Implement `disambiguate(hits, registry)` per design: token context wins when the caller token's registry pool is among `hits`; otherwise raise `AmbiguousUserPoolError(email, hits)` — never a silent first-match.
    - Implement `_legacy_pool_id_or_raise()`: return `os.getenv("COGNITO_USER_POOL_ID")` ONLY in the registry-absent branch; if unset there, raise `PoolResolutionError`.
    - Add `admin_user_exists(pool_id, email)` helper (`admin_get_user`; `UserNotFoundException` → `False`), never leaking the result to callers.
    - Define errors `UserPoolNotFoundError`, `AmbiguousUserPoolError`, `PoolResolutionError`.
    - Add unit tests in `backend/tests/unit/test_admin_pool_resolver.py` covering: `pool_id_from_issuer`; token mode (known iss → pool id; unknown issuer → reject); email mode (single hit; none → `UserPoolNotFoundError`/`None` under anti-enumeration); disambiguation (token-in-hits → that pool; tokenless multi-hit → `AmbiguousUserPoolError`); not-found (non-500 vs forgot-password success); registry-absent fallback (returns legacy var; unset → `PoolResolutionError`; registry present → legacy var never read).
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_admin_pool_resolver.py -v`
    - _Bug_Condition: isBugCondition(X) = poolFrom(COGNITO_USER_POOL_ID) <> registryPoolFor(X.targetUser)_
    - _Expected_Behavior: resolve target pool via registry keyed to target user (token mode by verified iss; email mode by declared-order probe + disambiguation); read no legacy var when registry present_
    - _Preservation: registry-absent fallback mirrors cognito_utils step (2); validation path untouched_
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 3.4_

  - [x] 3.2 Add the additive read-only `PoolRegistry.entries_in_declared_order()` accessor
    - In `backend/src/auth/pool_registry.py`, add a read-only method returning the `PoolConfig` entries in `COGNITO_POOL_KEYS` declaration order.
    - This is additive only: existing `get`/`require`/`issuers` behavior used by validation is untouched, and no validation code calls the new accessor.
    - Add/extend a unit test asserting declared-order return for a multi-key config.
    - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/ -k pool_registry -v`
    - _Preservation: existing PoolRegistry behavior and the validation path remain byte-for-byte unchanged (3.1)_
    - _Requirements: 2.1, 2.5, 3.1_

  - [x] 3.3 Migrate the 12 admin-op files onto the helper (per the design migration table)
    - **BEFORE migrating**, re-run `grep -rn "COGNITO_USER_POOL_ID" backend/src` to catch drift; the requirements blast-radius list is authoritative. **Exclude `backend/src/auth/cognito_utils.py`** (its read is the validation fallback, not an admin op).
    - For every file: replace the direct legacy read with a helper call — token mode when the request carries an authenticated caller token, email mode when the op starts from an email. Only the value passed as `UserPoolId=...` changes; preserve every request/response contract.

    - [x] 3.3.1 Migrate `backend/src/services/cognito_service.py`
      - Stop resolving the pool in `__init__` (`self.user_pool_id = os.getenv(...)`).
      - Add a `user_pool_id` parameter to the service entry points (or a per-call resolver hook) so callers pass the helper-resolved pool id; internally every `UserPoolId=self.user_pool_id` becomes `UserPoolId=<resolved pool id>`. Method signatures' return shapes unchanged.
      - _Bug_Condition: create/get/update/delete user, group add/remove, list, attribute ops previously used the legacy PROD var_
      - _Expected_Behavior: each admin_* / group call uses the registry-resolved pool id passed in by the caller_
      - _Preservation: same Cognito actions and return shapes (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 3.3_

    - [x] 3.3.2 Migrate `backend/src/routes/auth_routes.py` (forgot-password / confirm-reset)
      - Resolve via `resolve_pool_id_for_email(email, anti_enumeration=True)`; use the result as `UserPoolId` for `admin_get_user` / `admin_set_user_password`.
      - Preserve the anti-enumeration success responses; `None` (not found in any pool) is handled exactly like today's `UserNotFoundException` branch.
      - _Bug_Condition: password reset acted on the legacy PROD pool_
      - _Expected_Behavior: reset acts on the target user's registry-resolved pool (email mode)_
      - _Preservation: forgot-password returns the same success message for existent/non-existent/absent users (2.7, 3.5)_
      - _Requirements: 2.1, 2.4, 2.5, 2.7, 3.3, 3.5_

    - [x] 3.3.3 Migrate `backend/src/tenant_admin_routes.py` (`admin_list_groups_for_user`)
      - Token mode from the authenticated caller token; email mode where the op is by email.
      - _Bug_Condition: group listing used the legacy PROD var_
      - _Expected_Behavior: resolves the target user's registry pool_
      - _Preservation: same response contract (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 3.3_

    - [x] 3.3.4 Migrate `backend/src/admin_routes.py` (list/create/enable/disable/delete user, groups, attribute updates)
      - Token mode (admin-authenticated routes carry a token). Replace the `USER_POOL_ID not configured` 500 guard with the helper's `PoolResolutionError` mapping.
      - _Bug_Condition: all these admin ops used the legacy PROD var_
      - _Expected_Behavior: each op acts on the caller-token's registry pool_
      - _Preservation: same actions and contracts; error mapping is non-500 where appropriate (2.7, 3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 2.7, 3.3_

    - [x] 3.3.5 Migrate `backend/src/services/user_language_service.py` (get/set `custom:preferred_language`)
      - Resolve per target user (token mode if a token is in scope, else email mode).
      - Preserve the current `"nl"` default / `False` return contracts on failure.
      - _Bug_Condition: preferred-language read/write used the legacy PROD var_
      - _Expected_Behavior: acts on the target user's registry pool_
      - _Preservation: `"nl"` default and `False`-on-failure contracts unchanged (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 3.3_

    - [x] 3.3.6 Migrate `backend/src/services/signup_service.py`
      - Preserve the explicit `SIGNUP_COGNITO_USER_POOL_ID` override when set. When it is unset, replace ONLY the `os.getenv("COGNITO_USER_POOL_ID")` fallback with the helper (email mode for the self-service email).
      - _Bug_Condition: unset-override signup fell back to the legacy PROD var_
      - _Expected_Behavior: unset override resolves via the registry (email mode)_
      - _Preservation: SIGNUP_COGNITO_USER_POOL_ID override behavior and signup contract unchanged (3.3)_
      - _Requirements: 2.1, 2.4, 2.5, 3.3_

    - [x] 3.3.7 Migrate `backend/src/routes/sysadmin_provisioning.py`
      - Same as signup_service: keep the `SIGNUP_COGNITO_USER_POOL_ID` override; replace only the legacy fallback with the helper.
      - _Bug_Condition: unset-override provisioning fell back to the legacy PROD var_
      - _Expected_Behavior: unset override resolves via the registry_
      - _Preservation: override behavior and provisioning contract unchanged (3.3)_
      - _Requirements: 2.1, 2.4, 2.5, 3.3_

    - [x] 3.3.8 Migrate `backend/src/routes/sysadmin_health.py` (health/diagnostics admin reads)
      - Token mode (sysadmin routes carry a token). Diagnostics that report "configured pool" report the resolved pool.
      - _Bug_Condition: health/diagnostics reported/used the legacy PROD var_
      - _Expected_Behavior: reports/acts on the caller-token's registry pool_
      - _Preservation: same diagnostics response shape (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 3.3_

    - [x] 3.3.9 Migrate `backend/src/routes/tenant_admin_users.py` (user management)
      - Token mode from the caller token; email mode for by-email lookups.
      - _Bug_Condition: tenant admin user management used the legacy PROD var_
      - _Expected_Behavior: acts on the target user's registry pool_
      - _Preservation: same contracts (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 2.5, 3.3_

    - [x] 3.3.10 Migrate `backend/src/routes/tenant_admin_email.py` (two legacy sites)
      - Email mode for the user-lookup site; token or email mode for the password-set site. Preserve response shapes.
      - _Bug_Condition: both sites used the legacy PROD var_
      - _Expected_Behavior: both act on the target user's registry pool_
      - _Preservation: same response shapes (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 2.5, 3.3_

    - [x] 3.3.11 Migrate `backend/src/routes/sysadmin_helpers.py` (helper admin ops)
      - Token mode from the caller token.
      - _Bug_Condition: helper admin ops used the legacy PROD var_
      - _Expected_Behavior: act on the caller-token's registry pool_
      - _Preservation: same contracts (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 3.3_

    - [x] 3.3.12 Migrate `backend/src/routes/sysadmin_roles.py` (role/group admin ops)
      - Token mode from the caller token.
      - _Bug_Condition: role/group admin ops used the legacy PROD var_
      - _Expected_Behavior: act on the caller-token's registry pool_
      - _Preservation: same contracts (3.3)_
      - _Requirements: 2.1, 2.3, 2.4, 3.3_

- [x] 4. Verify bug-condition exploration tests now pass (fix-checking)
  - **Property 1: Expected Behavior** - Admin ops act on the target user's registry-resolved pool
  - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests.
  - The tests from task 1 encode the expected behavior; passing them confirms the bug is fixed.
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_admin_pool_resolution_bug.py -v`
  - **EXPECTED OUTCOME**: All four cases PASS — each op now passes the TEST pool id (registry-resolved), and no admin path reads `COGNITO_USER_POOL_ID` directly.
  - _Expected_Behavior: FOR ALL X WHERE isBugCondition(X): actedOnPool(F'(X)) = registryPoolFor(X.targetUser) AND reads_COGNITO_USER_POOL_ID(F') = FALSE_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 5. Verify preservation tests still pass (no regressions)
  - **Property 2: Preservation** - Non-buggy inputs unchanged after the fix
  - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests.
  - Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_admin_pool_resolution_preservation.py -v`
  - **EXPECTED OUTCOME**: All preservation tests still PASS — prod single-pool acts on PROD_A, registry-absent falls back to the legacy var, contracts and anti-enumeration are unchanged.
  - _Preservation: FOR ALL X WHERE NOT isBugCondition(X): F(X) = F'(X)_
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 6. Checkpoint - full backend suite green and no direct legacy reads in admin paths
  - Run the full backend suite: `cd backend && source .venv/bin/activate && pytest` (use `TEST_MODE=true` / `testfinance` for any DB-touching tests per steering). Confirm green.
  - Run a fresh sweep: `grep -rn "COGNITO_USER_POOL_ID" backend/src` and confirm no admin-op file reads it directly — the ONLY remaining read is `backend/src/auth/cognito_utils.py` (validation fallback, intentionally preserved).
  - Do NOT use diagnostics tooling; judge success from pytest output and grep output only.
  - Ensure all tests pass; ask the user if questions arise.
  - _Requirements: 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

## Notes

- **Bugfix ordering is load-bearing.** Task 1 tests MUST fail on unfixed code and Task 2
  tests MUST pass on unfixed code before any implementation begins. Do not "fix" a
  failing Task 1 test — its failure is the proof the bug exists.
- **Validation path is untouched.** `auth/cognito_utils.py` and `auth/pool_registry.py`
  keep their resolution behavior; the only registry change is the additive read-only
  `entries_in_declared_order()` accessor (3.1).
- **Registry-first, never legacy-first.** The legacy `COGNITO_USER_POOL_ID` is consulted
  ONLY in the registry-absent branch, mirroring `cognito_utils` step (2) exactly (3.4).
- **Two `SIGNUP_COGNITO_USER_POOL_ID` sites** (3.3.6, 3.3.7) keep the override; only the
  nested legacy fallback is replaced.
- **`cognito_utils.py` is excluded** from the migration sweep — its read is the
  validation fallback, not an admin op.
- **Forward-compatibility:** adding a future `PROD_B` is a config change
  (`COGNITO_POOL_KEYS`), not code; the declared-order probe and disambiguation rule
  already handle N pools deterministically (2.2, 2.6).
- **Test isolation:** unit/PBT tests use `mock_env` + `mock_cognito`; no real Cognito or
  MySQL. Drive the registry via `patch.dict` / `load_pool_registry(environ=...)`.
