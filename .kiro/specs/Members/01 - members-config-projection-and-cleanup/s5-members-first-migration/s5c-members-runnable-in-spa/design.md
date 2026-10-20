# Design Document

## S5c — Members-runnable-in-SPA (representative pilot, proven dev/test → prod) — Design

- Requirements: `./requirements.md`
- Primary input (settled): `./analysis.md` (F.1–F.8 are RESOLVED decisions).
- Parent (REUSE — domain unchanged): `.kiro/specs/multi-tenant/s5-members-first-migration/`.
- Predecessor (REUSE plumbing/frontend; SUPERSEDED): `.kiro/specs/multi-tenant/s5b-members-runnable-in-spa/`
  — its `design.md` documents the built projection contracts (C1–C14, the `config#*` /
  `scopegrant#` rows, Properties 1–4); s5c builds on them and does not restate their internals.
- Decisions of record: ADR 0003 (platform base), 0004 (verified JWT), 0005 (MySQL SoR +
  one-directional projection), 0006 (entitlement-in-token via PreTokenGen reading the projection).
- Steering: `20-platform-architecture`, `21-identity`, `22-authentication`, `23-aws-accounts`,
  `31-backend-database-flask-mysql`, `32-frontend-ui`, `33/34` (testing),
  `35-sam-module-architecture-sam`, `40-spec-workflow`, `42-local-dynamodb`.
- Deferred (must NOT block s5c): the generic definition-driven config-editor framework +
  draft/publish (`.kiro/specs/myBacklog/json-editor.md`).
- Grounding code (cited throughout): `backend/src/services/parameter_schema.py`,
  `parameter_service.py`, `projection_sync.py`, `projection_sync_trigger.py`, `module_registry.py`,
  `backend/src/routes/parameter_admin_routes.py`, `config_routes.py`,
  `backend/src/config/ledger_parameters.json`; `frontend/src/components/TenantAdmin/AccountModal.tsx`,
  `frontend/src/hooks/useTableConfig.ts`, `frontend/src/hooks/useMemberFieldConfig.ts`,
  `frontend/src/pages/MembersPage.tsx`, `frontend/src/types/members.ts`;
  `sam/members/domain/field_resolver.py`, `scope_dimensions.py`, `scope_access.py`,
  `handler/app.py`; `sam/pretokengen/*`.

## Overview

s5c does five things on top of the s5 domain + s5b plumbing:

1. **Switches on the generic PreTokenGen entitlement channel** (test pool first, then gated prod)
   so **capability travels the real S4 channel** (`custom:entitlements`) with **zero
   `cognito:groups` fallback** — eliminating the s5b bypass.
2. **Repoints the module's Cognito config** from prod Pool A to the non-prod dev/test pool
   `myAdmin-test` for local + CI (config-not-code).
3. **Declares the `members.*` parameter schema and ships a structured typed authoring UI** (reusing
   the ledger-account definition-driven editor), making scope dimensions, the field overlay, and
   view contexts **authorable in the SPA** — the direct fix for the "authoring UI unreachable"
   blocker (analysis B.3).
4. **Broadens the member surface to representative**: parameter-driven columns organized into
   multiple selectable view contexts, calculated fields, scope badge + filtering, view/edit/add/
   delete modals, export, deliberately-limited transitions — driven by a Fixed/Parameter/Calculated
   field model.
5. **Removes the s5b shortcuts** and **executes a gated PROD cutover** proving the full CI/CD path
   (build → deploy → provision → project → verify) with non-destructive governance rollback.

The unifying principle: **authoring lives on the Flask/MySQL governance plane; the SAM Members
module only READS the result via the one-directional projection.** Nothing about authoring touches
`sam/members/*`.

### The two planes and where each change lands

| Change | Plane | Where |
| --- | --- | --- |
| PreTokenGen trigger wiring | Identity (Cognito) + Data (Lambda) accounts | `sam/pretokengen/*` (reuse) + IaC/CLI trigger attach |
| Module Cognito repoint | SAM module config | `sam/members/env-vars.local.json` + CI env (config only) |
| `members.*` schema + authoring UI | **Flask/MySQL (myAdmin)** | `parameter_schema.py`, `config_routes.py`, `backend/src/config/members_parameters.json`, `frontend/src/components/TenantAdmin/*` |
| Projection of `members.*` | Flask/MySQL | `projection_sync.py` (already reads `members.*`; `view_contexts` added) |
| Field model + representative surface | SAM module domain + frontend | `sam/members/domain/fixed_fields.py` (broaden), `frontend/src/pages/MembersPage.tsx` + modals |
| Remove fallbacks | SAM module edge | `sam/members/handler/app.py`, `env-vars.local.json` |
| Prod cutover + rollback | Ops (both accounts) | provisioning playbook (tasks) |

### REUSE / ADD / REFACTOR / REMOVE (from analysis Section D)

| Component | Verdict | s5c action |
| --- | --- | --- |
| `sam/members/domain/*` (service, scope, lifecycle, hooks, catalog) | KEEP | unchanged |
| `sam/members/domain/fixed_fields.py` | REFACTOR | broaden the fixed base (R4.3) |
| `sam/members/repository/*` | KEEP | unchanged |
| `handler/routes.py` + `router.py` | KEEP | unchanged |
| `handler/app.py` verified-auth edge (core) | KEEP | wire off `custom:entitlements` only |
| `_local_dev_group_grants_capability` + `MEMBERS_LOCAL_AUTH_FALLBACK` | REMOVE | delete (R6.1) |
| `MEMBERS_LOCAL_TENANT_ID` fallback | REMOVE | delete (R6.2) |
| `Members_*` names (`Members_CRUD`/`Members_Read`/`Members_Export`) | ROLES, not a capability group | keep as roles; no Members capability derived from `cognito:groups` (R6.4) |
| `projection_schema.py` / `projection_sync*.py` / reader | KEEP | add `view_contexts` to `config#fields`-family |
| `sam/pretokengen/*` (Lambda + reader) | KEEP + WIRE | attach trigger test-pool-first then prod (R1) |
| `parameter_schema.py` — `members` namespace | ADD | declare `members.*` (R3) |
| Tenant-Admin members authoring UI | ADD/REFACTOR | typed editor reusing ledger pattern (R3) |
| Members frontend page + modals | KEEP + REFACTOR | broaden to representative (R5) |
| `onboard-hdcn-local.py` | REFACTOR | demote to data-track fixture (R6.5) |
| dev/test Cognito pool for the module | ADD | repoint to `myAdmin-test` + add trigger (R1/R2) |
| `module_registry.py` `MEMBERS` entry | KEEP | unchanged |

