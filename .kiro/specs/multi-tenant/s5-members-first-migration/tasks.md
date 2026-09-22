# Implementation Plan

## S5 — First app migration: Members (h-dcn) → myAdmin platform — Tasks
- Please relevant steering files in .kiro\steering
- Status: Draft
- Implements: `requirements.md` (R1–R9), `design.md` (C1–C7 + data models),
  `migration-plan.md` (Steps 1–7). Companion detail: `members-wireframe.md`,
  `generic-membership-design.md`, `scope-dimension-design.md`, `go-no-go.md`.
- Governing steering: `.kiro/steering/sam-module-architecture.md` (handler=thin adapter;
  logic in domain services; DynamoDB=integrity), `identity.md`, `aws-accounts.md`,
  `database-patterns.md`.

## Overview

Every numbered item below is a **leaf work item** (no task carries children with its own
body), so the scheduler queues and tracks each unit of work explicitly. Tasks are grouped
by deployable step; each step is independently deployable and reversible, and the live
h-dcn app stays the working fallback until the Step 6 gate. Execute top-down. The `X.0`
item in a step is that step's foundational scaffold and runs first. Each task cites the
requirements (`_Requirements:_`) it satisfies. Only coding/implementation activities are
listed (no manual-only ops).

## Tasks

### Step 1 — Design + skeleton of the generic Members module

- [x] 1.0 Scaffold the single Members module (one SAM Lambda, internal routing)
  - Create the SAM-backed module skeleton: one Lambda, an internal router keyed by
    method/path, and the four-layer package layout (handler / domain / repository) with
    dependencies pointing downward only.
  - Define the internal route map as the union of h-dcn's ~18 handler behaviours
    (member CRUD, membership lifecycle, delegates, member payments) — stubs only at this
    step.
  - _Requirements: R1.1, R1.2_

- [x] 1.1 Define the fixed base field registry (personal + membership)
  - Encode the platform-owned fixed fields (personal data; membership data incl. member
    number, status, join/leave dates) as first-class attributes of the member record,
    identical for every tenant, with canonical keys + validation.
  - _Requirements: R2.1_

- [x] 1.2 Wire the per-tenant variable field overlay
  - Implement `FieldResolver.resolve(tenant_id) -> FieldConfig` = fixed base + per-tenant
    overlay, using the `FieldConfigMixin` / `tenant_template_config` pattern; ensure adding
    a tenant needs no schema change.
  - _Requirements: R2.2, R2.3 (C3)_

- [x] 1.3 Define the scope-dimension model (multi-valued-capable; h-dcn = single "region")
  - Model `scope_dimensions` as a **list**, each with `enabled` / `multi_valued` /
    `values` / `all_wildcard` / `required_for`. Wire h-dcn as a single, single-valued
    `region` dimension; `enabled:false` collapses to tenant-wide.
  - _Requirements: R3.2, R3.3, R3.4 (C4)_

- [x] 1.4 Define the tenant-scoped table design + repository interface
  - Specify the `members` table (PK `tenant_id`, SK member/membership id), counters, and
    member-payments; define the repository interface (`get_member`, `list_members(tenant)`,
    `save_member`, counters) as the sole DynamoDB touch-point.
  - _Requirements: R3.1 (C6), R1.2_

- [x] 1.5 Define the Lidmaatschap Beheer (membership-type) catalog entity
  - Model the tenant-scoped membership-type catalog as a fixed-domain entity
    (`tenant_id` PK; entries carry `code`, `label` i18n nl/en, `active`, order). Add
    `membership_type` to the member record as a **reference** to a catalog entry.
  - Define catalog repository methods (list/get/save, soft-delete via `active=false`).
  - _Requirements: R2.1, R2.4 (Lidmaatschap Beheer — see `generic-membership-design.md`)_

### Step 2 — Register Members as a myAdmin module (entitlement plumbing)

- [x] 2.0 Add the `members` entry to `MODULE_REGISTRY` (backing: sam)
  - Register the module + its capabilities/roles in `services/module_registry.py`.
  - _Requirements: R4.2, R6.1 (C7)_

- [x] 2.1 Entitle the pilot tenant and confirm the projection answers
  - Entitle `h-dcn` via `tenant_modules`; verify the S3 projection carries the tenant's
    `members` module + roles and that `has_capability("members", ...)` resolves correctly.
  - _Requirements: R4.2, R6.1 (C7)_

### Step 3 — Module read path on myAdmin tooling

- [x] 3.0 Adopt the verified-auth + entitlement toolkit once at the handler edge
  - Wire `sam/shared/auth_utils.py` (`get_verified_claims`/`get_groups` +
    `get_entitlements`/`has_capability`) and `entitlement_claim.py` into the thin handler:
    parse -> authenticate (verified) -> tenant context -> authorize -> route. No header trust.
  - _Requirements: R1.1, R6.1 (Property 2)_

