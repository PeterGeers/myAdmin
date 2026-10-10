# Implementation Plan: S5b — Members runnable in the myAdmin SPA, fed by the governance projection

> **STATUS: SUPERSEDED by s5c (`.kiro/specs/multi-tenant/s5c-members-runnable-in-spa/`) — 2026-09-19. CLOSED, not completed. DO NOT RESUME work inside this spec.**
>
> s5b proved a SAM module can render in the myAdmin SPA, but it did NOT prove the core
> three-channel fact-propagation guarantee (capability was faked via `cognito:groups`, onboarding
> ran via a CLI script, not the SPA). Its **real artifacts are kept and REUSED by s5c** (SAM template,
> projection record-types/builders/sync trigger, module projection reader, frontend page/modals, docs).
> Its **flawed shortcuts are UNWOUND by s5c** (local `MEMBERS_LOCAL_AUTH_FALLBACK` / `MEMBERS_LOCAL_TENANT_ID`
> flags, prod-Pool-A coupling in `env-vars.local.json`, and the off-model prod `Members_CRUD` Cognito
> group — the last of which was removed 2026-09-19). See `s5c-members-runnable-in-spa/analysis.md`
> for the full gap analysis and disposition.

## Overview

Connect the S5 Members module's already-built config/grant seams to **real projected data**
via the governance projection, onboard `h-dcn` as a real tenant through Tenant Admin, and
make the module runnable + clickable in the SPA — local-first, then a gated prod phase. Each
task is < 1 day, builds on the previous, and ends wired together. Legend:

- `[A]` agent-doable · `[H]` human-run (deploys / AWS / prod / Tenant Admin authoring) ·
  `[R]` REUSES an existing S5 artifact (do not rebuild).
- Test sub-tasks marked `*` are optional (skippable for a faster runnable MVP); core
  implementation tasks are never optional.
- References use requirement ids from `./requirements.md`.
- **Removed vs the prior draft:** the pilot-routing gate (`MEMBERS_PILOT_ROUTING`,
  `_enforce_pilot_routing`) is deleted; access is capability (token) + scope grant
  (projection).

---

## Tasks

### Phase 0 — SAM app packaging + SPA gate + remove pilot-routing

- [x] 1. Members SAM app packaging
  - [x] 1.1 `[A]` Author `sam/members/template.yaml` — one `MembersFunction`
    (`sam.members.handler.app.handler`) + `MembersLayer` vendoring `sam/shared` +
    `sam/members` (+ shared `dynamodb_client`), `ANY /{proxy+}` API; params/env for
    `MEMBERS_TABLE`, `GOVERNANCE_PROJECTION_TABLE`, `AWS_REGION` (fail-fast); tables **not**
    template resources (managed-outside-CFN/retain); **no `MEMBERS_PILOT_ROUTING`**.
    - _Requirements: R6.1, R6.2, R6.5_
  - [x] 1.2 `[A]` Verify `sam build` succeeds for function + layer; document the command.
    - _Requirements: R6.3_
  - [x] 1.3 `[A]` Add local env config: `frontend/.env.local` (`MEMBERS_API_BASE_URL`) and a
    `sam local` env-vars file (`MEMBERS_TABLE=sam-members-local`,
    `GOVERNANCE_PROJECTION_TABLE=<local prefixed>`,
    `AWS_ENDPOINT_URL_DYNAMODB=http://dynamodb-local:8000`, `AWS_REGION=eu-west-1`).
    - _Requirements: R6.2, R7.3_

- [x] 2. Remove the pilot-routing gate + add the `hasMEMBERS` SPA gate
  - [x] 2.1 `[A][R]` Remove `_enforce_pilot_routing` + `MEMBERS_PILOT_ROUTING` from
    `sam/members/handler/app.py` (and `pilot_routing.py`); the edge now gates on capability
    (token) + scope grant (projection) only.
    - _Requirements: R4.1, R4.2_
  - [x] 2.2 `[A]` Add a `hasMEMBERS` boolean to the App-level modules hook (mirroring
    `hasFIN`/`hasSTR`/`hasZZP`) and thread it into `AppRoutes`/`MainMenu` props.
    - _Requirements: R7.2_
  - [x] 2.3 `[A]` Unit-test `hasMEMBERS=true` for a `MEMBERS`-entitled tenant, false otherwise.
    - _Requirements: R7.2_

