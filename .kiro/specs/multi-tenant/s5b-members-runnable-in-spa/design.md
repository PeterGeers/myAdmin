# Design Document

## S5b — Members runnable in the myAdmin SPA, fed by the governance projection — Design

- Requirements: `./requirements.md`
- Parent (REUSE — domain/repository/route map unchanged):
  `.kiro/specs/multi-tenant/s5-members-first-migration/`.
- Decisions: ADR `0004` (verified JWT), `0005` (MySQL SoR + one-directional projection),
  `0006` (entitlement + projection).
- Steering: `35-sam-module-architecture-sam.md`, `32-frontend-ui.md`,
  `42-local-dynamodb-testing.md`, `23-aws-accounts.md`, `22-authentication.md`,
  `21-identity.md`, `33-frontend-testing.md` / `34-backend-testing.md`.
- Grounding code (cited throughout): `backend/src/services/projection_schema.py`,
  `projection_sync_trigger.py`, `module_registry.py`, `parameter_service.py`,
  `backend/src/routes/parameter_admin_routes.py`, `backend/src/services/parameter_schema.py`;
  `frontend/src/services/sysadminService.ts`, `tenantAdminApi.ts`, `parameterService.ts`;
  `sam/members/domain/scope_dimensions.py`, `scope_access.py`, `field_resolver.py`,
  `sam/members/handler/app.py`; `sam/pretokengen/projection_governance_reader.py`.
- Actor split (verified against myAdmin code): tenant create + module entitlement + role
  definitions = **SysAdmin** (`/api/sysadmin/*`); users + role assignment + tenant-scope
  parameters = **Tenant Admin** (`/api/tenant-admin/*`).

## Overview

S5b answers one settled question: **how does the SAM-built Members module get its tenant
configuration (scope dimension + allowed values, field overlay) and its per-user subgroup
grants, given a SAM Lambda must never read MySQL (S1)?** The answer is to **feed the module
through the existing one-directional MySQL→DynamoDB governance projection** (ADR 0005/0006),
the same pipeline that already carries `tenant`/`module#…`/`role#…` governance rows. S5b
adds new projected record types, connects the module's already-built consuming seams to a
projection reader (replacing the S5 in-memory stubs), onboards `h-dcn` as a real tenant
through Tenant Admin, and makes the module runnable + clickable in the SPA (local-first,
then a gated prod phase).

**Three distinct channels, kept clean:**

| Channel | Question | System of record | Carrier to the module |
| --- | --- | --- | --- |
| **Capability** | May this user act on Members at all? | Cognito/entitlement (S4) | verified token `custom:entitlements` (`members:read/write/export/admin`) — **unchanged** |
| **Scope grant** | On which subgroup? | MySQL `user_tenant_roles` | projected `scopegrant#<email>#<dimension>` row |
| **Tenant config** | What dimension/values/fields? | MySQL `tenant_template_config` / parameters | projected `config#scope` + `config#fields` rows |

**Discipline (settled):**

- **One-directional / MySQL-SoR (ADR 0005).** The module READS config/grants from the
  projection and NEVER writes them back. Edits go to MySQL via the correct actor's surface —
  SysAdmin (`/api/sysadmin/*`: entitlement + role defs) or Tenant Admin (`/api/tenant-admin/*`:
  role assignment + tenant params) — and re-project.
- **No pilot-routing gate.** `MEMBERS_PILOT_ROUTING` is dropped as the access gate; access =
  capability (token) + scope grant (projection). Scope is **never** a token claim.
- **Empty-is-valid.** No `config#scope` → tenant-wide `["*"]`; no `config#fields` → the
  fixed base; empty entitlement → S4 semantics. Never a crash.
- **On-change sync.** The existing `enqueue_sync` trigger extends to fire on scope-grant /
  tenant-config change; reconciliation backstops any missed signal
  (`projection_sync_trigger.py`).
- **Both admin actors use the normal myAdmin SPA, not a MySQL tool.** SysAdmin
  (`/api/sysadmin/*`) provisions tenant + module entitlement + role defs; Tenant Admin
  (`/api/tenant-admin/*`) manages users + role assignment + tenant params. A members-only
  tenant is a normal tenant entitled only to MEMBERS.

### REUSED (S5, unchanged) vs NEW (S5b), and what is REMOVED