## Architecture

### The three channels (the guarantee s5c proves end-to-end)

| Channel | Question | System of record | Carrier to the module | s5c status change |
| --- | --- | --- | --- | --- |
| **Capability** | May this user act on Members? | Cognito/entitlement (S4) | verified token `custom:entitlements` | **NEW: wire PreTokenGen** so this is real, not faked (R1) |
| **Scope grant** | On which subgroup? | MySQL `user_tenant_roles` | projected `scopegrant#<email>#<dimension>` | drive via SPA, not CLI (R8.1) |
| **Tenant config** | Which dimensions/values/fields/views? | MySQL `members.*` params | projected `config#scope` + `config#fields` | **NEW: authoring UI** (R3) + `view_contexts` |

### Capability channel — PreTokenGen wiring (R1)

```
                 IDENTITY ACCOUNT (344561557829)          DATA ACCOUNT (506221081911)
                 ┌──────────────────────────────┐         ┌──────────────────────────────┐
  login  ───────▶│  Cognito pool                │         │  PreTokenGen Lambda           │
                 │   dev/test: myAdmin-test      │  invoke │   (sam/pretokengen, S4)       │
                 │     eu-west-1_xyrlzfqbl  ─────┼────────▶│   reads governance_projection │
                 │   prod:    Pool A (myAdmin)   │  (cross │   SAME-ACCOUNT (no cross-acct │
                 │     eu-west-1_Hdp40eWmu       │  account│    data read)                 │
                 │  attaches trigger + grants    │  invoke)│  resolves roles ∩ modules     │
                 │  aws_lambda_permission        │         │   → custom:entitlements       │
                 └──────────────────────────────┘         └──────────────────────────────┘
                          │                                          ▲
   token with            │                                          │ boto3 Query on
   custom:entitlements ◀─┘                                          │ tenant partition
                                                          governance_projection (DynamoDB)
```

- **Invoke crosses accounts; the data read does not** (ADR 0006 D2 / F.2). s5c adds the
  cross-account `aws_lambda_permission` from `myAdmin-test` → the data-account Lambda **first**,
  proves `custom:entitlements` on the test-pool token, then repeats for **Pool A** as the gated
  promotion.
- **Fail-safe:** resolution failure → claim omitted → login still succeeds → Flask plane
  authoritative. **Detach-to-rollback:** removing the trigger instantly restores prior login.
- **Dependency:** the pool's tenants must project token-relevant governance. Confirmed NOT a blocker
  (F.3): a Members-enabled tenant (h-dcn) already projects `module#MEMBERS` (active) +
  `role#…#Members_CRUD`, so the resolver produces a non-empty claim once the trigger is wired.

### Tenant-config channel — authoring on the Flask plane, read on the SAM plane (R3)

```
myAdmin SPA — Tenant-Admin "Members configuration" (typed editor, reuse AccountModal pattern)
  GET  /api/config/members-parameters      ── definition file (what controls to render)
  GET  /api/tenant-admin/parameters        ── current members.* values
  PUT  /api/tenant-admin/parameters        ── save WHOLE object per param (R3.5)
        members.field_overlay   (map-of-field-defs)     ── "what fields exist"
        members.scope_dimensions (list-of-objects)       ── "how rows are scoped"
        members.view_contexts    (list-of-named-column-sets, ui.tables-shaped)  ── "which fields show together"
  ▼  (after commit: enqueue_sync(scope_id) — parameter_admin_routes.py, F.8)
MySQL parameters (ParameterService, scope="tenant", namespace="members")   ── SYSTEM OF RECORD
  ▼  ProjectionSync (one-directional, single writer, versioned, idempotent)
governance_projection (DynamoDB)  PK tenant_id
  config#scope   ← members.scope_dimensions
  config#fields  ← members.field_overlay (+ view_contexts carried here or config#views)
  ▲  (boto3 Query — READ ONLY)
Members module projection reader (sam/members/repository/projection_config_reader.py)
  → ScopeConfigProvider   → ScopeConfig
  → TenantOverlayProvider → TenantOverlay
  → view-contexts provider → view contexts
  ▼
FieldResolver.resolve(tenant_id) = FIXED_FIELDS ⊕ overlay  → FieldConfig
  ▼  GET /members/field-config  →  useMemberFieldConfig()  →  SPA renders
```

The projection builders (`projection_sync.py`) and reader already exist for `scope_dimensions` /
`field_overlay` (s5b C2/C4). s5c's tenant-config change is: (1) declare the `members` namespace so
the authoring UI is reachable, (2) reuse the ledger typed-editor for it, (3) add the third
`view_contexts` parameter through the same path.

### Field resolution chain (already built — the basis for parameter-driven fields + view contexts)

```
members.field_overlay (Parameter, MySQL)
   │ enqueue_sync → projection
   ▼
config#fields (DynamoDB)  →  TenantOverlayProvider.get_overlay(tenant_id) → TenantOverlay{fields, overrides}
                                    │
FIXED_FIELDS (in-code, R4.3) ───────┤ FieldResolver.resolve(tenant_id)
Calculated field defs (R4.4) ───────┘   = fixed ⊕ overlay (+ derived)
                                    ▼
                             FieldConfig { fields: ResolvedField[] }   (each carries origin FIXED|VARIABLE, visible, label, group)
                                    ▼
                        GET /members/field-config → useMemberFieldConfig() → FieldConfig on the SPA
```

**A Parameter field is an `OverlayField` (origin `VARIABLE`); a Fixed field comes from
`FIXED_FIELDS` (origin `FIXED`, optionally presentation-overridden); a Calculated field is a
derived `ResolvedField`.** The frontend treats them uniformly — it renders whatever `FieldConfig`
lists. This is why view contexts reference field keys generically (see C-VIEW).

### Runtime data flow (SPA → module), local topology, accounts

