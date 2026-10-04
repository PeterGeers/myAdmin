# Code Quality Fixes — 2026-10-04

## Summary

**Local, source-level** code-quality scan (no CI, no test execution) of the myAdmin repo on
`main`, 2026-10-04. Covers file length, dead code, duplication, framework/reusable-block
(non-)use, type safety, mobile compliance, stale docs, and missing-test gaps.

| Dimension                       | Count (this run)                                   | Δ vs 2026-09-03 (last cycle)         |
| ------------------------------- | -------------------------------------------------- | ------------------------------------ |
| Files 500–1000 lines            | 93 (be 68 / fe 25) + sam 4                          | ↑ (89 last; sam not tracked prior)   |
| Files > 1000 lines (critical)   | **5** (be 1 / sam 4)                               | ↑ net, but backend ↓ 4→1 (see below) |
| Dead code (vulture ≥ 80)        | be 0 · sam 4 (source only)                         | be — stable · sam first tracked      |
| Duplicate patterns              | 3 backend + 3 frontend (6)                         | first tracked this cycle             |
| Framework bypasses              | **33** (frontend `fetch` → apiService) + minor     | first tracked this cycle             |
| Type safety                     | fe `any` 94 (prod) · be/sam missing-hint heuristic | fe ↑ (prior counted service only)    |
| Mobile not-optimized            | 5 tables (admin/sysadmin) · 0 exempt               | ↓ from ~6 (different set, improved)  |
| Stale docs                      | ~0 real (light pass clean)                         | first tracked this cycle             |
| Missing tests                   | be 47 · sam 0 · fe 157 (incl. exempt)              | first tracked this cycle             |

**Headline:** The backend file-length debt dropped sharply — the four backend files that were
> 1000 lines last cycle (`media_asset_service.py` 2984, `landing_page_routes.py` 1611,
`landing_page_renderers.py` 1118, `media_asset_routes.py` 1023) have all been split into cohesive
sub-modules. Only one backend file remains > 1000 (`projection_sync.py` 1368). The **SAM plane is
now the primary file-length concern** (4 files > 1000, led by `membership_service.py` at 2267).
The single clearest, broad-reach improvement this cycle is the **frontend data-fetch bypass**: 33
direct `fetch()` calls that skip the shared `services/apiService` layer.

---

## 1. File Length (split candidates)

Excludes test files, `.venv/`, `node_modules/`, `__pycache__/`, `build/`, `dist/`, `.aws-sam/`.

### Critical (> 1000 lines) — 5 files

| File                                             | Lines | Plane   | What to extract                                              |
| ------------------------------------------------ | ----- | ------- | ----------------------------------------------------------- |
| `sam/members/domain/membership_service.py`       | 2267  | sam     | Split by concern: reads vs writes vs lifecycle vs catalog.  |
| `sam/members/migration/hdcn_backfill.py`         | 1723  | sam     | One-off backfill script — extract step helpers; lower risk. |
| `sam/members/handler/app.py`                     | 1375  | sam     | Router handler — extract per-route dispatch into modules.   |
| `backend/src/services/projection_sync.py`        | 1368  | backend | Extract per-entity sync routines + the diff/apply helpers.  |
| `sam/shared/auth_utils.py`                        | 1017  | sam     | Split JWTVerifier / pool-registry / entitlement helpers.    |

### Notable 500–1000 line files

- **Backend (68 total):** `environment/consistency_guard.py` 965, `str_database.py` 910,
  `auth/cognito_utils.py` 894, `routes/tenant_admin_users.py` 839, `routes/str_routes.py` 829,
  `services/cognito_service.py` 800, `pattern_analyzer.py` 793, `services/budget_mutation_service.py` 792,
  `scalability_routes.py` 789, …
- **Frontend (25 total):** `pages/MembersPage.tsx` 956, `components/TenantAdmin/MembersConfig/MembersTypedField.tsx` 649,
  `components/pivot/PivotResultTable.tsx` 578, `components/reports/BnbActualsReport.tsx` 583,
  `components/TenantAdmin/LandingPage/LandingPageEditor.tsx` 581, `App.tsx` 601, …
