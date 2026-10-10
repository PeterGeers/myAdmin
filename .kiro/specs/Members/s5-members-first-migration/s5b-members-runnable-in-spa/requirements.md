# Requirements Document

## S5b — Members runnable in the myAdmin SPA, fed by the governance projection — Requirements

- Status: Draft (rewrite — settled projection-channel design; supersedes the prior
  pilot-routing framing).
- Roadmap step: closes the S5 gate's runnable/operational/UX obligations **and** the
  real-tenant-onboarding half S5 never covered
  (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`, the S5 section — "working
  migrated app" + operational deploy/rollback + look & feel/UX + a real tenant).
- Parent spec (REUSE — do not rebuild the domain):
  `.kiro/specs/multi-tenant/s5-members-first-migration/`
  (`requirements.md`, `design.md`, `generic-membership-design.md`,
  `scope-dimension-design.md`, `members-wireframe.md`, `go-no-go.md`).
- Decisions of record: ADR `docs/decisions/0003` (myAdmin base; apps as SAM modules),
  `0004` (verified-JWT-only), `0005` (**MySQL single system of record + one-directional
  MySQL→DynamoDB projection**), `0006` (entitlement-in-token + projection).
- Governing steering: `.kiro/steering/11-tech-stack.md`, `12-project-structure.md`,
  `20-platform-architecture.md`, `21-identity.md` (two-pool; per-tenant roles in MySQL
  `user_tenant_roles`, effective roles = global(token) ∪ per-tenant(MySQL)),
  `22-authentication.md`, `23-aws-accounts.md` (tables managed-outside-CFN/retain,
  `sam-` prefix, eu-west-1, `nonprofit-deploy`, prod high-risk), `32-frontend-ui.md`,
  `33-frontend-testing.md`, `34-backend-testing.md`, `35-sam-module-architecture-sam.md`,
  `40-spec-workflow.md`, `42-local-dynamodb-testing.md`.

## Introduction

S5 built and unit-tested (612 passing tests) a **generic, SAM-built / SAM-deployed /
DynamoDB Members module** — the consolidated one-Lambda edge
(`sam/members/handler/app.py`), the domain engine (`sam/members/domain/`), and the
tenant-scoped repository (`sam/members/repository/`). The SAM architecture is fixed and is
the whole reason for the exercise (World 2). But the module has **never been deployed, has
no SAM template, no provisioned table, and no UI**, and — the deeper gap — S5 never answered
how a **real tenant's configuration and per-user grants reach the module** given the S1 rule
that a SAM Lambda must **never open a MySQL connection**.

This spec (**S5b**) settles that. The answer, validated as sound and consistent with ADR
0005/0006, is to **feed the module through the EXISTING projection channel** — the same
one-directional MySQL→DynamoDB `governance_projection` pipeline that already carries
tenant/module/role governance (`backend/src/services/projection_schema.py`,
`projection_sync_trigger.py`). Tenant-specific config records and per-user scope grants are
pushed to the tenant's projection partition, exactly like `module#…`/`role#…` rows are
projected today. Access is gated the **normal SaaS way** — there is **no pilot-routing env
flag** as the access gate (the prior `MEMBERS_PILOT_ROUTING` shortcut is **dropped
entirely**), and **no scope on the token claim**.

Three DISTINCT channels are kept clean and MUST NOT be blurred:

1. **Capability** (may this user read/write Members at all) — the verified token's
   `custom:entitlements` claim (`members:read`/`write`/`export`/`admin`), the S4
   mechanism. **Unchanged.**
2. **Per-user subgroup scope grant** (e.g. "user X in tenant `h-dcn` is limited to
   `region=Noord`", or all) — a security-relevant per-tenant role fact whose system of
   record is MySQL `user_tenant_roles` (managed in Tenant Admin). Delivered to the module
   via the **projection** as a per-user row (mirroring the existing `role#email#role`
   rows). **NOT on the token, NOT invented in the module.**
3. **Tenant config** (the scope dimension definition + its predefined allowed values, e.g.
   Noord/Zuid/Oost/West; the fixed-vs-variable field overlay / parameters) — lower-stakes
   tenant data whose system of record is MySQL (`tenant_template_config` +
   `ParameterService`/`MODULE_REGISTRY`). Delivered via the **projection** as tenant-level
   rows.

The module already has the **consuming seams** built in S5 (currently fed by in-memory
stubs): `sam/members/domain/scope_dimensions.py` (`ScopeConfigProvider`),
`scope_access.py` (`resolve_scope_access`), `field_resolver.py` (`TenantOverlayProvider`).
This spec connects those seams to **real projected data** via a projection reader
(mirroring `sam/pretokengen/projection_governance_reader.py`), replacing the stubs. It also
makes the module **runnable and clickable** inside the myAdmin SPA — local-first, then a
gated prod phase — and **onboards `h-dcn` as the first real tenant** entirely through
myAdmin's normal Tenant Admin surface (no separate MySQL tool).

**This spec is the runnable-in-SPA + real-tenant-config delta.** It does not restate the
generic membership design (see S5); it does not change the S5 domain/repository logic.

## Glossary

- **Members module** — the S5 generic membership SAM module (one Lambda, internal routing,
  verified-auth edge, DynamoDB `sam-members` table). Code at `sam/members/`.
- **Governance projection** — the one-directional MySQL→DynamoDB copy of the tenant-level
  governance subset (`backend/src/services/projection_schema.py`, table
  `{ENV_PREFIX}governance_projection`, PK `tenant_id`, SK `record_type#id`, `version`).
- **Projection sync** — the on-change enqueue + reconciliation backstop that keeps the
  projection current after a committed MySQL governance write
  (`projection_sync_trigger.py`, `enqueue_sync`).
- **Projection reader** — a read-only, `boto3`-backed reader the module uses to consume the
  projected rows (mirroring `sam/pretokengen/projection_governance_reader.py`), replacing
  the S5 in-memory config providers.
- **Capability** — a Members permission carried on the verified token's
  `custom:entitlements` claim (`members:read/write/export/admin`), the S4 mechanism.
- **Scope grant** — a per-user grant of subgroup values for a scope dimension (e.g.
  `region=[Noord]`, or `*` for all), sourced from MySQL `user_tenant_roles`, delivered via
  the projection.
- **Scope dimension / tenant config** — the tenant-configurable within-tenant partition
  (h-dcn: `region`, values Noord/Zuid/Oost/West) + the fixed⊕variable field overlay,
  sourced from MySQL `tenant_template_config`/parameters, delivered via the projection.
- **SysAdmin** — myAdmin's platform-level admin (role `SysAdmin`, `/api/sysadmin/*`,
  `frontend/src/services/sysadminService.ts`) that creates tenants (`POST
  /api/sysadmin/tenants`), entitles modules (`PUT /api/sysadmin/tenants/{administration}/modules`,
  `tenant_modules`/`MODULE_REGISTRY`), and defines global/module role definitions
  (`/api/sysadmin/roles`, roles carry `precedence` + `category`). Backed by MySQL.
- **Tenant Admin** — myAdmin's per-tenant admin (role `Tenant_Admin`, `/api/tenant-admin/*`,
  scoped by `X-Tenant`) that manages users (`/api/tenant-admin/users`), assigns roles
  (`/api/tenant-admin/users/{username}/groups`, from `GET /api/tenant-admin/roles`), and
  authors tenant-scope parameters (`/api/tenant-admin/parameters` → `ParameterService`
  `scope="tenant"`) — `frontend/src/services/tenantAdminApi.ts` + `parameterService.ts` +
  `frontend/src/pages/TenantAdmin/`; backend `backend/src/routes/parameter_admin_routes.py`.
  Backed by MySQL.
