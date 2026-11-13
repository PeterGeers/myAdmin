# Implementation Plan: Code Quality Fixes 2026-11-12

## Overview

Prioritized improvement tasks from the 2026-11-12 local code-quality review (see
`requirements.md`). These are a plan only - do NOT execute them as part of generating this
spec. Effort: **S** <= 30 min / **M** <= 2 h / **L** > 2 h.

Every task must obey the execution principles: reuse before rewrite (steering
`37-shared-building-blocks.md`); consolidate duplicates into ONE home and migrate every call
site in the same change; verify a symbol is dead before deleting; split large files along
cohesion seams with a stable public import surface and zero behavior change; and drag the
paired tests along whenever observable behavior changes.

## Task Dependency Graph

Only two ordering constraints exist:

- Task **2** (delete orphaned components) must confirm there is no dynamic/route reference
  before deletion - it has no dependency on other tasks.
- Task **16** (collapse the `resolveLabel` shims) is cosmetic and should land *after* task 10
  if task 10 touches `memberPivotViewsHelpers.ts`, to avoid a conflict.

All SAM split tasks (3-9) touch disjoint modules, so they are mutually independent and may
be done in any order - but each must keep its own tests green.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "17", "18"] },
    { "wave": 2, "tasks": ["16"] }
  ],
  "dependencies": { "16": ["10"] }
}
```

## Tasks

## High

- [x] 1. **Collapse the 32 inline tenant-admin auth guards onto `@tenant_required`.** [L]
  Files: `backend/src/routes/tenant_admin_templates.py` (6 copies),
  `tenant_admin_roles.py` (6), `chart_of_accounts_routes.py` (5), `tenant_admin_users.py` (4),
  `tenant_admin_template_ai_routes.py` (3), `tenant_admin_scope.py` (3),
  `tenant_admin_config.py` (3), `chart_of_accounts_io_routes.py` (2).
  Each handler re-implements `parse Bearer -> get_user_tenants(jwt_token) -> is_tenant_admin ->
  jsonify({"error": ...}), 401/403`. Replace with the shared decorator
  (`backend/src/auth/tenant_context.py:280`), or - where a handler needs the decoded tenant list
  for its body - a single shared helper invoked from the decorator, so the guard exists in ONE
  place. Keep the response envelope/status codes byte-identical (`error_response`, 401 for
  missing/invalid Bearer, 403 for non-admin) so the contract is unchanged. Delete every inline
  copy; do not leave a half-migrated split. Verify: `cd backend && source .venv/bin/activate &&
  pytest tests/ -q` - especially `tests/api/test_tenant_admin*`, `test_chart_of_accounts*`,
  `tests/integration/test_tenant_admin_endpoints_accessible.py`; and
  `grep -rn "is_tenant_admin(" backend/src/routes` must return **0** hits outside
  `auth/tenant_context.py`.

- [x] 2. **Verify-and-delete the 3 orphaned frontend components.** [S]
  Files: `frontend/src/components/FilterErrorBoundary.tsx` (109 lines, no reference anywhere),
  `frontend/src/pages/ServiceUnavailable.tsx`, `frontend/src/pages/ServerError.tsx`.
  FIRST re-confirm each has no dynamic reference: `grep -rn "FilterErrorBoundary|ServiceUnavailable|ServerError"
  frontend/src` plus route-string checks in `App.tsx`, `appPages.tsx`, `main.tsx`, and any
  lazy `import()`. If genuinely unreferenced, delete the file (prefer deletion over
  commenting-out). Consider doing the same for `components/ViolinChartExample.tsx` (demo, no
  importers) - or rename it to `*.example.tsx` to keep it out of prod bundles. Verify:
  `cd frontend && npx tsc --noEmit && npx vitest run` stay green.

## Medium

- [x] 3. **Split `sam/members/migration/hdcn_backfill.py` (1726).** [L]
  Extract the read/paging phase, the field-shape transform table, the write phase, and the
  CLI/report harness into cohesive modules under `migration/hdcn_backfill/` (or sibling
  modules); re-export the public entry from the original path. Behavior change in zero places.
  Verify: `cd sam && python -m pytest tests/test_hdcn_backfill.py -q` (and
  `tests/test_hdcn_*`) stays green; prove the round-trip against a REAL `h-dcn` `config#fields`
  record, not a hand-built fixture (spec 11: trust runs, not inference).

- [x] 4. **Split `sam/members/domain/config_fields_crud_service.py` (1712).** [L]
  Separate read/overlay resolution, Change-Op apply, the source-integrity guard, and the
  wire-key normalisation helpers into cohesive modules; keep the class/module public surface
  re-exported from the original path. No behavior change. Verify:
  `cd sam && python -m pytest tests/test_config_fields_crud_service.py tests/test_field_config_endpoint.py -q`.

