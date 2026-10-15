# Requirements Document

Code Quality Fixes — 2026-10-15 (local, source-level scan).

## Introduction

This spec captures the findings of a local, source-level code-quality scan (no CI, no
test execution) run on 2026-10-15, and the prioritized improvement tasks derived from them.
Each requirement below is a scan dimension with its findings, counts, and the delta vs the
previous run (`code-quality-fixes-2026-10-04`). The actionable work lives in `tasks.md`.

## Glossary

- **Plane** — one of the three code areas: `backend` (Flask/MySQL), `sam` (Lambda/DynamoDB), `frontend` (React).
- **Bypass** — hand-rolled code that re-implements a shared building block instead of using it.
- **Missing-test candidate** — a source file whose basename is referenced by no test file (filename heuristic).
- **Test-exempt-via-parent** — a private `_`-prefixed module exercised through its public parent module's tests.

## Requirements

## Summary

**Local, source-level** code-quality scan (no CI, no test execution) of the myAdmin repo on
`test` (= `main`, just promoted via PR #110), 2026-10-15. Covers file length, dead code,
duplication, framework/reusable-block (non-)use, type safety, mobile compliance, stale docs,
and missing-test gaps. Compared against the previous run `code-quality-fixes-2026-10-04`.

| Dimension                     | Count (this run)                                      | Δ vs 2026-10-04                               |
| ----------------------------- | ----------------------------------------------------- | --------------------------------------------- |
| Files 500–1000 lines          | ~60 be+fe · ~11 sam                                   | ≈ stable                                      |
| Files > 1000 lines (critical) | **8** (fe 3 / be 1 / sam 4)                           | ↑ from 5 — frontend regressed (3 new)         |
| Dead code (vulture ≥ 80)      | be 0 · sam 4                                          | be stable · sam 4 (same class, moved lines)   |
| Duplicate patterns            | low-signal (OOP dunders + Chakra icon re-exports)     | no new real duplication surfaced              |
| Framework bypasses            | fe 2 real `fetch()` sites · be/sam clean              | ↓↓ from 33 — the apiService migration landed  |
| Type safety                   | fe `any` ~94 real (243 raw) · be/sam hint heuristic   | ≈ stable                                      |
| Mobile not-optimized          | ~5 real table/overflow risks (heuristic flags 20)     | ≈ stable                                      |
| Stale docs                    | ~0 real                                               | stable                                        |
| Missing tests                 | be 85 raw / sam 14 raw / fe 135 raw (heuristic)       | ↑ raw, but mostly `_`-private-module artifact |

**Headline:** Two clear wins since 2026-10-04 — the **frontend `fetch()` bypass dropped from 33
to 2** (the shared `apiService` migration largely landed), and **every frontend service and hook
now has a paired test** (last cycle flagged 7 services + 8 hooks untested; now 0). The new concern
is **frontend file-length regression**: three frontend files crossed 1000 lines
(`MemberPivotViews.tsx` 2007, `membersApiService.ts` 1267, `MembersPage.tsx` 1161) — frontend is
now the critical-length leader, where the SAM plane was last cycle. SAM still has 4 files > 1000.
The raw missing-test counts rose, but that is dominated by a **heuristic artifact**: refactor-split
private `_`-prefixed modules (e.g. `sam/shared/_verifier.py`, `sam/members/domain/_membership_writes.py`)
are covered through their public parent module, which a basename grep does not credit.

---

## 1. File Length (split candidates)

Excludes test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`, `dist/`, `.aws-sam/`.

### Critical (> 1000 lines) — 8 files

| File                                                       | Lines | Plane   | What to extract                                                   |
| ---------------------------------------------------------- | ----- | ------- | ----------------------------------------------------------------- |
| `frontend/src/components/members/analytics/MemberPivotViews.tsx` | 2007  | frontend | Split pivot builder / result rendering / preset+export into sub-components. 🆕 |
| `sam/members/migration/hdcn_backfill.py`                   | 1726  | sam     | One-off backfill — extract step helpers; lower risk.              |
| `sam/members/handler/app.py`                               | 1357  | sam     | Router handler — extract per-route dispatch into modules.         |
| `sam/members/repository/members_repository.py`             | 1333  | sam     | Split read / write / scope-filter query builders.                 |
| `frontend/src/services/membersApiService.ts`               | 1267  | frontend | Split per-resource client groups (members / column-prefs / config). 🆕 |
| `frontend/src/pages/MembersPage.tsx`                       | 1161  | frontend | Extract table, toolbar, pagination, and data-loading hooks. 🆕    |
| `sam/members/domain/_membership_writes.py`                 | 1134  | sam     | Split create / update / lifecycle write paths.                    |
| `backend/src/services/zzp_trip_import_service.py`          | 1119  | backend | Extract parse / validate / commit stages into cohesive helpers.   |

Note: last cycle's biggest file `sam/members/domain/membership_service.py` (2267) has since been
split — it no longer appears > 1000. `backend/src/services/projection_sync.py` (was 1368) also
dropped below the threshold.

### Notable 500–1000 line files (opportunistic)

- **Backend:** `str_database.py` 910, `_projection_config_builders.py` 920, `auth/cognito_utils.py` 894,
  `services/media_asset/lifecycle.py` 840, `routes/str_routes.py` 829, `routes/tenant_admin_users.py` 821,
  `services/cognito_service.py` 800, `pattern_analyzer.py` 793, `services/budget_mutation_service.py` 792.
- **Frontend:** `components/members/analytics/MemberMailCompose.tsx` 860,
  `components/members/analytics/MemberFieldPicker.tsx` 800,
  `components/members/analytics/MemberTemplateManager.tsx` 793,
  `components/TenantAdmin/MembersConfig/MembersFieldModal.tsx` 683,
  `components/TenantAdmin/MembersConfig/MembersTypedField.tsx` 664, `types/members.ts` 659,
  `components/pivot/PivotResultTable.tsx` 643.
- **SAM:** `domain/execute_and_deliver.py` 781, `domain/field_resolver.py` 757,
  `domain/attribute_catalog.py` 756, `domain/fixed_fields.py` 714, `worker/mail_send_worker.py` 666,
  `repository/projection_config_reader.py` 653, `domain/template_service.py` 618,
  `domain/lifecycle_config.py` 587.

Full scan saved at `.agent-output/cq-1-length.txt` during the run.

## 2. Dead Code

- **Backend (vulture ≥ 80): 0 findings.** Clean, consistent across cycles.
- **SAM (vulture ≥ 80, source only): 4 findings** — all low-confidence-of-safety given WHERE they sit:
  - `sam/members/repository/members_repository.py:102, 371, 596` — unused variable `scope_filter` (×3, 100%).
  - `sam/members/worker/mail_audit.py:96` — unused variable `actor_roles` (100%).
  - ⚠️ The `scope_filter` findings sit in **tenant-scoping repository code**. Verify they are not an
    intentional kwarg/local kept for signature uniformity or a half-wired scope filter **before**
    removing — a wrong deletion here is a cross-tenant risk, not a cleanup. (This recurs from the
    2026-10-04 run, where the same variable was flagged at different line numbers — the repository was
    refactored but the dead local persisted.)

## 3. Duplicate / Near-Duplicate Code

No new real duplication surfaced this cycle. The signature-frequency scan is dominated by expected
OOP dunders (`__init__` ×973, `__repr__`, `__eq__`) and third-party-shaped methods, and the frontend
"duplicate export" hits (`WarningIcon`, `ViewIcon`, … ×2 each) are **Chakra icon re-exports**, not
project duplication. The two genuine frontend duplicate utilities flagged last cycle
(`isValidEmail` in two util files; `buildApiUrl` in three places) should still be confirmed/collapsed —
carried forward as a low task. `resolveLabel` appears twice (backend-mirrored label resolver + a
frontend copy) — verify whether the two are intentional per-plane copies or a candidate for a shared
util.

## 4. (Non-)use of Frameworks / Reusable Building Blocks ← primary focus

### Frontend data fetching — down to 2 real bypasses (from 33)

The big win this cycle: the shared `services/apiService` migration largely landed. Only two
non-service `fetch()` sites remain:

| File                                                        | Note                                                             |
| ----------------------------------------------------------- | ---------------------------------------------------------------- |
| `frontend/src/pages/public/PublicLandingPage.tsx:230`       | `await fetch(url)` for a public, unauthenticated page — may be legitimate (no auth header needed); confirm it should still route through apiService for base-URL consistency. |
| `frontend/src/components/examples/TenantAwareComponent.example.tsx:137` | an `*.example.tsx` demo file — **exempt** (illustrative, not shipped logic). |

So effectively **one** borderline real site remains. Record and confirm.

### Backend / SAM — clean

- **Backend DB:** 0 raw `mysql.connector` bypasses outside `database.py` / `scalability_manager.py`.
  The 8 `execute(f"…")` hits (`financial_report_generator.py`, `year_end_journal_entries.py`,
  `xlsx_export.py`) are the same **false positives** as last cycle — the f-string is only a LIKE
  prefix inside the bound-parameter list (`[f"{administration}%", …]`); the SQL is parameterized.
- **Backend auth:** the route modules without `@cognito_required`/`@tenant_required` are the
  legitimately-public / aggregator / accessor files (`static_routes`, `config_routes`,
  `signup_routes`, `environment_routes`, `sysadmin_routes`, `landing_page_routes/public_endpoints`,
  `service_accessors`, `tenant_admin_template_constants`). Not real bypasses.
- **SAM:** 0 inline `boto3.resource('dynamodb')` outside `dynamodb_client.py`; 0 hand-rolled
  `jwt.decode`/`jose` outside `/shared/`. The DynamoDB grep hits are comments in
  `execute_and_deliver.py` and the legitimate injected-table reader
  `sam/pretokengen/projection_governance_reader.py:108` — not handler→repository boundary violations.

### Frontend — minor (low priority)

- **Theme:** hardcoded hex colors remain in chart/legend config (`.tsx`). Low priority.
- **Filters:** a few bespoke `useState`-filter / `.filter(..includes())` re-implementations where the
  shared `GenericFilter` framework exists. Low priority.

## 5. Type Safety

- **Frontend `any` (production): ~94 real.** The raw grep returns 243, but that is inflated by (a)
  comment lines containing the word "any" (e.g. "has any of the specified roles"), (b) the test-support
  mocks (`__mocks__/chakra-ui-react.tsx`, `TemplateManagement/chakraMock.tsx`), (c) `*.d.ts` and
  `setupTests.ts`. The real production `any` (~94) is spread thin across public landing blocks
  (`AboutBlock` `properties as any`), `types/parameterSchemaTypes.ts` (`default?: any`,
  `current_value?: any`), `utils/csvExport.ts` (`CellFormatter`/row types), zzp modals, and reports —
  the same thin spread as last cycle. The service-layer `Promise<any>` returns continue to persist.
- **Backend / SAM missing return hints (heuristic):** ~hundreds of inline `def` lines with no `->`,
  but this **overcounts** (multi-line signatures whose `->` lands on the closing-paren line). Rough
  indicator only; ANN rules are not enabled in ruff. Low priority.

## 6. Mobile Compliance (frontend)

Frontend remains **broadly mobile-ready**: `frontend/index.html` carries the correct
`<meta name="viewport" content="width=device-width, initial-scale=1" />`, **0 fixed 3-digit px
widths**, and Chakra responsive patterns are used widely. **0 `mobile-exempt` markers** found.

The heuristic "no responsive token on a `<Table>` page" flags 20 pages, but most render their table
through child components that DO carry wrappers — so this over-flags. The real horizontal-overflow /
no-mobile-fallback risks to verify (data-dense tables on primary flows):

| File                                              | Severity | Note                                   |
| ------------------------------------------------- | -------- | -------------------------------------- |
| `frontend/src/pages/CheckAccountsPage.tsx`        | Medium   | banking data table, user-facing        |
| `frontend/src/pages/CheckReferencePage.tsx`       | Medium   | banking data table, user-facing        |
| `frontend/src/pages/STRChannelRevenuePage.tsx`    | Medium   | revenue table, user-facing             |
| `frontend/src/pages/ZZPTrips.tsx`                 | Low      | large (1178-line) trips table — verify wrapper |
| `frontend/src/pages/ZZPInvoices.tsx` / `ZZPDebtors.tsx` | Low | zzp data tables — verify wrapper        |

Each needs a `TableContainer`/`overflowX` wrapper or a stacked/card mobile fallback **confirmed**
(the heuristic can't tell a wrapped child apart). Recurring category: new data tables keep landing
without an explicit responsive wrapper (noted the last two cycles).

## 7. Stale Documentation (light pass)

Essentially clean. No doc references modules that were split/removed. The historical point-in-time
status artifacts (`*_COMPLETE.md`, `*_SUMMARY/*_PLAN/*_REPORT.md` dated mid-2026) remain and could be
archived — lowest priority, no code contradiction.

## 8. Missing Tests (coverage gaps)

Filename-level heuristic (a source file is a candidate when no test file references its basename).
Raw counts: **backend 85 · SAM 14 · frontend 135**. These are UP from last cycle (be 47 / sam 0 / fe
157), but the jump is largely a **heuristic artifact** — read the classification below before treating
it as a regression.

### SAM — 14 raw, but ~all `_`-private refactor-split modules covered via parent

Every SAM candidate is a private `_`-prefixed module or a thin sub-module that is exercised through
its public parent, which the basename grep does not credit:

- `sam/shared/_verifier.py`, `_pool_registry.py`, `_auth_errors.py`, `_jwks.py` — the internals of
  `sam/shared/auth_utils.py` (JWTVerifier / pool registry / JWKS); covered via `auth_utils` tests.
- `sam/members/domain/_membership_{reads,writes,lifecycle,analytics,schedules,catalog}.py` — the
  split internals of the former `membership_service.py`; covered via the public service + handler tests.
- `sam/members/handler/_http.py`, `repository/mail_send_queue.py`, `repository/template_body_store.py`,
  `worker/mail_audit.py` — exercised via handler/worker tests.

**Action:** treat these as test-exempt-via-parent, but spot-check that the public parent's tests
actually drive the private module's branches (especially `_membership_writes.py` — tenant-scoped
writes). The one genuine gap worth a direct test is **`sam/members/worker/mail_audit.py`** (also has a
vulture dead-var finding — see §2), since audit logging is easy to under-cover.

### Backend — 85 raw; genuine high-risk gaps (same shortlist as last cycle, still open)

- **Test-exempt (not gaps):** 10 × `migrations/*` (one-off scripts, incl. the new
  `overrides_key_transform.py` which IS covered via `test_migrate_overrides_to_fixed_overrides.py` —
  heuristic miss), `wsgi.py`, `gunicorn.conf.py`, the `landing_page_renderers/*` (6) and
  `media_asset/*` (5) sub-modules (exercised via dispatch/parent — verify).
- **High risk (auth / DB / money / tenant-scoping / routes):**
  `services/year_end_journal_entries.py` (money/journal), `services/banking_mutatie_service.py`
  (DB/money), `admin_routes.py`, `audit_routes.py` (API routes), `routes/invoice_routes.py`,
  `routes/tax_routes.py`, `routes/user_routes.py`, `routes/chart_of_accounts_routes.py`.
- **Medium:** `services/zzp_invoice_delivery.py`, `services/zzp_invoice_numbering.py`,
  `services/zzp_invoice_factory.py`, `services/zzp_trip_calculation_service.py`,
  `services/zzp_trip_query_service.py`, `services/zzp_trip_crud_service.py`,
  `services/pivot_query_builder.py`, `services/chart_of_accounts_io_service.py`,
  `services/template_pdf_renderer.py`, `mutaties_cache_{loader,models,queries}.py`.
- **Low:** `xlsx_download_helpers.py`, `xlsx_styles.py`, `file_cleanup_actions.py`, `api_schemas.py`.

### Frontend — 135 raw; services & hooks now fully covered (improvement)

- 🎉 **Services: 0 untested. Hooks: 0 untested.** The 7 services + 8 hooks flagged on 2026-10-04 now
  all have paired tests. This is the cycle's clearest test-coverage win.
- The remaining 135 are predominantly **leaf/presentational** components (LandingPage blocks,
  public/blocks, SysAdmin panels) and **test-exempt** types/barrels — fill opportunistically, lowest
  priority.

---

## Comparison with 2026-10-04

| Metric                        | 2026-10-04              | 2026-10-15              | Trend                                        |
| ----------------------------- | ----------------------- | ----------------------- | -------------------------------------------- |
| Files > 1000 lines            | 5 (be 1 / sam 4)        | 8 (fe 3 / be 1 / sam 4) | ↑ frontend regressed (3 new > 1000)          |
| Frontend `fetch()` bypasses   | 33                      | 2 (1 real + 1 example)  | ↓↓ Big win — apiService migration landed     |
| FE untested services          | 7                       | 0                       | ↓↓ fixed                                     |
| FE untested hooks             | 8                       | 0                       | ↓↓ fixed                                     |
| Dead code (sam vulture)       | 4                       | 4                       | = same class, moved line numbers (persists)  |
| Mobile table risks            | 5                       | ~5 (verify)             | ≈ stable, recurring category                 |
| Frontend `any` (prod)         | 94                      | ~94                     | = stable                                     |

### Recurring Issues

1. **SAM `scope_filter` dead variable in tenant-scoping repository code** — flagged 2026-10-04 (lines
   74/194/335) and again now (102/371/596). The repo was refactored but the dead local travelled
   along. Resolve it deliberately (confirm scope-safety) rather than letting it recur a third cycle.
2. **Service-layer `Promise<any>`** persists across cycles.
3. **New data tables land without a responsive wrapper** — third cycle this category appears.

### New Debt Introduced Since

- 🆕 **Three frontend files crossed 1000 lines:** `MemberPivotViews.tsx` (2007 — now the single
  largest file in the repo), `membersApiService.ts` (1267), `MembersPage.tsx` (1161). The members
  analytics + config work this arc grew these files; frontend is now the critical-length leader.
- 🆕 **`backend/src/services/zzp_trip_import_service.py` (1119)** crossed 1000 — the trip-import
  redesign landed as one large service.

## Lessons / Recurring Issues

1. **The apiService migration proves the pattern works — now add a guard.** Dropping 33→2 `fetch()`
   bypasses is the headline win. Add an ESLint rule banning raw `fetch(`/`axios.` outside
   `src/services/` so the bypass can't creep back.
2. **Frontend length debt replaced SAM length debt.** As SAM files were split, the members
   analytics/config frontend grew past 1000. Apply the same cohesion-seam splitting to
   `MemberPivotViews.tsx` / `MembersPage.tsx` / `membersApiService.ts`.
3. **Kill `scope_filter` for good.** Two cycles of the same tenant-scoping dead variable is a signal
   to resolve it with intent (verify no scope regression, then delete) rather than re-flag it.
4. **A table needs a mobile story at creation** — make "no `TableContainer`/`overflowX`/card
   fallback" a review gate for any new `<Table>`.