- [x] 3.1 Implement `resolve_scope_access` in the domain layer
  - Generalize h-dcn's `determine_regional_access`: admin/all -> `["*"]`; scoped role ->
    subset; `required_for` capability without a grant -> deny (`none`); disabled -> `["*"]`.
    Reuse h-dcn's region functions as the body of a Rung-3 hook only where not declarative.
  - _Requirements: R3.3 (C4, Property 4)_

- [x] 3.2 Implement the READ routes on tenant-scoped reads
  - Build `get_member*`, list, list-filtered, export in the domain service + repository,
    keyed by `tenant_id`; apply scope filtering by `allowed_scopes`. Preserve the h-dcn API
    contract.
  - _Requirements: R1.2, R3.1 (C1 read, C2, C6, Property 1)_

- [x] 3.3 Expose the resolved field config endpoint (incl. membership-type options)
  - Serve the resolved field config (fixed + overlay) to the presentation-only frontend;
    include the tenant's **active Lidmaatschap Beheer catalog entries** as the
    `membership_type` dropdown options. Frontend holds no rules.
  - _Requirements: R2.3, R2.4 (C3)_

- [x] 3.4 Add the Lidmaatschap Beheer catalog READ routes
  - List/get membership-type catalog entries for the current tenant (active + all), keyed
    by `tenant_id`, behind the same verified-auth + entitlement gate.
  - _Requirements: R2.4, R6.1_

### Step 4 — New tenant-scoped tables + backfill (parallel to h-dcn)

- [x] 4.0 Provision the new tenant-scoped DynamoDB tables
  - Create `members` + counters + member-payments (data account, PAY_PER_REQUEST, managed
    outside CloudFormation / retain per `aws-accounts.md`), with `tenant_id` PK + IAM
    `LeadingKeys`. Live h-dcn tables untouched.
  - _Requirements: R5.1 (C6, Property 1)_

- [x] 4.1 Implement the h-dcn backfill (dry-run first)
  - Port the `migrationHDCNLedenbestand` import: map h-dcn member fields -> fixed base +
    variable overlay, stamp `tenant_id = "h-dcn"`, seed `scope_values.region`. Run
    **dry-run first** (fidelity check vs. live h-dcn), non-destructive.
  - _Requirements: R5.2 (Property 7)_

- [x] 4.2 Seed the h-dcn Lidmaatschap Beheer catalog
  - Seed h-dcn's membership types (Erelid/Donateur/Sponsor/...) as catalog **data** for
    tenant `h-dcn`; reconcile backfilled members' `membership_type` against seeded entries.
  - _Requirements: R2.4, R4.1 (Rung 1 — config/data)_

### Step 5 — Module write path + workflow

- [x] 5.0 Implement the lifecycle state machine + declarative rules (domain)
  - Build `MembershipService` states/transitions from tenant **config**; evaluate
    declarative guards; run side-effects via the `on_transition` hook. Tenant-agnostic core.
  - _Requirements: R1.4, R4.2 (C2, Property 5)_

- [x] 5.1 Implement the tenant hook registry (Rung 3)
  - Define named extension points (`validate_member`, `on_transition`,
    `resolve_visible_regions`, `derive_member_number`) resolved by `tenant_id`; register
    h-dcn implementations in a tenant-scoped package. Unregistered hook -> safe default.
  - _Requirements: R4.3 (C5, Property 5)_

- [x] 5.2 Implement the WRITE routes (create/update/transition/delegates/memberships)
  - Build the write routes on the tenant-scoped tables + verified auth, reusing h-dcn's
    workflow rules via config/rules/hooks. Enforce member-number uniqueness per tenant with
    DynamoDB **conditional writes**.
  - _Requirements: R1.4, R3.3 (C1 write, C2, C5, C6, Property 6)_

- [x] 5.3 Add the Lidmaatschap Beheer catalog WRITE routes + reference validation
  - CRUD for catalog entries (create/update/soft-delete via `active=false`). On member
    create/update, the domain layer **authoritatively validates** that `membership_type`
    references a live catalog entry for the tenant (React dropdown is convenience only).
  - _Requirements: R2.4, R1.4 (Referential integrity — `generic-membership-design.md`)_

### Step 6 — Exercise the migrated module (workflow + look & feel), then Go/No-Go

> h-dcn Members is **demo-only** (real data in a Google Sheet) — this is a hands-on
> walkthrough, **not** a production soak against live traffic.

- [x] 6.0 Build the parity/walkthrough harness (migrated vs. existing h-dcn behaviour)
  - Compare authz (incl. scope), data, API contract, and workflow between the migrated
    module and the existing h-dcn app for the pilot tenant/region, via hands-on exercise
    (not a live-traffic soak).
  - _Requirements: R7.1, R7.2_

- [x] 6.1 Wire the reversible pilot route (single tenant/region)
  - Route one pilot tenant/region to the migrated module; ensure route-back is a single
    reversible change.
  - _Requirements: R7.2 (Property 7)_