Reused from s5b unchanged: `membersApiService.ts` → `MEMBERS_API_BASE_URL` with Bearer token +
`X-Tenant` + `X-Language`; the module edge verifies the JWT, resolves tenant from the verified
entitlement, checks `has_capability` off `custom:entitlements`, resolves scope from the projected
grant, dispatches to the domain → repository (`sam-members`). Local topology per `42-local-dynamodb`
(Docker network `myadmin-local`, `dynamodb-local`, `sam local start-api`). Accounts per
`23-aws-accounts` (identity 344561557829 = Cognito; data 506221081911 = DynamoDB/Lambda/API GW).

## Components and Interfaces

> C1–C14 (projection record types, builders, sync trigger, module reader, edge scope integration,
> provider wiring, `membersApiService.ts`, `MembersPage`, modals, SPA registration, SAM template,
> SysAdmin/Tenant-Admin onboarding surfaces, module API contract, MkDocs manual) are **REUSED from
> s5b unchanged** unless noted below. s5c adds/refactors the components in this section.

### C-PTG — PreTokenGen channel wiring (NEW; R1)

- **Responsibility:** make the capability channel real end-to-end, test-pool-first then prod.
- **Reuse:** `sam/pretokengen/*` (the S4 Lambda + `projection_governance_reader.py`) unchanged.
- **Deploy (data account 506221081911):** deploy the PreTokenGen Lambda; it reads
  `governance_projection` **same-account** via boto3 + IAM (no cross-account data read).
- **Attach (identity account 344561557829):** attach the Lambda as the pool's V2
  Pre-Token-Generation trigger and grant a cross-account `aws_lambda_permission`
  (`lambda:InvokeFunction`, principal `cognito-idp.amazonaws.com`, source = the pool ARN) —
  **`myAdmin-test` first**, then **Pool A**.
- **Interface / claim:** the trigger stamps `custom:entitlements` **additively** (never touching
  `cognito:groups` / `custom:tenants`); the module's `has_capability` reads it. Empty projection →
  omitted claim → deny (fail-safe).
- **Verification hooks:** a seeded `myAdmin-test` user with a non-empty projected entitlement; assert
  the decoded token carries `custom:entitlements` and the module authorizes off it with grep-clean
  zero `cognito:groups` capability paths.
- **Open sub-item (T18 physical IAM):** the exact deploy + cross-account permission + attach is
  implemented here; the design is settled, only the wiring remains (F.2).

### C-POOL — Module Cognito repoint (NEW; R2)

- **Responsibility:** decouple local + CI from prod Pool A.
- **Interface (config-not-code):** set for local + CI —
  `HDCN_COGNITO_ISSUER = https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl`,
  `HDCN_COGNITO_JWKS_URI = …/eu-west-1_xyrlzfqbl/.well-known/jwks.json`,
  `HDCN_COGNITO_CLIENT_ID = 43s15cm8qcgg8an85udt0e087u`. The issuer→pool registry
  (`auth/pool_registry.py`) selects by `iss`, so this is the whole change.
- **Removes:** the prod-Pool-A coupling (`eu-west-1_Hdp40eWmu`) from `env-vars.local.json` (R2.3).

### C-SCHEMA — `members` parameter schema + definition endpoint (NEW; R3.1)

- **Responsibility:** make the schema-driven Tenant-Admin surface render Members config, and serve
  the typed-editor definitions.