- **SAM (4 in 500–1000):** `domain/fixed_fields.py` 714, `domain/field_resolver.py` 625,
  `domain/lifecycle_config.py` 587, `repository/members_repository.py` 546.

(Full backend+frontend list saved at `.agent-output/filelen_bf.txt` during the scan.)

## 2. Dead Code

- **Backend (vulture ≥ 80): 0 findings.** Clean, consistent with last cycle.
- **SAM (vulture ≥ 80, source only — excluding `.aws-sam/` build artifacts and `sam/tests/`): 4 findings.**
  - `sam/members/domain/tenant_hooks.py:124` — unused variable `user`.
  - `sam/members/repository/members_repository.py:74, 194, 335` — unused variable `scope_filter` (×3).
  - ⚠️ The `scope_filter` findings sit in **tenant-scoping repository code**. Verify they are not an
    intentional kwarg kept for signature uniformity / dynamic dispatch **before** removing — a wrong
    deletion here is a cross-tenant risk.
- **Frontend:** 1276 export statements in production code (heuristic baseline only; no deep
  unused-export / orphaned-component analysis performed this cycle).

## 3. Duplicate / Near-Duplicate Code

### Backend — 3 copy-paste patterns in the route layer

| Pattern            | Repeat count | Where                                                                                                                      | Consolidate into                              |
| ------------------ | ------------ | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `_caller_token()`  | 8 modules    | `admin_routes`, `sysadmin_health`, `tenant_admin_roles/users/email/scope`, `sysadmin_helpers`, `sysadmin_roles`            | one shared helper (docstrings literally say "Mirrors …") |
| `_resolve_pool_id()` | 7 modules  | `admin_routes`, `tenant_admin_roles/users/email/scope`, `sysadmin_helpers`, `sysadmin_roles`                              | same shared helper (wraps `resolve_pool_id_for_token(_caller_token())`) |
| `_get_service()`   | 11 modules   | `toeristenbelasting_generator`, `google_drive_storage`, `pivot_routes`, `parameter_admin_routes`, `tenant_function_routes`, `asset_routes`, `media_asset_routes/__init__`, `contact_routes`, `signup_routes`, `tax_rate_admin_routes`, `product_routes` | a shared lazy-service accessor factory |

`_caller_token`/`_resolve_pool_id` are confirmed near-identical. `sysadmin_helpers.py` already
holds canonical copies — the others should import from there rather than re-define.

### Frontend — 3 duplicate utilities

- `isValidEmail` — `utils/validationHelpers.ts` **and** `utils/emailVerificationUtils.ts`.
- `buildApiUrl` — `config/api.ts`, `services/apiService.ts`, **and** `config.ts` (3 copies of URL building).
- `getRequiredPlaceholders` — `types/template.ts`, `TemplateManagement/TemplateManagementHelpers.tsx`,
  `TemplateManagement/TemplateManagement.tsx` (one is likely a type re-export; verify).

## 4. (Non-)use of Frameworks / Reusable Building Blocks ← primary focus

### Frontend data fetching — 33 direct `fetch()`/axios calls bypassing `services/apiService`

The shared API layer (`services/apiService`, `buildApiUrl`) is bypassed by raw `fetch()` in
components/pages/hooks/utils. By file:

| File                                                     | Calls | Note                                               |
| -------------------------------------------------------- | ----- | -------------------------------------------------- |
| `components/TenantAdmin/UserManagement.tsx`              | 10    | all `buildApiUrl` + manual headers — should use apiService |
| `components/TenantAdmin/useStorageTab.ts`                | 6     | raw `${API_URL}` interpolation                     |
| `components/TenantAdmin/CredentialsManagement.tsx`       | 5     | raw `${import.meta.env.VITE_API_URL}` interpolation |
| `utils/missingInvoicesProcessor.ts`                      | 3     | `buildApiUrl`                                      |
| `pages/Login.tsx`                                        | 2     | `buildApiUrl`                                      |
| `components/TenantAdmin/TenantAdminDashboard.tsx`        | 1     | raw `${apiUrl}`                                    |
| `components/LanguageSelector.tsx`                        | 1     | bare relative `/api/user/language`                 |
| `pages/public/blocks/ContactBlock.tsx`, `pages/public/PublicLandingPage.tsx`, `hooks/useAssetSearch.ts`, `components/common/AssetPicker/AssetPicker.tsx`, `components/TenantAdmin/AccountModal.tsx`, `App.tsx`, `components/examples/TenantAwareComponent.example.tsx` | 1 each | mix of `buildApiUrl`, bare relative, injected URL |

**Adopt:** route all of these through `services/apiService` (which centralizes base-URL resolution,
auth headers, and error unwrapping). The `${import.meta.env.VITE_API_URL}` / `${API_URL}` hand-built
URLs are the worst offenders — they re-implement what `buildApiUrl`/apiService already own.

### Backend / SAM — clean

- **Backend DB:** 0 raw `mysql.connector` bypasses outside `database.py`/`scalability_manager.py`.
  The 8 `execute(f"…")` hits (`financial_report_generator.py`, `year_end_journal_entries.py`,
  `xlsx_export.py`) are **false positives** — the f-string sits only inside the parameter list
  (`[f"{administration}%", …]`); the SQL itself is parameterized. No injection, no bypass.
- **Backend auth:** 7 route modules lack `@cognito_required`/`@tenant_required`/`@module_required`
  (`static_routes`, `config_routes`, `signup_routes`, `landing_page_routes/public_endpoints`,
  `environment_routes`, `sysadmin_routes`, `tenant_admin_template_constants`). The first five are
  legitimately public; the last two are blueprint aggregators. Not flagged as real bypasses.
- **SAM:** 0 inline `boto3.resource('dynamodb')` outside `dynamodb_client.py`; 0 hand-rolled
  `jwt.decode`/`jose` outside `/shared/`. The one `.query()` hit
  (`sam/pretokengen/projection_governance_reader.py:108`) is a legitimate injected-table reader class
  that parallels the MySQL `GovernanceReader` — not a handler→repository boundary violation.

### Frontend — minor

- **Theme:** 108 hardcoded hex colors in `.tsx` (many in chart/legend config). Low priority.
- **Filters:** 7 bespoke `useState`-filter / `.filter(..includes())` re-implementations where the
  shared `GenericFilter` framework exists. Low priority.

## 5. Type Safety

- **Frontend `any` (production, excluding mocks/`.d.ts`/`setupTests`): 94.** The raw grep returns
  264, but 158 of those are in test-support mocks (`__mocks__/chakra-ui-react.tsx` 107,
  `TemplateManagement/chakraMock.tsx` 48) + `react-i18next.d.ts` 8 + `setupTests` 3 — all exempt.
  The real 94 are spread thin (3–5 per file) across zzp modals (`TripModal` 5, `TimeEntryModal`/
  `ProductModal`/`ContactModal`/`VehicleModal` 3–4), reports (`BnbYearMonthMatrix`,
  `BudgetDashboardTab`, `BnbViolinsReport`, `AangifteIbReport`), filters (`GenericFilter`,
  `FilterPanel` 3 each), services (`parameterService` 3), and `csvExport` (3). The service-layer
  `Promise<any>` returns flagged last cycle (`productService`, `contactService`, `taxRateService`,
  `fieldConfigService`) persist.
- **Backend / SAM missing return hints (heuristic): ~556 backend / ~174 SAM** inline `def` lines with
  no `->`. This **overcounts** — the grep flags multi-line signatures where the `->` lands on the
  closing-paren line. Treat as a rough indicator, not an exact count. Low priority (ANN rules are not
  enabled in ruff).

## 6. Mobile Compliance (frontend)