| Area | REUSED | NEW | REMOVED |
| --- | --- | --- | --- |
| Module edge | `handler/app.py`, router, routes | scope-grant edge integration wiring | pilot-routing gate (`_enforce_pilot_routing`, `MEMBERS_PILOT_ROUTING`) |
| Module domain | `scope_dimensions.py`, `scope_access.py`, `field_resolver.py` (unchanged logic) | a projection reader that implements `ScopeConfigProvider` + `TenantOverlayProvider` + a scope-grant lookup | the in-memory `StaticScopeConfigProvider`/`StaticOverlayProvider` as the production source |
| Repository | `repository/` + `table_design.py` (`sam-members`) | — | — |
| Projection | `projection_schema.py`, `projection_sync.py`, `projection_sync_trigger.py` | `config#scope`/`config#fields`/`scopegrant#` record types + builders + sync/trigger extension | — |
| Frontend | `apiService.ts`, `appPages.tsx`, `AppRoutes.tsx`, `ZZPInvoices.tsx`, SysAdmin (`sysadminService.ts`) + Tenant Admin (`tenantAdminApi.ts`, `parameterService.ts`) | `membersApiService.ts`, `MembersPage`, modals, hooks, `members` i18n, `hasMEMBERS` gate | — |
| Tests | 612 module tests | projection-reader + projection-builder + frontend tests | — |

## Architecture

### Data flow (config + grant provisioning → module consumption)

```
myAdmin SPA authoring surfaces (no MySQL tool)     ── two actors, correct split
  SysAdmin  (/api/sysadmin/*, sysadminService.ts)   ── tenant create + module entitlement + role DEFS
  Tenant Admin (/api/tenant-admin/*, tenantAdminApi.ts + parameterService.ts) ── users + role ASSIGNMENT + tenant params
  ▼  (writes, MySQL SoR — ADR 0005)
MySQL
  tenant_modules              ── MEMBERS entitlement ← SysAdmin (PUT /api/sysadmin/tenants/{h-dcn}/modules)
  role definitions            ── Members_* + region-scoped ← SysAdmin (/api/sysadmin/roles)
  user_tenant_roles           ── per-user role assignment (region=Noord | *) ← Tenant Admin (POST /api/tenant-admin/users/{u}/groups)
  tenant_template_config /    ── scope dimension values + field overlay ← Tenant Admin
    tenant-scope parameters      (parameterService.ts → ParameterService.set_param(scope="tenant"), /api/tenant-admin/parameters)
  ▼  (after commit: enqueue_sync(administration) — projection_sync_trigger.py, R5)
Projection sync (ProjectionSync, one-directional)  ── builds rows per projection_schema.py
  ▼  put_item into governance_projection partition tenant_id == administration
governance_projection (DynamoDB)   PK tenant_id, SK record_type#id, version
  tenant                                   (existing)
  module#members                           (existing — entitlement mirror ← SysAdmin)
  role#<email>#<role>                       (existing — per-user roles ← Tenant Admin)
  config#scope     (NEW, tenant-level)      ── dimension key/values/wildcard/required_for ← Tenant-Admin tenant params
  config#fields    (NEW, tenant-level)      ── variable overlay + fixed-field overrides ← Tenant-Admin tenant params
  scopegrant#<email>#<dimension> (NEW, per-user) ── granted values | "*" ← Tenant-Admin role assignment (user_tenant_roles)
  ▲  (boto3 Query on partition tenant_id — READ ONLY; never writes back)
Members module projection reader (mirrors sam/pretokengen/projection_governance_reader.py)
  ▼ implements the S5 seams
  ScopeConfigProvider   → scope_dimensions.ScopeConfig  (from config#scope)
  TenantOverlayProvider → field_resolver.TenantOverlay  (from config#fields)
  scope-grant lookup    → granted values per dimension  (from scopegrant# rows)
  ▼
Module edge (handler/app.py): get_verified_claims → tenant from verified entitlement →
  has_capability (S4 token) → resolve_scope_access(dimension, granted values) → dispatch
  ▼
Domain (MembershipService) → Repository (sam-members) → dynamodb-local / prod sam-members
```

### Data flow (SPA → module API, runtime)

```
Browser (Vite) — Ledenadministratie / Leden Overzicht page
  membersApiService.ts → MEMBERS_API_BASE_URL (import.meta.env, fail-fast)
  Authorization: Bearer <Cognito idToken>, X-Tenant, X-Language  (reused header logic)
  ▼ (CORS: module edge _CORS_HEADERS)
Members module API (sam local start-api local; API Gateway + Cognito authorizer prod)
  ▼
Members Lambda edge → get_verified_claims → capability (token) → scope (projection) →
  domain → repository → sam-members
```

The Flask backend (`API_BASE_URL`) still serves the rest of the SPA (auth context, tenant
list, Tenant Admin, other modules). Members traffic goes straight to the module API.

### Local run topology (per 42-local-dynamodb-testing.md)

Docker network `myadmin-local`; `dynamodb-local` container (alias `dynamodb-local:8000`
in-net, `localhost:8000` host); `sam local start-api --docker-network myadmin-local` joins
the network so the Lambda reaches `dynamodb-local:8000`; host provision/seed scripts use
`localhost:8000`. Both the `governance_projection` (local: prefixed) and `sam-members-local`
tables live in the same local DynamoDB. Long-running processes run via
`control_bash_process` / operator, never foreground.

