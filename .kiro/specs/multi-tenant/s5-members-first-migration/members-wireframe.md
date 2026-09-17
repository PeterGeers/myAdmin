# S5 — Members app: current-state wireframe (h-dcn)

- Status: Draft (scope capture of the EXISTING h-dcn Members app, as-is)
- Source of truth: `~/projects/h-dcn` (backend Lambda handlers, `backend/template.yaml`,
  `.kiro/specs/Members/*`). This document describes what Members **is today** so the
  migration plan (`migration-plan.md`) has a concrete surface to move, step by step.
- Purpose: the "wireframe the scope of the current app" input the migration plan needs.
  It does not change h-dcn; it inventories it.

> Members is chosen as the **first app to migrate** (user decision). It is a bounded,
> well-understood domain (CRUD + workflow + regional access) — a good pilot whose
> outcome is a **Go/No-Go** gate for further app migrations.

## What Members is (domain)

The membership system for h-dcn: member records, membership lifecycle (application →
approval → active → transitions), delegates, per-member payments, regional scoping, and
reporting/export. Members register/are-approved and their record IS the relationship
(the Pool-B-style "the member record is the tenancy relationship" model from `identity.md`).

## Backend surface (AWS SAM, Lambda-per-handler)

h-dcn's backend is ~99 Lambda handlers under `backend/handler/<action>/app.py`, deployed
via one SAM `backend/template.yaml`, sharing `backend/shared/` + `backend/layers/`. The
**Members slice** is ~18 handlers:

| Area | Handlers |
| --- | --- |
| Member CRUD | `create_member`, `get_member_byid`, `get_member_self`, `get_members`, `get_members_filtered`, `update_member`, `delete_member`, `export_members` |
| Membership lifecycle | `create_membership`, `get_membership_byid`, `get_memberships`, `update_membership`, `delete_membership`, `transition_member`, `bulk_transition_members` |
| Delegates | `manage_delegates`, `send_delegate_invitation` |
| Payments (member-scoped) | `get_member_payments` |

## Data model (DynamoDB, current)

- **`MembersTable`** — the member records (the core entity most handlers read/write).
- **`CountersTable`** — sequence/counter values (e.g. member numbers).
- **`PaymentsTable`** — per-member payments (shared with other domains).
- (Webshop/Events use `ProductenTable`/`OrdersTable`/`StockMovements` — out of scope here.)

No `tenant_id` partitioning today — h-dcn runs as a single (implicit) tenant.

## Auth / claims model (current — the part S2–S4 changes)

- Handlers authorize via h-dcn's own `backend/shared/auth_utils.py`:
  - `extract_user_credentials(event)` — reads identity/roles from the request, the
    **unverified** path (Authorization header / `X-Enhanced-Groups`).
  - `validate_permissions_with_regions(...)`, `determine_regional_access(...)`,
    `check_regional_data_access(...)` — **business authorization** (roles → permissions,
    region scoping). This is h-dcn domain policy.
  - `cors_headers()`, `handle_options_request()`, `create_error_response()`,
    `create_success_response()` — HTTP plumbing.
- Regional access is a first-class concept: members belong to regions; roles grant
  region-scoped access.

## Frontend surface

React app under `~/projects/h-dcn/frontend/src` (`modules/`, `pages/`, `services/`,
`context/`, `i18n/`). Members UI: lists/filters, member detail, membership workflow UI,
application flow, reporting. Out of scope for the first backend-focused migration steps;
noted for completeness.

## Relevant Members sub-specs (existing h-dcn design)

- `member-application-flow/` — application → approval workflow (design/req/tasks).
- `membership-workflow-ui/` — the workflow UI.
- `member field config/` — a member field-registry/configuration system.
- `MemberReporting performace/` — reporting + regional filtering + performance.
- `migrationHDCNLedenbestand/` — the historical Ledenbestand data import (Google Sheets).

## Layering principle: frontend / API-handler / application / data (DynamoDB)