- [ ] 3. Checkpoint — `sam build` passes, SPA compiles, pilot-routing removed. Ensure all
  tests pass, ask the user if questions arise.

---

### Phase 1 — Extend the projection: record types, builders, sync trigger

- [x] 4. New projected record types
  - [x] 4.1 `[A]` Register `RECORD_TYPE_CONFIG = "config"` (ids `scope`/`fields`) and
    `RECORD_TYPE_SCOPEGRANT = "scopegrant"` (ids `<email>`,`<dimension>`) in
    `backend/src/services/projection_schema.py`; keep `build_sort_key`/`split_sort_key` as
    the only composer/parser.
    - _Requirements: R1.1, R2.1_
  - [x] 4.2 `[A]` Unit-test the new SK round-trips
    (`config#scope`, `config#fields`, `scopegrant#<email>#<dimension>`) via
    `build_sort_key`/`split_sort_key`.
    - _Requirements: R1.1, R2.1_

- [x] 5. Projection builders (MySQL sources → rows)
  - [x] 5.1 `[A]` Build `config#scope` from `tenant_template_config`/`ParameterService`
    (`backend/src/services/parameter_service.py`) into the `ScopeDimension` shape.
    - _Requirements: R1.1, R1.2_
  - [x] 5.2 `[A]` Build `config#fields` from the field-config parameter system into the
    `TenantOverlay` shape (variable fields + fixed-field overrides).
    - _Requirements: R1.3_
  - [x] 5.3 `[A]` Build `scopegrant#<email>#<dimension>` from `user_tenant_roles` (decode
    per-tenant Members roles → granted values or `*`).
    - _Requirements: R2.1, R2.2_
  - [x] 5.4 `[A]` Property test: config round-trips MySQL → row → resolved provider.
    - **Property 2: Config round-trips MySQL → projection → resolved provider**
    - **Validates: Requirements 1.1, 1.2, 1.3, 10.6**

- [x] 6. Sync + on-change trigger extension
  - [x] 6.1 `[A]` Extend `ProjectionSync.sync_administration` to emit the C2 rows alongside
    `tenant`/`module`/`role`; keep it one-directional (no MySQL writes, no read-back).
    - _Requirements: R5.3, R5.5_
  - [x] 6.2 `[A]` Call `enqueue_sync(administration)` after committed writes to
    `tenant_template_config`/parameters (config) and `user_tenant_roles` (grant), mirroring
    `activate_module` in `module_registry.py`.
    - _Requirements: R5.1, R5.2_
  - [x] 6.3 `[A]` Unit-test the trigger fires on config/grant change using an injected
    in-memory trigger (`set_default_trigger`); reconciliation backstop covered.
    - _Requirements: R5.1, R5.2, R5.4, R10.3, R10.4_

- [ ] 7. Checkpoint — projection carries `config#*` + `scopegrant#*`; sync fires on change.
  Ensure all tests pass, ask the user if questions arise.

---

### Phase 2 — Module projection reader wired to the S5 seams