## Components and Interfaces

### C1 — New projected record types (`config#scope`, `config#fields`, `scopegrant#`)

- **Responsibility:** extend the projection's key schema with three new record types,
  registered where `RECORD_TYPE_TENANT`/`_MODULE`/`_ROLE` are defined in
  `backend/src/services/projection_schema.py`. The `#`-join / split convention stays owned
  by `build_sort_key`/`split_sort_key` (the only place the composite is assembled/parsed).
- **Interface (new tokens):** `RECORD_TYPE_CONFIG = "config"` (id parts `scope` | `fields`,
  tenant-level, no email segment) and `RECORD_TYPE_SCOPEGRANT = "scopegrant"` (id parts
  `<email>`, `<dimension>`, per-user). SK values:
  `build_sort_key("config", "scope")` → `config#scope`;
  `build_sort_key("config", "fields")` → `config#fields`;
  `build_sort_key("scopegrant", email, dimension)` → `scopegrant#<email>#<dimension>`.
- **PK/version:** unchanged — PK `tenant_id == administration`; `version` monotonic per item
  for idempotent writes + read-side staleness (as for existing rows).

### C2 — Projection builders (MySQL sources → new rows)

- **Responsibility:** build the three new rows from their MySQL systems of record during a
  tenant sync, alongside the existing `tenant`/`module`/`role` builders in
  `backend/src/services/projection_sync.py`.
- **`config#scope` source (← Tenant Admin):** tenant-scope parameters authored by the
  Tenant Admin (`parameterService.ts` → `/api/tenant-admin/parameters` →
  `ParameterService.set_param(scope="tenant")`, `backend/src/services/parameter_service.py`,
  `backend/src/routes/parameter_admin_routes.py`; `members.*` namespace gated to the active
  MEMBERS module by `backend/src/services/parameter_schema.py`) — the parameter-driven
  predefined-values system. Fields: `key`, `label`, `enabled`, `multi_valued`, `values`
  (e.g. Noord/Zuid/Oost/West), all-access wildcard role, `required_for` capabilities — the
  shape `sam/members/domain/scope_dimensions.py` `ScopeDimension` consumes.
- **`config#fields` source (← Tenant Admin):** the field-config tenant-scope parameters
  (same `/api/tenant-admin/parameters` surface; `FieldConfigMixin` / `tenant_template_config`).
  Fields: the variable overlay (added fields) + presentation overrides of fixed fields — the
  shape `sam/members/domain/field_resolver.py` `TenantOverlay` consumes.
- **`scopegrant#` source (← Tenant Admin):** MySQL `user_tenant_roles` for the tenant,
  written by the Tenant Admin's role assignment (`POST /api/tenant-admin/users/{username}/groups`,
  `tenantAdminApi.ts`) — decode each user's per-tenant Members roles into granted dimension
  values (a subgroup-scoped role → that value; an all-access role → `*`), using the dimension
  values from the tenant params above. One row per (user, dimension) with a grant. Note the
  underlying `Members_*` role **definitions** are authored by SysAdmin (`/api/sysadmin/roles`);
  the per-user **assignment** is the Tenant-Admin action projected here.
- **Discipline:** builders issue **zero** MySQL writes and never write the projection
  themselves — they return items for `ProjectionSync` (the sole writer), matching the
  one-directional contract documented in `projection_sync_trigger.py`.

### C3 — Sync + on-change trigger extension

- **Responsibility:** ensure the projection stays current when config/grants change.
- **Interface:** the config/grant write paths in the Flask plane call `enqueue_sync(admin)`
  after a committed write to `tenant_template_config`/parameters (config) or
  `user_tenant_roles` (grant), exactly as `activate_module` already calls it for
  `tenant_modules` (`backend/src/services/module_registry.py`). `ProjectionSync` builds the
  C2 rows during `sync_administration`; `reconcile` backstops any missed signal. The trigger
  never breaks the governance write (best-effort, logged) — unchanged semantics.

### C4 — Members module projection reader (replaces the S5 stubs)

- **Responsibility:** the module's read-only, `boto3`-backed consumer of the projected rows,
  mirroring `sam/pretokengen/projection_governance_reader.py` (one `Query` per tenant
  partition, per-invocation cache, fail-fast table resolution via
  `services.projection_schema.resolve_projection_table_name`, empty-is-valid).
