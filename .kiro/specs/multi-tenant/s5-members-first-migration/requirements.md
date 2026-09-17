# Requirements Document

## S5 — First app migration: Members (h-dcn) → myAdmin platform — Requirements

- Status: Draft
- Roadmap step: S5 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Depends on: **S1** (SAM-backed module contract), **S2** (verified-JWT toolkit,
  `sam/shared`), **S3** (MySQL system-of-record + one-directional DynamoDB projection +
  `tenant_modules`), **S4** (entitlement-handling functions available: resolver, codec,
  `get_entitlements`/`has_capability`; live Pool A trigger deferred here).
- Decision of record: ADR 0003–0006. Governing steering:
  `.kiro/steering/sam-module-architecture.md` (layering), `identity.md`, `architecture.md`,
  `aws-accounts.md`, `database-patterns.md`.
- Design companions (this document formalizes them): `members-wireframe.md`,
  `generic-membership-design.md`, `scope-dimension-design.md`, `migration-plan.md`,
  `go-no-go.md`.

## Introduction

S5 migrates the **Members** app (the first h-dcn app) onto the myAdmin platform as a
**generic membership administration module**, with h-dcn as its **first tenant**. It is
the **pilot** that proves the platform tooling (verified auth + entitlement, module
entitlement, tenant-scoped DynamoDB, fixed/variable fields, layered architecture) and ends
at an explicit **Go/No-Go** gate for further migrations. It is executed in
**independently-deployable steps**; the **live h-dcn app keeps running** on **new
tenant-scoped tables** until a gated pilot cutover.

## Glossary

- **Generic Members module** — one SAM-backed deployable (single Lambda, internal routing)
  owning membership administration common to any club/association.
- **Fixed fields** — platform-owned base registry: personal data + membership data
  (identical for every tenant).
- **Variable fields** — per-tenant overlay ("club details", e.g. h-dcn Motor fields) via
  the field-config / `tenant_template_config` mechanism, keyed by `tenant_id`.
- **Scope dimension** — a tenant-configurable within-tenant partition + role scope
  (h-dcn's "region"); disabled → tenant-wide. See `scope-dimension-design.md`.
- **Generic/tenant-specific ladder** — differences expressed as, in order:
  1) config/data → 2) declarative rules → 3) registered hooks → 4) separate service.
- **Tenant `h-dcn`** — the first tenant/config+data instance of the generic module.
- **Go/No-Go** — the decision gate + lessons-learned after the pilot soak (`go-no-go.md`).

## Guiding principles (settled; requirements below enforce them)

- **Generic core is tenant-agnostic** — no `if tenant == "h-dcn"` in the module core.
- **Best practice from the start** — consolidate h-dcn's ~18 handlers into **one module**;
  no 1:1 port-then-refactor.
- **Layered** — React (presentation) → thin Lambda handler (auth/entitlement/routing) →
  application/domain service (business rules) → repository (DynamoDB); dependencies
  downward only; DynamoDB owns data integrity, not business rules.
- **Additive, parallel-run, reversible** — new tenant-scoped tables; live h-dcn untouched
  until a gated cutover; each step independently deployable and reversible.
- **Test-first + gated** — validate on the test pool + local/`test_` DynamoDB before any
  production/pilot cutover.

## Requirements

### R1 — Generic membership module (consolidated, layered)
- **R1.1** The migrated Members app SHALL be a **single SAM-backed module** (one Lambda
  with internal routing), not a per-action handler set. The auth/entitlement toolkit SHALL
  be adopted **once** at the handler edge.
- **R1.2** The module SHALL follow the layered architecture in
  `sam-module-architecture.md`: a **thin handler** (parse, authenticate, tenant context,
  authorize, route, respond — no business logic, no direct DynamoDB), an
  **application/domain service** (business rules, storage-agnostic, testable), and a
  **repository** as the only DynamoDB touch-point.
- **R1.3** The generic module core SHALL contain **no tenant conditionals**; every h-dcn
  difference SHALL be expressed via the generic/tenant-specific ladder (config → rules →
  hooks → separate service).
- **R1.4** The module SHALL reuse h-dcn's **business logic** (regional access, membership
  workflow, response shapes) and **replace** its structure (18→1) and its unverified auth
  (`extract_user_credentials`) with the verified `sam/shared` toolkit.

### R2 — Fixed vs. variable member data model
- **R2.1** The module SHALL define a **fixed base field registry** (personal data +
  membership data) identical for every tenant, as first-class attributes of the
  tenant-scoped member store.