- [x] 8. Reader + provider wiring
  - [x] 8.1 `[A]` Add a module projection reader (mirror
    `sam/pretokengen/projection_governance_reader.py`) implementing `get_scope_config`
    (`ScopeConfigProvider`), `get_overlay` (`TenantOverlayProvider`), and
    `get_scope_grants`; one `Query` per tenant partition, per-invocation cache, fail-fast
    table resolution, empty-is-valid.
    - _Requirements: R1.4, R1.5, R1.6, R1.7, R2.3_
  - [x] 8.2 `[A]` Wire the reader into module cold start so `FieldResolver` +
    `ScopeConfigProvider` come from the projection, replacing the `Static*` providers
    (no domain changes).
    - _Requirements: R1.4, R1.5_
  - [x] 8.3 `[A]` Integrate scope grants at the edge (C5): resolve the tenant `ScopeConfig`,
    read the caller's projected grants, drive `resolve_scope_access`, filter the domain
    read/write by `allowed_scopes`.
    - _Requirements: R2.3, R2.4, R2.5, R2.6, R8.7_
  - [x] 8.4 `[A]` Property test: empty-is-valid collapse (no config → tenant-wide / fixed
    base).
    - **Property 3: Empty-is-valid collapses to tenant-wide / fixed base**
    - **Validates: Requirements 1.6, 1.7, 10.2, 10.6**
  - [x] 8.5 `[A]` Property test: scope-grant deny-by-default (required_for + no grant → deny;
    `*` → `["*"]`; subset → subset).
    - **Property 4: Scope grant deny-by-default**
    - **Validates: Requirements 2.4, 2.5, 2.6, 10.2, 10.6**
  - [x] 8.6 `[A]` Reader test: tenant isolation — one Query per partition, no cross-tenant
    rows.
    - **Property 5: Tenant isolation stays structural**
    - **Validates: Requirements 2.1, 7.4, 10.2, 10.5**

- [ ] 9. Checkpoint — the module resolves config/grants from projected rows; 612 S5 tests
  still green. Ensure all tests pass, ask the user if questions arise.

---

### Phase 3 — Onboard `h-dcn` as a real tenant (SysAdmin provisioning + Tenant-Admin config)

- [x] 10. SysAdmin provisioning — tenant + module entitlement + role definitions (`/api/sysadmin/*`, MySQL SoR)
  - [x] 10.1 `[H][R]` SysAdmin: create tenant `h-dcn` + seed initial admin via
    `createTenant({administration, display_name, contact_email, enabled_modules,
    initial_admin_email, locale})` → `POST /api/sysadmin/tenants` (`sysadminService.ts`).
    - _Requirements: R3.1_
  - [x] 10.2 `[H][R]` SysAdmin: entitle `MEMBERS` for `h-dcn` — via `enabled_modules` at
    create or `updateTenantModules` → `PUT /api/sysadmin/tenants/{h-dcn}/modules`
    (`tenant_modules`/`activate_module`, `module_registry.py`); confirm `has_module`.
    - _Requirements: R3.2, R3.8_
  - [x] 10.3 `[H][R]` SysAdmin: ensure `Members_*` role **definitions** exist — general
    `Members_CRUD`/`Members_Read`/`Members_Export` + any region-scoped defs (`precedence` +
    `category`) — via `createRole`/`updateRole` → `/api/sysadmin/roles`.
    - _Requirements: R3.3, R3.8_

- [x] 11. Tenant-Admin config — users + role assignment + tenant params (`/api/tenant-admin/*`, `X-Tenant`, MySQL SoR)
  - [x] 11.1 `[H][R]` Tenant Admin: create `h-dcn` users via `createUser` →
    `/api/tenant-admin/users` (`tenantAdminApi.ts`).
    - _Requirements: R3.4, R3.8_
  - [x] 11.2 `[H][R]` Tenant Admin: assign each user a Members role (general all-access vs
    subgroup-limited) via `assignRole` → `POST /api/tenant-admin/users/{username}/groups`
    (available roles `GET /api/tenant-admin/roles`; writes `user_tenant_roles`).
    - _Requirements: R3.5, R3.8_
  - [x] 11.3 `[H]` Tenant Admin: author `h-dcn`'s region values (Noord/Zuid/Oost/West) +
    field overlay as tenant-scope parameter **data** via `parameterService.ts` →
    `/api/tenant-admin/parameters` (`ParameterService.set_param(scope="tenant")`; `members.*`
    namespace gated to active MEMBERS by `parameter_schema.py`).
    - _Requirements: R3.6, R3.8_

- [x] 12. Seed module data + local projection provisioning (`[A]` for local; local onboarding writes the same MySQL rows the SysAdmin/Tenant-Admin endpoints would — the endpoints above are the production path)
  - [x] 12.1 `[A]` Provide/verify a seed for `h-dcn`'s membership-type catalog into
    `sam-members-local` (module data, not the projection).
    - _Requirements: R3.7_
  - [x] 12.2 `[A]` Local: provision the `governance_projection` (prefixed) + `sam-members-local`
    tables against `localhost:8000`; run the sync to project `h-dcn`'s
    `config#scope`/`config#fields`/`scopegrant#`/`module#members` rows.
    - _Requirements: R3.8, R9.1_