- **Interface / implements the S5 seams:**
  - `get_scope_config(tenant_id) -> ScopeConfig` — implements
    `scope_dimensions.ScopeConfigProvider` by reading the `config#scope` row and building
    `ScopeDimension`(s). A missing row → `ScopeConfig(tenant_id, dimensions=())`
    (tenant-wide), never an error (R1.6).
  - `get_overlay(tenant_id) -> TenantOverlay` — implements
    `field_resolver.TenantOverlayProvider` by reading the `config#fields` row. A missing row
    → `TenantOverlay()` (fixed base only), never an error (R1.7).
  - `get_scope_grants(tenant_id, email) -> {dimension: [values] | ["*"]}` — reads the
    `scopegrant#<email>#<dimension>` rows for the caller. A missing grant → absent from the
    map (the edge then applies deny-by-default via `required_for`, R2.6).
- **Layering:** SAM-plane infrastructure adapter — it depends on `boto3` + the projection
  schema, and produces the storage-agnostic domain shapes the unchanged domain consumes. The
  domain (`scope_dimensions`/`field_resolver`/`scope_access`) never imports it.

### C5 — Scope-grant edge integration (`handler/app.py`)

- **Responsibility:** wire the reader into the edge so `resolve_scope_access` runs on
  **projected** grants, and remove the pilot-routing gate.
- **Interface:** at request time the edge (1) `get_verified_claims` → tenant from verified
  entitlement (unchanged), (2) `has_capability` on the token (unchanged, R4), (3) resolves
  the tenant's `ScopeConfig` (C4), (4) reads the caller's projected grants (C4), (5) calls
  `sam/members/domain/scope_access.py` `resolve_scope_access(tenant, dimension,
  granted-as-roles)` — or, where the reader returns explicit granted values, resolves
  directly to those values / `["*"]` — then filters the domain read/write by
  `allowed_scopes`. The `_enforce_pilot_routing` step and `MEMBERS_PILOT_ROUTING` env are
  **removed**.
- **Note on the role→value seam:** `resolve_scope_access` already decodes roles→values
  generically; the reader can either project the *granted values* directly (preferred — the
  MySQL SoR already knows them) or project the scoped *role names* and let the existing
  decoder run. The design projects **values** for `scopegrant#` (cleaner, dimension-keyed)
  and keeps `resolve_scope_access` as the deny-by-default authority.

### C6 — Tenant-config / field-overlay provider wiring

- **Responsibility:** construct the module's `FieldResolver` (C3 in S5) and
  `ScopeConfigProvider` from C4 instead of the S5 `Static*` providers, at module cold start.
- **Interface:** dependency-injected exactly as the S5 seams intend (both `field_resolver.py`
  and `scope_dimensions.py` document a DynamoDB-backed provider swapped in "a later step" —
  this is that step). No domain code changes; only the provider construction changes.

### C7 — `membersApiService.ts` (SPA → module bridge)

- **Responsibility:** the single frontend seam reaching the Members module API.
- **Interface / inputs:** `MEMBERS_API_BASE_URL` (`import.meta.env`, fail-fast if unset); the
  Cognito ID token via the existing auth-token helper; current tenant + language for
  `X-Tenant`/`X-Language`.
- **Interface / outputs:** typed wrappers per route group — `listMembers`, `searchMembers`,
  `getMember`, `createMember`, `updateMember`, `deleteMember`, `exportMembers`,
  `getFieldConfig`, `listMembershipTypes`, `createMembership`, `transitionMembership`,
  `bulkTransition`.
- **Behaviour:** mirrors `frontend/src/services/apiService.ts` (auth header + `X-Tenant` +
  `X-Language` + 401 refresh-retry) but base = `MEMBERS_API_BASE_URL`.

### C8 — `MembersPage` (Ledenadministratie / Leden Overzicht) + table

- **Responsibility:** the runnable, clickable member-administration surface.
- **Interface / inputs:** rows from `GET /members` (+ `POST /members/search`); field config
  from `GET /members/field-config` (drives the view-switch columns, rendering fixed⊕overlay
  fields); i18n from the `members` namespace.
- **Structure — COMPOSES the shared toolkit (R7.9), does not rebuild it:** dark theme +
  header-right orange primary actions (`colorScheme="orange"` primary, `variant="ghost"`
  secondary) following `frontend/src/pages/ZZPInvoices.tsx` and the `32-frontend-ui.md`
  BankingProcessor pattern (no per-row buttons; row-click opens the view modal). The table
  is a Chakra `Table variant="simple"` on `bg="gray.800"` with sortable headers,
  hover-highlighted rows, `Badge` for the read-only subgroup/region column, responsive
  `overflowX="auto"`, driven by the shared Table Filter Framework v2 components at
  `frontend/src/components/filters/` (`FilterPanel.tsx`, `FilterableHeader.tsx`,
  `GenericFilter.tsx`, `YearFilter.tsx`, `types.ts`) via `useFilterableTable` /
  `useColumnFilters` / `useTableSort` for region/status/type pre-filters; compact/full view
  switch from field config; selection checkboxes drive bulk actions. The page reuses the
  shared chrome — `AuthContext`/`useAuth`, `TenantContext`/`useTenant`, `TenantSelector`,
  `UserMenu`, `MainMenu`, `ProtectedRoute`, `HelpButton`, `LanguageSelector`,
  `fieldConfigService.ts`/`useFieldConfig` — rather than introducing new equivalents.

