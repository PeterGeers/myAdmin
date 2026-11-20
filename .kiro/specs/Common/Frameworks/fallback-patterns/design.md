# Design — Fail-loud fallback remediation

**Location**: `.kiro/specs/Common/Frameworks/fallback-patterns/`
**Status**: Draft
**Related**: `requirements.md`, `tasks.md`, `deliverable-1-audit-table.md`

## Architecture overview

Three planes, one cross-cutting failure class (MASKING a missing input / stale derived data):

```text
Frontend SPA (React/TS)          Flask Backend (FastAPI)          SAM Edge (Lambda/Python)
├── VITE_MEMBERS_API_BASE_URL  ├── getCurrentUserRoles()        ├── PreTokenGen reads governance_projection
├── apiService fallback → localhost                     ├── tenant_context default-first
├── AuthContext (Amplify)      └── .env / AWS_PROFILE chain   └── TenantHookRegistry safe defaults
└── appEnv.ts fail-fast                                         └── build_projection_items()

        │ (1) build projection            │ (2) merge roles            │ (3) read projection for entitlements
        ▼                                ▼                            ▼
        DynamoDB governance_projection ──────► Cognito PreTokenGen ─────► Token claims / has_capability
```

Direction of truth:
- MySQL is the single source of record (tenant-scoped).
- SAM reads a one-directional projection (DynamoDB) via `ProjectionSync` (sole writer).
- Flask writes MySQL; SAM reads projection; Flask reads MySQL directly (auth).

## Deliverable designs

### D1 — Fallback inventory (deliverable #1)

Audit table = canonical decision artifact; nothing is blind-patched. Verified instances
(incl. the two newly verified findings below) are recorded in `deliverable-1-audit-table.md`.

**Newly verified findings** (2026-11-20):
- Instance 2 (frontend auth → guest): **NOT PRESENT**. `frontend/src/services/authService.ts`
  `getCurrentUserRoles()` returns `[]` on unauthenticated tokens; AuthContext relies on
  Amplify's `getCurrentUser` + `checkAuthenticated`. Fail-closed already.
- Instance 8 (cross-plane env): **REAL but separate**. Documented in
  `.kiro/specs/myBacklog/config-promotion-inconsistency-across-planes.md` — env selection models
  diverge per plane (Flask `.env`, SAM `samconfig.toml`, frontend `VITE_*`).

### D2 — Stale-projection reconcile (deliverable #2, security-first)

- Extend `ProjectionSync.sync_administration` to diff-delete obsolete `role#<email>#<role>` rows.
- Same pattern as `_reconcile_scopegrants`:
  1. Compute desired role sort keys from `source.user_tenant_roles`.
  2. Query stored `role#…` keys for the tenant partition (`begins_with(sk, 'role#')`).
  3. Delete stored keys not in the desired set (after puts — never transiently absent).
- Tenant-scoped: query keyed by `administration` partition; confined to `role#…` SK space.
- Idempotent: unchanged source → no deletes.
- `module#*`: **deferred — decision recorded (Phase 1, task 1.4).** The
  `role#…` reconcile fixes the security-relevant staleness (a cleared role can
  inflate an entitlement). A stale `module#<name>` row cannot inflate a *role*
  entitlement: module rows carry only `is_active`, are consumed by module-plane
  reads that re-check the live module list, and a disabled module's row has a
  separate lifecycle (module enable/disable), not the role-grant lifecycle this
  reconcile owns. Sweeping `module#*` here would couple two lifecycles and risk
  deleting a module row an in-flight enable just wrote. **Decision: defer the
  `module#*` sweep to a dedicated change** that owns module lifecycle; this
  deliverable reconciles only the `role#…` SK space.

Correctness properties:
- P1 (one-directional / tenant-scoped): reconcile never crosses tenants.
- P2 (idempotent): second sync with unchanged source deletes 0 rows.
- P3 (security): stale `role#` rows cannot persist after source removal.

### D3 — Fail-loud on missing REQUIRED config (deliverable #3)