- [x] 13. Checkpoint — `h-dcn` provisioned (SysAdmin) + configured (Tenant Admin),
  projected locally. Ensure all tests pass, ask the user if questions arise.

---

### Phase 4 — Run the module locally + smoke-test the bridge

- [x] 14. Run + smoke test (long-running via `control_bash_process`)
  - [x] 14.1 `[A]` Start `dynamodb-local` + `myadmin-local` (background) and
    `sam local start-api --docker-network myadmin-local` (background); confirm the module
    answers on its port.
    - _Requirements: R6.4, R9.3_
  - [x] 14.2 `[A]` Smoke-test routes via curl with a test-pool token: `GET /members`
    (scoped), `GET /membership-types`, `POST /members/search`; confirm scope filtering +
    CORS.
    - _Requirements: R7.4, R10.10_

- [ ] 15. Checkpoint — module serves scoped, seeded data locally over HTTP with CORS. Ensure
  all tests pass, ask the user if questions arise.

---

### Phase 5 — Frontend bridge: service + types + hooks + i18n + page + table

- [x] 16. `membersApiService.ts` + types + hooks + i18n
  - [x] 16.1 `[A]` Create `frontend/src/services/membersApiService.ts` targeting
    `MEMBERS_API_BASE_URL` (fail-fast), reusing the auth-token + `X-Tenant`/`X-Language` +
    401 refresh-retry logic from `apiService.ts`; typed route wrappers.
    - _Requirements: R7.3, R7.4_
  - [x] 16.2 `[A]` Add `frontend/src/types/members.ts` (`Member`, `MemberRow`,
    `MembershipType`, field-config types) — types only.
    - _Requirements: R7.5_
  - [x] 16.3 `[A]` `useMemberFieldConfig` hook (pairs with `fieldConfigService.ts`/
    `useFieldConfig.ts`) fetching `GET /members/field-config`; add the `members` i18n
    namespace (nl + en).
    - _Requirements: R7.6, R7.8_
  - [x] 16.4 `[A]` Vitest + MSW: each wrapper's method/path/headers; 401 refresh-retry.
    - _Requirements: R10.7_

- [x] 17. Register + build the table
  - [x] 17.1 `[A]` `appPages.tsx`: lazy `MembersPage`, `'members'` `PageType`, `'/leden'` in
    `urlPageMap`. `AppRoutes.tsx`: `case 'members'` under
    `ProtectedRoute requiredRoles={['Members_Read','Members_CRUD']}`; MainMenu entry gated by
    `hasMEMBERS`.
    - _Requirements: R7.1, R7.2_
  - [x] 17.2 `[A]` `frontend/src/pages/MembersPage.tsx` — REUSE the shared toolkit, do not
    rebuild it: dark theme + header-right orange primary actions
    (`colorScheme="orange"`/`variant="ghost"`) following `ZZPInvoices.tsx` and the
    `32-frontend-ui.md` BankingProcessor pattern (no per-row buttons); Chakra
    `Table variant="simple"` on `bg="gray.800"`, sortable headers, hover rows, responsive
    `overflowX="auto"`; load rows from `GET /members`; drive filters via the shared
    `frontend/src/components/filters/` components (`FilterPanel`, `FilterableHeader`,
    `GenericFilter`, `YearFilter`) + hooks `useFilterableTable`/`useColumnFilters`/
    `useTableSort` (region/status/type); compact/full view switch from field config;
    subgroup/region `Badge` column; row-click opens the view modal; reuse the shared chrome
    (`ProtectedRoute`, `MainMenu`, `AuthContext`/`TenantContext`, `HelpButton`,
    `LanguageSelector`).
    - _Requirements: R7.5, R7.6, R7.9, R8.7_
  - [x] 17.3 `[A]` Vitest + RTL + MSW: renders mocked rows; filter/sort; view-switch changes
    columns; scoped response shows only in-subgroup rows.
    - **Property 4: Scope grant deny-by-default (at the UI)**
    - **Validates: Requirements 8.7, 10.7, 10.8**