### C9 — Modals + actions

- **Pattern (R7.9):** every modal is a Chakra `Modal` built with Formik + Yup, a
  Cancel(ghost)/Save(orange) button layout, and `closeOnOverlayClick={false}` for edit
  modals — following `32-frontend-ui.md` and the `ZZPInvoices.tsx` reference, not bespoke
  form scaffolding.
- **View modal** — `GET /members/{member_id}` (read-only, row-click).
- **Edit modal** — Formik/Yup → `PUT /members/{member_id}`; membership-type dropdown from
  `GET /membership-types` (active-only).
- **Add / application modal** — Formik/Yup → `POST /members` (+ optional
  `POST /members/{member_id}/memberships`).
- **Delete** — confirm → `DELETE /members/{member_id}`.
- **Export** — `GET /members/export` or client-side CSV of loaded rows.
- **Single transition** — `POST /members/{member_id}/memberships/{membership_id}/transition`.
- **Bulk transition** — over selected ids → `POST /memberships/transition`.
- All are subgroup/scope-filtered by the module edge (C5) — the UI never invents scope.

### C10 — SPA registration + `hasMEMBERS` gate + i18n/hooks

- **Interface / `appPages.tsx`:** `MembersPage = lazy(...)`; `'members'` in the `PageType`
  union; `'/leden': 'members'` in `urlPageMap`.
- **Interface / `AppRoutes.tsx`:** `case 'members'` under
  `ProtectedRoute requiredRoles={['Members_Read','Members_CRUD']}` + standard chrome.
- **Interface / `MainMenu.tsx`:** an entry gated by `hasMEMBERS`.
- **`hasMEMBERS`:** a boolean alongside `hasFIN`/`hasSTR`/`hasZZP`, derived from the module
  entitlement (`MEMBERS` in `tenant_modules`), threaded into `AppRoutes`/`MainMenu`.
- **Hooks/i18n:** `useMemberFieldConfig` (pairs with `fieldConfigService.ts`/
  `hooks/useFieldConfig.ts`) fetching `GET /members/field-config`; the `members` i18n
  namespace (nl + en) via `useTypedTranslation`.

### C11 — Members SAM template + Lambda layer (operational)

- **Responsibility:** make the one-Lambda module build (`sam build`) and run
  (`sam local start-api`).
- **Interface / params+env:** `MEMBERS_TABLE`, `GOVERNANCE_PROJECTION_TABLE`, `AWS_REGION`
  (`eu-west-1`), and — local only — `AWS_ENDPOINT_URL_DYNAMODB` (all fail-fast, no
  defaults). **No `MEMBERS_PILOT_ROUTING`.**
- **Interface / outputs:** `MembersLayer` (vendors `sam/shared` + `sam/members` + shared
  `dynamodb_client`) + `MembersFunction` (handler `sam.members.handler.app.handler`,
  `ANY /{proxy+}` API, Cognito authorizer in prod). The `sam-members` and
  `governance_projection` tables are **not** template resources (managed-outside-CFN /
  retain, `23-aws-accounts.md`).

### C12 — SysAdmin provisioning + Tenant-Admin config authoring (REUSE)

- **Responsibility:** `h-dcn` is onboarded through the two existing myAdmin admin surfaces,
  each owned by the correct actor — no new UI, no MySQL tool. Every commit triggers the C3
  sync.
- **SysAdmin surface (`/api/sysadmin/*`, `frontend/src/services/sysadminService.ts`, role
  `SysAdmin`):**
  - Tenant creation + initial admin: `createTenant(...)` → `POST /api/sysadmin/tenants`
    (`administration`, `display_name`, `contact_email`, `enabled_modules`,
    `initial_admin_email`, `locale`).
  - Module entitlement: `getTenantModules`/`updateTenantModules` → `GET/PUT
    /api/sysadmin/tenants/{administration}/modules` (`tenant_modules`, `MODULE_REGISTRY`,
    `activate_module`, `backend/src/services/module_registry.py`).
  - Role definitions: `getRoles`/`createRole`/`updateRole` → `/api/sysadmin/roles`
    (`Members_*` + region-scoped defs; `precedence` + `category`).
