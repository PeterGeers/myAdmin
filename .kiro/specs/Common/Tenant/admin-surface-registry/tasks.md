# Implementation Plan: Admin Surface Registry

## Overview

Replace the hardcoded, ad-hoc Tenant-Admin tab list with a backend-owned **admin surface
registry** plus per-module **admin declarations**, and make `TenantAdminDashboard.tsx` a
registry-driven renderer. Deliverable planes: **backend** (`admin_surface_registry.py`,
`MODULE_REGISTRY` admin blocks, `GET /api/tenant/admin-surfaces`, `app.py` validation),
**frontend** (hook, component map, dashboard renderer, extracted `MembersAdminPanel`), and
**documentation** (tenant-admin manual + i18n keys). Design: [`./design.md`](./design.md);
requirements: [`./requirements.md`](./requirements.md).

## Tasks

- [ ] 1. Backend — surface registry and startup validation
  - [x] 1.1 Create `backend/src/services/admin_surface_registry.py`
    - Define `SurfaceKind`, `AdminSurface`, and `ADMIN_SURFACE_REGISTRY` with the twelve surfaces from design §1
    - Implement `admin_surface_ids()` and `surfaces_of_kind()` read-only helpers (no callers reach into the dict shape)
    - Import-safe: no cloud SDK, no database import at module top level
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 1.2 Implement `validate_admin_surface_registry()` in the same module
    - Check duplicate ids, kind literal, int `order`, `tenantAdmin.tabs.*` label key, `module` surfaces name a `MODULE_REGISTRY` key
    - Cross-check every module `admin.panel` / `admin.consumes` / `admin.typed_editor` target kind and unique typed namespaces
    - Raise `ValueError` naming the offending id
    - _Requirements: 1.5, 2.6, 8.1_
  - [x] 1.3 Call `validate_admin_surface_registry()` from `backend/src/app.py` startup
    - Place beside the existing `validate_function_registry()` call; application fails to start on violation
    - _Requirements: 1.5, 8.1_
  - [x] 1.4 Property test — registry integrity fails loud (Property 6)
    - Hypothesis-generated mutated registries and module declarations; assert `ValueError` naming the id; assert the committed registry validates
    - **Property 6 · Validates: Requirements 1.5, 2.6, 8.1**
  - [x] 1.5 Unit test — committed registry coverage
    - Assert the exact twelve ids and their kinds/orders (Requirement 1.4) and that `functions`/`pivot`/`storage`/`media`/`templates` are `capability`
    - _Requirements: 1.4_
  - [x] 1.6 Assert registry purity / plane-agnosticism (Property 12)
    - `import admin_surface_registry` must work with no DB/cloud credentials and no plane-specific import; every `admin` block must survive a `json.dumps`/`json.loads` round trip
    - **Property 12 · Validates: Requirements 1.3, 11.3, 11.4**

- [ ] 2. Backend — module admin declarations
  - [x] 2.1 Add the `admin` block to each `MODULE_REGISTRY` entry
    - FIN → `panel: financial`, `consumes: [storage, templates, pivot]`
    - MEMBERS → `panel: members`, `consumes: [storage, media]`, `typed_editor: {namespace: members, surface: members}`
    - STR → `consumes: [storage, pivot]`; ZZP → `consumes: [storage, templates, pivot]`; TENADMIN → `consumes: [functions]`
    - Keep every existing registry key unchanged
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 2.2 Expose the typed-namespace exclusion set
    - Add `typed_editor_namespaces()` / `typed_editors()` helpers returning `{namespace: (surface, owner)}`
    - Wire the namespace list into the backend route that feeds `ParameterManagement` so those namespaces are excluded from the raw table — the exclusion is by **owner**, not only by polish
    - _Requirements: 7.2, 7.3, 7.4_
  - [x] 2.3 Unit test — declarations, owners and exclusion
    - Assert each module's declared ids resolve to surfaces of the right kind; assert `members` is excluded from Advanced (owner `module`) and `storage`/`str`/`fin`/`zzp` are not; assert the `admin` block is JSON-serializable
    - _Requirements: 2.6, 7.2, 7.3, 7.4, 11.4_
  - [x] 2.4 Cross-plane vocabulary guard test (steering 36 rule 5)
    - `backend/tests/architecture/test_admin_surface_vocabulary.py`: asserts the `ADMIN_SURFACE_REGISTRY` id/label_key vocabulary is exactly the frontend label mirror's, that every surface id is mapped in `adminSurfaceComponents.tsx`, and that every `tenantAdmin.tabs.*` key resolves (non-empty) in BOTH locale files — so a drifted namespace/owner/label fails loudly (the `members_config_validation` vs `fixed_fields` pattern). Verified to fail on a deliberately removed key.
    - _Requirements: 11.4_