- [ ] 18. Checkpoint — page reachable, renders real projected/seeded data, filters + scope
  visible. Ensure all tests pass, ask the user if questions arise.

---

### Phase 6 — Modals + actions

> All modals REUSE the shared pattern (R7.9): Chakra `Modal` + Formik/Yup,
> Cancel(ghost)/Save(orange), `closeOnOverlayClick={false}` for edit modals, per
> `32-frontend-ui.md` + `ZZPInvoices.tsx` — no bespoke form scaffolding.

- [x] 19. View + edit + delete
  - [x] 19.1 `[A]` View modal (row-click) from `GET /members/{member_id}`.
    - _Requirements: R8.1, R7.9_
  - [x] 19.2 `[A]` Edit modal (Formik/Yup) → `PUT /members/{member_id}`; membership-type
    dropdown from `GET /membership-types` (active-only).
    - _Requirements: R8.2, R7.7_
  - [x] 19.3 `[A]` Delete (confirm → `DELETE /members/{member_id}`).
    - _Requirements: R8.2_

- [x] 20. Add + export + transitions
  - [x] 20.1 `[A]` Add / application modal (Formik/Yup) → `POST /members` (+ optional
    `POST /members/{id}/memberships`); active-only dropdown.
    - _Requirements: R8.3, R7.7_
  - [x] 20.2 `[A]` Export (`GET /members/export` or client-side CSV of loaded rows).
    - _Requirements: R8.4_
  - [x] 20.3 `[A]` Single transition →
    `POST /members/{id}/memberships/{mid}/transition`; allowed targets from module response.
    - _Requirements: R8.5_
  - [x] 20.4 `[A]` Bulk actions incl. bulk transition over selected rows →
    `POST /memberships/transition`.
    - _Requirements: R8.6_
  - [x] 20.5 `[A]` Vitest + RTL + MSW: edit/add request bodies; dropdown active-only; delete
    confirm→DELETE; single + bulk transition paths.
    - _Requirements: R10.7, R10.1, R10.9_

- [ ] 21. Checkpoint — all views/modals/actions wired + tested. Ensure all tests pass, ask
  the user if questions arise.

---

### Phase 7 — Local end-to-end walkthrough (the runnable acceptance)

- [ ] 22. Walkthrough
  - [x] 22.1 `[A]` Author `walkthrough.md`: from a clean start — `npm start` + docker
    (`myadmin-local` + `dynamodb-local`) + `sam build` + `sam local start-api` + provision
    the projection + `sam-members-local` + project `h-dcn` config/grants + seed catalog —
    then log in and step filter → view → edit → add → transition (single + bulk) → export.
    - _Requirements: R9.1, R9.3_
  - [ ] 22.2 `[H]` Run the walkthrough end-to-end: confirm a Noord-scoped user sees only
    Noord, a general user sees all; record look & feel / UX for the S5 Go/No-Go MANUAL item.
    - **Property 8: Runnable-not-just-tested definition of done**
    - **Validates: Requirements 9.1, 9.2**

- [x] 23. End-user documentation (MkDocs manual)
  - [x] 23.1 `[A]` Author the `docs/docs/members/` MkDocs manual section (nl primary +
    `*.en.md`) for Leden Overzicht — overview table + filters/view-switch, view/edit/add/
    delete, export, single + bulk transition, membership-type dropdown, subgroup/region
    scoping — following `docs/docs/zzp/` + `docs/docs/tenant-admin/` and
    `.kiro/specs/Common/end-user-documentation/`; wire a `Leden`/`Members` section into
    `docs/mkdocs.yml` `nav`; cross-reference tenant-admin docs for R3 onboarding rather than
    duplicate; confirm `mkdocs build` succeeds (nl + en).
    - _Requirements: R11.1, R11.2, R11.3, R11.4, R11.5, R10.11_

---

### Phase 8 — Prod run (GATED, human-run, high-risk)

