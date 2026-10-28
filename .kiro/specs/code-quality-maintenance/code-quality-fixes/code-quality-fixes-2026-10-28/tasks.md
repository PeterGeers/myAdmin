# Implementation Plan: Code Quality Fixes 2026-10-28

## Overview

Prioritized improvement tasks from the 2026-10-28 local code-quality scan (see `requirements.md`).
These are a plan only — do NOT execute them as part of generating this spec. Effort: S <= 30 min /
M <= 2 h / L > 2 h.

## Task Dependency Graph

Tasks are largely independent (each targets distinct files). The only ordering constraint: task 2
(ESLint fetch/axios guard) should land after or together with any migration of the one remaining
`fetch()` site — but that site is an exempt `*.example.tsx` demo, so the guard can be added directly
with an allow for `*.example.tsx`. All other tasks have no inter-dependencies and may be done in any
order or in parallel.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"] }
  ],
  "dependencies": {}
}
```

## Tasks

Improvement tasks from the 2026-10-28 local scan, grouped by priority. Effort: **S** ≤ 30 min ·
**M** ≤ 2 h · **L** > 2 h. Do NOT change observable behavior while refactoring; where a change is
behavioral, update the paired test in the same change (Change-With-Tests Contract). Pure
move/rename needs no test change but still run the affected suite.

## High

- [x] 1. **Consolidate the 8 `resolveLabel` copies into ONE shared util.** [M]
  Files: `frontend/src/pages/MemberAnalyticsPage.tsx:131`, `components/members/fieldForm.ts:97`,
  `components/members/FieldChecklist.tsx:46`, `components/members/analytics/memberFieldPicker.helpers.ts:48`,
  `components/members/analytics/MemberOverviewStats.tsx:75`, `components/members/analytics/memberPivotViewsHelpers.ts:60`,
  `components/members/overview/membersOverviewModel.ts:48`, `components/public/application/applicationForm.model.ts:52`.
  Grew from 2 copies last cycle to 8 — the clearest new consolidation target. Diff the 8
  implementations; extract the common behavior into one shared util
  (`frontend/src/components/members/labelResolver.ts` or `utils/`), preserving any per-site
  fallback/locale nuance behind a param. Update every call site in the same change and delete the
  copies. Verify: `cd frontend && npx vitest run` for the affected component/util tests; confirm no
  label output changed (pure refactor). Add a focused test for the shared util.

- [x] 2. **Add an ESLint guard banning raw `fetch(`/`axios.` outside `src/services/`.** [S]
  File: `frontend/.eslintrc*` (or `eslint.config.*`). Real bypasses are down to one exempt demo file;
  lock in the completed apiService migration with a `no-restricted-syntax`/`no-restricted-globals`
  rule, allowing `src/services/**` and `*.example.tsx`. Verify:
  `cd frontend && npx eslint src --max-warnings=0` stays green.

## Medium

- [x] 3. **Split `sam/members/domain/_membership_writes.py` (1940 — largest file in repo).** [L]
  Extract create / update / lifecycle / analytics write paths into cohesive sub-modules; keep the
  public import surface stable (re-export from the original path). Behavior change in zero places.
  Verify: `cd sam && python -m pytest tests/ -q` — membership service + handler + write-dispatch green.

- [x] 4. **Split `sam/members/handler/_dispatch.py` (1479) by resource.** [L]
  Group the dispatch table into per-resource modules; keep the handler's public entry stable. Verify:
  `cd sam && python -m pytest tests/test_members_write_dispatch.py tests/test_analytics_set_routes.py -q`.

- [x] 5. **Split `frontend/src/components/members/analytics/MemberPivotViews.tsx` (1718).** [L]
  Extract pivot builder / result rendering / preset+export into sub-components; keep the exported
  component API stable. Pure structural refactor. Verify:
  `cd frontend && npx vitest run src/components/members/analytics` — all 340 stay green.

- [x] 6. **Split `projection_config_reader.py` (1185, sam) and `_projection_config_builders.py` (1099, backend).** [L]
  Extract overlay read / resolve / wire-shape helpers (reader) and per-builder helpers (builders)
  into cohesive modules; keep import surface stable. Verify:
  `cd sam && python -m pytest tests/test_config_roundtrip_props.py tests/test_field_resolver.py -q`;
  backend builders — run the projection-sync/config tests that import them.

- [x] 7. **Reduce service-layer `Promise<any>` in the frontend.** [M]
  Frontend `services/**` returns typed `Promise<any>` (recurring across cycles). Give the service
  functions concrete return types (reuse existing `types/`), starting with the members/report
  services. No behavior change. Verify: `cd frontend && npx tsc --noEmit` stays clean; affected
  service tests green.

- [x] 8. **Confirm/add mobile table wrappers on the 4 data-dense pages.** [M]
  Files: `frontend/src/pages/CheckAccountsPage.tsx`, `CheckReferencePage.tsx`, `STRChannelRevenuePage.tsx`,
  `TransactionsPage.tsx`. The heuristic can't see wrappers in child components, so FIRST verify each
  actually lacks a `TableContainer`/`overflowX`/card fallback; add one only where genuinely missing.
  Mark any intentional exception with `// mobile-exempt: <reason>`. Verify in a narrow viewport that
  the table scrolls/stacks instead of overflowing.

- [x] 9. **Add direct tests for the high-risk untested backend route/scoping modules.** [M]
  Files: `admin_routes.py`, `audit_routes.py`, `routes/system_health_routes.py`,
  `routes/duplicate_detection_routes.py`, `routes/members_analytics_audit.py`,
  `services/_projection_scopegrant.py` (tenant-scoping). Add service/route-level tests under
  `backend/tests/` covering the happy path + auth/tenant guard + the error envelope
  (`error_response`). Extend a sibling test file where one exists. Verify:
  `cd backend && source .venv/bin/activate && pytest tests/ -q` for the new files.

## Low

- [x] 10. **Opportunistically split the 500–1000 line files when touched.** [L]
  Targets: backend `str_database.py` (926), `members_config_validation.py` (866); frontend
  `membersResourceApi.ts` (994), `MemberTemplateManager.tsx` (793); sam `config_write_service.py` (853),
  `config_fields_crud_service.py` (848). Refactor only when already in the file for other work. Verify:
  paired tests green after each split.

- [x] 11. **Trim genuine production `any` in public landing blocks and param-schema types.** [M]
  Files: `pages/public/blocks/AboutBlock.tsx` (`properties as any`), `types/parameterSchemaTypes.ts`
  (`default?: any`, `current_value?: any`), zzp modals, reports. Replace with concrete/union types.
  No behavior change. Verify: `cd frontend && npx tsc --noEmit` clean.

- [x] 12. **Fill medium-value frontend test gaps.** [M]
  Files: `components/members/overview/useMembersSelection.ts`, `components/pivot/usePivotConfig.ts`,
  `components/members/overview/membersOverviewModel.ts`. Add focused unit tests for the branch logic
  (selection toggles, pivot config derivation, model resolution). Prefer extending a sibling test
  file. Verify: `cd frontend && npx vitest run` for the new tests.

- [x] 13. **Archive stale point-in-time status docs.** [S]
  Move `*_COMPLETE.md` / `*_SUMMARY/*_PLAN/*_REPORT.md` historical artifacts under an `archive/` or
  delete if superseded. No code contradiction — lowest priority. Verify: `grep` shows no live link
  breaks before moving.

## Notes

- Scan is static/local only — it did NOT run CI or the test suite. Executing/triaging the Full Test
  Suite is the separate `prompt-test-suite-results.md` job.
- Do not fix issues as part of generating this spec. These tasks are the plan; run them later.
- Raw scan outputs captured under `.agent-output/cq-*.txt` during generation (git-ignored).