Overall the frontend is **broadly mobile-ready**: `index.html` carries the correct
`<meta name="viewport" content="width=device-width, initial-scale=1">`, and Chakra responsive
patterns (`{ base, md }`, `display={{ base, md }}`, `useBreakpointValue`, card fallbacks) are used
widely. **0 fixed 3-digit px widths** and **0 `mobile-exempt` markers** found.

**Violations — 5 data tables with neither a responsive wrapper (`TableContainer`/`overflowX`) nor a
mobile breakpoint/card fallback** (horizontal-overflow risk):

| File                                               | Severity | Note                               |
| -------------------------------------------------- | -------- | ---------------------------------- |
| `components/TenantAdmin/CredentialsManagement.tsx` | Medium   | tenant-admin, user-facing          |
| `components/TenantAdmin/TaxRateManagement.tsx`     | Medium   | tenant-admin, 12 table elements    |
| `components/SysAdmin/HealthCheck.tsx`              | Low      | sysadmin-only                      |
| `components/SysAdmin/PipelineResultsPanel.tsx`     | Low      | sysadmin-only, 28 table elements   |
| `components/SysAdmin/PipelineLogAndErrors.tsx`     | Low      | sysadmin-only                      |

The 147 `_hover`/`:hover` occurrences are Chakra tokens with normal tap/focus fallbacks — cosmetic,
not violations. **Improvement vs last cycle:** the 6 tables flagged on 2026-09-03 (`STRInvoice`,
`MediaAssetAdminPage`, `InvoiceVatTotals`, `BudgetNewVersionModal`, `CheckAccountsPage`,
`ContactModal`) now have wrappers or card fallbacks; the current set is a different, smaller, more
admin-centric group.

## 7. Stale Documentation (light pass)

Essentially clean. No doc references the modules that were split/removed last cycle
(`media_asset_service.py`, `landing_page_routes.py`, `landing_page_renderers.py`,
`media_asset_routes.py`) — the refactor left no dangling doc references. The infra EC2 docs reference
EC2, but `infrastructure/README.md` explicitly marks it **"Disabled (Railway is used instead)"**
alongside `ec2.tf.disabled` — accurate, not stale. The only light signal is a set of point-in-time
status artifacts (`ENVIRONMENT_VALIDATION_COMPLETE.md`, `OPENAPI_DOCUMENTATION_COMPLETE.md`, and
`backend/*_SUMMARY/*_PLAN/*_REPORT.md`, all dated 2026-06-26) that are historical and could be
archived — lowest priority, no code contradiction.

## 8. Missing Tests (coverage gaps)

Filename-level heuristic (a source file is a candidate when no test references its basename). Reads
test files by design.

### Backend — 47 candidates

- **Test-exempt (not gaps):** `wsgi.py`, `gunicorn.conf.py` (entrypoints); 8 × `migrations/*`
  (one-off scripts). The `landing_page_renderers/*` (6) and `media_asset/*` (5) sub-modules are
  likely exercised via their dispatch/parent module — verify before counting.
- **High risk (auth / DB / money / tenant-scoping / routes):**
  `security_validators.py`, `year_end_journal_entries.py` (money/journal),
  `database_banking_queries.py` + `services/banking_mutatie_service.py` (DB/money),
  `services/scope_canon.py` (tenant-scoping), `services/google_oauth_service.py` (auth),
  `admin_routes.py`, `audit_routes.py` (API routes).
- **Medium:** zzp invoice/trip services (`zzp_invoice_delivery`, `zzp_invoice_numbering`,
  `zzp_invoice_factory`, `zzp_trip_calculation_service`, `zzp_trip_query_service`,
  `zzp_trip_crud_service`), `pivot_query_builder.py`, `chart_of_accounts_io_service.py`,
  `template_pdf_renderer.py`, `invoice_test_ai_rerun.py`, `mutaties_cache_{loader,models,queries}.py`,
  `pdf_parsing_strategies.py`.
- **Low:** `xlsx_download_helpers.py`, `xlsx_styles.py`, `file_cleanup_actions.py`.

### SAM — 0 candidates