- [ ] 24. Deploy + provision + project + verify + rollback (**high-risk**, `23-aws-accounts.md`)
  - [ ] 24.1 `[H]` `sam build` + `sam deploy` the Members SAM app to myAdmin prod
    (`nonprofit-deploy`, `eu-west-1`).
    - _Requirements: R9.4_
  - [ ] 24.2 `[H][R]` Provision prod `sam-members` + confirm the prod `governance_projection`
    (managed-outside-CFN/retain, PAY_PER_REQUEST).
    - _Requirements: R9.4_
  - [ ] 24.3 `[H]` Author `h-dcn` config in prod: SysAdmin (`/api/sysadmin/*`) creates the
    tenant + entitles `MEMBERS` + role defs; Tenant Admin (`/api/tenant-admin/*`) creates
    users + assigns roles + authors tenant params; run the sync so prod projects
    `config#*`/`scopegrant#*`/`module#members`; set `MEMBERS_MODULE_API_BASE`.
    - _Requirements: R9.4_
  - [ ] 24.4 `[H]` Verify Leden Overzicht in myAdmin prod (scoped + general users).
    - _Requirements: R9.4_
  - [ ] 24.5 `[H]` IF live-token entitlement is required, follow S5 Step 7 Pool A PreTokenGen
    (S5 R6.2/R6.3) — cross-referenced, not duplicated.
    - _Requirements: R9.5_
  - [ ] 24.6 `[H]` Confirm reversible rollback via governance: remove the `MEMBERS`
    entitlement (SysAdmin) and/or the scope-granting role assignments (Tenant Admin) and
    re-project — no destructive table ops.
    - _Requirements: R9.6_

---

## Session status & notes (last updated: 2026-09-18)

**MILESTONE REACHED: the 4 `h-dcn` members render in the SPA Leden Overzicht page**, end-to-end:
SPA → Members SAM API (local, port 3001) → governance projection (`test_governance_projection`)
→ `dynamodb-local`. Auth passes and the table shows the seeded members across Noord/Zuid/West.

Completed this session (in addition to the `[x]` boxes above): backend Phases 1–2 (tasks 4, 5,
6, 8) green; frontend service (16.1) + types (16.2) + page/route/menu/i18n (17.1, 17.2) + view
modal (19.1); local seeding (12.1, 12.2); and the two `[A]` test backfills (16.4 = 26 tests,
17.3 = 6 tests, both green).

### LOCAL-DEV deviations to be aware of (NOT production behaviour)

1. **Local auth fallback (flag-gated, prod-unreachable).** The local Cognito token carries
   `cognito:groups` but no `custom:entitlements` claim (no PreTokenGen trigger on the pool), so
   `has_capability` and tenant resolution both return "token doesn't answer" and the edge 403s.
   Two flag-gated fallbacks were added in `sam/members/handler/app.py`, both OFF in prod:
   - `MEMBERS_LOCAL_AUTH_FALLBACK=true` → when `has_capability` returns `None`, derive the
     capability from a `Members_*` group (never softens a `False` denial).
   - `MEMBERS_LOCAL_TENANT_ID=h-dcn` → when the verified entitlement resolves no tenant, use 
     this tenant instead of 403-ing (caught `TenantResolutionError` in the caller only;
     `_establish_tenant_context` itself is unchanged).
   Both flags are declared in `sam/members/template.yaml` with EMPTY defaults and set only in
   `sam/members/env-vars.local.json`. Prod is byte-for-byte identical to before.

2. **Local dev is currently coupled to PROD Pool A.** `env-vars.local.json` points
   `HDCN_COGNITO_ISSUER` at `eu-west-1_Hdp40eWmu` (PROD Pool A, account 344561557829). To make the
   page work, `Members_CRUD` was added to user `webmaster@h-dcn.nl` in THAT pool — a
   reversible prod Cognito write (`admin-remove-user-from-group ... --group-name Members_CRUD`
   to undo). BACKLOG: switch local dev to a non-prod dev/test pool (the "test-pool hygiene
   switch"), per the stated intent "we should have a dev pool that is not the prod pool".

3. **Frontend envelope + shape normalization (why the list first came back empty).** The module
   returns `{"data": [...]}` and NESTED member records (`personal.name`, `personal.contact`,
   `membership.status/membership_type`, `scope_values.region[0]`). `membersApiService.ts` now
   `unwrapData()`s the envelope and `flattenMember()`s the nested record to the flat shape the
   page/types expect (name/email/status/membership_type/region). The backend was correct
   throughout (a temporary `LOCAL-DEV SCOPE DIAG` log confirmed `resolved_scopes=['*']`, then was
   removed). Covered by `membersApiService.test.ts`.

4. **SAM layer build fix.** `sam/members/layer/Makefile` now selects the pip interpreter
   deterministically (`PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(PYTHON))`) so
   an inherited `PYTHON` env var can't force the pip-less system `python3` (build had
   failed with "No module named pip").

