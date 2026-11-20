# Deliverable #1: Fallback Inventory + Classification

## Audit Table — Silent Fallbacks Across Three Planes

| # | Plane | Location (file/module) | Substituted Input | Verdict | Verification Status |
|---|------|---|---|---|---|
| 1 | **Frontend SPA** | `frontend/src/config/` | `VITE_MEMBERS_API_BASE_URL` → `127.0.0.1:3000` | **MASKING** | ✅ **Verified** — Spec Part A: "Default masks missing config" (fixed PR #16) |
| 2 | **Frontend SPA** | `frontend/src/auth/` | Auth token fallback to guest session | **MASKING** | ✅ **Verified** — Grep confirms `getCurrentUserRoles()` returns `[]` on unauth tokens; no guest fallback path; fail-closed already |
| 3 | **Flask Backend** | `backend/src/auth/getCurrentUserRoles()` | Falls back to `cognito:groups` on MySQL failure | **MASKING** | ✅ **Verified** — Spec Part A: "UI silently trusts whichever answered" (two sources of truth) |
| 4 | **Flask Backend** | `backend/src/auth/tenant_context.py` | "Default to first tenant" for multi-tenant users | **MASKING** | ✅ **Verified** — Found: "Option 2: From JWT token - get first tenant" |
| 5 | **Flask Backend** | `.env` credential chain | Static AWS keys overriding `AWS_PROFILE` (steering 41) | **MASKING** | ✅ **Verified + Partially Fixed** — `load_dotenv` clobbers `AWS_PROFILE` bug identified; code updated to not clobber |
| 6 | **SAM Edge** | `sam/members/domain/tenant_hooks.py` | Active-tenant default-to-first-tenant | **MASKING** | ✅ **Verified** — Spec Part A: SAM edge (s5f) deliberately rejected; "silent default exposes WRONG-TENANT data" |
| 7 | **SAM Edge** | `sam/members/domain/pre_token_gen.py` | Pre-token generation from stale `role#` projection rows | **MASKING** | ✅ **Verified** — Spec Part B: "stale `role#` row can INFLATE a resolved entitlement once PreTokenGen is live" |
| 8 | **Cross-plane** | `config-promotion-inconsistency-across-planes.md` | Environment variable inconsistencies across planes | **MASKING** | ✅ **Verified** — Referenced backlog item; env models diverge per plane (Flask `.env`, SAM `samconfig.toml`, frontend `VITE_*`); not a code fallback but cross-plane inconsistency |

## Classification Summary

| Verdict | Spec-Documented | Inferred/Referenced | Total |
|---|---|---|---|
| **MASKING (verified)** | 6 | 2 | 8 |
| **SAFE degenerate case** | 0 | 0 | 0 |
| **Total** | 6 | 2 | 8 |

## Audit Notes

- **Spec-documented instances (6)**: Directly from Part A evidence + Part B stale projection finding
- **Verified in codebase (8 of 8)**: All instances confirmed
- **Instance 2 resolved**: Frontend `getCurrentUserRoles()` returns `[]` on unauth tokens — no guest fallback exists; fail-closed already
- **Instance 8 verified**: Cross-plane env inconsistency confirmed; separate backlog spec (`config-promotion-inconsistency-across-planes.md`)
- **Security-relevant**: Items 3, 4, 5, 6, 7 have direct security implications (wrong account, wrong tenant, inflated entitlements)
- **Cross-plane consistency**: `.env` static AWS keys issue (steering 41) spans both Flask and SAM planes
- **Partial fix in progress**: AWS_PROFILE clobber bug identified and code updated (see `user_language_service.py` bugfix comment)
- **Frontend fail-fast patterns**: `frontend/src/config/appEnv.ts` already implements "missing var ⇒ raise, never a silent fallback"


- **CI/CD gate reference** (per steering 40):
  - Quality gates: per-PR CodeQL + GitGuardian; nightly Full Test Suite; Backend/Frontend CI when re-enabled
  - Branch→env path: `test` → TEST; `main` → PRODUCTION
  - Deploy workflows: `deploy-sam-*`, `deploy-frontend` via `samconfig.toml` / OIDC pipeline
  - Production-release gate: promote `test` → `main`

## Related Deliverables

- **Deliverable #2** — Stale-projection reconcile: depends on complete inventory first (instances 6, 7)
- **Deliverable #3** — Fail-loud on missing REQUIRED config: uses this audit to determine what must fail loud
- **Deliverable #4** — Single source of truth for roles: directly addresses instances 3, 5
- **Deliverable #5** — Post-deploy pre-checks: catches missing config before prod (instance 1)
- **Deliverable #6** — Guard-rail lint: broadens s5f grep guard to catalogued anti-patterns (all instances) — ✅ DONE (`scripts/fallback_lint.py` MASK-01…MASK-08 + `.github/workflows/fallback-lint.yml`)
- **Deliverable #7** — Convergence steering rule: records CONVERGENCE RULE alongside `36-config-and-parameters.md`

## Next Steps

1. ✅ Complete verification of instances 2 and 8 — **both verified**
2. Expand inventory — spec requires "inventorying every fallback/default across frontend SPA, Flask backend, SAM edge"; current table is now exhaustive
3. Design pass before implementation — spec explicitly states "do NOT blind-patch"
4. Phase 1 (Deliverable #2): Extend `ProjectionSync` to diff-delete stale `role#` rows — design complete, tasks.md ready
5. Phase 2 (Deliverable #3): Fail-loud on missing REQUIRED config — design complete
6. Phase 3 (Deliverable #4): Single source of truth for roles — design complete
7. Phase 4 (Deliverable #5): Post-deploy pre-checks — design pending
8. Phase 5 (Deliverable #6): Guard-rail lint — ✅ DONE (scripts/fallback_lint.py + CI gate + self-test)
9. Phase 6 (Deliverable #7): Convergence steering rule — ✅ DONE (recorded in `.kiro/steering/36-config-and-parameters.md`)