- [x] 5. **Split `sam/members/handler/app.py` (1653).** [L]
  Move the auth/authorize helpers (`_authenticate_and_authorize`, `_authorize_schedule_route`,
  `_resolve_scope_access_for_admin`, `_resolve_scope_access_for_schedule`, `_any_capability_granted`)
  into a dedicated `handler/authorization.py`, and the stale-bundle rejection into its own
  module; keep the lambda entry (`lambda_handler`) and route registration stable.
  Verify: `cd sam && python -m pytest tests/test_public_app_edge.py tests/test_schedule_routes.py -q`.

- [x] 6. **Split `sam/members/repository/members_repository.py` (1551).** [L]
  Group by operation family (create / read / update / lifecycle / queries) into repository
  sub-modules behind one `MembersRepository` facade. The repository stays the SOLE DynamoDB
  touch-point (steering 35) and no raw record shape leaves it (steering 39). Verify:
  `cd sam && python -m pytest tests/test_members_repository.py tests/test_members_projection_reader.py -q`.

- [x] 7. **Split `sam/members/worker/mail_send_worker.py` (1236).** [L]
  Separate the SES send path, template rendering, audit-record building, and retry/backoff into
  cohesive modules under `worker/`; keep the Lambda handler entry stable. Verify:
  `cd sam && python -m pytest tests/test_application_mail_worker.py -q`.

- [x] 8. **Split `sam/members/repository/table_design.py` (1172) and
  `sam/members/handler/public_app.py` (1171).** [L]
  `table_design.py`: table/key/schema definitions vs migration helpers. `public_app.py`: public
  intake routes vs submission/serve helpers. Keep the public import surface stable and the
  no-`.scan()` guarantee (Property 4 / SEC-6) intact. Verify:
  `cd sam && python -m pytest tests/test_public_app_edge.py -q` and the table-design tests.

- [x] 9. **Split `sam/members/domain/config_write_service.py` (1119),
  `handler/routes.py` (1074) and `handler/_dispatch_services.py` (1073).** [L]
  `config_write_service.py`: body normalisation (`fixed_overrides`/`overrides` coercion),
  Change-Op planning, apply orchestration. `handler/routes.py`: the route table vs the
  `dispatch_*` implementations. `_dispatch_services.py`: the service container vs the
  stale-bundle guard constants/helpers. Preserve the foolproof-CRUD contract (ADR 0009 /
  spec 03). Verify: `cd sam && python -m pytest tests/test_config_write_service.py
  tests/test_config_write_repository_apply_ops.py tests/test_config_roundtrip_props.py
  tests/test_members_write_dispatch.py -q`.

- [x] 10. **Split `frontend/src/components/members/analytics/MemberPivotViews.tsx` (1054).** [M]
  Extract the pivot builder, result rendering, and preset/export concerns; `sam`
  and `MemberPivotResultActions.tsx` already exist as sibling seams. Keep the component's
  public export stable. Verify: `cd frontend && npx vitest run` for
  `MemberPivotViews.test.tsx`, `PivotBuilder.test.tsx`; `npx tsc --noEmit` clean.

- [x] 11. **Add return/param type hints to SAM handler/domain/repository functions.** [M]
  Start with `handler/app.py` (`_authenticate_and_authorize`, `_resolve_scope_access_*`,
  `_any_capability_granted`), `handler/router.py` (`resolve`), `handler/_dispatch_services.py`,
  `handler/_dispatch_members.py`, `handler/_dispatch.py` (`dispatch_route`),
  `handler/_dispatch_config.py`, `worker/mail_audit.py`. Annotate return types and public
  params with the existing typing conventions/aliases; no behavior change.
  Verify: `cd sam && python -m pytest tests/ -q` green; re-run the hint grep to confirm
  the count dropped.

- [x] 12. **Add return/param type hints to backend service/route functions.** [M]
  Same heuristic (1248 raw). Prioritise `services/budget_query_service.py`,
  `services/budget_ai_service.py`, `services/year_end_service.py`, `services/zzp_*`,
  `services/output_service.py`, `services/payment_check_helper.py`. No behavior change.
  Verify: `cd backend && source .venv/bin/activate && pytest tests/ -q` green; `ruff` clean if
  configured.