### Phase-3 actor-split note (tasks 10–13)
Tasks 10, 11, 13 are `[H]`/`[R]` **prod provisioning** via the SysAdmin/Tenant-Admin endpoints and
remain `not_started` on purpose. Their **local equivalent** was satisfied by the `[A]` onboarding
script (task 12) + the Cognito group add above — do NOT mark the prod-provisioning tasks complete
on the basis of the local run.

### Still open / next
- 14.2 smoke test; 16.3 `useMemberFieldConfig` hook (page currently calls `getFieldConfig`
  directly — not blocking); Phase 6 modals (19.2/19.3, 20.x); Phase 7 walkthrough + docs (22, 23);
  Phase 8 prod (24, gated `[H]`). Pre-existing UNRELATED failing tests in
  `backend/tests/unit/test_tenant_admin_per_tenant_roles.py` are not part of S5b — do not chase.

---

## Notes

- Tasks marked `*` are optional test sub-tasks (skippable for a faster runnable MVP).
- `[R]` tasks reuse existing S5 artifacts (module domain/repository, projection, SysAdmin +
  Tenant Admin surfaces) — do not rebuild them.
- `[H]` tasks are human-run (SysAdmin provisioning, Tenant-Admin authoring, deploys, prod);
  the agent does not run long-running/interactive prod commands.
- **Actor split (Phase 3):** tenant create + module entitlement + role definitions =
  SysAdmin (`/api/sysadmin/*`); users + role assignment + tenant-scope parameters = Tenant
  Admin (`/api/tenant-admin/*`). Local onboarding (task 12, `[A]`) writes the same MySQL
  rows those endpoints would; the endpoints are the production path.
- The S5 **612 module tests** stay green throughout (R10.1) — this spec changes no domain
  logic; it swaps the stub config providers for a projection reader.
- **Pilot-routing removed:** access is capability (token) + scope grant (projection).
- **Definition of done = runnable + clickable** (Phase 7), not just passing tests (R9, R10.5).
- Long-running processes run in the background (`control_bash_process`) / by the operator —
  never foreground (R9.3).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "2.3", "4.2"] },
    { "id": 2, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 3, "tasks": ["5.4", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3"] },
    { "id": 6, "tasks": ["8.4", "8.5", "8.6", "10.1"] },
    { "id": 7, "tasks": ["10.2", "10.3"] },
    { "id": 8, "tasks": ["11.1", "11.3"] },
    { "id": 9, "tasks": ["11.2"] },
    { "id": 10, "tasks": ["12.1", "12.2"] },
    { "id": 11, "tasks": ["14.1"] },
    { "id": 12, "tasks": ["14.2", "16.1", "16.2"] },
    { "id": 13, "tasks": ["16.3", "16.4", "17.1"] },
    { "id": 14, "tasks": ["17.2"] },
    { "id": 15, "tasks": ["17.3", "19.1", "20.1", "20.2"] },
    { "id": 16, "tasks": ["19.2", "19.3", "20.3", "20.4"] },
    { "id": 17, "tasks": ["20.5", "22.1", "23.1"] },
    { "id": 18, "tasks": ["22.2"] },
    { "id": 19, "tasks": ["24.1"] },
    { "id": 20, "tasks": ["24.2"] },
    { "id": 21, "tasks": ["24.3"] },
    { "id": 22, "tasks": ["24.4", "24.5"] },
    { "id": 23, "tasks": ["24.6"] }
  ]
}
```