- **`hasMEMBERS`** — the SPA module-entitlement gate for the Members page, mirroring
  `hasFIN`/`hasSTR`/`hasZZP`.
- **myAdmin SPA** — the React 19 + Vite frontend (`frontend/`).
- **Ledenadministratie / Leden Overzicht** — the member-administration overview screen
  refactored into the SPA (admin table + Table Filter Framework v2 + view/edit/add/delete/
  export + single & bulk lifecycle transition + active-only membership-type dropdown +
  subgroup/region display).
- **Definition of done: runnable + clickable** — the acceptance bar: a human starts the
  stack, logs in, and operates Leden Overzicht against real projected/seeded data — not
  merely "tests pass".

## Guiding principles (settled; requirements below enforce them)

- **The projection is the module's only config/grant channel.** The module READS config and
  grants from the projection and NEVER writes them back; edits go to MySQL via Tenant Admin
  and re-project. MySQL stays the single system of record (ADR 0005).
- **No pilot-routing gate.** `MEMBERS_PILOT_ROUTING` is dropped as the access gate; access
  is capability (token) + scope grant (projection), the normal SaaS way.
- **Empty-is-valid.** A tenant with no scope config projected → no subgroup dimension
  (tenant-wide `["*"]`), never a crash. Missing field overlay → the fixed base. Empty
  entitlement → S4 semantics.
- **Both actors use the normal myAdmin SPA, not a MySQL tool.** SysAdmin provisions the
  tenant + module entitlement + role definitions (`/api/sysadmin/*`); Tenant Admin manages
  users + role assignment + tenant-scope parameters (`/api/tenant-admin/*`). A members-only
  tenant is just a normal tenant entitled only to MEMBERS.
- **Reuse S5, do not rebuild.** The module domain/repository/tests and the consuming
  provider seams already exist; S5b swaps the stub providers for a projection reader and
  adds the deploy/run/UI/onboarding wrapper.
- **Local-first, then prod.** The representative target is a full local dev end-to-end run;
  prod is a later, gated, human-run phase.
- **Verified-token flow preserved (ADR 0004).** The SPA sends the Cognito JWT; the module
  edge authenticates from verified claims (`get_verified_claims`) — never from a
  header/body.
- **Presentation-only frontend (35-sam).** The Leden Overzicht page holds no business rules
  or data-shape authority; it renders the resolved field config the module serves and the
  module authoritatively validates every write.