A generic architectural rule the migrated module (and every later app migration) follows:
**four layers, dependencies point downward only, nothing skips a layer.** This is what
lets h-dcn's 18 mixed-concern handlers collapse into one clean module and makes the next
migration mechanical.

```
Frontend (React)              presentation only — renders UI, calls the API
      │  (HTTP; never DynamoDB)
      ▼
API / handler layer (thin)    the HTTP edge: routing (the module's internal routes),
      │                       request parse, AUTH (verified token, sam/shared) +
      │                       ENTITLEMENT/authz gate (has_capability, regional access),
      │                       CORS, response shaping. NO business logic, NO DynamoDB.
      ▼
Application / domain layer     the business rules: membership lifecycle/transitions,
      │                       delegate rules, field resolution (fixed base + per-tenant
      │                       overlay), validation. Storage-agnostic + testable; builds
      │                       NO HTTP responses, writes NO DynamoDB queries.
      ▼
Data / repository layer        the ONLY layer that touches DynamoDB: table shape, keys
(DynamoDB)                     (tenant_id partition + LeadingKeys), queries. Exposes
                               repo methods (get_member, list_members(tenant), save_member).
                               TENANT SCOPING is enforced here (every query keyed by
                               tenant_id) so the domain layer cannot cross tenants.
```

**The rule:** Frontend → API handler → Application/domain → Data/DynamoDB, downward only.

> **Authoritative rule:** `.kiro/steering/sam-module-architecture.md` (the full
> responsibility matrix + non-negotiables). Two that matter most for Members:
> - **Handler = thin adapter, not the logic.** `handler = parse → authenticate/tenant
>   context → authorize → delegate to a domain service → to_http_response`. Substantial
>   business logic lives in application/domain services the handler calls, never in the
>   handler — so the same rules are reusable by other APIs/jobs/events.
> - **Never trust React to enforce a business rule.** Validation is duplicated on purpose:
>   React for immediate feedback, Lambda for the **authoritative** decision (a client can
>   bypass the frontend). DynamoDB protects *data* integrity (conditional writes /
>   transactions), it is **not** the business-rule engine.

- **Frontend never hits DynamoDB** — only the backend API. It holds no business rules and
  no data-shape authority; it renders whatever field config (fixed + variable) the backend
  serves.
- **Handlers are thin** — authenticate, authorize (entitlement + regional), route,
  respond. The "adopt the `sam/shared` verified-auth + entitlement toolkit **once**" lives
  here. No domain logic, no direct table access.
- **Domain is storage-agnostic** — it calls the repository through an interface; it does
  not know it is DynamoDB and does not build HTTP responses. This is where h-dcn's reused
  business logic (regional access, workflow) lands, cleanly separated from transport.
- **Data layer owns DynamoDB + tenancy** — table/keys/`LeadingKeys` and `tenant_id`
  scoping are enforced in one place, so cross-tenant access is structurally impossible from
  the layers above.

**Why this is generic (reusable for Events/Webshop):** the API-handler and data layers are
where the platform tooling plugs in (verified auth + entitlement at the edge; tenant-scoped
DynamoDB at the bottom). Only the application/domain layer is app-specific. Migrating the
next app is then "write its domain layer + repository, reuse the edge + tenancy" — which is
exactly what the Go/No-Go pilot is meant to prove.

## Data model principle: fixed (platform) vs. variable (per-tenant) fields

A member record splits into two layers — a **platform-fixed** core plus a **per-tenant
variable** overlay. This is the multi-tenant generalization of two systems that ALREADY
exist, so it is a principle to formalize, not new machinery to invent:

- **myAdmin** already has per-tenant field/template configuration: the
  `tenant_template_config` table + the `FieldConfigMixin` (`FIELD_CONFIG_KEY`, e.g.
  `trip_field_config` for ZZP). Per-tenant field overlays are a proven myAdmin capability.
- **h-dcn** already designed the "Member Field Configuration System — Hybrid Approach": a
  **base field registry** (single source of truth for all member fields, grouped Personal
  / Address / Membership / Motor / Financial) + **context-specific overrides** +
  role-based permissions + dynamic resolution.

