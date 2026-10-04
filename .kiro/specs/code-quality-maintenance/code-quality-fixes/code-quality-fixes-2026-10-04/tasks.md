# Code Quality Fixes — Tasks (2026-10-04)

Effort: **S** ≤ 30 min · **M** ≤ 2 h · **L** > 2 h. Do NOT fix in the analysis pass — these are the
improvement tasks the scan generated. Each task lists file path(s), the action, and a verification note.

> Principles (see prompt): reuse before rewrite · consolidate duplicates into ONE home · verify a
> symbol is truly dead before deleting · split large files along cohesion seams (stable import
> surface, zero behavior change) · a behavior change drags its tests along.

---

## High priority — broad reach, security/consistency, high-risk coverage

- [x] **H1. Route all frontend `fetch()` calls through `services/apiService`.** [L]
  - Files (33 calls): `components/TenantAdmin/UserManagement.tsx` (10),
    `components/TenantAdmin/useStorageTab.ts` (6), `components/TenantAdmin/CredentialsManagement.tsx` (5),
    `utils/missingInvoicesProcessor.ts` (3), `pages/Login.tsx` (2), and 1 each in
    `TenantAdminDashboard.tsx`, `LanguageSelector.tsx`, `pages/public/blocks/ContactBlock.tsx`,
    `pages/public/PublicLandingPage.tsx`, `hooks/useAssetSearch.ts`,
    `components/common/AssetPicker/AssetPicker.tsx`, `components/TenantAdmin/AccountModal.tsx`, `App.tsx`.
  - Action: replace raw `fetch(...)` + manual headers with the shared apiService; delete
    `${import.meta.env.VITE_API_URL}` / `${API_URL}` hand-built URLs in favor of apiService/`buildApiUrl`.
    Skip `components/examples/TenantAwareComponent.example.tsx` (example file).
  - Verify: `npm test` for the touched components passes; no remaining `import.meta.env.VITE_API_URL`
    outside the api/config layer (`grep -rn "VITE_API_URL" frontend/src/components frontend/src/pages`).

- [x] **H2. Consolidate `_caller_token` / `_resolve_pool_id` into one shared helper.** [M]
  - Files: `admin_routes.py`, `routes/sysadmin_health.py`, `routes/tenant_admin_roles.py`,
    `routes/tenant_admin_users.py`, `routes/tenant_admin_email.py`, `routes/tenant_admin_scope.py`,
    `routes/sysadmin_roles.py` → import from the canonical `routes/sysadmin_helpers.py` (which already
    holds both). Remove the local copies in the same change.
  - Verify: `backend && pytest tests/unit -k "sysadmin or tenant_admin or admin_routes"`; behavior
    unchanged (pure move).

- [x] **H3. Add tests for the highest-risk untested backend modules.** [L]
  - Targets (auth / DB / money / tenant-scoping / routes): `services/scope_canon.py`,
    `services/year_end_journal_entries.py`, `database_banking_queries.py`,
    `services/banking_mutatie_service.py`, `security_validators.py`, `services/google_oauth_service.py`,
    `admin_routes.py`, `audit_routes.py`.
  - Action: add `backend/tests/unit/test_<module>.py` per target, covering the branch-y paths
    (scoping, money math, auth failure modes). Prefer extending a sibling test file if one covers an
    adjacent concern.
  - Verify: new tests pass; cover at least the happy path + one failure/edge branch each.

- [x] **H4. Add tests for the untested frontend banking hooks + API services.** [L]
  - Hooks (money logic): `hooks/useBankingProcessor.ts`, `useBankingPatterns.ts`, `useBankingUpload.ts`,
    `useBankingState.ts`, `useCheckAccounts.ts`, `useCheckReference.ts`, `useTransactions.ts`,
    `useStrChannelRevenue.ts`. Services: `services/{routePresetService,yearEndConfigService,vehicleService,domainApi,landingPageApi,tripService,mediaAssetService}.ts`.
  - Action: co-located `*.test.ts(x)` per file (mock apiService); assert state transitions / request
    shaping / error handling. Prioritize the banking hooks first.
  - Verify: `npm test` green for the new files.

## Medium priority — large-file splits, remaining bypasses, service/route types

- [x] **M1. Split `sam/members/domain/membership_service.py` (2267 lines).** [L]
  - Action: extract along cohesion seams — reads / writes / lifecycle / catalog into sub-modules under
    `sam/members/domain/`; keep the public import surface stable (re-export from `membership_service`).
  - Verify: `sam && pytest tests` green; zero behavior change (structural refactor only).

- [x] **M2. Split the other 3 files > 1000 lines.** [L]
  - `sam/members/handler/app.py` (1375) — extract per-route dispatch; `backend/src/services/projection_sync.py`
    (1368) — extract per-entity sync + diff/apply helpers; `sam/shared/auth_utils.py` (1017) — split
    JWTVerifier / pool-registry / entitlement helpers. (`sam/members/migration/hdcn_backfill.py` 1723 is
    a one-off migration — split only opportunistically, lowest of this group.)
  - Verify: affected `pytest` suites green; import surfaces preserved.