## Requirements

### R1 — Tenant config fed via the projection (scope dimension + field overlay)

**User Story:** As a platform operator, I want a tenant's Members scope dimension and field
overlay to reach the SAM module through the existing governance projection, so that the
Lambda never reads MySQL yet always sees the tenant's current configuration.

#### Acceptance Criteria

1. THE governance projection SHALL carry a tenant-level `config#scope` record per tenant
   describing the scope dimension(s) (key, label, `enabled`, `multi_valued`, predefined
   `values`, all-access wildcard role, `required_for` capabilities), registered as a new
   record type alongside `tenant`/`module`/`role` in
   `backend/src/services/projection_schema.py`.
2. THE `config#scope` record SHALL be sourced from the tenant-scope parameters the Tenant
   Admin authors (`/api/tenant-admin/parameters` → `ParameterService.set_param(scope="tenant")`,
   `backend/src/services/parameter_service.py`, `backend/src/routes/parameter_admin_routes.py`)
   — the parameter-driven predefined-values system — and SHALL NOT be authored in the module.
3. THE governance projection SHALL carry a tenant-level `config#fields` record per tenant
   describing the per-tenant variable field overlay plus presentation overrides of fixed
   fields, sourced from the field-config parameter system (the `tenant_template_config` /
   `FieldConfigMixin` analogue).
4. WHEN the module resolves a tenant's scope config, THE module projection reader SHALL
   supply `sam/members/domain/scope_dimensions.py`'s `ScopeConfigProvider` from the
   projected `config#scope` record, replacing the S5 in-memory `StaticScopeConfigProvider`.
5. WHEN the module resolves a tenant's field config, THE module projection reader SHALL
   supply `sam/members/domain/field_resolver.py`'s `TenantOverlayProvider` from the
   projected `config#fields` record, replacing the S5 in-memory `StaticOverlayProvider`.
6. IF a tenant has no `config#scope` record projected, THEN THE module SHALL treat the
   tenant as having no subgroup dimension (tenant-wide `["*"]`) and SHALL NOT raise.
7. IF a tenant has no `config#fields` record projected, THEN THE module SHALL fall back to
   the platform fixed-field base and SHALL NOT raise.

### R2 — Per-user subgroup scope grant fed via the projection

**User Story:** As a tenant administrator, I want a member-administrator user's subgroup
scope (e.g. limited to region Noord, or all-access) to be a per-tenant role fact in MySQL
that flows to the module, so that a scoped user sees only their subgroup and a general user
sees all — deny-by-default.

#### Acceptance Criteria

1. THE governance projection SHALL carry a per-user `scopegrant#<email>#<dimension>` record
   per granted user carrying the granted values (a list, or `*` for all-access), registered
   as a new record type in `backend/src/services/projection_schema.py` and mirroring the
   existing `role#<email>#<role>` per-user rows.