### The two layers (the migration's member data model)

| Layer | Owner | Examples | Where it lives |
| --- | --- | --- | --- |
| **Fixed fields** | the **platform** (Members module base registry) — identical for every tenant | **Personal data** (name, contact, address, birthdate…); **Membership data** (member number, status, join/leave dates, transitions) | Core columns/attributes of the tenant-scoped `members` table |
| **Variable fields** | the **tenant** (per-tenant overlay) | **Club details** — tenant-specific fields (e.g. h-dcn's Motor / region / club-specific attributes) | Per-tenant field config (the `tenant_template_config` / field-registry-overlay mechanism), keyed by `tenant_id`, applied over the fixed core |

- **Fixed = platform base registry.** Personal + membership fields are defined once by the
  Members module and are the same shape for every tenant. Validation, grouping, and the
  canonical field keys come from the base registry.
- **Variable = per-tenant overlay.** A tenant (h-dcn) configures its own additional
  "club details" fields and any per-tenant overrides (labels, required-ness, ordering,
  which fields show in which context) **without changing the platform base**. This is the
  h-dcn hybrid registry + myAdmin's `tenant_template_config` pattern, resolved at runtime
  per `tenant_id`.
- **Tenant = h-dcn** is the first overlay instance: its Motor/region/club-specific fields
  are the variable layer over the fixed personal+membership core.

### Why this matters for the migration

- The new tenant-scoped `members` table carries the **fixed** fields as first-class
  attributes; the **variable** fields are resolved from the per-tenant field config, so
  adding a second tenant later needs **no schema change** — only a new overlay.
- The consolidated Members module reads BOTH layers through one field-resolution path
  (base registry + per-tenant overlay), reusing h-dcn's hybrid-registry design and
  myAdmin's `FieldConfigMixin`/`tenant_template_config` — not a bespoke per-tenant fork.
- Migration step (see `migration-plan.md`): the module's data-model design (Step 1) must
  define the fixed base registry (personal + membership) and wire the per-tenant variable
  overlay from day one, with h-dcn's existing member fields split accordingly (fixed →
  base; club/Motor/region-specific → overlay).

## Reuse vs. replace (what the migration keeps vs. changes)

Grounded in the h-dcn `auth_utils.py` inventory:

| h-dcn piece | Migration disposition |
| --- | --- |
| `extract_user_credentials` (unverified identity/roles, `X-Enhanced-Groups`) | **REPLACE** with myAdmin `sam/shared/auth_utils.py` verified path (`get_verified_claims`/`get_groups`) + `get_entitlements`/`has_capability` (S4) — verify-before-trust, no header trust (ADR 0004) |
| `validate_permissions_with_regions` + regional-access helpers | **REUSE** (h-dcn business policy) — now fed VERIFIED roles/entitlement instead of unverified |
| `cors_headers` / responses / OPTIONS | **REUSE** as-is (pure HTTP plumbing) |
| DynamoDB tables (`MembersTable` etc.) | **NEW tenant-scoped tables** (add `tenant_id` partition key) so migrated Members runs beside the live h-dcn tables (no big-bang) |
| SAM `template.yaml` / **18 Lambda-per-handler** | **REPLACE the structure** — consolidate to **ONE Members module** (single SAM Lambda with internal routing), adopting myAdmin's module tooling (registry entry, `tenant_modules` entitlement, projection read, `LeadingKeys`). The 18-handler sprawl is a learning-curve artifact (h-dcn was the first Kiro/TS/Python/AWS project), not a design to keep. Migrate straight to best practice — no 1:1 port-then-refactor. |

## Open questions for the migration plan (answered there)

- Exactly which tables get a `tenant_id`-keyed twin, and the dual-run/backfill approach.
- How Members registers as a myAdmin module (`MODULE_REGISTRY` entry + `tenant_modules`).
- The consolidated module's internal route map (union of the 18 handlers' behaviours).
- Backend-first: the migration is backend + data; the h-dcn frontend stays until parity.
