# fallback-patterns — Fail-loud fallback remediation spec

**Location**: `.kiro/specs/Common/Frameworks/fallback-patterns/`
**Status**: Draft
**Owner**: Cross-cutting code-quality (steering 41, s5f / ADR 0007)
**Planes touched**: Frontend SPA (`frontend/src/`), Flask backend (`backend/src/`), SAM edge (`sam/members/`)

## Navigation

| File | Purpose |
|------|---------|
| `README.md` | Navigation index (this file) |
| `requirements.md` | User stories, acceptance criteria, success metrics, out of scope |
| `design.md` | Architecture, contracts, correctness properties, error handling, testing strategy |
| `tasks.md` | Phased task breakdown with checkboxes and dependencies |
| `deliverable-1-audit-table.md` | Deliverable #1 — verified fallback inventory (8 instances) |
| `findings.md` | Source analysis findings (Part A / B / C) |
| `fallback-pattern.md` | Original backlog analysis (Parts A, B, C + 7 deliverables) |

## Deliverables (in priority order)

| # | Deliverable | File | Status |
|---|-------------|------|--------|
| 1 | Fallback inventory + classification | `deliverable-1-audit-table.md` | ✅ Complete (verified) |
| 2 | Stale-projection reconcile (`role#` rows) | `backend/src/services/projection_sync.py` | ✅ Complete |
| 3 | Fail-loud on missing REQUIRED config | frontend `appEnv.ts` + `tenant_context.py` | ✅ Complete |
| 4 | Single source of truth for roles | `role_cache.py` + `authService.ts` | ✅ Complete |
| 5 | Post-deploy pre-checks | `scripts/post_deploy_pre_check.py` | ✅ Complete |
| 6 | Guard-rail lint (broaden s5f guard) | `scripts/fallback_lint.py` | ✅ Complete (rules MASK-01…MASK-08; CI gate) |
| 7 | Convergence steering rule | `.kiro/steering/36-config-and-parameters.md` | ✅ Complete |

**Post-delivery hardening (Phase 7 in `tasks.md`):** Deliverable #5's pre-check env is
single-sourced (one workflow-level `env` block in `deploy-frontend.yml`) and guarded by
`scripts/check_frontend_env_parity.py` — run per PR in `fallback-lint.yml` and pinned by
`backend/tests/unit/test_deploy_frontend_env_parity.py`. A duplicated list had turned the
PROD deploy red *after* the Pages publish had succeeded.

## Related steering
- `40-spec-workflow.md` — this spec structure
- `36-config-and-parameters.md` — config model (Deliverable #7 companion)
- `41-shell-environment.md` — AWS_PROFILE / credential context (instance 5)
- s5f / ADR 0007 — SAM edge authorization contract (deny-don't-default template)

## Definition of done (per steering 40)
- Every affected plane updated, paired tests per plane, CI/CD tasks named
- No UI anywhere still reflects the pre-change (silent-fallback) model
- Steering/ADRs updated to match any changes made