2. THE `scopegrant#<email>#<dimension>` record SHALL be sourced from the Tenant Admin's role
   assignment recorded in MySQL `user_tenant_roles` (via `POST /api/tenant-admin/users/{username}/groups`,
   myAdmin's system of record for per-tenant roles) combined with the dimension values from
   the tenant-scope parameters (R3.6), and SHALL NOT be carried on the token nor invented in
   the module.
3. WHEN the module authenticates a request, THE module projection reader SHALL supply the
   caller's granted scope values for each dimension from the projected `scopegrant#` rows,
   and the edge SHALL drive `sam/members/domain/scope_access.py`'s `resolve_scope_access`
   with those values.
4. WHERE a user holds a general (all-access) Members role, THE module SHALL resolve
   `allowed_scopes = ["*"]` for that dimension (see `resolve_scope_access` `access_type`
   `admin`/`all`).
5. WHERE a user holds a subgroup-limited grant, THE module SHALL resolve `allowed_scopes`
   to exactly the granted subset (`access_type = "scoped"`).
6. IF a user holds a capability the dimension lists in `required_for` but has no projected
   scope grant in that dimension, THEN THE module SHALL deny (empty `allowed_scopes`,
   `access_type = "none"`) — deny-by-default.

### R3 — Onboard `h-dcn` as a real tenant: SysAdmin provisioning + Tenant-Admin config (no separate MySQL tool)

**User Story:** As a platform SysAdmin and as `h-dcn`'s Tenant Admin, I want each actor to
onboard `h-dcn` through the surface that actor actually owns — SysAdmin provisions the
tenant + module entitlement + role definitions, Tenant Admin manages users + role
assignment + tenant parameters — so that a members-only tenant is a normal SaaS tenant and
never needs a separate MySQL function.

**Actor boundary (verified against myAdmin code):** tenant creation + module entitlement +
role definitions = **SysAdmin** (`/api/sysadmin/*`, role `SysAdmin`,
`frontend/src/services/sysadminService.ts`); users + role assignment + tenant-scope
parameters = **Tenant Admin** (`/api/tenant-admin/*`, role `Tenant_Admin`, scoped by
`X-Tenant`, `frontend/src/services/tenantAdminApi.ts` + `parameterService.ts`). Both use
existing myAdmin SPA surfaces (SysAdmin dashboard / Tenant Admin dashboard) — no separate
MySQL tool.

#### Acceptance Criteria — SysAdmin provisioning (`/api/sysadmin/*`)

1. THE SysAdmin SHALL create tenant `h-dcn` (the `administration` key) and seed its initial
   tenant admin via `createTenant({administration, display_name, contact_email,
   enabled_modules, initial_admin_email, locale})` → `POST /api/sysadmin/tenants`
   (`frontend/src/services/sysadminService.ts`).
2. THE SysAdmin SHALL entitle `h-dcn` to the `MEMBERS` module — set at creation via
   `enabled_modules` or later via `updateTenantModules` → `PUT
   /api/sysadmin/tenants/{h-dcn}/modules` (`tenant_modules`, `MODULE_REGISTRY`,
   `activate_module`/`has_module`, `backend/src/services/module_registry.py`) — the same
   gate FIN/STR/ZZP use.
3. THE SysAdmin SHALL ensure the `Members_*` role **definitions** exist — the general
   `Members_CRUD`/`Members_Read`/`Members_Export` plus any region-scoped role definitions
   (each carrying `precedence` + `category: 'platform'|'module'|'other'`) — via
   `getRoles`/`createRole`/`updateRole` → `/api/sysadmin/roles`. Role definitions are
   platform-level; assigning them to users is a Tenant-Admin action (see R3.5).

#### Acceptance Criteria — Tenant-Admin config (`/api/tenant-admin/*`, scoped by `X-Tenant`)

4. THE Tenant Admin SHALL create `h-dcn` users via `createUser`/`listUsers`/`removeUser` →
   `/api/tenant-admin/users` (`frontend/src/services/tenantAdminApi.ts`).
5. THE Tenant Admin SHALL assign each user a Members role from the tenant's available roles
   — the general (all-access) `Members_CRUD` vs a subgroup-limited grant — via
   `assignRole`/`removeRole` → `POST/DELETE /api/tenant-admin/users/{username}/groups`,
   available roles via `getAvailableRoles` → `GET /api/tenant-admin/roles`; the assignment
   is recorded in MySQL `user_tenant_roles`.
6. THE Tenant Admin SHALL author `h-dcn`'s tenant-scope parameters — the region dimension
   values (Noord/Zuid/Oost/West) and the field overlay — as parameter **data** (not code)
   via `parameterService.ts` → `/api/tenant-admin/parameters` (GET/POST/PUT/DELETE), backed
   by `backend/src/routes/parameter_admin_routes.py` + `ParameterService.set_param(
   scope="tenant", scope_id="h-dcn", ...)`. The `members.*` parameter namespace is available
   only once `MEMBERS` is an active module (gated by `backend/src/services/parameter_schema.py`
   `PARAMETER_SCHEMA`). These tenant-scope params are the source of the `config#scope` /
   `config#fields` projection rows.

#### Acceptance Criteria — module data + projection

7. THE `h-dcn` membership-type catalog SHALL be seeded as **module data** in the
   `sam-members` table (tenant business data per S5 C8), distinct from the governance
   projection and from the tenant parameters above.
8. WHEN any of the above governance/param facts (module entitlement, role definitions, role
   assignments, tenant-scope parameters) is committed in MySQL, THE projection sync SHALL
   push the derived `config#scope`/`config#fields`/`scopegrant#` rows to `h-dcn`'s
   projection partition so the module sees it (see R5).

### R4 — Capability via token entitlement (S4), unchanged

**User Story:** As a security owner, I want whether a user may read/write Members at all to
remain a verified-token entitlement, so that capability and subgroup scope stay distinct
channels.

#### Acceptance Criteria

1. THE module edge SHALL gate each route by the verified token's `custom:entitlements`
   capability (`members:read`/`write`/`export`/`admin`) via `has_capability`, unchanged
   from S4/S5.
2. THE capability channel SHALL be independent of the scope-grant channel (R2) and the
   tenant-config channel (R1) — capability answers "may act on Members", scope answers
   "on which subgroup".
3. IF a user's Members entitlement is empty, THEN THE module SHALL apply S4 empty-is-valid
   semantics (no capability → denied at the edge), without consulting scope grants.

### R5 — On-change projection sync includes config + scope grants

**User Story:** As a platform operator, I want the projection to stay current when a
tenant's config or a user's scope grant changes, so that the module reflects Tenant Admin
edits within the projection's bounded delay.

#### Acceptance Criteria

1. WHEN a MySQL governance write mutates a tenant's scope/field config
   (`tenant_template_config`/parameters), THE write path SHALL call `enqueue_sync` for the
   affected `administration` after commit (`projection_sync_trigger.py`).
2. WHEN a MySQL governance write mutates a user's scope grant (`user_tenant_roles`), THE
   write path SHALL call `enqueue_sync` for the affected `administration` after commit.
3. THE projection sync SHALL build the `config#scope`, `config#fields`, and
   `scopegrant#<email>#<dimension>` rows from their MySQL sources during a tenant sync, in
   addition to the existing `tenant`/`module#…`/`role#…` rows.
4. IF an `enqueue_sync` signal is lost, THEN THE reconciliation backstop (`reconcile`)
   SHALL re-project the tenant on its next pass — the projection is eventually consistent
   and never left unbounded-stale (as documented in `projection_sync_trigger.py`).
5. THE projection SHALL remain one-directional: the sync writes the projection, the module
   only reads it, and neither writes back to MySQL.

### R6 — Members SAM app: template + layer, builds + runs locally

**User Story:** As a developer, I want the one-Lambda Members module to have a SAM template
and layer, so that it builds and runs locally against DynamoDB-Local.

#### Acceptance Criteria

1. THE Members module SHALL have a SAM template (`sam/members/template.yaml`) defining one
   Lambda (the `sam/members/handler/app.py` edge), an API Gateway (`ANY /{proxy+}`), and a
   Lambda layer vendoring `sam/shared` + `sam/members` (+ the shared `dynamodb_client`),
   mirroring the S-plane layer pattern but with ONE Lambda.
2. THE SAM template SHALL declare parameters/environment for `MEMBERS_TABLE`,
   `GOVERNANCE_PROJECTION_TABLE`, `AWS_REGION`, and (local only)
   `AWS_ENDPOINT_URL_DYNAMODB`, each resolved fail-fast (no dangerous defaults, per
   `23-aws-accounts.md`), and SHALL NOT declare `MEMBERS_PILOT_ROUTING`.
3. WHEN a developer runs `sam build`, THE Members SAM app SHALL build the function + layer
   without error.
4. WHEN a developer runs `sam local start-api --docker-network myadmin-local` against
   `dynamodb-local`, THE Members module SHALL serve its declared routes locally.
5. THE `sam-members` and `governance_projection` DynamoDB tables SHALL be managed outside
   the SAM/CFN template (or `DeletionPolicy: Retain`), per `23-aws-accounts.md` — the
   template SHALL only reference their names via env vars.

### R7 — Ledenadministratie / Leden Overzicht page in the SPA (runs + renders real data)

**User Story:** As a member administrator, I want the Leden Overzicht screen inside the
myAdmin SPA rendering real member data scoped to my subgroup, so that I can administer
members without a separate application.

#### Acceptance Criteria

1. THE SPA SHALL register a Ledenadministratie / Leden Overzicht page: a `members`
   `PageType` in `frontend/src/appPages.tsx` (lazy import + `urlPageMap` `/leden`), a
   `case 'members'` in `frontend/src/AppRoutes.tsx` wrapped in
   `ProtectedRoute requiredRoles={['Members_Read','Members_CRUD']}`, and a MainMenu entry
   (`frontend/src/components/MainMenu.tsx`).
2. THE page SHALL be module-gated by `hasMEMBERS` (mirroring `hasFIN`/`hasSTR`/`hasZZP`) so
   it appears only for a `MEMBERS`-entitled tenant.
3. THE page SHALL reach the module through a dedicated
   `frontend/src/services/membersApiService.ts` targeting `MEMBERS_API_BASE_URL`
   (`import.meta.env`, fail-fast if missing), reusing the Cognito-JWT / `X-Tenant` /
   `X-Language` header logic + 401 refresh-retry from `frontend/src/services/apiService.ts`.
4. THE verified-token flow (ADR 0004) SHALL be preserved: the SPA sends the Cognito ID
   token as `Authorization: Bearer`; the module edge authenticates via `get_verified_claims`
   and derives tenant from the verified entitlement — never from a header/body.
5. THE page SHALL render real member data from the module API (`GET /members` /
   `POST /members/search`), subgroup-filtered by the caller's projected scope grant,
   following `32-frontend-ui.md` and the `frontend/src/pages/ZZPInvoices.tsx` reference
   (dark theme, header-right orange primary actions, Chakra `Table`).
6. THE table SHALL use the shared Table Filter Framework v2 components at
   `frontend/src/components/filters/` (`FilterPanel.tsx`, `FilterableHeader.tsx`,
   `GenericFilter.tsx`, `YearFilter.tsx`, `types.ts`) via the hooks `useFilterableTable` /
   `useColumnFilters` / `useTableSort` (`32-frontend-ui.md`), NOT a bespoke table/filter,
   and SHALL support context/view switching driven by the module's resolved field config
   (`GET /members/field-config`), rendering the fixed⊕overlay fields, with the
   subgroup/region value visibly displayed.
7. THE membership-type input in add/edit SHALL be a dropdown fed by the module's catalog
   endpoint (`GET /membership-types`) listing active-only entries — no free text.
8. THE `members` i18n namespace SHALL provide nl + en strings via
   `useTypedTranslation('members')`, with the locale files located under
   `frontend/src/locales/{nl,en}/members.json` — no hardcoded user-visible text.
9. THE page SHALL reuse myAdmin's shared frontend building blocks — it composes existing
   chrome and toolkit, it does NOT introduce bespoke equivalents:
   - **Shared filter components** — the `frontend/src/components/filters/` components and
     the `useFilterableTable` / `useColumnFilters` / `useTableSort` hooks (R7.6), not a
     hand-rolled table/filter.
   - **`32-frontend-ui.md` UI patterns as hard requirements** — the BankingProcessor
     pattern (row-click opens a Chakra `Modal`, NO per-row action buttons; primary actions
     Add/Export/Bulk in the header row, right-aligned, `colorScheme="orange"`, secondary
     `variant="ghost"`); a Chakra UI `Table variant="simple"` on `bg="gray.800"` with
     sortable headers, hover-highlighted rows, `Badge` for status/read-only (subgroup/
     region) cells, and responsive `overflowX="auto"`; Chakra `Modal` for all CRUD with
     Formik + Yup and a Cancel(ghost)/Save(orange) layout, `closeOnOverlayClick={false}`
     for edit modals; responsive Chakra props throughout — following
     `frontend/src/pages/ZZPInvoices.tsx` as the concrete reference implementation.
   - **Shared services/hooks/context** — `frontend/src/services/membersApiService.ts` is
     built on the existing `frontend/src/services/apiService.ts` auth/tenant/language/
     401-retry logic (R7.3), and the page reuses `AuthContext`/`useAuth`,
     `TenantContext`/`useTenant`, `TenantSelector`, `UserMenu`, `MainMenu`,
     `ProtectedRoute`, `HelpButton`, `LanguageSelector`, and the field-config pattern
     (`frontend/src/services/fieldConfigService.ts` + `hooks/useFieldConfig.ts` /
     `useMemberFieldConfig`) — myAdmin's existing building blocks, not new ones.

### R8 — Leden Overzicht views, modals, and actions (the bounded UI surface)

**User Story:** As a member administrator, I want the full Leden Overzicht view/modal/action
surface, so that I can operate members end-to-end within my subgroup.

#### Acceptance Criteria

1. THE page SHALL provide a member view modal (read-only detail, opened on row-click)
   sourced from `GET /members/{member_id}`.
2. THE page SHALL provide a member edit modal (Formik/Yup → `PUT /members/{member_id}`) and
   member delete (`DELETE /members/{member_id}`, with confirmation).
3. THE page SHALL provide a member add / application modal (Formik/Yup → `POST /members`
   and/or `POST /members/{member_id}/memberships`).
4. THE page SHALL provide an export action (`GET /members/export` or client-side CSV of
   loaded rows).
5. THE page SHALL provide a single-member lifecycle transition action
   (`POST /members/{member_id}/memberships/{membership_id}/transition`), with allowed
   transitions constrained by the module response.
6. THE page SHALL provide bulk actions including a bulk lifecycle transition over selected
   rows (`POST /memberships/transition`).
7. ALL views/modals/actions SHALL be subgroup/scope-filtered — a scoped user sees and acts
   only within their granted subgroup, as enforced authoritatively by the module edge.

### R9 — Local end-to-end run + gated prod run

**User Story:** As a reviewer, I want a documented, runnable local walkthrough and a gated
prod deploy, so that "done" means clickable against real data, not just green tests.

#### Acceptance Criteria

1. A documented walkthrough (`walkthrough.md` in this spec folder) SHALL let a human, from a
   clean start, run `npm start` (frontend) + docker (`myadmin-local` + `dynamodb-local` on
   `localhost:8000`) + `sam build` + `sam local start-api` + provision the local
   `governance_projection` and `sam-members-local` tables + project `h-dcn`'s config/grants
   + seed the catalog, log in, open Ledenadministratie → Leden Overzicht, and step through
   filter → view → edit → add → transition (single + bulk) → export.
2. THE walkthrough SHALL demonstrate scope: a Noord-scoped `h-dcn` user sees only Noord
   members, and a general (all-access) user sees all — closing the S5 Go/No-Go MANUAL look
   & feel/UX item (`s5-members-first-migration/go-no-go.md`).
3. Long-running processes (`docker compose up`, `sam local start-api`, `npm start`) SHALL be
   run by the operator or via `control_bash_process`, never as foreground blocking commands
   (per `41-shell-environment.md` / `42-local-dynamodb-testing.md`).
4. As a gated, human-run, high-risk phase (`23-aws-accounts.md`), the Members SAM app SHALL
   be deployable to myAdmin prod (`sam build` + `sam deploy` under `nonprofit-deploy`,
   `eu-west-1`), the prod `sam-members` + `governance_projection` tables SHALL be
   managed-outside-CFN/retain, and `h-dcn`'s config/grants SHALL be projected in prod.
5. IF the prod pilot requires live-token entitlement for `h-dcn`, THEN that is the deferred
   S5 Step 7 Pool A PreTokenGen trigger — this spec SHALL cross-reference S5 R6.2/R6.3 and
   NOT duplicate it.
6. Prod rollback SHALL be reversible via governance: remove the `MEMBERS` entitlement and/or
   the scope grants in Tenant Admin and re-project — no destructive table operations.

### R10 — Testing preserved + new reader/frontend tests added

**User Story:** As an engineer, I want the S5 tests preserved and the S5b delta covered
across both test planes plus the docs build, so that the projection builders/sync, the
module projection reader, the frontend page, and the manual are all verified — placed on
the correct plane, property-tested where the design's correctness properties apply, and
meeting the coverage bar — without touching proven logic.

#### Acceptance Criteria

1. THE existing 612 S5 module tests SHALL continue to pass and SHALL NOT be modified by this
   spec (the module domain/repository logic is unchanged).
2. THE module projection reader SHALL have tests feeding `scope_dimensions`/`field_resolver`/
   `scope_access` from projected rows — including the empty-is-valid cases (R1.6, R1.7) and
   deny-by-default (R2.6) — mirroring `sam/tests/test_projection_governance_reader.py`.
3. THE projection builder + sync extension SHALL have backend unit tests covering
   `config#scope`, `config#fields`, and `scopegrant#` row construction from their MySQL
   sources, and the `enqueue_sync` trigger on config/grant change.
4. THE projection builder + sync-trigger tests (the `config#scope`/`config#fields`/
   `scopegrant#` row construction plus `enqueue_sync` on config/grant change, R10.3) SHALL
   be Flask/MySQL-plane tests placed in `backend/tests/unit/`, using the `mock_db`/`mock_env`
   fixtures and the pytest markers per `34-backend-testing.md` (no real DB connection), and
   named `test_{function}_{scenario}_{expected}`.
5. THE module projection-reader tests (R10.2) SHALL be SAM-plane tests placed in
   `sam/tests/` and run via `sam/pytest.ini` per `35-sam-module-architecture-sam.md` (an
   in-memory fake table / local `dynamodb-local`), mirroring
   `sam/tests/test_projection_governance_reader.py`.
6. THE design correctness Properties 2 (config round-trip), 3 (empty-is-valid), and 4
   (scope-grant deny-by-default) SHALL be verified by property-based tests using a
   property-based library for the target language (Python `hypothesis` on the SAM plane
   for the pure MySQL→row and row→provider mapping layers), running a minimum of 100
   generated iterations each, tagged
   `Feature: s5b-members-runnable-in-spa, Property N: <text>` — consistent with the design
   Testing Strategy and the module's existing property tests. The frontend / SAM-template /
   config layer stays example-tested.
7. THE new frontend service + page + modals SHALL have component/service tests per
   `33-frontend-testing.md` (Vitest + React Testing Library + MSW), covering render,
   filtering, row-click modal, subgroup filtering, active-only dropdown, and each action's
   request shape.
8. THE frontend component tests (Vitest + RTL + MSW, `33-frontend-testing.md`) SHALL assert
   the Leden Overzicht page uses the shared Table Filter Framework v2 components
   (`FilterableHeader` / `FilterPanel` from `frontend/src/components/filters/`) and the
   shared chrome — that it renders and drives the shared filter components rather than a
   bespoke table/filter — so the R7.9 reuse obligation cannot silently regress.
9. THE new backend/module code introduced by this spec (the projection builders, the
   sync-trigger extension, and the module projection reader) SHALL meet the
   `34-backend-testing.md` coverage target of 80% for new code (`pytest --cov`), focused on
   the mapping/business logic and not boilerplate.
10. A local smoke test SHALL exercise the module's routes via curl/token against
    `dynamodb-local` (module up under `sam local start-api`, `h-dcn` config/grants projected)
    to confirm the bridge before the UI walkthrough.
11. THE end-user documentation (R11) SHALL be verified by a successful `mkdocs build` (from
    `docs/`) for BOTH the nl and en locales with the new `docs/docs/members/` section wired
    into `docs/mkdocs.yml` `nav`, before the feature is considered done.

### R11 — End-user documentation (MkDocs manual section)

**User Story:** As a member administrator, I want a published manual section for Leden
Overzicht, so that I can learn the member-administration workflows without reading the code
— satisfying the steering rule that every feature ships an end-user manual section
(`40-spec-workflow.md`: "End-user documentation: every feature needs a manual section per
`.kiro/specs/Common/end-user-documentation/`").

#### Acceptance Criteria

1. THE Leden Overzicht feature SHALL have an end-user manual section under
   `docs/docs/members/` (a new per-module section), authored bilingually (nl primary +
   en) following the existing `*.md` + `*.en.md` convention used by the other module
   sections (e.g. `docs/docs/zzp/`, `docs/docs/tenant-admin/`).
2. THE `docs/docs/members/` section SHALL cover the member-administrator workflows: the
   overview table + filters/view-switch, viewing a member, editing a member, adding a
   member, deleting a member, exporting, single and bulk lifecycle transition, the
   membership-type dropdown, and how subgroup/region scoping affects what a user sees.
3. THE new section SHALL be wired into the MkDocs navigation (`docs/mkdocs.yml` `nav`)
   alongside the other module sections, matching the Material for MkDocs + i18n-plugin
   setup already declared in `docs/mkdocs.yml`.
4. THE documentation SHALL follow the conventions in
   `.kiro/specs/Common/end-user-documentation/` and the existing module docs
   (`docs/docs/zzp/`, `docs/docs/tenant-admin/`) as the pattern.
5. THE manual SHALL be scoped to the Leden Overzicht surface (consistent with this spec's
   UI scope); WHERE the SysAdmin / Tenant-Admin onboarding steps (R3) are relevant, the
   manual SHALL cross-reference the existing tenant-admin docs
   (`docs/docs/tenant-admin/`) rather than duplicate them.

## Success metrics

- A scoped `h-dcn` user (e.g. region Noord) sees only Noord members through the SPA, and a
  general user sees all — with the scope decision driven entirely by projected
  `scopegrant#` rows and `config#scope`, never a token scope claim or a pilot flag.
- `h-dcn`'s tenant + module entitlement + role definitions are provisioned by SysAdmin
  (`/api/sysadmin/*`), and its users + role assignments + tenant-scope parameters are
  authored by the Tenant Admin (`/api/tenant-admin/*`) — both in the normal myAdmin SPA
  (backed by MySQL) — and flow to the module via the projection sync; a members-only tenant
  never opens a MySQL tool.
- The module Lambda reads config/grants only from the `governance_projection` (boto3), never
  from MySQL — the S1 rule holds.
- A human completes the R9 local walkthrough end-to-end against real projected/seeded data —
  the runnable+clickable definition of done — satisfying the S5 Go/No-Go MANUAL item.
- The 612 S5 tests stay green; new projection-reader, projection-builder, and frontend tests
  are green.
- The prod phase (R9.4–R9.6) is deployable by a human with a reversible governance rollback,
  executed only under the gate.
- The feature has a published bilingual (nl + en) end-user manual section under
  `docs/docs/members/`, wired into `docs/mkdocs.yml` `nav`, and `mkdocs build` succeeds
  (R11).

## Out of scope

- **Other h-dcn surfaces:** MyAccount / self-service, Events, Webshop, and the rest of the
  h-dcn admin surface beyond Leden Overzicht (future migrations).
- **Rebuilding the S5 membership domain** — the S5 generic membership domain
  (`sam/members/domain/`) and repository (`sam/members/repository/`) business logic, and
  its 612 tests, are out of scope to rewrite; S5b changes only the wiring around them (swap
  the stub config providers for the projection reader, remove the pilot-routing gate, add
  the SAM template / SPA / onboarding). Changing the membership domain logic itself is out
  of scope.
- **Pilot-routing as an access gate** — `MEMBERS_PILOT_ROUTING` is dropped entirely; access
  is capability (token) + scope grant (projection).
- **Scope on the token claim** — subgroup scope is a projected per-user fact, never a token
  claim.
- **The S5 Step 7 production Pool A live-token trigger** — deferred and cross-referenced
  (R9.5).
- **A Flask `/api/members/*` proxy (single-origin routing option)** — this spec has the
  SPA call the Members module API **directly** (`membersApiService.ts` → `MEMBERS_API_BASE_URL`,
  design D1 option a). An alternative is to route member calls through the Flask backend —
  Flask exposes `/api/members/*` and forwards to the module API server-side (via
  `resolve_module_api_base`) so the browser talks to a single origin. This is purely a
  network/origin choice (it does **not** change authorization — the module edge enforces
  capability + scope either way) and is noted as a later prod-consolidation option, **not
  built here** (design D1 option b).
- **Second-tenant onboarding, new membership domains, or module logic changes** — `h-dcn`'s
  `region` is the first instance; a second club's dimension (e.g. `team`) is pure config,
  no code, and out of scope for this spec.

## Prerequisites (already satisfied / available)

- The S5 Members module code (`sam/members/`), 612 passing tests, the consuming provider
  seams (`scope_dimensions.py` `ScopeConfigProvider`, `field_resolver.py`
  `TenantOverlayProvider`, `scope_access.py` `resolve_scope_access`), and the `MEMBERS`
  `MODULE_REGISTRY` entry (`api_base_env=MEMBERS_MODULE_API_BASE`).
- The governance projection + sync (`backend/src/services/projection_schema.py`,
  `projection_sync.py`, `projection_sync_trigger.py`) and the reader pattern to mirror
  (`sam/pretokengen/projection_governance_reader.py`).
- The MySQL config/grant sources: `tenant_template_config` + `ParameterService`
  (`backend/src/services/parameter_service.py`) + `FieldConfigMixin`; `user_tenant_roles`
  + `auth`/`role_cache.py`.
- Tenant Admin surfaces (`backend` `tenant_admin` routes/tests,
  `frontend/src/services/tenantAdminApi.ts`, `frontend/src/pages/TenantAdmin/`).
- The SPA integration seams (`appPages.tsx`, `AppRoutes.tsx`, `apiService.ts`, `AuthContext`,
  `TenantContext`, `fieldConfigService.ts`, `hooks/useFieldConfig.ts`, `ProtectedRoute`,
  `MainMenu.tsx`) and the `ZZPInvoices.tsx` reference page.
- Local infra: docker `dynamodb-local` + `myadmin-local` network, the standing test pool.
