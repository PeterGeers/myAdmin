# Requirements Document: Admin Surface Registry

## Introduction

The Tenant-Admin dashboard (`frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`)
renders a **flat, hardcoded tab list with ad-hoc gating**: most tabs always render, FIN shows
behind `if hasFIN`, the Members panel behind `if hasMembers`, and there is no model of *which
admin surface belongs to or is needed by which module*. The differences an operator sees
(FIN tenants get Financial; Members tenants get a 4-sub-tab editor) are therefore **accidental,
not designed**, and every new module requires editing the dashboard.

This feature introduces a **single, backend-owned registry of admin surfaces** plus a per-module
**admin declaration**. Each surface declares *when it applies*; each module declares *what it
owns* (its own panel) and *what it consumes* (cross-cutting capabilities). The dashboard
**derives** its tabs from that registry — no `if`-ladder — so adding a module's admin surface is
one registry entry, and the surfaces an operator sees are a deliberate, testable consequence of
the tenant's entitlements and the caller's roles.

## Glossary

- **Admin_Surface**: One addressable area of the Tenant-Admin dashboard (a tab), identified by a stable string id (e.g. `users`, `storage`, `financial`, `members`, `advanced`).
- **Surface_Registry** (`ADMIN_SURFACE_REGISTRY`): The single in-code registry (`backend/src/services/admin_surface_registry.py`) defining every Admin_Surface, its `kind`, its applicability rule, its display order, and its i18n label key.
- **Kind**: One of `always` (platform baseline), `module` (owned by one module), `capability` (cross-cutting, consumed by modules), or `role` (role-gated generic surface).
- **Module_Admin_Declaration**: The optional `admin` block on a `MODULE_REGISTRY` entry declaring the module's own panel (`panel`), the capabilities it consumes (`consumes`), and any namespace for which it ships a typed editor (`typed_editor`).
- **Capability**: A cross-cutting surface (Storage, Templates, Media Assets, Functions) that is not owned by one module but *serves* modules; it renders when at least one entitled module declares it consumes it.
- **Module_Panel**: A module-owned admin surface (Financial for FIN, Members for MEMBERS). Its internal richness (a single view or a sub-tabbed panel) is the module's own concern.
- **Namespace_Editor**: An admin editor for one **config namespace**. A namespace is owned by exactly one **config owner** (see Config_Ownership): either Flask-authored (rows in the MySQL `parameters` table) or module-plane-owned (rows on the DynamoDB governance projection). The generic **Advanced** surface edits Flask-authored namespaces only.
- **Flask_Authored_Namespace**: A config namespace whose single writer is the Flask plane, stored as rows in the MySQL `parameters` table and resolved user - role - tenant - system by `ParameterService` (e.g. `storage.*`, `fin.*`, `str.*`, `zzp.*`).
- **Module_Plane_Owned_Namespace**: A config namespace whose single writer is the module plane (the serverless Lambda plane under `sam/`), stored as `config#*` rows on the DynamoDB governance projection, written by the owning module's Change-Op write path (ADR 0009) and read by that module's projection reader, which serves clients the **resolved (Flat_View)** model — the raw overlay shape never crosses the API boundary. There is **no Flask writer and no `ProjectionSync`** for it. `members.*` (`config#fields` / `config#scope` / `config#mail`) is the canonical case.
- **Typed_Editor**: A module-registered editor for one namespace, declared as `admin.typed_editor: {namespace, surface, owner}` where `owner` is `flask` or `module`. It is the namespace's single authoring door and supersedes the generic form for it.
- **Frontend_Plane**: The React app (`frontend/src/**`) — a **delivery plane** in its own right (steering 40, "All-planes delivery"). It owns **no** tenant config namespace: it renders the derived surfaces, holds its own UI state (the `X-Tenant` selector, language, per-user view preferences), and performs each write against whichever backend plane owns the namespace.
- **Flask_Plane**: The Flask / MySQL plane (`backend/src/**`) — the admin + finance backend, the author of `flask`-owned config, and the host of the surface-derivation endpoint.
- **Module_Plane**: The serverless module plane (`sam/**`; "Plane B" in steering 12) — Lambda + DynamoDB, the author of its own `config#*` rows and the reader of the projection.
- **Config_Ownership**: The relation between a tenant-scoped config namespace and the **single plane that writes it**: `flask` (MySQL `parameters`) or `module` (the governance projection's `config#*` rows). **Two owners, three planes** — ownership is a property of a namespace, not a taxonomy of planes.
- **Config_Ownership_Boundary**: The rule that a surface's editor must target the namespace's owning plane — the Advanced (Flask `parameters`) editor offers **no write path** for a `module`-owned namespace; the two backend planes never reach around the boundary by calling each other at runtime; and the frontend performs each plane's write separately.
- **Namespace_Scope**: Ownership governs **tenant-scoped** namespaces that an admin surface edits. User-scoped config (e.g. per-user column preferences, served by the module plane) and pure frontend UI state are not namespaces and are outside this spec.
- **Surface_Derivation**: The pure function that maps (entitled modules, consuming declarations, caller roles) → an ordered list of applicable Admin_Surfaces.
- **Entitlement_Truth**: The set of modules the *tenant* has active (`tenant_modules.is_active = TRUE`), independent of which modules the *caller* has role permissions for.
- **Tenant_Admin**: A user holding the `Tenant_Admin` role for the current tenant; the audience of this dashboard.
- **SysAdmin**: A platform administrator; the intended gate for raw/dangerous surfaces.
- **Surface_Component_Map**: The frontend map from Admin_Surface id → React component, which MUST be total over every id the Surface_Registry can emit.

## Requirements

### Requirement 1: Single backend source of admin surfaces

**User Story:** As a platform developer, I want every admin surface defined in one registry, so that I can reason about the dashboard's shape without reading a JSX `if`-ladder.

#### Acceptance Criteria

1. THE Surface_Registry SHALL define, for every Admin_Surface, a unique id, a `kind` in {`always`, `module`, `capability`, `role`}, an integer `order`, and an i18n label key under `tenantAdmin.tabs.*`.
2. THE Surface_Registry SHALL be the single source of truth: no admin-surface applicability decision may exist only in frontend code.
3. THE Surface_Registry SHALL be a pure, importable Python module with no cloud-SDK or database import at module top level.
4. THE Surface_Registry SHALL cover EVERY surface the dashboard renders today: `users`, `functions`, `financial`, `members`, `storage`, `media`, `templates`, `tenant-info`, `sender`, `pivot`, `landing`, `advanced`.
5. WHEN the application starts, THE system SHALL raise a `ValueError` naming the offending id IF any surface has a duplicate id, an unknown `kind`, a missing `order`, or a missing i18n label key.

### Requirement 2: Per-module admin declaration

**User Story:** As a module developer, I want to declare my module's admin surface and the capabilities it uses on my `MODULE_REGISTRY` entry, so that adding admin UI needs no dashboard edit.

#### Acceptance Criteria

1. THE Module_Admin_Declaration SHALL live in the module's `MODULE_REGISTRY` entry under an `admin` key, and SHALL be optional (a module with no admin UI declares nothing).
2. `admin.panel` SHALL, when present, name an Admin_Surface whose `kind` is `module` (FIN → `financial`, MEMBERS → `members`).
3. `admin.consumes` SHALL, when present, be a list of Admin_Surface ids whose `kind` is `capability`.
4. `admin.typed_editor` SHALL, when present, declare the parameter `namespace` for which the module ships a typed editor and the surface id that hosts it.
5. THE declared capability list SHALL reflect the module's real needs and SHALL NOT include a capability the module does not use — a module that stores no objects SHALL NOT declare `consumes: [storage]`.
6. AT application startup, THE system SHALL raise a `ValueError` naming the module and the offending id IF any `admin.panel` target is not a `module` surface, IF any `admin.consumes` entry is not a `capability` surface, or IF any `admin.typed_editor.namespace` collides with another module's typed namespace.
7. WHEN a module is added to `MODULE_REGISTRY` with an `admin` declaration, THE system SHALL require no change to `TenantAdminDashboard.tsx` for that module's surface to appear.

### Requirement 3: Surface derivation

**User Story:** As a system architect, I want the dashboard's tabs to be derived from entitlements plus the registry, so that what an operator sees is designed and testable.

#### Acceptance Criteria

1. WHEN deriving surfaces, THE Surface_Derivation SHALL include every `always` surface unconditionally.
2. WHEN deriving surfaces, THE Surface_Derivation SHALL include a `module` surface IF AND ONLY IF its declared module is in Entitlement_Truth.
3. WHEN deriving surfaces, THE Surface_Derivation SHALL include a `capability` surface IF AND ONLY IF at least one module in Entitlement_Truth declares `admin.consumes` containing that capability id.
4. WHEN deriving surfaces, THE Surface_Derivation SHALL include a `role` surface IF AND ONLY IF the caller holds at least one role listed on that surface.
5. THE Surface_Derivation SHALL return surfaces ordered by `order` ascending, then by id ascending, and SHALL return each surface at most once.
6. THE Surface_Derivation SHALL be a pure function of its inputs (no database access, no environment reads, no clock) so it is deterministic and directly testable.
7. THE Surface_Derivation SHALL use Entitlement_Truth (tenant-active modules) as the basis for `module` and `capability` inclusion, and SHALL NOT use the caller's module-level role permissions as a substitute for entitlement.
8. WHEN an entitled module declares `consumes: [storage]`, THE `storage` capability surface SHALL be derived even for a tenant with no FIN module — the surface follows the *consumption*, not a fixed list.

### Requirement 4: Admin-surface API contract

**User Story:** As a frontend developer, I want one tenant-scoped endpoint that returns the applicable surfaces, so that the dashboard does not re-derive the rule client-side.

#### Acceptance Criteria

1. THE backend SHALL expose `GET /api/tenant/admin-surfaces` returning the derived, ordered surfaces for the caller's current tenant.
2. THE response SHALL contain, per surface, `id`, `kind`, `order`, and `label_key`, plus a top-level `tenant` echo of the resolved tenant.
3. THE endpoint SHALL resolve the tenant from the `X-Tenant` selector and SHALL verify it against the caller's verified tenant list — the `custom:tenants` claim of the verified token (ADR 0004/0005) — returning HTTP 403 when the tenant is not authorized. It SHALL NOT validate against the module edge's capability-scoped `tenant_keys` set (ADR 0007): the two sets are deliberately different, and the header never grants a tenant in either plane.
4. THE endpoint SHALL derive Entitlement_Truth from `tenant_modules` (`is_active = TRUE`) for that tenant, and the caller's roles from the request context.
5. THE endpoint SHALL require an authenticated caller and SHALL return HTTP 401 when no valid token is presented.
6. IF the tenant has no active modules, THEN THE endpoint SHALL still return the `always` surfaces (HTTP 200) rather than an error.
7. THE endpoint SHALL NOT be cacheable across tenant switches: it SHALL send `Cache-Control: no-store` (a tenant switch must never replay a previous tenant's surface list).
8. THE existing `GET /api/tenant/modules` response SHALL remain unchanged (backwards compatible) so existing consumers (`useTenantModules`, `LandingPageEditor`) are unaffected.

### Requirement 5: Registry-driven dashboard

**User Story:** As a platform developer, I want the dashboard to render whatever the backend derives, so that no tab logic lives in the component.

#### Acceptance Criteria

1. THE `TenantAdminDashboard` SHALL render its tabs by mapping over the derived surfaces, and SHALL contain NO per-module conditional (`hasFIN`, `hasMembers`) and NO hardcoded tab list.
2. THE Surface_Component_Map SHALL be total over the Surface_Registry: every id the backend can emit SHALL have a component; a property test SHALL enforce this totality.
3. IF a derived surface id is absent from the Surface_Component_Map, THEN THE dashboard SHALL render a visible error panel naming the unknown id and SHALL log the error — it SHALL NOT silently drop the surface.
4. THE dashboard SHALL retain its existing Tenant_Admin guard and its loading, no-tenant, access-denied, and select-tenant states unchanged.
5. WHEN the current tenant changes, THE dashboard SHALL re-fetch the surface list and SHALL discard a superseded response (no cross-tenant bleed), reusing the `useTenantModules` tenant-at-start idiom.
6. A shared renderer SHALL produce both the tab list and the panels from one ordered array, so tab order and panel order cannot drift apart.

### Requirement 6: Storage as a shared capability

**User Story:** As an operator, I want the Storage surface when — and only when — my tenant's modules actually store objects, so the UI matches reality.

#### Acceptance Criteria

1. THE `storage` surface SHALL be a `capability` surface, not an `always` surface.
2. THE `storage` surface SHALL appear IF AND ONLY IF an entitled module declares `consumes: [storage]`.
3. WHEN more than one entitled module consumes storage, THE `storage` surface SHALL appear exactly once (not once per consumer).
4. THE `storage` surface SHALL read/write the single tenant-scoped parameter `storage.invoice_provider` (`services/parameter_schema.py`) and SHALL NOT introduce a second storage-config store.
5. ALL object-storing modules SHALL dispatch through the single resolver `services/storage_resolver.py::resolve_storage_provider` — config chooses, code runs (steering 36); no per-tenant code branch.
6. IF `storage.invoice_provider` is unset or unreadable, THEN THE resolver SHALL fall back to its documented safe default and SHALL NOT raise into the dashboard.

### Requirement 7: Advanced and typed namespace editors (one rule)

**User Story:** As an architect, I want the raw "Advanced" table and a module's typed config editor to be one mechanism at two polish levels, so the two never duplicate the same namespace.

#### Acceptance Criteria

1. THE `advanced` surface SHALL be modelled as the **generic Flask `parameters` editor** and SHALL retain Surface_Registry membership (a registered catch-all), consistent with `Parameter redesign/analysis.md` §2.4.
2. THE `advanced` surface SHALL cover **only Flask_Authored_Namespaces**: it SHALL NOT render a `module`-owned namespace, because the MySQL `parameters` table is not that namespace's store, and offering a second write door recreates the two-writers-one-config hazard (see Requirement 11).
3. WHEN a module declares `admin.typed_editor` for a namespace, THE `advanced` surface SHALL exclude that namespace, so a namespace has exactly one editing door.
4. THE typed-editor exclusion SHALL be derived from the Module_Admin_Declaration (namespace + `owner`), not hardcoded in `ParameterManagement` or in the parameters route, so adding a typed editor is a registry change.
5. A `typed_editor` declaration SHALL state the plane that authors the namespace (`owner`: `flask` or `module`) and, for a module-plane editor, the **name** of the env var holding the module API base (never a URL).
6. THE `advanced` surface SHALL keep the current audience (any Tenant_Admin of the tenant) at this time; the backend SHALL continue to scope rows to the tenant plus its active modules and to mask secrets. (Gating it to SysAdmin is a deliberate non-decision recorded in `design.md` §Decisions.)
7. A write through the wrong door SHALL fail closed: an attempt to save a module-plane-owned namespace through the Flask parameter path SHALL be rejected with a caller-safe error and SHALL NOT create or update a Flask row for that namespace.
8. THE retired `members.*` Flask rows (the validator mirror left behind by the module-plane cutover) SHALL NOT be presented as an editing surface anywhere in the admin UI.

### Requirement 8: Failure behaviour and safe defaults

**User Story:** As an operator, I want a registry problem to be loud for developers but never to give me a broken admin page.

#### Acceptance Criteria

1. IF the Surface_Registry or a Module_Admin_Declaration is invalid, THEN THE application SHALL fail at startup with a `ValueError` naming the offending id (fail loud, at boot — never a silent partial dashboard).
2. IF the surface-derivation endpoint fails or the frontend fetch fails, THEN THE dashboard SHALL render the `always` (baseline) surfaces only and SHALL surface a toast — it SHALL NOT render module/capability surfaces it cannot vouch for.
3. IF the frontend receives a surface id it does not recognise, THEN behaviour SHALL match Requirement 5.3 (visible error, logged) rather than a silent drop.
4. THE surface list SHALL NEVER be derived on the frontend from module names — the frontend is a renderer of the backend contract.

### Requirement 9: Equivalence (non-regression)

**User Story:** As a maintainer, I want proof that the derived dashboard matches today's behaviour, so the refactor changes architecture without changing what operators see (except the intended fixes).

#### Acceptance Criteria

1. FOR a tenant entitled to FIN only, THE derived surface set SHALL equal today's set: baseline ∪ {`financial`} ∪ capabilities FIN declares.
2. FOR a tenant entitled to MEMBERS only, THE derived surface set SHALL equal baseline ∪ {`members`} ∪ capabilities MEMBERS declares.
3. FOR a tenant entitled to both FIN and MEMBERS, THE derived set SHALL contain both module panels and the union of consumed capabilities, each exactly once.
4. THE spec SHALL document every intentional delta from today's behaviour (e.g. a module that stores nothing no longer getting `storage`) in `design.md`, and each delta SHALL be asserted by a test.

### Requirement 10: Extensibility and governance

**User Story:** As a platform owner, I want adding admin UI for a new module to be one registry entry plus tests, so the model survives growth.

#### Acceptance Criteria

1. WHEN a new module is added, THE model SHALL require one `MODULE_REGISTRY` entry with an `admin` block plus the module's own components — and NO change to the surface-derivation algorithm.
2. THE spec's `tasks.md` SHALL make the CI/CD surface explicit per steering 43 (quality gates, branch→env deploy path, promote step) and SHALL include a task per affected plane (backend, frontend, docs) per steering 40.
3. THE feature SHALL be covered by tests on every affected plane: backend derivation/registry properties, endpoint integration, and frontend hook plus component tests.

### Requirement 11: Config ownership boundary (three planes; one writer per namespace)

**User Story:** As a platform architect, I want the admin registry to respect config ownership inside the three-plane model (frontend, Flask, module), so that no admin surface ever writes a namespace into a store its owning plane does not own.

#### Acceptance Criteria

1. THE system SHALL treat every **tenant-scoped** config namespace as owned by exactly one **config owner** — `flask` (MySQL `parameters`, authored through `ParameterService` and optionally projected) or `module` (DynamoDB governance-projection `config#*` rows, authored by the owning module's Change-Op write path per ADR 0009 and read through that module's projection reader / resolved view per ADR 0009 + steering 39). Config ownership is a property of a namespace, NOT a taxonomy of planes.
2. THE MySQL `parameters` table SHALL NOT be read or written by the module plane, and a namespace already cut over to module ownership SHALL NOT be authored by the Flask plane (retired parameter rows and `ProjectionSync` config builders).
3. THE Surface_Registry and Surface_Derivation SHALL remain pure metadata with no store access and no plane-specific import, so the registry stays importable from both planes.
4. THE `admin` block added to `MODULE_REGISTRY` SHALL be pure data (strings, lists, dicts only; JSON-serializable), because `MODULE_REGISTRY` is imported by carriers on both planes; agreement of this shared vocabulary across planes SHALL be guarded by a test (steering 36 rule 5).
5. THE Flask and module planes SHALL NOT call each other at runtime; where a single logical edit spans both, the frontend SHALL perform each plane's write separately — module-plane write first (authoritative), then the Flask leg as a best-effort mirror — and SHALL surface a mirror failure rather than hiding it.
6. WHEN a namespace is cut over from Flask to module ownership, THE admin surface SHALL follow the namespace to its typed editor, and the generic Advanced surface SHALL stop offering it; a namespace SHALL never be editable through both doors.
7. THE Surface_Registry SHALL record namespace ownership (`owner`), making the boundary machine-checkable: a surface whose editor's plane does not match its namespace's owner SHALL raise a `ValueError` at startup.
8. THE system SHALL name the three delivery planes explicitly — **frontend** (`frontend/src/**`), **Flask** (`backend/src/**`), **module** (`sam/**`) — and THE **frontend plane SHALL own no config namespace**: it renders the derived surfaces and performs each plane's write separately, so it is the only bridge and never an authority.
9. A module-plane-editor surface SHALL target the owning module's API (`MODULE_REGISTRY.backing.api_base_env` name, resolved by `resolve_module_api_base`) rather than the Flask base — the frontend reaches the module plane directly, per ADR 0003's `backing` contract.

## Success Metrics

- `TenantAdminDashboard.tsx` contains zero per-module conditionals and zero hardcoded tab entries.
- Adding a module's admin surface requires editing exactly one registry entry (no dashboard diff).
- 100% of `Surface_Registry` ids are asserted to have a frontend component by an automated test.
- The derivation is deterministic and pure: property tests pass for at least 100 generated `(modules, roles)` combinations.
- No admin surface offers a write path into a store other than its namespace's declared owner (asserted by test).

## Out of Scope

- Consolidating the internal implementation of every admin panel (Members' 4 sub-tabs stay; richness is the module's own concern).
- Re-gating `advanced` to SysAdmin (explicitly deferred — see Requirement 7.3).
- Any entitlement behaviour change: `consumes` is a *display/scoping* declaration only; it never auto-activates a module.
- Rewriting `useTenantModules` or `GET /api/tenant/modules` (both kept, backwards compatible).
- The Members dual-surface cleanup itself (owned by `Members/01 - members-config-projection-and-cleanup`; this spec only consumes the typed-namespace rule).
- Re-cutting any namespace between config owners: the `members.*` cutover is owned by `Members/02 - members-config-sam-owned-write-path`. This spec only *respects* the resulting boundary.
- Per-surface permission tuning beyond the `role` kind (no new RBAC model).

## Dependencies

| Dependency | Role in this spec |
| --- | --- |
| `backend/src/services/module_registry.py` (`MODULE_REGISTRY`) | Gains the `admin` declaration block |
| `backend/src/services/function_registry.py` (`FUNCTION_REGISTRY`) | Applicability signal for the `functions` surface |
| `backend/src/services/storage_resolver.py` + `services/parameter_schema.py` | The storage capability (single provider choice, one resolver) |
| `backend/src/tenant_module_routes.py` (`GET /api/tenant/modules`) | Entitlement plumbing reused; response kept stable |
| `frontend/src/hooks/useTenantModules.ts` | Tenant-at-start / no-store idiom reused by the new hook |
| Steering `36-config-and-parameters.md` | "Config chooses, code runs" resolver rule |
| Steering `32-frontend-ui.md` | Table/modal/i18n conventions for the dashboard |
| Steering `40-spec-workflow.md`, `43-cicd-deploys.md` | Spec trio shape; CI/CD tasks and all-planes delivery |
| `Members/02 - members-config-sam-owned-write-path` | The settled module-plane ownership of `config#fields` / `config#scope` / `config#mail`; the source of the "Advanced offers no write path for any `members.*` key" rule |
| `backend/src/services/projection_sync.py` | Today emits **zero** `config#*` rows (split ownership) — the fact this spec's Advanced rule depends on |
| `backend/src/services/members_config_validation.py` + `sam/members/domain/fixed_fields.py` | The existing cross-plane vocabulary guard this spec's `typed_editor` guard mirrors |
| `docs/decisions/0003` (platform base + `backing` contract) | The registry shape the `admin` block extends |
| `docs/decisions/0004` (verified-JWT-only) + `0007` (active-tenant resolution) | How the surface endpoint resolves and validates its tenant |
| `docs/decisions/0005` (MySQL system-of-record + one-directional projection) | Entitlement truth; **text needs the config-ownership carve-out note** — see `design.md` §Alignment |
| `docs/decisions/0006` (entitlement in token via PreTokenGen) | Why `MODULE_REGISTRY` must stay importable/serializable off-Flask |
| `docs/decisions/0009` (`config#fields` Change-Op CRUD) | The module-plane write path and the Flat_View read contract for a `module`-owned namespace |
