# Requirements Document

Code Quality Fixes — 2026-11-12 (local, source-level scan).

## Introduction

This spec captures the findings of a **local, static, source-level** code-quality review (no test-suite execution) run on 2026-11-12, and the prioritized improvement
tasks derived from them. Each requirement below is a scan dimension with its findings,
counts, and the delta vs the previous run (`code-quality-fixes-2026-10-28`). The
actionable work lives in `tasks.md`.

Nothing was fixed during this scan — this document is the analysis; `tasks.md` is the plan.

## Glossary

- **Plane** — one of the three code areas: `backend` (Flask/MySQL), `sam` (Lambda/DynamoDB
  members app), `frontend` (React/Chakra).
- **Bypass** — hand-rolled code that re-implements a shared building block instead of using it.
- **Critical file** — a source file > 1000 lines.
- **Missing-test candidate** — a source file whose basename is referenced by no test file
  (filename heuristic; see §8 for the verification caveat).
- **Test-exempt-via-parent** — a private `_`-prefixed module exercised through its public
  parent module's tests.

## Scan methodology / environment

- Run from `/home/peter/projects/myAdmin` (WSL Ubuntu), bash only.
- Global excludes applied: test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`,
  `dist/`, `.hypothesis/`, `mysql_data/`, `.agent-output/`, and SAM build artifacts
  (`sam/**/.aws-sam/**`, `sam/build/**`). §8 is the one section that reads test files.
- `vulture` is **not** installed in the root `.venv`; the scanner available in this repo is
  `backend/.venv/bin/vulture` (recorded because the prompt's command `vulture ...` fails as
  written).
- Raw scan dumps are written under `.agent-output/cq-*.txt` (git-ignored).
- Counts marked *(heuristic)* are pattern matches that over-count by construction (multi-line
  signatures, nested components, delegating wrappers) and must be re-verified before acting.

## Summary

| Dimension                                | Count (this run)                                                     | D vs 2026-10-28                                          |
| ---------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------- |
| Files 500-1000 lines                     | **122** (be 70 / fe 38 / SAM 25)                                     | approx stable; be grew (services + endpoint sub-modules) |
| Files > 1000 lines (critical)            | **11** (SAM 10 / fe 1 / be 0)                                        | UP from 9 - SAM regressed again (7 -> 10)                |
| Dead code (vulture >= 80)                | **0** (be 0 / SAM 0) + **3** orphan frontend components              | = 0 for vulture; fe orphans newly identified             |
| Duplicate patterns                       | **1 real**: inline auth guard x **32** across **8** files            | NEW measurement; `resolveLabel` (x8) now RESOLVED        |
| Framework/reusable-block bypasses        | **32** (backend auth) / fe 1 exempt / SAM 0 / DB 0                   | backend auth bypass newly surfaced (was unmeasured)      |
| SAM raw-shape boundary leaks             | **0** real                                                           | = 0 (guard code only; Members drift stays fixed)         |
| SAM foolproof-CRUD violations            | **0**                                                                | = 0 (migration backfills are sanctioned)                 |
| Type safety                              | fe `any` **113** prod / be hints **1248** raw / SAM hints **463** raw| approx stable (heuristic shape unchanged)                |
| Mobile not-optimized                     | heuristic **420** TSX w/o breakpoint / **166** hover / **0** exempt  | DOWN real risk - the 4 flagged table pages are wrapped   |
| Stale documentation                      | **2** residual                                                       | DOWN from ~5 (`docs/archive/` migration completed)       |
| Missing tests                            | be **47** / SAM **17** (all `_`-private) / fe **136**                | DOWN backend real gaps (prior high-risk routes tested)   |

**Headline:** the reduction work from last cycle largely landed, but two *unrelated*
regressions were found:

1. **SAM length debt** - files > 1000 lines in the SAM plane rose 7 -> 10.
2. **Intra-Flask auth-guard duplication** (previously unmeasured) - 32 inline guard blocks
   in 8 `backend/src/routes/*.py` files re-implement the backend's OWN `@tenant_required`
   decorator (`backend/src/auth/tenant_context.py:280`).

Neither finding is a SAM <-> Flask cross-plane duplication: the 32 sites are all in the Flask
backend, and the SAM plane has 0 hand-rolled auth guards (it uses `sam/shared/auth_utils.py`).

WINS -

1. **`resolveLabel` consolidation (last cycle task 1) is genuinely complete**: the shared
   `components/members/labelResolver.ts` is now the single implementation; the 9 remaining
   `resolveLabel` symbols are 8 thin one-line delegates plus that shared source, so real
   duplication is 0.
2. **The ESLint fetch/axios guard (task 2) is in place** - `frontend/eslint.config.mjs:89-121`
   bans raw `fetch(` / `axios.*` / hand-built `VITE_API_URL` outside `src/services/**`.
3. **The two largest SAM modules were split successfully** - `_membership_writes.py` (1940)
   and `_dispatch.py` (1479) are gone; both families now sit at 666-762 lines.
4. **Backend critical-length debt is 0** (was 1): `members_config_validation.py` decomposed
   into `_members_config_*` modules.
5. **The 4 data-dense table pages now have mobile wrappers** (`TableContainer` / `overflowY`).
6. **Previously-untested high-risk backend routes now have tests** -
   `backend/tests/api/test_admin_routes.py`, `test_audit_routes.py`,
   `test_system_health_routes.py`, `test_duplicate_detection_routes.py`,
   `test_members_analytics_audit.py` all exist.

REGRESSION - **SAM is again the critical-length leader with 10 files > 1000** (up from 7, and
from 4 two cycles ago): `hdcn_backfill.py` 1726, `config_fields_crud_service.py` 1712,
`handler/app.py` 1653, `members_repository.py` 1551, `mail_send_worker.py` 1236,
`table_design.py` 1172, `public_app.py` 1171, `config_write_service.py` 1119,
`handler/routes.py` 1074, `_dispatch_services.py` 1073.

NEW FINDING - **32 inline tenant-admin auth-guard blocks** across 8 backend route files
re-implement what `@tenant_required` (`backend/src/auth/tenant_context.py:280`) already
provides, and that decorator is adopted 308x elsewhere. This is simultaneously the largest
duplication and the largest framework bypass in the repo, and it carries a consistency /
security risk (each copy can drift on status code, role check, or tenant scoping).

---

## Requirement 1 - File length (split candidates)

Over-long source files are the usual home of duplication and dead code.

**Totals:** **122** files in 500-1000 lines / **11** files over 1000 lines (critical).
Critical: SAM 10 / frontend 1 / backend 0.

### 1a. Critical files (> 1000 lines) - 11

- `sam/members/migration/hdcn_backfill.py` - **1726**
- `sam/members/domain/config_fields_crud_service.py` - **1712**
- `sam/members/handler/app.py` - **1653**
- `sam/members/repository/members_repository.py` - **1551**
- `sam/members/worker/mail_send_worker.py` - **1236**
- `sam/members/repository/table_design.py` - **1172**
- `sam/members/handler/public_app.py` - **1171**
- `sam/members/domain/config_write_service.py` - **1119**
- `sam/members/handler/routes.py` - **1074**
- `sam/members/handler/_dispatch_services.py` - **1073**
- `frontend/src/components/members/analytics/MemberPivotViews.tsx` - **1054**

### 1b. Extraction seams per critical file

- `hdcn_backfill.py` (1726) - a one-off migration whose read / transform / write phases plus
  per-field strategies are separable: reading (`scan` paging), the field-shape transform table,
  the write phase, and the CLI/report harness.
- `config_fields_crud_service.py` (1712) - cohesive units hinted by its own section comments:
  read/overlay resolution, Change-Op apply, source-integrity guard, wire-key normalisation.
- `handler/app.py` (1653) - route table + the auth/authorize helpers
  (`_authenticate_and_authorize`, `_authorize_schedule_route`, `_resolve_scope_access_*`) +
  stale-bundle rejection; the authorize helpers form their own module.
- `members_repository.py` (1551) - CRUD/list/query paths plus projection reads; split by
  operation family, keeping the repository as the public surface (steering 35/39).
- `mail_send_worker.py` (1236) - SES send path, template render, audit logging, retry/backoff.
- `table_design.py` (1172) - table/key/schema definitions vs migration helpers.
- `public_app.py` (1171) - public intake routes vs submission/serve helpers.
- `config_write_service.py` (1119) - body normalisation (the `fixed_overrides`/`overrides`
  coercion), Change-Op planning, and apply orchestration.
- `handler/routes.py` (1074) + `_dispatch_services.py` (1073) - the `dispatch_*` fleet and the
  stale-bundle guard constants/helpers.
- `MemberPivotViews.tsx` (1054) - pivot builder, result rendering, preset/export; sibling
  `memberPivotViewsHelpers.ts` already exists as a seam.

### 1c. Files 500-1000 lines - 122 (opportunistic refactor only)

- **backend (70)** - top offenders: `str_database.py` 926, `auth/cognito_utils.py` 894,
  `routes/tenant_admin_users.py` 859, `services/media_asset/lifecycle.py` 852,
  `scalability_routes.py` 852, `routes/str_routes.py` 841, `services/cognito_service.py` 800,
  `pattern_analyzer.py` 793, `services/budget_mutation_service.py` 792,
  `services/projection_sync.py` 787, `routes/chart_of_accounts_routes.py` 787.
- **frontend (38, non-test)** - `services/members/membersResourceApi.ts` 994,
  `TenantAdmin/MembersConfig/ApplicationFormBuilder.tsx` 938,
  `members/analytics/MemberMailCompose.tsx` 790, `types/members.ts` 771,
  `TenantAdmin/MembersConfig/MembersFieldModal.tsx` 740,
  `members/analytics/MemberFieldPicker.tsx` 736, `MemberTemplateManager.tsx` 722,
  `ApplicationFieldModal.tsx` 700, `MembersTypedField.tsx` 664, `App.tsx` 645.
- **SAM (25)** - `domain/application_form_render.py` 957,
  `repository/projection_config_write_repository.py` 828, `domain/application_publish.py` 819,
  `domain/attribute_catalog.py` 811, `domain/_membership_writes_fieldconfig.py` 762,
  `domain/fixed_fields.py` 749, `domain/_membership_writes_validation.py` 722,
  `repository/_fields_overlay_reader.py` 721, `repository/slug_marker_store.py` 670.

Per principle 4, splits must extract one concern per module, keep the public import surface
stable (re-export from the original path), and change behavior in **zero** places.

---

## Requirement 2 - Dead code

Command: `backend/.venv/bin/vulture backend/src backend/vulture_whitelist.py
--min-confidence 80 --exclude validate_pattern/` and the same for `sam`
(excluding `.aws-sam`, `build`, `tests`).

- **backend: 0 findings** at confidence >= 80.
- **SAM: 0 findings** at confidence >= 80.
- **frontend orphaned components (heuristic: basename never referenced outside its own file):**
  - `frontend/src/components/FilterErrorBoundary.tsx` (109 lines) - **genuinely dead**, no import
    and no string/route reference anywhere in `frontend/src`.
  - `frontend/src/pages/ServiceUnavailable.tsx` - no reference outside itself; not registered in
    `App.tsx` / `appPages.tsx`.
  - `frontend/src/pages/ServerError.tsx` - no reference outside itself.
  - `frontend/src/components/ViolinChartExample.tsx` - demo file, no importers (candidate for
    removal or an explicit `*.example` rename).
- **Exempt (do not treat as dead):** `components/examples/*.example.tsx`,
  `src/__mocks__/**`, `components/TenantAdmin/TemplateManagement/chakraMock.tsx` (test double).

Verify a symbol is not referenced dynamically (route strings, lazy `import()`, template,
entry point) before deleting any of the above.

---

## Requirement 3 - Duplicate / near-duplicate code (code reduction)

### 3a. REAL - inline tenant-admin auth guard x 32 (8 files)

The block `auth_header.startswith("Bearer ")` -> `get_user_tenants(jwt_token)` ->
`if not is_tenant_admin(...)` -> `jsonify({"error": ...}), 401/403` is copy-pasted per handler:

| File | Copies |
| ---- | ------ |
| `backend/src/routes/tenant_admin_templates.py` | 6 |
| `backend/src/routes/tenant_admin_roles.py` | 6 |
| `backend/src/routes/chart_of_accounts_routes.py` | 5 |
| `backend/src/routes/tenant_admin_users.py` | 4 |
| `backend/src/routes/tenant_admin_template_ai_routes.py` | 3 |
| `backend/src/routes/tenant_admin_scope.py` | 3 |
| `backend/src/routes/tenant_admin_config.py` | 3 |
| `backend/src/routes/chart_of_accounts_io_routes.py` | 2 |

**Partially migrated, not un-migrated.** Each of these 8 files already applies
`@tenant_required` / `@cognito_required` / `@module_required` on *some* handlers
(2-7 decorators per file) while hand-rolling the guard on others - exactly the
half-migrated state the prompt warns against. The fix is to finish the migration in
the same file, not to introduce a new helper.

Single home it should live in: the existing `@tenant_required` decorator
(`backend/src/auth/tenant_context.py:280`), already used 308x in the codebase.

### 3b. RESOLVED - `resolveLabel`

9 symbols match, but `components/members/labelResolver.ts` is the single implementation and the
other 8 are one-line delegates (`return sharedResolveLabel(label, lang, fallback, ...)`).
No further consolidation required (optional cleanup in tasks.md Low).

### 3c. Minor / intentional repetition

- `return error_response(e, "...", status=500)` appears 18 (admin) / 16 (banking) / 11 (pivot) /
  10 (STR) / 10 (budget) times - distinct messages, already routed through the shared
  `error_response` helper. Not a reduction target.
- `strftime('%Y-%m-%d')` x 9 - trivial, not worth a helper.

---

## Requirement 4 - (Non-)use of frameworks / reusable building blocks

### Backend

- **DB access (DatabaseManager / dialect helpers): 0 bypasses.**
  `grep -rn "import mysql.connector|mysql.connector.connect" backend/src` returns only
  `database.py` / `scalability_manager.py` (the helpers' own implementations).
- **Raw SQL string interpolation: 0 real.** The 8 `execute(query, [f"{administration}%", ...])`
  hits in `report_generators/financial_report_generator.py`, `services/year_end_journal_entries.py`,
  `xlsx_export.py` interpolate **parameter values**, not SQL - parameterised (`%s`) calls, safe.
- **Auth decorators: 32 bypasses** (the 8 files in Requirement 3a). Routes **not** covered by
  `@cognito_required` / `@tenant_required` / `@module_required` (12 files) were reviewed and are
  legitimate: `routes/__init__.py`, `service_accessors.py`, `error_responses.py`,
  `tenant_admin_template_constants.py`, `static_routes.py`, `signup_routes.py`,
  `sysadmin_routes.py`, `environment_routes.py`, `config_routes.py`,
  `landing_page_routes/public_endpoints.py`, and the two package `__init__.py` files - these are
  public/unauthenticated-by-design or non-route modules, not bypasses.
- **Shared error envelope:** `jsonify({"error": "Invalid authorization"})` (32x) and
  `jsonify({"error": "Tenant admin access required"})` (22x) re-implement the standard envelope
  instead of `error_response` - folded into the auth-guard task.

### SAM plane

- **DynamoDB layering (steering 35): 0 real bypasses.** Hits are (a) explanatory comments naming
  the rejected `.scan()` anti-pattern in `handler/public_app.py`, `domain/execute_and_deliver.py`,
  and (b) two one-off migration scripts (`membership_type_catalog_to_field_options.py`,
  `functional_groups_list_to_map.py`) that legitimately page `table.scan(...)` / `table.put_item(...)`
  outside the runtime repository. `pretokengen/projection_governance_reader.py` uses a configured
  table handle. No handler/router crosses the repository boundary.
- **Raw boto3 client construction: 0** - no `boto3.resource("dynamodb")` outside
  `services/dynamodb_client.py`.
- **Data-shape boundary leaks (steering 39): 0 real.** `field_overlay` / `overrides` /
  `fixed_overrides` / `functional_groups` appear in `sam` only as (a) the jail/guard code that
  **rejects** the retired whole-overlay shape (`handler/routes.py:254`, `_dispatch_services.py:956-1001`,
  `public_app.py:694`, `app.py:1585`), and (b) the authoring **wire aliases** inside
  `domain/config_write_service.py` / `domain/config_fields_crud_service.py` that normalise
  `fixed_overrides` -> `overrides` on the boundary. No raw record shape crosses into a domain
  service, API response, or DTO. The Members field-config drift class remains closed.
- **Repository raw accessors on a cross-boundary path: 0.** `repository/_fields_overlay_reader.py`
  and `MembersProjectionReader.get_overlay` are repository-internal.
- **Foolproof-CRUD violations (ADR 0009 / spec 03): 0.** No raw `put_item` / `update_item` /
  `delete_item` on a `config#*` governance record outside the sanctioned Change-Op write
  repository; no handler/domain assembling a WHOLE `functional_groups`/overlay object; no
  frontend writing a whole `field_overlay` (the frontend uses per-identity Change-Ops).
- **SAM auth (shared auth_utils / entitlement_claim): 0 hand-rolled JWT decodes.**
  `grep -rn "jwt.decode|jwks|from jose|import jwt" SAM` (excluding `shared/`) returns nothing.

### Frontend

- **Direct axios/fetch bypasses: 1, exempt.** The only hit is
  `components/examples/TenantAwareComponent.example.tsx:137` - a demo file explicitly allow-listed
  in `frontend/eslint.config.mjs` (`**/*.example.{ts,tsx}`). All production data access goes
  through `src/services/**` / `apiService`.
- **Bespoke table/filter code: no new violations found** - the shared `GenericFilter` /
  Table Filter Framework are used; local `useState(...filter)` hits are component-local UI state,
  not re-implementations.

---

## Requirement 5 - Type safety

- **Frontend `any` in production code: 113** (raw grep `:\s*any\b|as any|<any>` minus
  `__tests__`, `*.test.*`, `__mocks__`, `setupTests`, `*.d.ts`). Concentrations:
  `components/reports/BnbYearMonthMatrix.tsx`, `BnbFutureReport.tsx`, `AangifteIbReport.tsx`,
  `BudgetDashboardTab.tsx`, `STRPricing.tsx`, `components/BankingProcessor.utils.ts`,
  `pages/public/blocks/*` (`properties as any`), `types/parameterSchemaTypes.ts`.
  Most are `useState<any>(null)` result holders and sort comparators - reducible to
  concrete/union types or the existing `types/**` shapes.
- **Backend functions without a return type hint: 1248 raw** *(heuristic)* -
  `grep -rn "def \w\+(" backend/src | grep -v -- '->'`. Over-counts every multi-line signature
  whose `->` sits on a continuation line. Concentrations: `services/budget_query_service.py`,
  `services/budget_ai_service.py`, `services/zzp_*`, `services/year_end_service.py`.
- **SAM functions without a return type hint: 463 raw** *(heuristic)* - same caveat.
  Concentrations: `handler/router.py`, `handler/_dispatch_services.py`, `handler/app.py`
  (`_authenticate_and_authorize`, `_resolve_scope_access_*`), `handler/_dispatch_*.py`,
  `worker/mail_audit.py`.

---

## Requirement 6 - Mobile compliance (frontend)

- **Viewport meta: OK** - `frontend/index.html:6` has
  `<meta name="viewport" content="width=device-width, initial-scale=1" />`.
- **No responsive-breakpoint token: 420 `.tsx`** *(heuristic)* - `grep -rL
  "@media|sm:|md:|lg:|breakpoints|useMediaQuery|useBreakpointValue"`. This over-counts badly:
  it includes `__tests__` files and every component that inherits responsiveness from a shared
  layout/parent. **No new real violation** was identified this cycle.
- **Fixed pixel widths: 1 file, effectively exempt** -
  `components/TenantAdmin/MembersConfig/pageStyles.ts` (`min-width: 280px`, `max-width: 800/1100px`)
  inside generated landing-page CSS that **does** carry `@media (max-width: 768px)` /
  `(max-width: 480px)` blocks and a `(min-width: 769px)` upgrade. Not a violation.
- **Hover-only interactions: 166** occurrences of `:hover` / `_hover` *(heuristic)* - most are
  Chakra decorative states on already-tappable controls; no hover-only *action* was found in the
  primary flows.
- **Table overflow (the recurring category): resolved for the 4 flagged pages.**
  `pages/CheckAccountsPage.tsx` (208/271), `pages/CheckReferencePage.tsx` (220/314),
  `pages/STRChannelRevenuePage.tsx` (207/285) now wrap tables in `TableContainer` with
  `overflowY="auto"`. `pages/TransactionsPage.tsx` is a **false positive** - it renders no table;
  it delegates to `components/banking/BankingMutatiesTab`, which owns the responsive wrapper.
- **Explicit exemption markers: 0** (`grep -rn "mobile-exempt" frontend/src` is empty). No
  component claims an exemption, so none is counted as exempt.

---

## Requirement 7 - Stale documentation (light pass)

- `docs/archive/` already holds the historical artifacts
  (`FIELD_MAPPINGS_VALIDATION_REPORT.md`, `ENVIRONMENT_VALIDATION_COMPLETE.md`,
  `BACKEND_RBAC_UPDATE_PLAN.md`, `OPENAPI_DOCUMENTATION_COMPLETE.md`, `MYSQL_UPDATE_SUMMARY.md`).
- **2 residual point-in-time docs outside `archive/`:**
  `backend/tests/TESTING_COMPLETE_SUMMARY.md`, `backend/docs/RBAC_IMPLEMENTATION_SUMMARY.md`.
- No doc references a deleted module, retired endpoint, or retired framework was found; the ADRs
  in `docs/decisions/0001-0010` still match the code (notably 0009 config-fields Change-Op,
  which the scan confirms is honoured).

---

## Requirement 8 - Missing tests (test coverage gaps)

Conventions: backend `backend/src/**` -> `backend/tests/**`; SAM `sam/**` ->
`sam/tests/**`; frontend `frontend/src/**` -> co-located `*.test.ts(x)` or a sibling `__tests__/`.
Heuristic: a source file whose basename is referenced by no test file.

**Backend: 47 candidates** (excluding `migrations/` and `__init__`; basename absent from every
`backend/tests/**/*.py`). Notable, risk-ranked:

- **High (tenant-scoping / service correctness):** `services/_projection_scopegrant.py`,
  `services/_projection_scope_builder.py`, `services/zzp_invoice_delivery.py`,
  `services/zzp_invoice_numbering.py`, `services/zzp_invoice_factory.py`,
  `services/zzp_trip_crud_service.py`, `services/zzp_trip_query_service.py`,
  `services/chart_of_accounts_io_service.py`, `services/pivot_query_builder.py`,
  `services/invoice_test_ai_rerun.py`, `pdf_decision_handler.py`.
- **Medium (route modules):** `routes/chart_of_accounts_io_routes.py`, `routes/zzp_time_routes.py`,
  `routes/media_asset_routes/{sysadmin,admin,user,admin_maintenance}_endpoints.py`,
  `routes/landing_page_routes/{sysadmin,domain,draft,version,branding,slug,image}_endpoints.py`.
- **Test-exempt:** `wsgi.py`, `gunicorn.conf.py` (entry points); `api_schemas.py`,
  `routes/tenant_admin_template_constants.py`, `routes/service_accessors.py` (declarations/glue);
  `_members_config_fields.py`, `_members_config_scalars.py`, `_members_config_labels.py`,
  `_projection_*_builder.py`, `_projection_config_common.py`, `_projection_source.py`,
  `landing_page_renderers/*`, `mutaties_cache_*`, `xlsx_styles.py`, `scalability_workers.py`
  (private/leaf, exercised via their public parents).
- **Caveat:** the prompt's stricter loop
  (`grep -q -e "import .*\b$base\b" -e "from .*\b$base\b"`) reports 89; verification showed it
  over-counts - e.g. `admin_routes`, `audit_routes`, `system_health_routes`,
  `duplicate_detection_routes`, `members_analytics_audit` **do** have tests under
  `backend/tests/api/`. The 47 above is the verified figure.

**SAM: 17 candidates - all test-exempt-via-parent** (`_`-prefixed or package-private):
`handler/_dispatch_analytics.py`, `handler/_dispatch_members.py`, `domain/_membership_writes_crud.py`,
`domain/_membership_analytics.py`, `domain/_membership_reads.py`, `domain/_membership_schedules.py`,
`domain/_delivery_models.py`, `domain/application_messages.py`, `repository/_scope_reader.py`,
`repository/_mail_config_reader.py`, `repository/_config_reader_base.py`,
`repository/mail_send_queue.py`, `repository/template_body_store.py`, `shared/_pool_registry.py`,
`shared/_verifier.py`, `shared/_auth_errors.py`, `shared/_jwks.py`. No gap to open.

**Frontend: 136 candidates.** Genuine medium-value gaps (branch-bearing hooks/models/services):
`components/members/analytics/useMemberSetLibrary.ts`, `useMemberPivotExport.ts`,
`memberPivotViewsHelpers.ts`, `memberTemplateManager.helpers.ts`, `memberMailHelpers.ts`,
`services/members/membersResourceApi.ts`, `membersColumnPreferencesApi.ts`, `membersPageSize.ts`,
`config/pivotDataSources.ts`, `components/TenantAdmin/useStorageTab.ts`,
`components/help/helpLinks.ts`.
Test-exempt (types-only / barrels / leaf presentational / demo): `types/*.ts`,
`pages/public/blocks/*`, `pages/public/*` presentational shells, `appPages.tsx`,
`components/ViolinChartExample.tsx`, `context/AuthContext.example.tsx`,
`TenantAdmin/TemplateManagement/chakraMock.tsx`, and the `zzp/*` leaf modals.

---

## Comparison with the previous run (2026-10-28)

| Metric                          | 2026-10-28                              | 2026-11-12                       | Trend                                        |
| ------------------------------- | --------------------------------------- | -------------------------------- | -------------------------------------------- |
| Files > 1000 lines              | 9 (SAM 7 / be 1 / fe 1)                | 11 (SAM 10 / fe 1 / be 0)     | UP - SAM regressed again; backend cleared |
| Largest source file             | `_membership_writes.py` 1940            | `hdcn_backfill.py` 1726          | DOWN (split landed)                          |
| Dead code (vulture >= 80)       | 0                                       | 0                                | = stable                                     |
| `resolveLabel` copies (fe)      | 8                                       | 1 real + 8 thin delegates        | DOWN - consolidation RESOLVED                |
| Raw fetch/axios bypasses        | 1 exempt                                | 1 exempt                         | = stable (ESLint guard now enforces it)      |
| Backend auth-guard duplication  | not measured                            | **32 inline blocks / 8 files**   | NEW - surfaced this run                      |
| Mobile table risks              | ~4                                      | 0 real (1 false positive)        | DOWN - wrappers landed                       |
| Frontend `any` (prod)           | ~123 raw                                | 113                              | approx stable                                |
| Missing tests (backend)         | ~60 raw                                 | 47 verified (89 raw heuristic)   | DOWN - prior high-risk routes now tested     |

### Resolved since (previously flagged)

- `resolveLabel` duplication (8 copies) - now one shared `labelResolver.ts`.
- ESLint fetch/axios guard - added as `no-restricted-syntax` in `frontend/eslint.config.mjs`.
- SAM `_membership_writes.py` (1940) and `_dispatch.py` (1479) - both split.
- Backend `members_config_validation.py` (>1000) - split into `_members_config_*`.
- Mobile table wrappers on the 4 flagged pages.
- Tests for `admin_routes` / `audit_routes` / `system_health_routes` /
  `duplicate_detection_routes` / `members_analytics_audit`.
- Stale-doc archival into `docs/archive/`.

### New debt introduced since 2026-10-28

- SAM critical files **7 -> 10**; new entrants `migration/hdcn_backfill.py` (1726),
  `handler/app.py` (1653), `repository/members_repository.py` (1551),
  `repository/table_design.py` (1172), `worker/mail_send_worker.py` (1236),
  `handler/routes.py` (1074), `handler/_dispatch_services.py` (1073).
- **32 inline tenant-admin auth guards** across 8 route files (duplication + decorator bypass).
- 3 orphaned frontend components (`FilterErrorBoundary.tsx`, `ServiceUnavailable.tsx`,
  `ServerError.tsx`).

---

## Lessons / Recurring Issues

1. **Length debt migrates between planes rather than net-reducing (5th consecutive cycle).**
   Last cycle's split of `_membership_writes.py` and `_dispatch.py` was real and correct, yet the
   SAM plane still ended **higher** (7 -> 10) because the config-fields and handler arcs grew
   new large modules in the same window. Splitting individual files is not enough - apply the
   cohesion-seam gate at *creation* time for SAM handler/domain/repository modules, and treat
   "new module > 800 lines" as a review block. The backend plane shows this can be beaten
   (critical count 1 -> 0) when the split is done as the module is written.
2. **A duplication fix is only complete when every call site moves.** `resolveLabel` is now the
   *good* example (one shared impl, thin shims) - hold the auth-guard consolidation to the same
   bar: delete the inline blocks, do not leave a half-migrated split.
3. **Enforce the shared auth decorator.** `@tenant_required` exists, is documented, and is used
   308x, yet 8 route files still hand-roll the guard. This is the same class of drift as the
   Members field-config leak: a correct shared building block bypassed by copy-paste. Add a lint/
   review gate for `is_tenant_admin(` appearing outside `auth/tenant_context.py`.
4. **Service-layer `any` persists** across cycles (now 113 prod). It never regresses much but never
   gets closed either - collapse it by type (start with `services/**` and `components/reports/**`).
5. **The mobile table category finally closed** - keep the "a table needs a responsive wrapper
   at creation" gate, since it took 4 cycles to clear.
6. **The missing-test heuristic needs verification before acting.** The prompt's stricter loop
   reported 89 backend gaps; 42 were false positives because the test imports the module
   indirectly. Verify by grepping the module basename across `backend/tests/**` before opening a
   test task.