- **`parameter_schema.py` — add a `members` namespace** gated by `module: "MEMBERS"`, declaring the
  three params so `get_schema_for_tenant(active_modules)` includes them and
  `parameter_admin_routes.py` permits them for a Members-enabled tenant. Each is a `json` param
  (single object/list value, R3.5). This is the single missing declaration that `projection_sync.py`
  already anticipates in its comments ("the `members.*` namespace declaration/gating … is a later
  `[H]` task").
- **Definition endpoint — reuse the ledger pattern:** add `GET /api/config/members-parameters`
  (`config_routes.py`, analogous to `GET /api/config/ledger-parameters`) serving a new
  `backend/src/config/members_parameters.json`. The definition language extends the ledger def set
  (`key`, `type` in `boolean|string|string[]|number`, `label_en`/`label_nl`, `description`,
  `depends_on`, `options`, `module`) with two composite types Members needs:
  - **`list<object>`** — for `scope_dimensions` and `view_contexts` (an ordered list of records, each
    a set of typed sub-fields);
  - **`map<field_def>`** — for `field_overlay` (a keyed map of field definitions).
- **Contract stability:** the definition/endpoint shape matches the future generic framework's
  contract (`json-editor.md`) so the later extraction (rule-of-three) is cheap.

### C-EDITOR — Members typed authoring UI (NEW; R3.2–R3.6)

- **Responsibility:** a structured, bilingual, no-raw-JSON editor for the three `members.*` params,
  reusing the `AccountModal.tsx` typed-editor renderer (Switch / input / Select / `string[]`+
  `options` multi-select / `depends_on` / bilingual labels), extended for `list<object>` and
  `map<field_def>`.
- **Location:** `frontend/src/components/TenantAdmin/` — a `MembersConfig*` component set, reachable
  from the Tenant-Admin area for a Members-enabled tenant.
- **Sub-editors:**
  - **Field overlay** (`map<field_def>`): add/remove field definitions (key, type, label{nl,en},
    required, visible) + presentation overrides of fixed fields.
  - **Scope dimensions** (`list<object>`): each dimension = key, label{nl,en}, enabled, multi_valued,
    **values** (`string[]`+`options`), all_wildcard role, required_for capabilities.
  - **View contexts** (`list<object>`, `ui.tables`-shaped): each context = key, label{nl,en},
    permission_roles, `columns` (field-key references), `filterable_columns`, `default_sort`,
    `page_size`. The column picker offers only field keys resolvable in the current field set
    (fixed ⊕ overlay ⊕ calculated) — reference validation at authoring time (R5.1a).
- **Write-granularity (R3.5):** each sub-editor commits its **whole** param object in one PUT →
  `ParameterService.set_param(scope="tenant", "members", <key>, <object>)` →
  `enqueue_sync(scope_id)` (already wired, F.8) → one per-tenant re-projection.
- **Draft-state (R3.6):** **save-once + unsaved-changes guard** (warn on navigate-away). No draft/
  publish (deferred to `json-editor.md`).
- **Not built:** no bespoke field-builder from scratch; no raw-JSON `ParameterManagement` as the
  authoring path; no generic framework (R3.3).

### C-FIELDS — Field model: Fixed / Parameter / Calculated (REFACTOR; R4)

- **Fixed base (`sam/members/domain/fixed_fields.py`, REFACTOR):** broaden from the current ~9 fields
  toward a representative universal base (see the classification table in Data Models), using
  **English canonical `snake_case` keys** + `{nl, en}` labels (R4.6/R4.7). Fixed = universal-in-code;
  a field MAY be Fixed while its **enum values** are Parameter (R4.2).
- **Parameter overlay:** the remainder authored via `members.field_overlay` (C-EDITOR) → `config#fields`
  → `TenantOverlay` → `FieldResolver` (origin `VARIABLE`). **Overlay keys are tenant-authored**
  (snake_case-validated, not language-forced). Seeding defaults use **generic placeholder names**
  (Region A/B; Field A), never h-dcn's real list (R4.5).
- **Calculated (R4.4):** derived, never stored; English canonical keys + `{nl, en}` labels.
  `display_name` (from name parts), `years_member` (from `joined_date`), `age` (from `birth_date`)
  computed in the domain/presentation layer and surfaced as read-only `ResolvedField`s. The
  classification table names each calculated field + its inputs.
- **Storage group vs functional group (R4.9):**
  - **Storage group (FIXED, structural):** the record has a closed 3-bucket shape by field origin —
    `member["personal"][…]` / `member["membership"][…]` (fixed fields, per `FieldGroup`) and
    `member["overlay"][…]` (ALL parameter/variable fields, per `OverlayField` — "lands under the
    record's `overlay` attribute"). Calculated fields are not stored. Adding a tenant field never
    changes this shape. Address fields are Fixed under `personal`.
  - **Functional group (PARAMETER-DRIVEN, presentation):** a separate `functional_group` attribute on
    every `ResolvedField`, orthogonal to the storage bucket. Authored via `members.field_overlay`:
    a `functional_groups` catalog (key + `{nl,en}` label + order) + a `functional_group` per field.
    Parameter fields carry it inline (`OverlayField.functional_group`); Fixed/Calculated fields get it
    via an extended `FixedFieldOverride.functional_group` (tenant-overridable, base default).
    `FieldResolver` surfaces `functional_group` on each `ResolvedField`. View contexts + modals section
    by it. Reference-validated (Property 7): offer-only-defined at authoring; reject dangling on Save;
    fall back to a default section at render.

  ```
  storage bucket (FIXED, by origin)      functional_group (PARAMETER, tenant-authored)
    personal.first_name            ─►    "personal"    (default; tenant may reassign)
    personal.street                ─►    "address"     (tenant-defined functional group)
    membership.status              ─►    "membership"
    overlay.motor_brand            ─►    "motor"        (tenant-defined)
    overlay.iban                   ─►    "financial"    (tenant-defined)
  ```

### C-VIEW — View contexts (NEW parameter + generic renderer; R5.1/R5.1a)

- **Parameter:** `members.view_contexts` — a `list<object>` where each object is field-compatible
  with myAdmin's existing `ui.tables` per-view shape (`columns`, `filterable_columns`, `default_sort`,
  `page_size`) plus `key` / `label{nl,en}` / `permission_roles`. This **generalizes single-view
  `ui.tables` to multiple selectable contexts**; `ui.tables` itself is unchanged (FIN/STR stay
  single-view).
- **Projection:** carried through the tenant-config channel (either folded into `config#fields` or a
  sibling `config#views` row — see Open Design Items). The module reader exposes it via a
  view-contexts provider; a missing/empty value → a single default context over all visible fields
  (empty-is-valid).
- **Renderer:** the SPA resolves the list, offers a **context dropdown** (gated by `permission_roles`
  — view convenience only), and per selected context hands `{columns, filterableColumns, defaultSort,
  pageSize}` to the **existing** `useFilterableTable` / `FilterableHeader` toolkit. So per-context it
  collapses onto the same single-view primitives `useTableConfig` already feeds.
- **Reference resolution + validation (R5.1a):** each column `field_key` is looked up in `FieldConfig`
  (`field(dotted_key)`); Fixed / Parameter / Calculated all resolve uniformly. At authoring the editor
  offers only resolvable keys; on Save the backend rejects a context referencing an unresolvable key
  (mirroring `FieldResolver._reject_invalid_overlay` fail-fast); at render an unresolvable key is
  skipped, never a crash.
- **Scope is orthogonal:** the selected context chooses **which columns** show; **row scope filtering
  (C-SCOPE / R5.3) is always applied server-side** regardless of context.

### C-SCOPE — Representative scope badge + filtering (REUSE + surface; R5.3)

- **Reuse:** the built `scopegrant#` channel + `resolve_scope_access` (s5b B.2/C5). The edge resolves
  the caller's projected grant per dimension: admin/all → `["*"]`; subgroup grant → that subset;
  `required_for` capability with no grant → deny-by-default.
- **Surface:** a read-only scope/region `Badge` column + a scope pre-filter in the table (reuse the
  region Badge already present). Values come from the `config#scope` dimension `values` (tenant
  parameter data, generic placeholder names by default).

### C-SURFACE — Representative Leden Overzicht + modals (REFACTOR; R5)

- **Reuse:** the s5b `MembersPage` + modals + `membersApiService.ts` + `useMemberFieldConfig` +
  shared toolkit + `members` i18n. Broaden per R5:
  - parameter-driven columns organized into multiple view contexts (C-VIEW);
  - calculated fields as read-only columns/fields (C-FIELDS);
  - scope badge + filtering (C-SCOPE);
  - view / edit / add / delete modals over the resolved field set, honoring field-level view/edit
    permissions + `showWhen` conditional visibility;
  - export wired to `export_members` (not "coming soon");
  - single + bulk lifecycle transitions, **deliberately limited** (do not over-build the state
    machine);
  - `membership_type` dropdown of active catalog entries, domain-validated (reuse s5 catalog).
- **Layering (steering 35 / 32):** presentation only; authoritative validation/permission/scope stay
  server-side; BankingProcessor modal pattern (row-click opens modal, no per-row buttons).

### C-UNWIND — Remove s5b shortcuts (REMOVE; R6)

- Delete `_local_dev_group_grants_capability` + `MEMBERS_LOCAL_AUTH_FALLBACK` (capability now real).
- Delete the `MEMBERS_LOCAL_TENANT_ID` tenant fallback (tenant from verified entitlement).
- Remove prod-Pool-A coupling from `env-vars.local.json` (C-POOL).
- The `Members_*` names (`Members_CRUD`/`Members_Read`/`Members_Export`) are ROLES, not a
  capability-granting group: they are assigned via MySQL `user_tenant_roles`, projected as
  `role#<email>#<role>`, consumed by `required_for` scope gating (`scope_dimensions.py` →
  `resolve_scope_access`), and carried in `RequestContext.groups`. They remain present on prod
  Pool A and are DISTINCT from capabilities (`members:read/write/export/admin`). R6.4's actual
  requirement is a code contract — NO Members *capability* is derived from `cognito:groups`;
  capability comes solely from the verified `custom:entitlements` claim. Enforced by the removals
  in tasks 0.1/0.2 and pinned by the standalone guard test
  (`sam/tests/test_members_capability_no_groups_guard.py`, Property 5). Deleting those role groups
  would break scope gating and MUST NOT be done.
- Demote `onboard-hdcn-local.py` to a data-track fixture (never the governance path).

### C-DEPLOY — Gated PROD cutover + rollback (NEW ops; R7/R8)

- **CI/CD path:** build → deploy (`sam-members`, `sam/pretokengen`) → provision (onboard h-dcn via
  the prod SPA) → project (run/observe sync) → verify (scoped + general users).
- **Tables managed outside CFN / retain:** `sam-members` + `governance_projection` are not template
  resources; the deploy never creates or drops them (steering 23).
- **Gate:** attach the Pool A PreTokenGen trigger only after the dev/test channel proof passes.
- **Rollback (non-destructive, governance-based):** detach the trigger; remove the `MEMBERS`
  entitlement / scope-role assignments; re-project. NO table drops, NO data deletion. Parallel-run
  safety: s5 uses NEW tables; the live h-dcn app is untouched.

### C-PLAYBOOK — Provisioning playbook: two hard-separated tracks (NEW; R8)

- **Governance track (SPA only — never scripted around):**
  - SysAdmin (`/api/sysadmin/*`): create tenant + `MEMBERS` entitlement + role definitions.
  - Tenant-Admin (`/api/tenant-admin/*`): assign user roles (→ `user_tenant_roles`) + author the
    three `members.*` params (C-EDITOR). **Role assignments MUST flow through the endpoints** (a
    script may DRIVE an endpoint but not write MySQL directly), so `enqueue_sync` → projection is
    genuinely exercised (F.8).
- **Data/migration track (scripts — idempotent + dry-run + verify):**
  - **member import** — REUSE `sam/members/migration/hdcn_backfill.py`: the Google Sheet is consumed
    as a **CSV/JSON export file** via `FileSourceAdapter` (no live Google API — "a Google-Sheet export
    *is* a CSV/JSON"); `map_hdcn_row` transforms + validates each row (mapping Dutch source columns →
    English Fixed keys; `member_number` → fixed string validated against the tenant format), and
    writes **only via `MembersRepository`** (tenant_id-keyed, uniqueness → 409). Runs as a host script
    → `dynamodb-local` (dev/test) then prod `sam-members`. It writes **member business data only** —
    never the `parameters` table or the projection (those are the governance track). h-dcn's
    `migrationHDCNLedenbestand` is the prior art;
  - membership-type catalog seed;
  - bulk Cognito user load into `myAdmin-test` (dev) / Pool A (prod) from an **editable file derived
    from the existing h-dcn Cognito pool** (~10×2 + 3 users) carrying each user's capability + scope;
    users created by the script, **role assignments via the governance endpoint**.
- **Reconciliation backstop (R8.6):** confirm the periodic `reconcile()` is scheduled/runnable in
  dev/test and prod (the only open operational sub-item; the on-change path is proven).

## Data Models

### The three `members.*` parameters (MySQL, namespace `members`, scope `tenant`)

**`members.field_overlay`** — the tenant field-config object. Carries three parts: a
`functional_groups` catalog, a `fields` map (`map<field_def>` — the added variable fields), and
`fixed_overrides` (presentation overrides of fixed/calculated fields, incl. `functional_group`).
Feeds `config#fields` → `TenantOverlay`:

```json
{
  "functional_groups": [
    {"key": "personal",       "label": {"nl": "Persoonlijk", "en": "Personal"},       "order": 1},
    {"key": "address",        "label": {"nl": "Adres",       "en": "Address"},         "order": 2},
    {"key": "membership",     "label": {"nl": "Lidmaatschap","en": "Membership"},      "order": 3},
    {"key": "motor",          "label": {"nl": "Motor",       "en": "Motorcycle"},      "order": 4},
    {"key": "financial",      "label": {"nl": "Financieel",  "en": "Financial"},       "order": 5},
    {"key": "administrative", "label": {"nl": "Administratie","en": "Administrative"},  "order": 6}
  ],
  "fields": {
    "motor_brand": {"type": "string", "required": false, "visible": true,
                    "label": {"nl": "Motormerk", "en": "Motor brand"},
                    "functional_group": "motor", "order": 20}
  },
  "fixed_overrides": {
    "personal.street":   {"functional_group": "address"},
    "personal.postal_code": {"functional_group": "address"},
    "personal.city":     {"functional_group": "address"},
    "personal.country":  {"functional_group": "address"}
  }
}
```

Note: `functional_group` values reference the `functional_groups` catalog (reference-validated,
Property 7); storage stays `personal` (fixed) / `membership` (fixed) / `overlay` (parameter) — the
override moves only the *display* group, never the storage bucket. Seeding defaults use generic
placeholder group/field names.

**`members.scope_dimensions`** — `list<object>` (how rows are scoped). Feeds `config#scope` →
`ScopeConfig`. Values are generic placeholders by default:

```json
[
  {"key": "region", "label": {"nl": "Regio", "en": "Region"}, "enabled": true,
   "multi_valued": false, "values": ["Region A", "Region B", "Region C"],
   "all_wildcard": "Regio_All", "required_for": ["Members_CRUD"]}
]
```

**`members.view_contexts`** — `list<object>`, `ui.tables`-shaped (which fields show together):

```json
[
  {"key": "overview", "label": {"nl": "Overzicht", "en": "Overview"},
   "permission_roles": ["Members_Read", "Members_CRUD"],
   "columns": ["member_number", "korte_naam", "email", "region", "status", "membership_type"],
   "filterable_columns": ["korte_naam", "region", "status", "membership_type"],
   "default_sort": {"field": "korte_naam", "direction": "asc"}, "page_size": 50},
  {"key": "financial", "label": {"nl": "Financieel", "en": "Financial"},
   "permission_roles": ["Members_CRUD"],
   "columns": ["member_number", "korte_naam", "membership_type", "payment_method", "iban", "status"],
   "filterable_columns": ["membership_type", "payment_method", "status"],
   "default_sort": {"field": "korte_naam", "direction": "asc"}, "page_size": 50}
]
```

Each `columns` / `filterable_columns` entry is a `field_key` validated against `FieldConfig`
(R5.1a). Pilot seeds 2–3 generic-placeholder contexts; h-dcn's real contexts are later parameter
data, no code change.

### Key vs. label naming convention (R4.6)

- A **field key is a stable identifier**, never user-facing, never translated. **Fixed and
  Calculated keys are platform-canonical: English, `snake_case`, stable** (they belong to the
  platform base registry, read by every tenant and module author) — consistent with the existing
  `fixed_fields.py` base (`personal.name`, `membership.member_number`), the ledger defs
  (`bank_account`), and `ui.tables` column keys.
- **Parameter (overlay) keys are tenant-authored:** the platform validates format (`snake_case`) but
  does NOT impose a language — a tenant's own vocabulary (e.g. h-dcn's Dutch `motormerk`) is
  respected. This mirrors R4.5 (don't bake platform assumptions into tenant data).
- Every field's **user-facing label is a localized `{nl, en}` map** (R3.2 / R4.7); the frontend
  renders `label[language]`. The Dutch in h-dcn's field names survives as the `nl` label, not as the
  key. The gsheet→DynamoDB importer (task 6.2) maps h-dcn's Dutch **source columns** → the English
  **Fixed keys** (the one clean place that translation happens).

### Field classification table (h-dcn field set — R4.1 deliverable)

Rebuilt from `/home/peter/projects/h-dcn/frontend/src/config/memberFields/`. **Fixed** = universal
base registry (`fixed_fields.py`, English canonical keys); **Parameter** = tenant overlay
(`members.field_overlay`, tenant-authored keys); **Calculated** = derived, not stored (English
canonical keys). Note the R4.2 rule: a Fixed field may have Parameter enum values (its value LIST is
tenant config even though the field itself is universal). The **h-dcn source key** column is the
Dutch reference for the migration mapping, NOT the platform key.

**On the "Group" column (R4.9):** it shows the **functional (display) group** — which is
**parameter-driven** and tenant-overridable. It is distinct from the **storage group** (structural,
fixed by origin): Fixed fields store under `personal`/`membership`, all Parameter fields under
`overlay`, Calculated fields are not stored. So h-dcn's `address` / `motor` / `financial` /
`administrative` are **functional groups**; address fields still **store** under `personal`.

| Platform key (Fixed/Calculated: canonical EN · Parameter: tenant-authored) | Group | Classification | h-dcn source key | Notes / enum-values source |
| --- | --- | --- | --- | --- |
| `first_name`, `last_name`, `name_infix`, `initials` | personal | **Fixed** | `voornaam`, `achternaam`, `tussenvoegsel`, `initialen` | universal name parts |
| `display_name` | personal | **Calculated** | `korte_naam` | from `first_name`+`name_infix`+`last_name` |
| `birth_date` | personal | **Fixed** | `geboortedatum` | |
| `age` | personal | **Calculated** | `leeftijd` | from `birth_date` |
| `birthday` | personal | **Calculated** | `verjaardag` | day+month from `birth_date` |
| `gender` | personal | **Fixed** (Parameter enum values) | `geslacht` | value list `M/V/X/N` is tenant config |
| `email` | personal | **Fixed** | `email` | account identity |
| `phone` | personal | **Fixed** | `telefoon` | |
| `guardian_name` | personal | **Parameter** | `minderjarigNaam` | conditional (minors) — tenant overlay + `showWhen` |
| `street`, `postal_code`, `city`, `country` | address | **Fixed** | `straat`, `postcode`, `woonplaats`, `land` | universal address |
| `status` | membership | **Fixed** (Parameter enum values) | `status` | lifecycle states are tenant config |
| `membership_type` | membership | **Fixed ref + Parameter catalog** | `lidmaatschap` | references the Lidmaatschap Beheer catalog (tenant data). **Value-level role gating (R4.12):** options `Erelid`, `Overig` restricted to `Members_CRUD`/`System_User_Management` (h-dcn `enumPermissions`). h-dcn base options: `Gewoon lid`, `Gezins lid`, `Donateur`, `Gezins donateur`, `Erelid`, `Overig`. |
| `region` | membership | **Parameter** (scope dimension) | `regio` | authored via `members.scope_dimensions`. **Value-level role gating (R4.12):** option `Overig` restricted to `Members_CRUD`/`System_User_Management` (h-dcn `enumPermissions`). |
| `member_number` | membership | **Fixed `string`; Parameter format; manual entry** (derivation = tenant hook, OUT) | `lidnummer` | fixed-type **string** (stable/sortable/leading-zero-safe), repository-enforced unique (conditional write → 409). **Format pattern is tenant Parameter** (e.g. `Nr-0001` / `Nr-00001` / regex), domain-validated. **Generation is a tenant policy, OUT** — s5c: manual entry (`Members_CRUD` types a value matching the pattern); h-dcn's auto-counter stays in its `derive_member_number` hook (not promoted). Generic numbering *function* is future (R4.8). **h-dcn source shape:** `lidnummer` is `dataType: number`, `computed: true`, `membershipTypeRestricted: [Gewoon lid, Gezins lid, Erelid]`, `showWhen` those membership types — the platform re-classifies it to a Fixed **string** with manual entry (the numeric/computed/show conditions are h-dcn policy, not platform). |
| `joined_date` | membership | **Fixed** | `ingangsdatum` | |
| `years_member` | membership | **Calculated** | `jaren_lid` | from `joined_date` |
| `magazine_pref`, `newsletter_pref`, `privacy_consent`, `referral_source` | membership | **Parameter** | `clubblad`, `nieuwsbrief`, `privacy`, `wiewatwaar` | communication prefs — tenant overlay (enum values tenant config). `referral_source` (`wiewatwaar`) is **conditionally required for new applications** in the h-dcn source (`member_id` not_exists) — modeled via `show_when`/validation on the overlay field. |
| (tenant-authored, e.g. `motor_brand`, `motor_type`, `build_year`, `license_plate`) | motor | **Parameter** | `motormerk`, `motortype`, `bouwjaar`, `kenteken` | club-specific overlay (h-dcn "Motor"); keys are h-dcn's choice; `showWhen` by membership type |
| `iban`, `payment_method` | financial | **Parameter** | `bankrekeningnummer`, `betaalwijze` | financial overlay (enum values tenant config) |
| `notes`, `signature_date` | administrative | **Parameter** | `notities`, `datum_ondertekening` | admin overlay |
| `created_at`, `updated_at` | administrative | **Fixed** (system) | `created_at`, `updated_at` | record timestamps |
| `application_year` | administrative | **Calculated** | `aanmeldingsjaar` | from record creation year |
| (n/a) | administrative | **OUT** | `welcome_pack_*` | Welkomstpakketten out of scope (R11.2) |

> **This table is the AUTHORITATIVE SOURCE for the field definitions (R4.10).** The concrete
> `fixed_fields.py` base (English canonical keys + `{nl,en}` labels) + calculated fields + the seeded
> `members.field_overlay` (generic placeholder names) are built **row-by-row** from it in Phase 1:
> each **Fixed** row → one `FixedField`; each **Calculated** row → one derived field; each
> **Parameter** row → an overlay seed/example; `OUT` rows are defined nowhere. The mapping is
> **total** (table ⇄ definitions), asserted in task 1.5. Enum-value lists marked "Parameter enum
> values" ship as tenant config, not code constants. Parameter-row platform keys shown in parentheses
> are illustrative — the real keys are whatever the tenant authors (snake_case-validated).

### Dropdown / enum fields — where each option list lives (R4.11)

h-dcn's member surface is dropdown-heavy. Each dropdown's **option list** has a specific home; there
are **four buckets**, all tenant data (no hardcoded platform vocabularies):

| Bucket | h-dcn dropdowns (source key) | Option list lives in | Rendered from |
| --- | --- | --- | --- |
| **1. Enum values on a Fixed field** (R4.2) | `gender` (geslacht: M/V/X/N), `status` (lifecycle states) | `members.field_overlay` — the fixed field's `enum_values` (tenant config) → projected `config#fields` | resolved field's `choices` |
| **2. Enum values on a Parameter (overlay) field** | `magazine_pref` (clubblad), `newsletter_pref` (nieuwsbrief), `privacy_consent` (privacy), `referral_source` (wiewatwaar), `payment_method` (betaalwijze), `motor_brand` (motormerk) | inside the `OverlayField` definition's `choices`, in `members.field_overlay` | resolved field's `choices` |
| **3. Managed catalog** | `membership_type` (lidmaatschap) | the **Lidmaatschap Beheer catalog** — `membershiptype#` rows in `sam-members` (module data, s5), **active-only** | `GET /membership-types`, domain-validated (R5.8) |
| **4. Scope dimension** | `region` (regio) | the `region` dimension's `values` in `members.scope_dimensions` → projected `config#scope` | the dimension's values (also drives scope, C-SCOPE) |

So buckets 1/2/4 ride the tenant-config channel (parameter → projection → resolved field), bucket 3
is the catalog module-data path. None is a code constant.

### Role-restricted enum values (h-dcn `enumPermissions`) — value-level gating (R4.12)

Distinct from field-level permission ("may you see/edit this field?"), **value-level** gating asks
"of this field's options, which may *you* choose?". h-dcn examples: `lidmaatschap` `Erelid`/`Overig`
only for `Members_CRUD`/`System_User_Management`; `regio` `Overig` only for CRUD.

- **Shape:** each enum option MAY carry a `roles` restriction:
  `{ "value": "erelid", "label": {"nl": "Erelid", "en": "Honorary"}, "roles": ["Members_CRUD"] }`.
  An option with no `roles` is available to anyone who may edit the field. Authored wherever the
  option list lives (buckets 1/2 above; the catalog can carry the same per-entry restriction for
  bucket 3).
- **Enforcement (steering 35):** the **frontend** filters the dropdown to the caller's allowed
  options (convenience); the **domain layer authoritatively REJECTS** a create/edit that sets a value
  the caller's role is not permitted (422/403) — the real gate. Same frontend-convenience /
  server-authority split as everything else.
- **Conditional visibility (`showWhen`):** related h-dcn behavior — motor fields shown only for
  certain membership types. This is a per-field `show_when` condition on the resolved field (already
  present in the field-config shape); the dropdown/field renders only when the condition holds, and
  the server does not require a hidden field. In scope for the representative surface (R5.5).

### Governance projection rows (REUSE from s5b; unchanged shapes)

`config#scope`, `config#fields`, `scopegrant#<email>#<dimension>` — see s5b `design.md` Data Models.
s5c adds `view_contexts` (folded into `config#fields` or a sibling `config#views` row — Open Design
Items). `sam-members` module data (members, memberships, catalog, counters) unchanged.

## Correctness Properties

The s5 domain + s5b plumbing properties are inherited (tenant isolation, member-number uniqueness,
lifecycle legality; s5b Properties 1–4: one-directional, config round-trip, empty-is-valid, scope
deny-by-default). s5c adds:

### Property 5: Capability travels the token, never `cognito:groups`

For all module authorization decisions in dev/test and prod (once the trigger is wired), the
capability is derived from the verified `custom:entitlements` claim; there exists no code path that
derives a Members capability from `cognito:groups`. (Enforced by removing
`_local_dev_group_grants_capability`; verified by grep + authorization-trace assertions.)

**Validates: Requirements 1.3, 6.1, 12.1**

### Property 6: PreTokenGen is fail-safe and detach-reversible

For all entitlement-resolution failures, the trigger omits `custom:entitlements` and login still
succeeds; and detaching the trigger restores the pre-trigger login/authorization behavior exactly.

**Validates: Requirements 1.4, 12.5, 7.5**

### Property 7: Config references resolve or are safely dropped

For all view contexts (and their `field_key`s) and all field `functional_group` assignments, either
the reference resolves — a `field_key` in `FieldConfig` (Fixed/Parameter/Calculated), a
`functional_group` in the `functional_groups` catalog — and renders, or it is rejected at Save
(authoring) / skipped/defaulted at render (runtime) — never a crash. A parameter-driven (overlay)
field, once authored, is a valid context reference and a valid functional-group member with no code
change.

**Validates: Requirements 5.1**

### Property 8: Config authoring is save-once → one projection

For all logical config edits, the editor issues exactly one param PUT per `members.*` object, which
triggers exactly one `enqueue_sync` and one per-tenant re-projection (idempotent, versioned); no
per-field write path exists.

**Validates: Requirements 3.5, 8.4**

### Property 9: Prod cutover and rollback are non-destructive

For all cutover and rollback executions, no `sam-members` / `governance_projection` table is created
or dropped by the deploy, and rollback deletes no member data — it only detaches the trigger and
removes governance rows, then re-projects.

**Validates: Requirements 7.2, 7.5, 12.3**

PBT applies to the projection/reader/resolver/validation layers (universally-quantified); the
frontend/config/IaC layers are example-tested per the PBT exclusions in
`35-sam-module-architecture-sam.md`.

## Error Handling

- **Empty-is-valid throughout:** no `config#scope` → tenant-wide; no `config#fields` → fixed base; no
  `view_contexts` → one default context; empty entitlement → deny (S4). Never a crash.
- **PreTokenGen resolution failure:** claim omitted, login succeeds (fail-safe).
- **Bad config (dangling view reference / invariant-weakening overlay):** rejected fail-fast at Save
  with a descriptive error; the running module is unaffected (still reads the last good projection).
- **Cross-account invoke misconfig:** the trigger simply doesn't stamp the claim → deny → detectable
  in verification (token has no `custom:entitlements`); reversible by fixing the permission.
- **Module edge:** reused status contract — 401 unauth, 403 unentitled/out-of-scope-write, 404
  not-found/out-of-scope-read, 405 wrong method.
- **Secrets:** never echo pool/client secrets; reference by name (the pool/client IDs above are
  public identifiers, not secrets).

## Testing Strategy

Per steering 33/34 and the PBT exclusions in `35-sam-module-architecture-sam.md`.

- **Unit / domain (SAM):** broadened `fixed_fields.py`; calculated-field derivations; view-context
  reference validation; `FieldResolver` merge with the broadened base. Reuse the 600+ existing
  module tests.
- **Property-based:** Property 2 (config round-trip incl. `view_contexts`), Property 3
  (empty-is-valid), Property 4 (scope deny-by-default), Property 7 (view-context reference resolution).
- **Backend (Flask):** `members` namespace gating in `get_schema_for_tenant`; the members-parameters
  definition endpoint; save-once → single `enqueue_sync` (Property 8); parameter validation rejects
  dangling references.
- **Frontend:** the typed editor (list-of-objects + map-of-field-defs rendering; unsaved-changes
  guard); the view-context dropdown + per-context column rendering via `useFilterableTable`; scope
  badge + filtering; modals (view/edit/add/delete) over resolved fields; export.
- **Capability channel (integration, dev/test):** seed a `myAdmin-test` user + projected entitlement;
  attach the trigger; assert the token carries `custom:entitlements` and the module authorizes off it
  with zero `cognito:groups` reliance (Property 5); assert fail-safe on resolution failure and
  detach-reversibility (Property 6).
- **Provisioning (dev/test-first):** governance authored via the SPA (SysAdmin + Tenant-Admin) with
  `enqueue_sync` → projection observed; data/migration scripts idempotent + dry-run + verify;
  reconciliation backstop confirmed scheduled.
- **Prod verification:** scoped user sees subset; general user sees all; capability via
  `custom:entitlements`; non-destructive rollback demonstrated (Property 9).
- **Docs:** `mkdocs build` succeeds (both locales) — extend the `docs/docs/members/` manual with the
  authoring UI + representative surface + scope behavior.
- Clean up any temporary files under `.agent-output/`; no long-running foreground processes.

## Open Design Items (decide during design/tasks — do not block)

1. **`view_contexts` projection shape — SETTLED (task 3.1): sibling `config#views` row.** Decided
   for a **sibling `config#views` row** (not folded into `config#fields`): clean separation of
   concern (`config#fields` maps 1:1 to the `TenantOverlay` the `FieldResolver` consumes, whereas
   view contexts are a distinct "which fields show together" concern with a different consumer,
   authoring parameter, and validation) and independent versioning (a views-only edit advances only
   the `config#views` row's version, so a re-sync does not churn the fields row — R5.6). No concrete
   reason to fold was found in the existing projection code. Built: `build_config_views_row` in
   `projection_sync.py` (Flask builder, wired into the per-tenant sync), `get_view_contexts` on the
   `MembersProjectionReader` (SAM reader), and the storage-agnostic `sam/members/domain/view_contexts.py`
   model; empty/absent `config#views` → exactly one default context over all visible fields
   (empty-is-valid). Row token lives in `services.projection_schema` (`CONFIG_ID_VIEWS`).
2. **`MEMBERS_MODULE_API_BASE` under prod:** confirm whether needed under the direct-to-module-API
   path (analysis D1 option a).
3. **Reporting reachability (R10.1):** how member DynamoDB data reaches myAdmin's reporting toolkit —
   leave the data model + module boundary cleanly addable; do not architect it out. Not built in s5c.
4. **`fixed_fields.py` broadening extent:** exact universal base vs overlay split, finalized against
   the classification table when authored (R4.3).

## Cross-references

- Requirements: `./requirements.md`. Analysis: `./analysis.md` (F.1–F.8).
- Reuse: s5 (`../s5-members-first-migration/`), s5b (`../s5b-members-runnable-in-spa/design.md`).
- Deferred: `.kiro/specs/myBacklog/json-editor.md` (generic config-editor framework + draft/publish).
- Steering: 20/21/22/23/31/32/33/34/35/40/42. ADR 0003–0006.