- **Tenant-Admin surface (`/api/tenant-admin/*`, scoped by `X-Tenant`, role `Tenant_Admin`):**
  - Users: `createUser`/`listUsers`/`removeUser` → `/api/tenant-admin/users`
    (`frontend/src/services/tenantAdminApi.ts`).
  - Role assignment: `assignRole`/`removeRole` → `POST/DELETE
    /api/tenant-admin/users/{username}/groups`, available roles via `getAvailableRoles` →
    `GET /api/tenant-admin/roles` (writes `user_tenant_roles`).
  - Tenant parameters: region values + field overlay via `frontend/src/services/parameterService.ts`
    → `/api/tenant-admin/parameters` (GET/POST/PUT/DELETE) →
    `backend/src/routes/parameter_admin_routes.py` + `ParameterService.set_param(scope="tenant")`;
    `members.*` namespace gated to the active MEMBERS module by
    `backend/src/services/parameter_schema.py`.

### C13 — Module API contract (REUSE, as declared by `routes.py`)

| UI action | Method + path | Capability |
| --- | --- | --- |
| Table load | `GET /members` | `members:read` |
| Server-side filter | `POST /members/search` | `members:read` |
| Field config / view switch | `GET /members/field-config` | `members:read` |
| View member | `GET /members/{member_id}` | `members:read` |
| Add member | `POST /members` | `members:write` |
| Edit member | `PUT /members/{member_id}` | `members:write` |
| Delete member | `DELETE /members/{member_id}` | `members:admin` |
| Export | `GET /members/export` | `members:export` |
| Add membership | `POST /members/{member_id}/memberships` | `members:write` |
| Single transition | `POST /members/{member_id}/memberships/{membership_id}/transition` | `members:write` |
| Bulk transition | `POST /memberships/transition` | `members:admin` |
| Membership types | `GET /membership-types` (active-only) | `members:read` |

Edge status contract (reused): `401` unauth, `403` unentitled/out-of-scope-write, `404`
not-found / out-of-scope-read, `405` wrong method. (No `not-pilot-routed` status — the
pilot gate is removed.)

### C14 — End-user documentation (MkDocs manual section)

- **Responsibility:** ship the feature's end-user manual, per the steering rule that every
  feature needs a manual section (`40-spec-workflow.md`;
  `.kiro/specs/Common/end-user-documentation/`). Docs are content, not code — no PBT.
- **Interface / files:** a new per-module section `docs/docs/members/` authored bilingually
  (nl primary + `*.en.md`) matching the existing module docs (`docs/docs/zzp/`,
  `docs/docs/tenant-admin/`): an `index.md`/`index.en.md` overview plus pages covering the
  overview table + filters/view-switch, view/edit/add/delete a member, export, single +
  bulk lifecycle transition, the membership-type dropdown, and how subgroup/region scoping
  changes what a user sees (R11.1, R11.2).
- **Nav wiring:** a `Leden` (nl) / `Members` (en) section added to `docs/mkdocs.yml` `nav`
  alongside the other module sections, under the Material for MkDocs theme + `i18n` plugin
  already configured there (R11.3). SysAdmin/Tenant-Admin onboarding (R3) is
  cross-referenced to `docs/docs/tenant-admin/`, not duplicated (R11.5).
- **Verification:** `mkdocs build` succeeds (both locales build) — the docs-build check in
  the Testing Strategy. Deployed to GitHub Pages by the existing docs pipeline.

## Data Models

### New governance projection rows (grounded in `projection_schema.py`)

All rows: PK `tenant_id` (== `administration`), SK per `build_sort_key`, `version` attr.

**`config#scope`** (tenant-level, one per tenant; source `tenant_template_config`/params):

```json
{
  "tenant_id": "h-dcn",
  "sk": "config#scope",
  "version": "2026-06-01T10:00:00Z",
  "dimensions": [
    {
      "key": "region",
      "label": {"nl": "Regio", "en": "Region"},
      "enabled": true,
      "multi_valued": false,
      "values": ["Noord", "Zuid", "Oost", "West"],
      "all_wildcard": "Regio_All",
      "required_for": ["Members_CRUD"]
    }
  ]
}
```

Consumed by C4 `get_scope_config` → `scope_dimensions.ScopeConfig`. A tenant with no row →
tenant-wide (empty dimensions).

**`config#fields`** (tenant-level, one per tenant; source field-config parameters):

```json
{
  "tenant_id": "h-dcn",
  "sk": "config#fields",
  "version": "2026-06-01T10:00:00Z",
  "fields": {
    "motor_type": {"type": "string", "required": false,
                   "label": {"nl": "Motor", "en": "Motorcycle"}, "order": 10}
  },
  "overrides": {
    "personal.name": {"label": {"nl": "Naam", "en": "Name"}, "order": 1}
  }
}
```

Consumed by C4 `get_overlay` → `field_resolver.TenantOverlay`. A tenant with no row → the
fixed base only. The overlay may never weaken a platform invariant (enforced by
`FieldResolver._reject_invalid_overlay`).

**`scopegrant#<email>#<dimension>`** (per-user; source `user_tenant_roles`):

```json
{
  "tenant_id": "h-dcn",
  "sk": "scopegrant#alice@h-dcn.example#region",
  "version": "2026-06-01T10:00:00Z",
  "dimension": "region",
  "values": ["Noord"]
}
```

