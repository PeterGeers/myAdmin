# Requirements — Fail-loud fallback remediation

**Location**: `.kiro/specs/Common/Frameworks/fallback-patterns/`
**Status**: Complete
**Origin**: Backlog item `myBacklog/fallback-pattern.md` → moved here; consolidation of fallbacks
**Related**: `design.md`, `tasks.md`, `deliverable-1-audit-table.md`, `findings.md`, `fallback-pattern.md`

## Overview

Cross-cutting code-quality spec. Silent fallbacks (MASKING verdicts) hide missing inputs and
make failures surface far from their cause. Derived-data staleness (Part B) can inflate entitlements
once the SAM edge PreTokenGen trigger is live.

## User stories

### US-1 — Complete the fallback inventory (Deliverable #1)

As an operator, I want a complete inventory of every fallback/default across the three planes
(frontend SPA, Flask backend, SAM edge) with SAFE vs MASKING classifications, so that remediation
is driven by evidence rather than assumption.

**Acceptance criteria**:
- [x] Audit table lists fallback instances across all three planes (frontend / Flask / SAM / cross-plane)
- [x] Each entry records: location, substituted input, verdict (SAFE degenerate case vs MASKING missing input), verification status
- [x] Instances 1–7 verified in codebase via grep/search
- [x] Instance 2 verified: **NOT PRESENT** (frontend `getCurrentUserRoles()` returns `[]` on unauthenticated tokens — fail-closed already)
- [x] Instance 8 verified: **cross-plane env inconsistency confirmed** (referenced backlog item; not a code fallback)

### US-2 — Reconcile stale projection rows (Deliverable #2)

As a security engineer, I want stale `role#<email>#<role>` projection rows to be reconciled away
against MySQL `user_tenant_roles`, so that a removed role cannot inflate an entitlement once the
SAM edge PreTokenGen trigger is live.

**Acceptance criteria**:
- [x] `ProjectionSync` diff-deletes obsolete `role#…` rows for one tenant (same pattern as `_reconcile_scopegrants`)
- [x] Decision recorded on whether `module#*` rows are reconciled now or deferred
- [x] Regression coverage: role removed from MySQL → no lingering `role#` row in projection
- [x] Tenant-scoped reconcile (no cross-tenant access)

### US-3 — Fail loud on missing REQUIRED config (Deliverable #3)

As a developer / operator, I want missing REQUIRED config to raise an explicit error at startup or
edge time instead of silently substituting a reasonable default.

**Acceptance criteria**:
- [x] Missing frontend API base URL → error, never `127.0.0.1:3000 fallback
- [x] Missing tenant selection for multi-tenant user → error, never first-tenant default
- [x] Missing entitlement → explicit error
- [x] Follows s5f template: select-never-grant, deny-don't-default

### US-4 — Single source of truth for roles (Deliverable #4)

As an admin, I want MySQL-merged roles (`/api/auth/me`) to be authoritative for entitlements, with
`cognito:groups` divergence surfaced as an error rather than silently trusted.

**Acceptance criteria**:
- [x] `getCurrentUserRoles()` removes the `cognito:groups` fallback branch
- [x] MySQL-merged roles authoritative; `cognito:groups` divergence → error (logged/alerted, not swallowed)
- [x] Callers of `getCurrentUserRoles()` updated for explicit-error contract

### US-5 — Post-deploy pre-checks (Deliverable #5)

As a release engineer, I want post-deploy verification that required config/parameters are
available and projection freshness is sane, so a missing input is caught at deploy time rather than
surfacing as an empty screen in prod.

**Acceptance criteria**:
- [x] Post-deploy step asserts API URLs / required env vars / projection freshness
- [x] Wired into the `test` → TEST and `main` → PRODUCTION deploy paths

### US-6 — Guard-rail lint (Deliverable #6)

As a maintainer, I want the existing s5f "no fallback tenant symbol" grep guard broadened into a
reusable lint that flags the known fallback anti-patterns from the audit, so regressions are caught
in CI.

**Acceptance criteria**:
- [x] Lint covers catalogued MASKING anti-patterns across frontend / Flask / SAM planes (`scripts/fallback_lint.py`, rules MASK-01…MASK-08)
- [x] Runs as part of PR quality gates (CodeQL / GitGuardian surface) — `.github/workflows/fallback-lint.yml` on every PR/push to `main`

### US-7 — Convergence steering rule (Deliverable #7)

As an architect, I want the generic-vs-tenant placement CONVERGENCE RULE recorded as steering
alongside `36-config-and-parameters.md`, so new tenant-specific behavior defaults to config-selected
generic handlers and never tenant-name branches.

**Acceptance criteria**:
- [x] Steering rule recorded (C default, B for un-configurable, never A) — in `.kiro/steering/36-config-and-parameters.md`
- [x] Proven template: `services/storage_resolver.py::resolve_storage_provider`

## Success metrics

- 0 unverified/misleading audit entries remain after this spec completes
- 0 stale `role#` projection rows after a clean reconcile run
- 0 silent fallbacks remain in catalogued paths (per audit)
- CI lint fails a PR that reintroduces any catalogued MASKING pattern

## Out of scope

- Landing the SAM edge PreTokenGen trigger itself (Deliverable #2 makes the projection safe for it;
  does not deliver it)
- Changing tenant-selection storage or the SAM edge authorization contract
- Generic fallback service (decided: per-instance fail-loud / reconcile instead of a single service —
  avoids over-complication; recorded in spec analysis)