- [ ] 3. Backend — derivation and endpoint
  - [x] 3.1 Implement `derive_admin_surfaces(entitled_modules, user_roles, registry=None, module_registry=None)`
    - Single pass over the registry; `always` / `module` / `capability` / `role` rules per design §3
    - Sort by `(order, id)`; ignore unregistered module names; no DB/env/clock access
    - _Requirements: 3.1–3.8_
  - [x] 3.2 Add `GET /api/tenant/admin-surfaces` to `backend/src/tenant_module_routes.py`
    - Reuse `get_current_tenant` and `get_user_tenants_from_jwt`; read `tenant_modules` (`is_active = TRUE`) for Entitlement_Truth
    - Return `{tenant, admin_surfaces: [...]}` with `Cache-Control: no-store`
    - 400 no tenant · 403 unauthorized tenant · 500 logged internal error
    - _Requirements: 4.1–4.7_
  - [x] 3.3 Property tests — derivation soundness/completeness/uniqueness/purity/capability (Properties 1–5)
    - Hypothesis over random entitled-module subsets, role sets, and `consumes` declarations; ≥100 iterations each
    - **Properties 1–5 · Validates: Requirements 3.1–3.6, 3.8, 6.1, 6.2_
  - [x] 3.4 Unit test — equivalence cases (Property 10)
    - FIN-only, MEMBERS-only, both, neither; assert the derived set equals today's set adjusted by exactly the four documented deltas (design §Delta)
    - **Property 10 · Validates: Requirements 9.1–9.4**
  - [x] 3.5 Integration tests — endpoint contract
    - Flask test client: FIN tenant set; missing `X-Tenant` → 400; unauthorized tenant → 403; no token → 401; module-free tenant → 200 baseline only; `no-store` header present
    - Assert the tenant check uses the verified `custom:tenants` claim and NOT the module edge's capability-scoped `tenant_keys` (ADR 0004/0007): a tenant the user is entitled to but which grants no members capability still resolves here
    - Assert `GET /api/tenant/modules` shape unchanged
    - Pin the wire contract to the checked-in `SURFACE_CONTRACT` literal `(id, kind, order, label_key)` for an all-modules tenant, so any backend surface change is a deliberate, reviewed edit
    - _Requirements: 4.1–4.8, 8.2_