`values: ["*"]` denotes all-access. Consumed by C4 `get_scope_grants`; the edge (C5) drives
`resolve_scope_access` — a subgroup grant → that subset, `*` → `["*"]`, no grant on a
`required_for` capability → deny.

### `sam-members` module data (REUSE, unchanged from S5)

Table `sam-members` (`sam-members-local` locally), PK `tenant_id`, SK `record_type#id`
(`member#`, `membership#`, `delegates`, `payment#`, `counter#`, `membernum#`,
`membershiptype#`). The membership-type catalog (`membershiptype#`) stays **module data**
seeded into `sam-members` (tenant business data per S5 C8), **not** the governance
projection. The frontend defines TypeScript types only, never data-shape authority.

## Correctness Properties

*A property is a characteristic that should hold across all valid executions of the system —
a formal statement of what the system should do.*

The S5 domain is unchanged, so its properties (tenant isolation, member-number uniqueness,
lifecycle legality) are inherited. The **new** S5b code is (a) projection builders that map
MySQL facts to projected rows, (b) a module projection reader that maps rows to the domain
provider shapes, and (c) a frontend/config layer. (a) and (b) carry genuine
universally-quantified properties (round-trip of a fact through the projection, empty-is-valid,
deny-by-default) and are property-testable; the frontend/config/IaC layer is example-tested
per the PBT exclusions in `35-sam-module-architecture-sam.md`. The properties below govern
the settled design.

### Property 1: One-directional — the module never writes config/grants back

For all module executions, the module issues zero writes to the `config#*` / `scopegrant#*`
projection rows and zero writes to MySQL; the only writer of those rows is `ProjectionSync`,
and the only editor of the underlying facts is Tenant Admin (MySQL). MySQL remains the
single system of record.

**Validates: Requirements 1.4, 1.5, 2.3, 5.5**

### Property 2: Config round-trips MySQL to projection to resolved provider

For all tenant scope/field configurations authored in MySQL (`tenant_template_config`/
parameters), building the `config#scope` / `config#fields` row and then reading it back
through the module projection reader yields a `ScopeConfig` / `TenantOverlay` equivalent to
the authored configuration (a round-trip through the projection preserves the config).

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

### Property 3: Empty-is-valid collapses to tenant-wide / fixed base

For all tenants with no `config#scope` row, the reader yields a tenant-wide `ScopeConfig`
(empty dimensions, so `resolve_scope_access` returns `["*"]`); and for all tenants with no
`config#fields` row, the reader yields the fixed-field base — in both cases without raising.

**Validates: Requirements 1.6, 1.7**

### Property 4: Scope grant deny-by-default

For all users and dimensions, a user holding a capability the dimension lists in
`required_for` but having no projected `scopegrant#` for that dimension resolves to an empty
`allowed_scopes` (`access_type = "none"`) — a deny — while an all-access grant (`*`) resolves
to `["*"]` and a subgroup grant resolves to exactly its granted subset.

**Validates: Requirements 2.4, 2.5, 2.6**

### Property 5: Tenant isolation stays structural

For all module reads, the projection reader issues a single DynamoDB `Query` on partition
`tenant_id`, so a caller's config/grants can only ever come from their own tenant partition —
cross-tenant reads remain structurally unaddressable (as for the existing governance rows).

**Validates: Requirements 2.1, 7.4**

### Property 6: Verify-before-trust preserved across the SPA to module bridge

For all requests routed through `membersApiService.ts`, the module edge derives `tenant_id`
and capability from the verified token (`get_verified_claims` / `custom:entitlements`) and
never from an `X-Tenant` header or request body; the bridge changes only the network path,
not the verification.

**Validates: Requirements 4.1, 7.3, 7.4**

### Property 7: Capability and scope are independent channels

For all requests, capability (token `custom:entitlements`) determines whether the user may
act on Members, and the projected scope grant determines which subgroup; an empty capability
denies at the edge without consulting scope, and a present capability with no scope grant on
a `required_for` dimension denies via scope — the two channels compose without one masking
the other.

**Validates: Requirements 4.2, 4.3, 2.6**

### Property 8: Runnable-not-just-tested definition of done

For all acceptance of this spec, "done" requires the R9 local walkthrough to complete
against real projected/seeded data (a Noord-scoped user sees only Noord, a general user sees
all) — passing unit tests alone is insufficient.

**Validates: Requirements 9.1, 9.2, 10.5**

## Error Handling

- **Empty-is-valid (never a crash):** a missing `config#scope`/`config#fields` row or a
  missing `scopegrant#` row is a valid state — tenant-wide / fixed-base / deny-by-default
  respectively (Properties 3, 4). The reader mirrors
  `sam/pretokengen/projection_governance_reader.py`: missing/empty partitions return empty,
  never raise.