- Frontend: remove API-base-URL → localhost fallback class; fail at build/startup instead (PR #16 failure mode). ✅ DONE — appEnv.ts fails fast on missing VITE_APP_ENV; no API-base-URL localhost fallback remains.
- Backend/SAM edge: missing tenant selection → explicit error; missing entitlement → explicit error. ✅ DONE — tenant_context.py:get_current_tenant no longer defaults multi-tenant users to tenants[0]; returns None → caller fails loud via validate_tenant_access. entitlement_reader.py already fail-closed. SAM authorization.py already denies when verified token carries no usable tenant.
- Follows s5f template (select-never-grant, deny-don't-default).

### D4 — Single source of truth for roles (deliverable #4) — ✅ DONE

- `getCurrentUserRoles()` treats MySQL-merged `/api/auth/me` roles as authoritative.
- Remove `cognito:groups` fallback branch.
- On MySQL failure / divergence: raise `RoleDivergenceError` (logged + alerted); do not silently substitute.
- Implemented: frontend `getCurrentUserRoles` removed JWT fallback; backend `cognito_required` raises `RoleDivergenceError` on DB failure.

### D5 — Post-deploy pre-checks (deliverable #5) — ✅ DONE

- Post-deploy verification step asserting required config/parameter availability and projection
  freshness; wired into deploy paths.
- Implemented: scripts/post_deploy_pre_check.py checks env vars, Cognito config, projection freshness
- Wired into: deploy-sam-members.yml (test→TEST, main→PROD) and deploy-frontend.yml (main→PROD)

### D6 — Guard-rail lint (deliverable #6) — ✅ DONE

- Broadened the s5f R4.3 grep guard into a reusable lint for catalogued fallback anti-patterns.
- Implemented: `scripts/fallback_lint.py` — 8 named rules (MASK-01…MASK-08) over
  frontend/src, backend/src, sam; Python comments + docstrings are masked (the s5f
  docstring exclusion preserved), TS/JS comments stripped; guard-aware so the
  legitimate single-tenant `len(...) == 1` case does not fire. Green on the remediated repo.
- Wired into CI: `.github/workflows/fallback-lint.yml` (PR/push to `main`), plus a
  pytest self-test `backend/tests/unit/test_fallback_lint.py`.

### D7 — Convergence steering rule (deliverable #7) — ✅ DONE

- Recorded the CONVERGENCE RULE (C default / B for un-configurable / never A) as steering in
  `.kiro/steering/36-config-and-parameters.md` (§The convergence rule), citing
  `services/storage_resolver.py::resolve_storage_provider` as the (C) proven template and the SAM
  `TenantHookRegistry` as the (B) example; (A) tenant-name branches are forbidden on every plane.

## Contracts / error handling

| Situation | Behaviour |
|---|---|
| Frontend missing API base URL | Explicit error (fail build / loud startup); never localhost |
| Multi-tenant user missing tenant selection | Explicit error; deny (never first-tenant default) |
| MySQL `/api/auth/me` failure / divergence | `RoleDivergenceError` (logged/alerted) — no silent `cognito:groups` substitution |
| Stale `role#` row in projection | Reconcile deletes it; regression test prevents lingering stale rows |
| Required config missing at startup | Raise; never silent default |

## Testing strategy (per plane)

- Frontend: unit tests for fail-fast env resolution; integration for no guest fallback.
- Flask: unit tests for `getCurrentUserRoles` divergence error; integration for fail-loud tenant selection.
- SAM: property tests for reconcile (in-memory fakes) in `tests/unit/test_projection_sync*.py`; PreTokenGen entitlement test.

## CI/CD integration (per steering 40)

- Quality gates: per-PR CodeQL + GitGuardian; nightly Full Test Suite; Backend/Frontend CI when re-enabled.
- Branch→env: `test` → TEST; `main` → PRODUCTION via `deploy-sam-*` / `deploy-frontend` workflows.
- Promote `test` → `main` as production-release gate.

## All-planes delivery

For each behavior change, enumerate planes and write a task per plane; never "backend done,
UI later"; update any admin UI still reflecting pre-change model; paired tests per plane.

## Related
- `docs/decisions/0005-…` (one-directional projection ADR)
- steering `36-config-and-parameters.md`, `41-shell-environment.md`, `43-cicd-deploys.md`