- [ ] 4. Frontend — hook, component map, registry-driven dashboard
  - [x] 4.1 Create `frontend/src/hooks/useTenantAdminSurfaces.ts`
    - Mirror `useTenantModules`: tenant-at-start capture, `cache: 'no-store'`, cancelled-flag discard, `error` state
    - Expose `{ surfaces, fallbackSurfaceIds, loading, error }`; `fallbackSurfaceIds` = the `always`-kind ids
    - _Requirements: 5.5, 8.2, 4.7_
  - [x] 4.2 Extract `MembersAdminPanel.tsx` from `TenantAdminDashboard.tsx`
    - Pure move of the current inline Members sub-tab JSX; internals unchanged
    - _Requirements: 5.2_
  - [x] 4.3 Create `frontend/src/components/TenantAdmin/adminSurfaceComponents.tsx`
    - Total id → component map (twelve ids from design §5); export `SurfaceProps`
    - _Requirements: 5.2_
  - [x] 4.4 Rewrite `TenantAdminDashboard.tsx` as a renderer
    - Map one ordered surface array into both `<Tab>` and `<TabPanel>`; remove `hasFIN`/`hasMembers` and the hardcoded tab list
    - Preserve loading, access-denied, no-tenant, select-tenant states and the `key={currentTenant}` remount
    - Unknown id → `<UnknownSurfacePanel id=... />` + `console.error`
    - _Requirements: 5.1, 5.3, 5.4, 5.6_
  - [x] 4.5 Property test — component-map totality (Property 7)
    - fast-check over a checked-in mirror of the registry ids; assert every id has a component
    - Also asserts every surface's `label_key` resolves to a non-empty tab label in BOTH `en` and `nl` (a missing key renders the raw key in the tab bar)
    - **Property 7 · Validates: Requirements 5.2**
  - [x] 4.6 Hook property tests — tenant-switch isolation and safe degradation (Properties 8, 9)
    - fast-check over tenant sequences and failure modes
    - **Properties 8, 9 · Validates: Requirements 5.5, 8.2, 4.7**
  - [x] 4.7 Component tests — dashboard rendering
    - Mocked surfaces → exactly those tabs; FIN / MEMBERS / dual / storage-once cases; fetch failure → baseline + toast; unknown id → error panel; existing guard states
    - _Requirements: 5.1–5.6, 8.2, 8.3_

- [ ] 5. Capability wiring — storage and Advanced
  - [x] 5.1 Confirm every object-storing module dispatches through `resolve_storage_provider`
    - Audit FIN / Members / STR storage call sites; no direct provider branching remains
    - _Requirements: 6.4, 6.5, 6.6_
  - [x] 5.2 Keep the Storage surface the single authoring path for `storage.invoice_provider`
    - No second storage-config store; the existing provider save in the Storage surface remains the only door
    - _Requirements: 6.4_
  - [x] 5.3 Keep the Advanced audience unchanged, and make it ownership-correct
    - Confirm no extra gate is added; the backend continues tenant + active-module scoping and secret masking
    - Advanced renders only Flask-owned namespaces; `members.*` (module-owned) is not rendered at all
    - _Requirements: 7.1, 7.2, 7.6, 7.8, 8.4_
  - [x] 5.4 Unit tests — storage visibility, Advanced exclusion, plane ownership
    - Members-only tenant still gets `storage`; a store-nothing tenant does not
    - `members.*` excluded from Advanced with owner `module`; `storage`/`str`/`fin`/`zzp` remain editable there
    - _Requirements: 6.1, 6.2, 6.3, 7.2, 7.3, 11.1_
  - [x] 5.5 Property test — plane fidelity (Property 11)
    - Generate namespaces with `owner` ∈ {`flask`, `module`}; assert Advanced never emits a `module`-owned namespace and every typed-editor target matches its owner's plane
    - **Property 11 · Validates: Requirements 7.2, 7.5, 7.7, 11.1, 11.2, 11.6, 11.7**
  - [x] 5.6 Integration test — a wrong-door write fails closed
    - `PUT/POST /api/tenant-admin/parameters` with `namespace=members` is rejected with a caller-safe error; a follow-up read shows no Flask row created or updated
    - _Requirements: 7.7, 11.2, 11.6_
  - [x] 5.7 Frontend test — the cross-plane bridge surfaces a mirror failure
    - Assert the module-plane-first then best-effort Flask mirror path returns `{success, version, mirrorError}` and the UI offers retry — never a silent success
    - _Requirements: 11.5_

