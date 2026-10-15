# Implementation Plan: Code Quality Fixes 2026-10-15

## Overview

Prioritized improvement tasks from the 2026-10-15 local code-quality scan. These are a plan
only — do NOT execute them as part of generating this spec. Effort: S <= 30 min / M <= 2 h / L > 2 h.

## Task Dependency Graph

Tasks are largely independent (each targets distinct files). The only ordering constraint:
task 2 (ESLint fetch guard) should land after or together with task 3 (migrate the last real
`fetch()` site) so the guard does not fail on an un-migrated call. All other tasks have no
inter-dependencies and may be done in any order or in parallel.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"] },
    { "wave": 2, "tasks": ["2"] }
  ],
  "dependencies": {
    "2": ["3"]
  }
}
```

## Tasks

Improvement tasks from the 2026-10-15 local scan, grouped by priority. Effort: **S** ≤ 30 min ·
**M** ≤ 2 h · **L** > 2 h. Do NOT change observable behavior while refactoring; where a change is
behavioral, update the paired test in the same change (Change-With-Tests Contract). Pure
move/rename needs no test change but still run the affected suite.

## High

- [x] 1. **Resolve the recurring SAM `scope_filter` dead variable (tenant-scoping repository).** [M]
  Files: `sam/members/repository/members_repository.py:102, 371, 596`. This is the SECOND cycle the
  same unused `scope_filter` local is flagged (was lines 74/194/335 on 2026-10-04). FIRST confirm it
  is genuinely dead — not a half-wired scope filter the query should actually apply (a missing filter
  here is a cross-tenant READ risk, the opposite of harmless). If the filter SHOULD be applied, wire
  it into the query and add a scope-isolation test; if it is truly vestigial, delete it. Do not just
  silence it. Verify: `vulture sam/ --min-confidence 80` no longer lists it; `python -m pytest sam/tests -q`.

- [x] 2. **Add an ESLint guard banning raw `fetch(`/`axios.` outside `src/services/`.** [M]
  File: `frontend/.eslintrc*` (or `eslint.config.*`). The apiService migration dropped the bypass
  from 33→2; lock in the win with a `no-restricted-syntax`/`no-restricted-globals` rule so new
  components can't reintroduce a direct fetch. Allow `src/services/**` and `*.example.tsx`. Verify:
  `cd frontend && npx eslint src` passes clean (the 1 remaining real site in `PublicLandingPage.tsx`
  must be migrated — task 3 — or explicitly allow-listed first).

- [x] 3. **Migrate the one real `fetch()` bypass in `PublicLandingPage.tsx`.** [S]
  File: `frontend/src/pages/public/PublicLandingPage.tsx:230`. Route `await fetch(url)` through
  `services/apiService` (or a thin public-fetch helper) for base-URL consistency. If the public,
  unauthenticated nature means apiService's auth headers are inappropriate, document why and
  allow-list it in the task-2 rule instead. `TenantAwareComponent.example.tsx` is exempt (demo file).
  Verify: `cd frontend && npx vitest run` for any affected test; manual check the landing page loads.

## Medium

- [x] 4. **Split `frontend/src/components/members/analytics/MemberPivotViews.tsx` (2007 lines).** [L]
  Now the single largest file in the repo. Extract along cohesion seams: pivot-builder controls,
  result-table rendering, and preset/export handling into sibling sub-components, keeping the public
  import surface stable (re-export from the original path). Zero behavior change. Verify:
  `cd frontend && npx vitest run src/components/members/analytics/MemberPivotViews.test.tsx` stays green.

- [x] 5. **Split `frontend/src/services/membersApiService.ts` (1267 lines).** [M]
  Break into per-resource client groups (members / column-preferences / config) re-exported from the
  original module path so callers are unaffected. Pure move. Verify:
  `cd frontend && npx vitest run src/services/membersApiService.test.ts` (58 tests) stays green.

- [x] 6. **Split `frontend/src/pages/MembersPage.tsx` (1161 lines).** [L]
  Extract the table, toolbar, pagination, and data-loading into cohesive child components/hooks;
  keep behavior identical. Verify: `cd frontend && npx vitest run src/pages/__tests__/MembersPage*` green.

- [x] 7. **Split `backend/src/services/zzp_trip_import_service.py` (1119 lines).** [L]
  Extract the parse / validate / commit stages into cohesive helpers (or a small sub-package),
  keeping the public service import surface stable. Change behavior in zero places. Verify:
  `cd backend && source .venv/bin/activate && python -m pytest tests/unit/test_zzp_trip_import*.py -q` green.

- [x] 8. **Add a direct test for `sam/members/worker/mail_audit.py`.** [M]
  It is both a missing-test candidate AND carries a vulture dead-var finding (`actor_roles:96`) —
  audit logging is easy to under-cover. Add `sam/tests/test_mail_audit*.py` covering the audit-record
  shape and the `actor_roles` path (which decides whether that variable is dead or should be used).
  Verify: `python -m pytest sam/tests/test_mail_audit*.py -q`.

- [x] 9. **Backfill high-risk backend missing tests (money / routes).** [L]
  No paired test references: `services/year_end_journal_entries.py` (journal/money),
  `services/banking_mutatie_service.py` (DB/money), `admin_routes.py`, `audit_routes.py`,
  `routes/invoice_routes.py`, `routes/tax_routes.py`. Add service-level unit tests (prefer extending a
  sibling test file) focusing on money math, tenant scoping, and error/abort paths. Verify:
  `cd backend && source .venv/bin/activate && python -m pytest tests/unit -q -k "year_end or banking_mutatie or admin_routes or audit_routes or invoice_routes or tax_routes"`.

- [x] 10. **Spot-check SAM `_`-private module coverage via their parents.** [M]
  Files: `sam/members/domain/_membership_writes.py` (tenant-scoped writes) + the other
  `_membership_*` and `sam/shared/_*` modules. Confirm the public parent's tests actually drive the
  private module's branches; where a branch is uncovered (esp. a write/scope path), add a case to the
  parent's test file. This is verification + targeted top-up, not a new test file per private module.

## Low

- [x] 11. **Collapse the confirmed frontend duplicate utilities.** [S]
  `isValidEmail` (in `utils/validationHelpers.ts` and `utils/emailVerificationUtils.ts`) and
  `buildApiUrl` (in `config/api.ts`, `services/apiService.ts`, `config.ts`) — consolidate each into
  one home and update imports in the same change. Confirm `resolveLabel`'s two copies are intentional
  per-plane (backend-mirror vs frontend) before touching. Verify: `cd frontend && npx vitest run`.

- [x] 12. **Confirm/repair mobile wrappers on the 5 data-table pages.** [M]
  `pages/CheckAccountsPage.tsx`, `pages/CheckReferencePage.tsx`, `pages/STRChannelRevenuePage.tsx`
  (Medium, user-facing) + `pages/ZZPTrips.tsx`, `ZZPInvoices.tsx`/`ZZPDebtors.tsx` (Low). The scan
  heuristic can't see wrappers in child components, so FIRST verify each actually lacks a
  `TableContainer`/`overflowX`/card fallback; add one only where genuinely missing. Verify in a narrow
  viewport that the table scrolls/stacks instead of overflowing.

- [x] 13. **Reduce production `any` in the thin-spread hotspots.** [M]
  `types/parameterSchemaTypes.ts` (`default?: any`, `current_value?: any`), `utils/csvExport.ts`
  (`CellFormatter`/row types), the zzp modals, and the persisting service-layer `Promise<any>`
  returns. Replace with precise types/generics where cheap; leave genuinely dynamic shapes documented.
  Verify: `cd frontend && npx tsc --noEmit` clean; `npx vitest run` for touched modules.

- [x] 14. **Opportunistically split notable 500–1000 line files.** [L]
  Backend `str_database.py` (910), `auth/cognito_utils.py` (894); frontend
  `MemberMailCompose.tsx` (860), `MemberFieldPicker.tsx` (800); SAM `execute_and_deliver.py` (781),
  `field_resolver.py` (757). Only split along clean cohesion seams with no behavior change; skip any
  that don't have an obvious seam. Verify the paired suite for each file touched.

- [x] 15. **Archive stale point-in-time status docs.** [S]
  Move the historical `*_COMPLETE.md` / `*_SUMMARY/*_PLAN/*_REPORT.md` (dated mid-2026) into an
  `archive/` or delete if superseded. No code references them. Verify: `grep` shows no live link
  breaks.

## Notes

- Scan is static/local only — it did NOT run CI or the test suite. Executing/triaging the Full Test
  Suite is the separate `prompt-test-suite-results.md` job.
- Do not fix issues as part of generating this spec. These tasks are the plan; run them later.
- Raw scan outputs captured under `.agent-output/cq-*.txt` during generation (git-ignored).