- [x] 6.2 Record the Go/No-Go + lessons learned
  - Capture parity, did-the-toolkit-hold, look & feel/UX, operational (deploy/rollback,
    fail-safe), and effort/ROI into `go-no-go.md`; record the **rung distribution** and the
    **second-club design verdict** (teams + season + family + per-type fees).
  - _Requirements: R8.1, R8.2, R8.3_

### Step 7 — (Conditional) wire the live Pool A PreTokenGen trigger

> Only if the pilot needs **live-token entitlement**. Otherwise the module uses its
> authoritative fallback and the pilot runs auth against the test pool. Highest blast
> radius (production login) — done last, gated, test-pool-validated, detach-to-rollback.

- [ ] 7.0 Widen the S3 projection to carry h-dcn governance (prerequisite)
  - Extend the projection (today gated to SAM-backed tenants) so h-dcn's governance is
    carried; empty projection -> empty entitlement remains a valid handled outcome.
  - _Requirements: R6.3 (Property 3)_

- [ ] 7.1 Wire the cross-account Pool A PreTokenGen trigger (gated, reversible)
  - Attach the built + tested PreTokenGen Lambda cross-account to live Pool A; validate on
    the **test pool first**; ensure detach-to-rollback and no broken logins.
  - _Requirements: R6.2 (Property 3)_

### Step 8 — Governance update on completion

- [ ] 8.0 Record the migration pattern in steering + an ADR
  - Document the generic membership model, the scope-dimension generalization, the
    fixed/variable field model, the Lidmaatschap Beheer catalog coupling, and the
    next-app migration template.
  - _Requirements: R9.1_

## Task Dependency Graph

Execution is strictly sequential and top-down: within a step the `X.0` scaffold precedes
its siblings, and each step depends on the prior step completing (parallel-run, additive,
reversible). Each wave below is a single task.

```json
{
  "waves": [
    { "wave": 1,  "tasks": ["1.0"], "dependsOn": [] },
    { "wave": 2,  "tasks": ["1.1"], "dependsOn": ["1.0"] },
    { "wave": 3,  "tasks": ["1.2"], "dependsOn": ["1.1"] },
    { "wave": 4,  "tasks": ["1.3"], "dependsOn": ["1.2"] },
    { "wave": 5,  "tasks": ["1.4"], "dependsOn": ["1.3"] },
    { "wave": 6,  "tasks": ["1.5"], "dependsOn": ["1.4"] },
    { "wave": 7,  "tasks": ["2.0"], "dependsOn": ["1.5"] },
    { "wave": 8,  "tasks": ["2.1"], "dependsOn": ["2.0"] },
    { "wave": 9,  "tasks": ["3.0"], "dependsOn": ["2.1"] },
    { "wave": 10, "tasks": ["3.1"], "dependsOn": ["3.0"] },
    { "wave": 11, "tasks": ["3.2"], "dependsOn": ["3.1"] },
    { "wave": 12, "tasks": ["3.3"], "dependsOn": ["3.2"] },
    { "wave": 13, "tasks": ["3.4"], "dependsOn": ["3.3"] },
    { "wave": 14, "tasks": ["4.0"], "dependsOn": ["3.4"] },
    { "wave": 15, "tasks": ["4.1"], "dependsOn": ["4.0"] },
    { "wave": 16, "tasks": ["4.2"], "dependsOn": ["4.1"] },
    { "wave": 17, "tasks": ["5.0"], "dependsOn": ["4.2"] },
    { "wave": 18, "tasks": ["5.1"], "dependsOn": ["5.0"] },
    { "wave": 19, "tasks": ["5.2"], "dependsOn": ["5.1"] },
    { "wave": 20, "tasks": ["5.3"], "dependsOn": ["5.2"] },
    { "wave": 21, "tasks": ["6.0"], "dependsOn": ["5.3"] },
    { "wave": 22, "tasks": ["6.1"], "dependsOn": ["6.0"] },
    { "wave": 23, "tasks": ["6.2"], "dependsOn": ["6.1"] },
    { "wave": 24, "tasks": ["7.0"], "dependsOn": ["6.2"] },
    { "wave": 25, "tasks": ["7.1"], "dependsOn": ["7.0"] },
    { "wave": 26, "tasks": ["8.0"], "dependsOn": ["7.1"] }
  ]
}
```

- **1.0** scaffolds the module + route map that **1.1–1.5** populate.
- **Step 2** (module registration) depends on the Step 1 skeleton.
- **3.0** (auth toolkit at the handler edge) precedes the read routes **3.1–3.4**.
- **4.0** (tables) precedes backfill/seed **4.1–4.2**.
- **5.0** (lifecycle engine) precedes hooks + write routes **5.1–5.3**.
- **6.0–6.2** exercise the module and record the Go/No-Go gate.
- **Step 7** is conditional (live Pool A trigger) and gated; **8.0** records governance.

## Notes

- Every numbered item is a **leaf work item** — no task carries children with its own body,
  so the scheduler queues and tracks each unit of work explicitly.
- Steps are independently deployable and reversible; the live h-dcn app stays the working
  fallback until the Step 6 gate.