- [ ] 6. Documentation and i18n
  - [x] 6.1 Add/confirm i18n keys under `tenantAdmin.tabs.*` for all twelve surfaces
    - `frontend/src/locales/en/admin.json` and `.../nl/admin.json`; reuse existing keys, add any missing
    - _Requirements: 1.1, 5.4_
  - [x] 6.2 Update the tenant-admin end-user documentation
    - `docs/docs/tenant-admin/` (and `admin/`) — describe which tabs appear for which module set, per steering 40
    - _Requirements: 10.2_
  - [x] 6.3 Cross-link the model in the steering reference docs
    - Link from `36-config-and-parameters.md` (namespace-editor rule + the `flask`/`module` ownership values) and note the capability-consumption idea
    - _Requirements: 7.1, 10.2, 11.4_
  - [x] 6.4 Retire the backlog candidate
    - `git mv .kiro/specs/myBacklog/tenant-administration-architecture.md` → this spec's `README.md` (2026-11-17); the original framing is preserved there under §Original framing
    - _Requirements: 10.2_
  - [x] 6.5 Governance: amend ADR 0005 with the config-ownership carve-out (steering 40 definition-of-done)
    - Its decision text says the sync is the writer of the projection table and the module plane "never writes the projection" — stale since split ownership (module-authored `config#*` rows; `ProjectionSync` emits zero)
    - Add the carve-out note pointing at ADR 0009 + `Members/02`, and state what still holds (no MySQL client on the module plane, no two-way write to MySQL)
    - Owned jointly with `Members/02`, which caused the change; this spec only *depends* on the resulting boundary
    - _Requirements: 11.2_

- [ ] 7. CI/CD, verification, and completion
  - [x] 7.1 Run local quality gates
    - Backend: `ruff` + `pytest` unit/property suites for the new module; Frontend: `vitest` for hook/component tests; `py_compile` sanity check
    - _Requirements: 10.3_
  - [x] 7.2 Confirm per-PR gates (per steering 43)
    - Verified live (`gh workflow list --all`): **CodeQL Advanced** `active` — runs on push + PR to **both** `main` and `test` (+ weekly schedule + dispatch). **GitGuardian** is a GitHub App status check, not a workflow (configured by `.gitguardian.yaml` v2); a local proxy scan of the changed non-test files found no secret-shaped literals.
    - **Backend CI** (`backend-code-quality.yml`) and **Frontend CI** (`frontend-ci.yml`) are `disabled_manually` — confirmed live — so neither will run. **Full Test Suite** is `active` and is therefore the only automated lint/test gate today: run it on demand with `gh workflow run "Full Test Suite" --ref <branch>`.
    - "Green" itself is observable only on the PR (CodeQL + GitGuardian execute there); this task confirms the gates exist, are active, and are correctly scoped to this change.
    - _Requirements: 10.2_
  - [ ] 7.3 Verify the branch→env deploy path
    - Paths this change touches (`backend/**`, `frontend/**`, `docs/**`, `.kiro/**`) trigger exactly one deploy on push to **`main`**: `deploy-frontend.yml` (paths `frontend/**` or `docs/**`) → GitHub Pages PRODUCTION. Note it is **`main`-only** — there is no TEST-env frontend deploy through CI, so a `test` branch push deploys no frontend.
    - **No SAM deploy fires**: `deploy-sam-*` are path-filtered to `sam/members/**` / `sam/pretokengen/**` / `sam/shared/**`, none of which this change touches.
    - No new stack, workflow, `samconfig.toml`, or IAM/OIDC wiring.
    - _Requirements: 10.2_
  - [x] 7.4 No new workflow / `samconfig.toml` / IAM-OIDC wiring required
    - Confirm explicitly; this change adds no stack, usage plan, or deploy path
    - _Requirements: 10.2_
  - [ ] 7.5 Manual/visual verification
    - Tenant_Admin walk-through for FIN-only / Members-only / dual tenants; tab sets match design §Surface reference; order stable across a tenant switch
    - _Requirements: 9.1, 9.2, 9.3_
  - [ ] 7.6 Promote `test` → `main` as the production-release gate
    - _Requirements: 10.2_
  - [ ] 7.7 Final checkpoint
    - Ensure all tests pass; ask the user if questions arise
    - _Requirements: 10.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP (none are marked optional in this plan — every task is on the critical path).