Every SAM source module is referenced by a test. Strongest-covered plane.

### Frontend — 157 candidates

- **Test-exempt (not gaps):** `types/*` (7, type-only), config/barrel/trivial pages
  (`NotFound.tsx`, `ServerError.tsx`, `ServiceUnavailable.tsx`), `components/examples/*`.
- **High / Medium risk — services & hooks (the testable logic):**
  - **7 untested services:** `routePresetService`, `yearEndConfigService`, `vehicleService`,
    `domainApi`, `landingPageApi`, `tripService`, `mediaAssetService`.
  - **8 untested hooks** — the banking cluster is the priority (money logic): `useBankingProcessor`,
    `useBankingPatterns`, `useBankingUpload`, `useBankingState`, `useCheckAccounts`,
    `useCheckReference`, `useTransactions`, `useStrChannelRevenue`.
- **Medium — data pages:** `TransactionsPage.tsx`, `CheckAccountsPage.tsx`, `CheckReferencePage.tsx`.
- **Lower — presentational:** the bulk of the LandingPage (26), public/blocks (10), and SysAdmin (10)
  components are leaf/presentational; fill opportunistically.

---

## Comparison with 2026-09-03

> Note: the 2026-09-03 run was a combined test-suite + code-quality report, so some of its headline
> numbers (ruff lint, test failures) are out of scope for this static-only scan. The comparison below
> is limited to the shared static dimensions.

| Metric                        | 2026-09-03         | 2026-10-04              | Trend                                      |
| ----------------------------- | ------------------ | ----------------------- | ------------------------------------------ |
| Backend files > 1000 lines    | 4                  | 1                       | ↓ Good — the big-four were split           |
| Files 500–1000 (be+fe)        | 89                 | 93                      | ↑ slight — splits created more mid files   |
| SAM files > 1000              | not tracked        | 4                       | 🆕 now the main length concern             |
| Dead code (vulture)           | be Pass            | be Pass · sam 4         | be stable · sam newly surfaced             |
| Mobile tables not-optimized   | 6                  | 5                       | ↓ Good — prior set fixed, new set is admin |
| Frontend `any` (prod)         | ~30 (service only) | 94 (whole app)          | scope widened; service-layer still present |

### Recurring Issues

1. **Service-layer `Promise<any>`** flagged on 2026-09-03 (`productService`, `contactService`,
   `taxRateService`, `fieldConfigService`) is still present — carried into this cycle's broader 94.
2. **Frontend tables shipping without responsive wrappers** recurs as a category (different files each
   cycle). New table components keep landing without a `TableContainer`/`overflowX` or card fallback —
   a lint/review rule would stop the churn.

### New Debt Introduced Since

- 🆕 **SAM `membership_service.py` (2267) and `handler/app.py` (1375)** are now the largest files in
  the repo — SAM length debt grew while backend length debt shrank.
- 🆕 **33 frontend `fetch()` bypasses** of the shared apiService (first time this dimension was
  measured; several in newer TenantAdmin code using raw `import.meta.env.VITE_API_URL`).

## Lessons / Recurring Issues

1. **Splitting worked — keep the seam discipline.** The backend > 1000-line cluster was successfully
   broken up with no apparent stale doc fallout. Apply the same cohesion-seam approach to the SAM
   plane next; it is now where the length debt lives.
2. **Centralize data fetching once.** 33 raw `fetch()` calls (especially the `${VITE_API_URL}`
   hand-built URLs) re-implement what `services/apiService` already owns. Migrate them and add a lint
   rule so new components can't reintroduce the bypass.
3. **Verify `scope_filter` before deleting.** The SAM dead-code hits are in tenant-scoping repository
   code — confirm they aren't an intentional signature kwarg before removal; a wrong cut is a
   cross-tenant risk, not a cleanup.
4. **A table needs a mobile story at creation.** This is the second cycle a fresh batch of unwrapped
   tables appears. Treat "no `TableContainer`/`overflowX`/card fallback" as a review gate for any new
   `<Table>`.