- **R2.2** The module SHALL support a **per-tenant variable field overlay** ("club
  details") resolved by `tenant_id` (field-config / `tenant_template_config` pattern),
  applied over the fixed core, such that adding a tenant needs **no schema change**.
- **R2.3** The module SHALL expose a **resolved field config** (fixed ⊕ overlay) to a
  presentation-only frontend; the frontend SHALL hold no business rules or data-shape
  authority.

### R3 — Tenant isolation + scope dimension (generalized "region")
- **R3.1** Every member record SHALL be keyed by `tenant_id`; tenant **isolation** SHALL be
  enforced in the repository/data layer (partition key + IAM `dynamodb:LeadingKeys`), so no
  upper layer can cross tenants.
- **R3.2** The module SHALL provide a **tenant-configurable scope dimension** (a list of
  dimensions, each optionally multi-valued) that partitions data within a tenant and scopes
  roles to a subset of values. A tenant MAY **disable** it (→ tenant-wide, no code path
  change).
- **R3.3** `resolve_scope_access(tenant, dimension, user_roles)` SHALL generalize h-dcn's
  `determine_regional_access` (admin/all → `["*"]`; scoped role → subset; a
  scope-requiring capability without a grant → deny). Scope-value **filtering** is a
  **domain-layer** concern (a scoped user remains inside their tenant); h-dcn's region
  functions MAY be reused as the body of a Rung-3 hook.
- **R3.4** h-dcn SHALL be configured as a **single, single-valued "region"** dimension for
  the pilot; the model SHALL NOT hardcode single-value/single-dimension assumptions.

### R4 — h-dcn as the first tenant (config + overlay + data), no fork
- **R4.1** Supporting h-dcn SHALL be achieved by **tenant config + field overlay + data
  backfill** into the new tenant-scoped tables — no generic-code fork.
- **R4.2** h-dcn's membership states/transitions, regions, and roles SHALL be expressed as
  generic config (transition config, scope dimension, `tenant_modules` entitlement).
- **R4.3** Any genuinely bespoke h-dcn behavior that is not config/rules SHALL be a
  **registered hook** keyed by `tenant_id` (e.g. `validate_member`, `on_transition`,
  `resolve_visible_regions`, `derive_member_number`), whose body reuses h-dcn's existing
  logic — **never** a conditional in the generic core.

### R5 — Parallel-run, additive, reversible; new tables; live h-dcn untouched
- **R5.1** The migration SHALL create **new tenant-scoped DynamoDB tables** (data account,
  PAY_PER_REQUEST, managed outside CloudFormation / retain per `aws-accounts.md`); the live
  h-dcn tables SHALL remain **untouched**.
- **R5.2** Backfill of h-dcn member data SHALL be **dry-run first**, non-destructive, and
  leave the live tables as the source of truth until a gated cutover.
- **R5.3** Every step SHALL be **independently deployable and reversible**; at no step is
  the live h-dcn Members app left broken.

### R6 — Verified auth + entitlement adoption (S2/S4 toolkit)
- **R6.1** The module SHALL authorize from the **verified** Cognito token via `sam/shared`
  (`get_verified_claims`/`get_groups` + `get_entitlements`/`has_capability`) — never from
  unverified headers (`X-Enhanced-Groups`), per ADR 0004.
- **R6.2** If the pilot requires live token entitlement, the **Pool A Pre-Token-Generation
  trigger** (S4 T18, deferred) SHALL be wired **cross-account** under a gate, validated on
  the **test pool first**, with detach-to-rollback. Empty projection → empty entitlement is
  a valid, handled outcome.
- **R6.3** For token-carried entitlement to be non-empty for h-dcn, the S3 projection SHALL
  be **widened** to carry the tenant's governance (today gated to SAM-backed tenants) — an
  S3/S5 coordination item; until then the module falls back to its authoritative source and
  the pilot may run auth against the test pool.

### R7 — Test-first, gated pilot cutover
- **R7.1** The module + data model SHALL be validated **first** against the test pool +
  local/`test_` DynamoDB (parity with h-dcn behaviour: authz incl. scope, data, API
  contract, workflow) before any pilot cutover.
- **R7.2** Pilot cutover SHALL be limited to a **single pilot tenant/region**, soaked, and
  **reversible** (route back to live h-dcn).

### R8 — Go/No-Go + lessons learned (definition of done for the pilot)
- **R8.1** After the soak, an explicit **Go/No-Go** decision for further app migrations
  SHALL be recorded in `go-no-go.md`, against: parity, did-the-toolkit-hold, operational
  (deploy/rollback, latency, fail-safe), and effort/ROI.
- **R8.2** The decision SHALL record the **rung distribution** (how much of h-dcn landed on
  config vs. rules vs. hooks vs. escape hatch) and a **design-review verdict** on whether a
  hypothetical second club (teams+season+family+per-type fees) fits the generic model.
- **R8.3** Lessons learned SHALL feed a **roadmap revision** (proceed / conditional /
  no-go); further app migrations (Events, Webshop) are **gated** on a Go.

### R9 — Governance updated on completion
- **R9.1** On completion, steering + an ADR SHALL record the generic membership model, the
  scope-dimension generalization, the fixed/variable field model, and the migration pattern
  (feeds the next-app template). Authored as tasks in `tasks.md`.

## Deployable steps (each independently shippable + reversible)

> These implement `migration-plan.md`. Each step maps to requirements and becomes tasks in
> `tasks.md`. Nothing is cut over until the Step 6 gate.

- **Step 1 — Design + skeleton of the generic Members module** (R1, R2.1, R3.2, R3.3):
  define internal routes (union of the 18 handlers), the layered skeleton, the fixed base
  registry (personal + membership) + per-tenant overlay wiring, the scope-dimension model
  (list, multi-valued-capable; h-dcn = single "region"), and the tenant-scoped table
  design. Deployable as the module skeleton; reversible (remove it).
- **Step 2 — Register Members as a myAdmin module** (R4.2, R6.1): `MODULE_REGISTRY` entry
  (backing sam) + entitle the pilot tenant via `tenant_modules`; confirm projection +
  `has_capability` answer for `members`. Deployable/reversible (config).
- **Step 3 — Module read path on myAdmin tooling** (R1.2, R2.3, R3.1, R3.3, R6.1): the
  single module's READ routes (`get_member*`, lists, export) — verified auth + entitlement
  once, reused regional business logic, tenant-scoped reads (`tenant_id` + `LeadingKeys`),
  resolved field config to the frontend. Pilot/shadow route. Reversible (route only).
- **Step 4 — New tenant-scoped tables + backfill** (R5.1, R5.2): create the new tables;
  dry-run then backfill h-dcn members stamped `tenant_id = h-dcn`; live tables untouched.
  Reversible (new tables are a copy).
- **Step 5 — Module write path + workflow** (R1.4, R3.3, R4.3): create/update/transition/
  delegates/memberships on the tenant-scoped tables + verified auth, reusing h-dcn workflow
  rules via config/rules/hooks. Per-route deployable; h-dcn is the fallback.
- **Step 6 — Pilot cutover for one tenant/region + soak, then Go/No-Go** (R7.2, R8): route
  one pilot tenant/region to the migrated module; soak + parity-compare vs. live h-dcn;
  record the Go/No-Go + lessons. Reversible (route back).
- **Step 7 (conditional, R6.2) — Wire the live Pool A PreTokenGen trigger** if the pilot
  needs live token entitlement: cross-account, test-pool-validated, detach-to-rollback,
  after widening the S3 projection (R6.3).

## Acceptance criteria

- **Generic module:** one consolidated, layered SAM module; toolkit adopted once; no tenant
  conditionals in core; h-dcn business logic reused, structure + auth replaced.
- **Data model:** fixed base registry + per-tenant variable overlay; adding a tenant needs
  no schema change; frontend renders the resolved config only.
- **Isolation + scope:** `tenant_id` + `LeadingKeys` isolation in the repository; a
  tenant-configurable, multi-valued-capable scope dimension; h-dcn "region" expressed as
  config (+ a hook only if a nuance is not declarative); disabling the dimension is a no-op.
- **h-dcn as tenant:** runs as config + overlay + backfill (+ hooks), generic core untouched.
- **Parallel-run:** new tables; live h-dcn never broken; every step reversible.
- **Verified auth:** module authorizes from the verified token/entitlement; no header trust.
- **Gated pilot:** validated on test pool + `test_`/local DynamoDB first; pilot cutover
  limited + reversible.
- **Go/No-Go:** recorded with rung distribution + second-club design verdict; further
  migrations gated on a Go; governance updated.

## Prerequisites (already satisfied / available)

- S1 module contract; S2 verified-JWT toolkit (`sam/shared`); S3 projection +
  `tenant_modules` + `projection_schema` + `LeadingKeys` plan; S4 entitlement functions
  (resolver, codec, `get_entitlements`/`has_capability`) built + tested + available.
- Test Cognito pool (`eu-west-1_xyrlzfqbl`), Docker MySQL, local/`test_` DynamoDB.