- [x] **M3. Verify + remove SAM dead code.** [S]
  - `sam/members/domain/tenant_hooks.py:124` (`user`) and
    `sam/members/repository/members_repository.py:74,194,335` (`scope_filter` ×3). **First confirm**
    `scope_filter` is not an intentional kwarg / not referenced via dynamic dispatch; only then remove.
  - Verify: `sam && pytest tests/test_members_repository.py tests/test_tenant_hooks.py` green; grep shows
    no dynamic reference to the removed names.

- [x] **M4. De-duplicate frontend utilities.** [S]
  - `isValidEmail` → keep one home (`utils/validationHelpers.ts`), re-point `emailVerificationUtils.ts`.
    `buildApiUrl` → single source (consolidate `config/api.ts`, `services/apiService.ts`, `config.ts`
    onto one). `getRequiredPlaceholders` → one implementation (confirm `types/template.ts` copy is a
    type re-export vs a real duplicate).
  - Verify: `npm test`; update every call site in the same change (no half-migration).

- [x] **M5. Consolidate the backend `_get_service` accessor pattern.** [M]
  - 11 route/storage modules each define a local lazy service accessor. Extract a small shared factory
    (e.g. in `routes/` helpers) and adopt it where the body is identical. Leave genuinely divergent ones.
  - Verify: `backend && pytest tests/unit` for the touched blueprints; behavior unchanged.

- [x] **M6. Add responsive wrappers to the 2 Medium-severity mobile tables.** [S]
  - `components/TenantAdmin/CredentialsManagement.tsx`, `components/TenantAdmin/TaxRateManagement.tsx`.
  - Action: wrap each `<Table>` in `<TableContainer>` / `<Box overflowX="auto">`, or add a card fallback
    via `useBreakpointValue`.
  - Verify: render at 375px width shows no horizontal page overflow; `npm test` green.

- [x] **M7. Tighten service-layer + recurring `any` in frontend prod code.** [M]
  - Replace `Promise<any>` / `any` in `services/{productService,contactService,taxRateService,fieldConfigService,parameterService}.ts`
    and the zzp modals (`TripModal`, `TimeEntryModal`, `ProductModal`, `ContactModal`, `VehicleModal`)
    with concrete types. ~94 prod occurrences; focus on the service layer first.
  - Verify: `npm run build` / `tsc` passes; no new `any` introduced.

## Low priority — opportunistic refactors, minor types, housekeeping

- [x] **L1. Add responsive wrappers to the 3 Low-severity (sysadmin) mobile tables.** [S]
  - `components/SysAdmin/HealthCheck.tsx`, `PipelineResultsPanel.tsx`, `PipelineLogAndErrors.tsx`.
  - Verify: no horizontal overflow at mobile width; tests green.

- [x] **L2. Refactor 500–1000 line files opportunistically.** [L]
  - Candidates: `backend/src/environment/consistency_guard.py` (965), `str_database.py` (910),
    `auth/cognito_utils.py` (894), `frontend/src/pages/MembersPage.tsx` (956). Split only when touching
    them for another reason; keep import surfaces stable.
  - Verify: affected suites green.

- [x] **L3. Reduce the backend/SAM missing-return-hint count where cheap.** [M]
  - Add return hints to public service/route functions in the hottest modules. Treat the ~556/~174
    heuristic as a rough guide (it overcounts multi-line signatures). Optional: enable a scoped ruff
    `ANN` rule to make this enforceable.
  - Verify: `ruff check` clean; `pytest` unaffected.

- [x] **L4. Replace bespoke filter re-impls with the shared `GenericFilter` framework.** [M]
  - 7 `useState`-filter / `.filter(..includes())` sites. Adopt `GenericFilter` where it fits.
  - Verify: filtering behavior unchanged; tests green.

- [x] **L5. Archive stale point-in-time status docs.** [S]
  - Move `ENVIRONMENT_VALIDATION_COMPLETE.md`, `OPENAPI_DOCUMENTATION_COMPLETE.md`, and
    `backend/*_SUMMARY/*_PLAN/*_REPORT.md` (2026-06-26 artifacts) to a `docs/archive/` folder (or delete
    if superseded). No code impact.
  - Verify: no source/doc links point at the moved files (`grep -rn "<filename>" --include='*.md' .`).

- [x] **L6. Add a lint/review gate for the two recurring categories.** [S]
  - (a) A frontend rule flagging raw `fetch(` outside `services/`; (b) a rule/checklist item flagging a
    new `<Table>` without `TableContainer`/`overflowX`/card fallback. Stops H1 and the mobile-table debt
    from recurring.
  - Verify: the rule fires on a deliberately-bad sample and passes on current (post-fix) code.
