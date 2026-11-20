# Tasks — Fail-loud fallback remediation

**Location**: `.kiro/specs/Common/Frameworks/fallback-patterns/`
**Status**: Draft
**Related**: `requirements.md`, `design.md`, `deliverable-1-audit-table.md`

## Progress tracking convention
- `- [ ]` — not started
- `- [x]` / `- ✅` — completed
- `- ❌` — blocked or failed

## Phase 0 — Audit completion & groundwork (Deliverable #1)

Dependency: feeds every later phase.

- [x] Task 0.1 — Mark instance 2 verified (NOT PRESENT; fail-closed already) in audit table
- [x] Task 0.2 — Mark instance 8 verified (cross-plane env inconsistency; separate backlog spec)
- [x] Task 0.3 — Confirm audit table verdict column = SAFE/MASKING for all 8 instances
- [x] Task 0.4 — Add CI/CD gate reference (quality gates, branch→env, promote step) to audit notes

## Phase 1 — Stale-projection reconcile (Deliverable #2; security-first)

Depends on: Phase 0 (inventory complete)

- [x] Task 1.1 — Add `_list_role_sort_keys(administration)` to `ProjectionSync` (tenant-scoped query, `begins_with(sk,'role#')`)
- [x] Task 1.2 — Add `_reconcile_role_grants(administration, desired_items)` (diff-delete pattern from `_reconcile_scopegrants`)
- [x] Task 1.3 — Call reconcile after `build_projection_items` in `sync_administration`
- [x] Task 1.4 — Record decision on `module#*` inclusion (now or deferred) in design.md
- [x] Task 1.5 — Add regression test: role removed from MySQL `user_tenant_roles` leaves no lingering `role#` row (property test, in-memory fake)
- [x] Task 1.6 — Backend plane CI: property tests pass (in-memory fake; never touches AWS/MySQL)

## Phase 2 — Fail-loud on missing REQUIRED config (Deliverable #3)

Depends on: Phase 1 (reconcile precedent) — independent implementation path

- [x] Task 2.1 — Frontend plane: remove API-base-URL → localhost fallback; fail-fast at build/startup (PR #16 fixed; appEnv.ts fails fast on missing VITE_APP_ENV; no API-base-URL localhost fallback remains)
- [x] Task 2.2 — Backend plane: missing tenant selection → explicit error (deny-don't-default) (tenant_context.py:get_current_tenant no longer defaults multi-tenant users to tenants[0]; returns None → caller fails loud via validate_tenant_access 'No tenant specified')
- [x] Task 2.3 — Backend plane: missing entitlement → explicit error (entitlement_reader.py already token-preferred + DB fallback + fail-closed; no silent grant)
- [x] Task 2.4 — SAM plane: missing required config → explicit error at edge startup (sam/members/handler/authorization.py already 'NEVER default-to-first'; denies when verified token carries no usable tenant)
- [x] Task 2.5 — Frontend/Backend/SAM CI per plane (paired tests) (test_tenant_context.py: 28 passed incl. 2 new fail-loud tests; projection_sync.py: 134 passed; tenant_guard.py: 9 passed)

## Phase 3 — Single source of truth for roles (Deliverable #4)

Depends on: Phase 2 (fail-loud precedent)

- [x] Task 3.1 — Locate and open `getCurrentUserRoles()` backend implementation (no dedicated backend `getCurrentUserRoles`; backend `cognito_required` in cognito_utils.py already merges MySQL tenant roles into `/api/auth/me`)
- [x] Task 3.2 — Remove `cognito:groups` fallback branch; MySQL `/api/auth/me` authoritative (frontend getCurrentUserRoles: JWT cognito:groups fallback removed; API is single source of truth)
- [x] Task 3.3 — Add `RoleDivergenceError` + logging/alerting on divergence (role_cache.py: RoleDivergenceError exception defined; cognito_utils.py: DB failure raises RoleDivergenceError with error logging)
- [x] Task 3.4 — Update callers for explicit-error contract (backend cognito_required raises RoleDivergenceError on DB failure)
- [x] Task 3.5 — Frontend plane: update `getCurrentUserRoles()` consumer to handle explicit error (AuthContext.tsx: catches RoleDivergenceError in checkAuthState + refreshRolesForTenant)
- [x] Task 3.6 — Unit test: divergence throws `RoleDivergenceError` (never silent substitution)

## Phase 4 — Post-deploy pre-checks (Deliverable #5)

Depends on: Phase 3

- [x] Task 4.1 — Post-deploy step asserts required env vars / API URLs (scripts/post_deploy_pre_check.py checks VITE_API_URL, Cognito config, Members API URL)
- [x] Task 4.2 — Post-deploy step asserts projection freshness (scripts/post_deploy_pre_check.py queries GovernanceProjectionTable for projection_timestamp age < 24h)
- [x] Task 4.3 — Wire into `test` → TEST and `main` → PRODUCTION deploy paths (.github/workflows/deploy-sam-members.yml and deploy-frontend.yml both call post_deploy_pre_check.py)

## Phase 5 — Guard-rail lint (Deliverable #6)

Depends on: Phase 4 (catalogue stable)

- [x] Task 5.1 — Broaden s5f R4.3 grep guard into reusable lint (`scripts/fallback_lint.py`; Python comments+docstrings masked, TS/JS comments stripped — mirrors the s5f docstring exclusion)
- [x] Task 5.2 — Lint flags catalogued MASKING anti-patterns (all 8 instances) (rules MASK-01…MASK-08; guard-aware so legitimate `len(...) == 1` single-tenant returns do not fire; green on the remediated repo)
- [x] Task 5.3 — Run lint as CI PR quality gate (`.github/workflows/fallback-lint.yml` on PR/push to `main`; pytest self-test `backend/tests/unit/test_fallback_lint.py`)

## Phase 6 — Convergence steering rule (Deliverable #7)

Depends on: Phase 5

- [x] Task 6.1 — Record CONVERGENCE RULE as steering alongside `36-config-and-parameters.md` (C default / B un-configurable / never A) (added §The convergence rule to `.kiro/steering/36-config-and-parameters.md`)
- [x] Task 6.2 — Cite `services/storage_resolver.py::resolve_storage_provider` as proven template (cited as the (C) exemplar in that steering section)

## CI/CD checklist (per steering 40 — required on every spec)

- [x] CI/CD: quality gates named (per-PR CodeQL + GitGuardian; nightly Full Test Suite)
- [x] CI/CD: branch→env path named (`test` → TEST; `main` → PRODUCTION)
- [x] CI/CD: workflows triggered named (`deploy-sam-*`, `deploy-frontend` via `samconfig.toml` / OIDC)
- [x] CI/CD: promote `test` → `main` step named as production-release gate
- [x] CI/CD: any new/changed `samconfig.toml` / IAM-OIDC wiring is its own task if needed

## All-planes delivery (per steering 40)

For each task, confirm: planes touched listed; task per plane; paired tests per plane; admin UI checked for pre-change model.