- Each task references specific requirements for traceability.
- Backend: Flask/Python + MySQL, pytest + Hypothesis. Frontend: React/TypeScript + Chakra UI, Vitest + fast-check + React Testing Library.
- Follow existing patterns: `MODULE_REGISTRY`, `FUNCTION_REGISTRY`, `validate_function_registry()` at boot, the `useTenantModules` tenant-at-start idiom, and the `storage_resolver` config→handler dispatch (steering 36).
- Database access stays behind the existing `DatabaseManager` abstraction with parameterized queries.
- **All planes, one spec:** backend registry + endpoint, frontend renderer, i18n, and docs land together — "backend done" is not "feature done" (steering 40, All-planes delivery).
- **Three planes, three task groups:** the frontend plane (`frontend/src/**` — hook, component map, renderer), the Flask plane (`backend/src/**` — registry, derivation, endpoint, validation), and the module plane (`sam/**` — the Change-Op write path and projection reader this spec *depends on* rather than builds). Config ownership (`flask` vs `module`) is a property of each namespace, not a fourth plane — see `README.md` §The three planes.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.2"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "1.5", "1.6", "2.2", "3.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "3.2", "4.1", "4.3"] },
    { "id": 4, "tasks": ["3.3", "3.4", "4.4", "5.1", "5.3"] },
    { "id": 5, "tasks": ["3.5", "4.5", "4.6", "5.2", "6.1"] },
    { "id": 6, "tasks": ["4.7", "5.4", "5.5", "5.6", "5.7", "6.2", "6.3", "6.4", "6.5"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3", "7.4"] },
    { "id": 8, "tasks": ["7.5", "7.6", "7.7"] }
  ]
}
```

- [x] 8. Option B — retire the Members/02 frontend mirror (approved follow-on)
  - Repointed all THREE Flask-side scope readers at the projected `config#scope` row through
    the existing read-only `ProjectionReader`, via a new shared seam
    (`services/scope_vocabulary.py`: `load_scope_dimensions` + `dimension_index`): grant
    validation, the picker API, and the `scopegrant#` projection builder now resolve the
    vocabulary through ONE code path instead of three copies of the same parse.
  - Deleted the mirror end-to-end: the frontend's second write leg
    (`membersConfigService.saveMembersParameter` → Flask params) plus its `mirrorError` retry
    plumbing and the editor's existing-row lookup; `members.scope_dimensions` from
    `parameter_schema.py` and `members_parameters.json`; `_SCOPE_DIMENSIONS_PARAM_KEY` (its
    definition and re-export); and `flask_mirror_keys` (accessor, boot validation, the
    `typed_editors()` exposure, and the `parameter_admin_routes` fail-open allowance). A
    module-owned namespace now fails closed for EVERY key — one config, one writing door.
  - Measured: backend 498 pass (scoped set incl. `tests/api` + `tests/architecture`),
    frontend 38 pass (service + editor), `ruff format --check src/` clean (346 files).
  - Known trade-off (documented in `scope_vocabulary.py`): the Flask plane now reads the
    projection at REQUEST time for the picker + grant validation, so it needs
    `GOVERNANCE_PROJECTION_TABLE`; staleness is bounded by sync delay + read TTL.
  - Docs updated (this was the §8 follow-up): this spec's `design.md` gains a dedicated
    "Option B — the Members/02 validator mirror is retired" section, plus corrections to the
    `members.*` ownership bullet, the "frontend is the only bridge" principle, decision D9, and
    the error table (the old `mirrorError` row replaced by a `config#scope` read-failure row).
    `Members/02 …/design.md` carries an amendment banner (its surviving mirror / KEPT /
    auto-mirror wording is historical) and its `tasks.md` 3.1a is marked RETIRED; the myBacklog
    `scope-dimension-authoring-trigger.md` is marked partly superseded. **ADR 0005 needed no
    change — verified: it never described the mirror.**
  - _Requirements: Members/02 R11.1/R11.2 (split ownership), R22 (mirror retirement)_