- [x] 13. **Add direct tests for the genuinely-untested backend high-risk modules.** [M]
  Files (verify first - nothing already imports them in `backend/tests/**`):
  `services/_projection_scopegrant.py`, `services/_projection_scope_builder.py`
  (tenant-scoping = highest risk), `services/zzp_invoice_delivery.py`,
  `services/zzp_invoice_numbering.py`, `services/zzp_invoice_factory.py`,
  `services/zzp_trip_crud_service.py`, `services/zzp_trip_query_service.py`,
  `services/chart_of_accounts_io_service.py`, `services/pivot_query_builder.py`,
  `routes/chart_of_accounts_io_routes.py`, `routes/zzp_time_routes.py`.
  Cover the happy path + the tenant/auth guard + the `error_response` envelope; prefer extending
  a sibling test file. Do NOT open tasks for the test-exempt entries listed in requirements §8.
  Verify: `cd backend && source .venv/bin/activate && pytest tests/ -q` for the new files.

## Low

- [x] 14. **Trim production `any` in the frontend (113 sites).** [M]
  Collapse by concentration, not by count: `components/reports/BnbYearMonthMatrix.tsx`,
  `BnbFutureReport.tsx`, `AangifteIbReport.tsx`, `BudgetDashboardTab.tsx` (`useState<any>`,
  sort comparators, `{} as any`), `components/STRPricing.tsx`, `components/BankingProcessor.utils.ts`
  (`bankLookup: any`), `pages/public/blocks/*` (`properties as any`),
  `types/parameterSchemaTypes.ts` (`default?: any`, `current_value?: any`) - reuse the existing
  `types/**` shapes. No behavior change. Verify: `cd frontend && npx tsc --noEmit` clean.

- [ ] 15. **Opportunistically split the 500-1000 line files when already in them.** [L]
  Targets: backend `str_database.py` 926, `auth/cognito_utils.py` 894,
  `routes/tenant_admin_users.py` 859, `services/media_asset/lifecycle.py` 852,
  `scalability_routes.py` 852; frontend `services/members/membersResourceApi.ts` 994,
  `TenantAdmin/MembersConfig/ApplicationFormBuilder.tsx` 938; SAM
  `domain/application_form_render.py` 957, `repository/projection_config_write_repository.py` 828,
  `domain/application_publish.py` 819. Refactor only when the file is open for other work.
  Verify: paired tests green after each split.

- [x] 16. **Collapse the 8 thin `resolveLabel` delegate shims to direct imports.** [S]
  Files: `pages/MemberAnalyticsPage.tsx:138`, `components/members/FieldChecklist.tsx:52`,
  `components/members/analytics/memberFieldPicker.helpers.ts:52`,
  `components/members/analytics/MemberOverviewStats.tsx:78`,
  `components/members/analytics/memberPivotViewsHelpers.ts:64`,
  `components/members/overview/membersOverviewModel.ts:56`,
  `components/public/application/applicationForm.model.ts:57`. Each is one line delegating to
  `components/members/labelResolver.ts`. Import the shared function directly (note the
  `en-first` locale at the application-form site) and delete the shim. Purely cosmetic and
  low-value - only do it if the file is touched for other reasons. Verify:
  `cd frontend && npx tsc --noEmit && npx vitest run` green; label output unchanged.

- [x] 17. **Archive the 2 residual point-in-time docs.** [S]
  Move `backend/tests/TESTING_COMPLETE_SUMMARY.md` and
  `backend/docs/RBAC_IMPLEMENTATION_SUMMARY.md` under an `archive/` folder (or delete if
  superseded). Lowest-priority signal. Verify: `grep` shows no live link breaks before moving.

- [x] 18. **Fill the medium-value frontend test gaps.** [M]
  Files: `components/members/analytics/useMemberSetLibrary.ts`, `useMemberPivotExport.ts`,
  `memberPivotViewsHelpers.ts`, `memberTemplateManager.helpers.ts`, `memberMailHelpers.ts`,
  `services/members/membersResourceApi.ts`, `membersColumnPreferencesApi.ts`,
  `membersPageSize.ts`, `config/pivotDataSources.ts`, `components/TenantAdmin/useStorageTab.ts`,
  `components/help/helpLinks.ts`. Add focused unit tests for the branch logic; prefer extending a
  sibling test file. Leave the test-exempt entries (types-only, barrels, public/blocks leaf
  components, `appPages.tsx`, demo files) alone. Verify: `cd frontend && npx vitest run`.

## Notes

- This review is static/local only - it did NOT run CI or the test suite. Executing and
  triaging the Full Test Suite is the separate `prompt-test-suite-results.md` job.
- Do NOT fix these issues as part of generating this spec. These tasks are the plan; run them
  later.
- Raw scan outputs captured under `.agent-output/cq-*.txt` during generation (git-ignored).
- `vulture` lives at `backend/.venv/bin/vulture` (not the root `.venv`); use that path if
  re-running the dead-code scan.
- Heuristic counts (file length excepted) must be re-verified before acting - see the caveat in
  requirements §8 for the missing-test numbers.