- **Fail-fast config:** missing `MEMBERS_API_BASE_URL` (frontend) or `MEMBERS_TABLE` /
  `GOVERNANCE_PROJECTION_TABLE` / `AWS_REGION` (module/scripts) throws at startup — no silent
  default (`services.dynamodb_client.require_env`, `23-aws-accounts.md`).
- **Sync never breaks the governance write:** `enqueue_sync` is best-effort and logged; a
  failed signal is picked up by `reconcile` (documented in `projection_sync_trigger.py`).
- **Malformed config surfaces at resolve time:** an invalid overlay/scope config raises
  `OverlayError` / `ScopeConfigError` (fail-fast, a config bug) — the reader builds the
  provider shapes that the domain validates.
- **Edge status:** `403` on out-of-scope write, `404` on out-of-scope read (indistinguishable
  from not-found — no cross-subgroup existence leak); the frontend maps non-2xx to a toast
  and preserves table state (ZZPInvoices pattern). CORS headers are emitted on every response
  incl. errors.

## Testing Strategy

Per `33-frontend-testing.md` / `34-backend-testing.md`.

- **Reuse (backend domain):** the 612 S5 module tests run unchanged (R10.1) — the domain is
  untouched.
- **Projection builder tests (backend unit):** for all authored MySQL configs/grants, assert
  the built `config#scope`/`config#fields`/`scopegrant#` rows match (Property 2), and that
  `enqueue_sync` fires on config/grant change (R5.1, R5.2) using the injectable
  in-memory trigger (`projection_sync_trigger.set_default_trigger`). These are Flask/MySQL-plane
  tests placed in `backend/tests/unit/` using the `mock_db`/`mock_env` fixtures and
  `test_{function}_{scenario}_{expected}` naming per `34-backend-testing.md` (R10.4).
- **Projection reader tests (module):** mirror `sam/tests/test_projection_governance_reader.py`
  — feed `scope_dimensions`/`field_resolver`/`scope_access` from projected rows, including
  empty-is-valid (Property 3) and deny-by-default (Property 4), against an in-memory fake
  table / local `dynamodb-local`. These are SAM-plane tests placed in `sam/tests/` and run
  via `sam/pytest.ini` per `35-sam-module-architecture-sam.md` (R10.5).
- **Coverage (new backend/module code):** the projection builders, the sync-trigger
  extension, and the module projection reader meet the `34-backend-testing.md` 80%-for-new-code
  target (`pytest --cov`), focused on the mapping/business logic, not boilerplate (R10.9).
- **Property-based tests (pure mapping layers):** Properties 2, 3, 4 are universally
  quantified over generated configs/grants and MUST use a property-based library for the
  target language (min. 100 iterations, tagged
  `Feature: s5b-members-runnable-in-spa, Property N: <text>`). The frontend/SAM-template/
  config layer is example-tested (PBT excluded per `35-sam-module-architecture-sam.md`).
- **Frontend component/service tests (Vitest + RTL + MSW):** `membersApiService` wrapper
  method/path/headers + 401 refresh-retry; `MembersPage` render + filter/sort + view-switch
  columns from mocked field config + scoped response shows only in-subgroup rows (Property
  4/7 at the UI); modals' request bodies; active-only membership-type dropdown; delete
  confirm; single + bulk transition paths. The page's use of the shared Table Filter
  Framework v2 (`FilterableHeader` / `FilterPanel` from `frontend/src/components/filters/`)
  and shared chrome is asserted so the R7.9 reuse obligation cannot silently regress (R10.8).
- **Local smoke test (R10.5):** module up under `sam local start-api` with `h-dcn`
  config/grants projected to the local `governance_projection`; curl a few routes with a
  test-pool token to confirm the bridge + CORS + scope before the walkthrough.
- **Manual walkthrough (R9):** the documented `walkthrough.md` — the runnable+clickable
  definition of done and the S5 Go/No-Go look & feel/UX evidence.
- **Docs build check (R11):** `mkdocs build` (from `docs/`) succeeds for both the nl and en
  locales with the new `docs/docs/members/` section wired into `docs/mkdocs.yml` `nav` —
  the end-user documentation is content (no PBT), verified by a successful build.

## Open items / cross-references

- **Prod live-token entitlement:** if the prod pilot needs it, that is S5 Step 7 Pool A
  PreTokenGen (S5 R6.2/R6.3) — cross-referenced, not duplicated (R9.5). Until then, auth
  runs against the test pool.
- **Flask `/api/members/*` proxy:** deferred prod-consolidation option (single origin, no
  browser CORS to the module) — noted, not built.
- **Second dimension (e.g. `team` for club #2):** pure `config#scope` data, no code — the
  generic point of the projection-channel design; out of scope for this spec.
