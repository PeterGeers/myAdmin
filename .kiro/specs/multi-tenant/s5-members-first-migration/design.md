# Design Document

## S5 — First app migration: Members (h-dcn) → myAdmin platform — Design

- Status: Draft (design of record for the Members migration pilot)
- Requirements: `requirements.md` (R1–R9, Steps 1–7)
- Consolidates the companion design docs (which remain as detail references):
  `members-wireframe.md` (current-state h-dcn scope + fixed/variable fields + layering),
  `generic-membership-design.md` (generic core + generic/tenant-specific ladder),
  `scope-dimension-design.md` (region → scope dimension), `migration-plan.md` (the steps),
  `go-no-go.md` (the gate).
- Governing steering: `.kiro/steering/sam-module-architecture.md` (layering + handler=adapter),
  `identity.md`, `architecture.md`, `aws-accounts.md`, `database-patterns.md`.
- ADRs: 0003 (platform base + SAM-backed modules), 0004 (verified-JWT-only), 0005 (two-pool
  identity + MySQL SoR + projection), 0006 (entitlement-in-token; functions available).

## Overview

S5 migrates the h-dcn **Members** app onto the myAdmin platform as **one generic,
tenant-agnostic membership module** with **h-dcn as its first tenant**. It is a **pilot**:
built alongside the existing h-dcn app on **new tenant-scoped tables**, exercised for a
single pilot tenant/region under a gate (hands-on, not a production soak — h-dcn is
demo-only, real data in a Google Sheet), and it ends at an explicit **Go/No-Go**.

The design rests on four pillars, each traced to requirements:

1. **One consolidated, layered module** (R1) — replaces h-dcn's ~18 per-action Lambdas with
   a single SAM Lambda that routes internally; four layers, dependencies downward only.
2. **Generic core + generic/tenant-specific ladder** (R1.3, R3, R4) — no tenant conditionals
   in core; differences land on config → declarative rules → registered hooks → separate
   service, and the pilot measures the distribution.
3. **Fixed/variable data model + tenant isolation + scope dimension** (R2, R3) — a
   platform-fixed base registry plus a per-tenant overlay, all keyed by `tenant_id`, with a
   tenant-configurable scope dimension generalizing h-dcn's "region", and the
   **Lidmaatschap Beheer** membership-type catalog backing `membership_type` (C8).
4. **Additive parallel-run + verified auth + gated hands-on validation + Go/No-Go**
   (R5, R6, R7, R8) — new tables, live h-dcn untouched, verified-token authorization,
   test-first, reversible. h-dcn Members is **demo-only** (real data in a Google Sheet), so
   Step 6 is a hands-on walkthrough (how it works + look & feel), **not** a production soak.

## Architecture

### Layered module (the non-negotiable shape — R1.2, per steering)

```
Frontend (React)              presentation only — renders the resolved field config,
      │  (HTTP; never DynamoDB)   calls the API; holds NO business rules, NO data-shape authority
      ▼
Handler layer (thin)          the HTTP edge of the single Members Lambda:
      │                       internal ROUTING + request parse + verified AUTH (sam/shared)
      │                       + ENTITLEMENT/authz gate (has_capability + scope access)
      │                       + CORS + response shaping. NO business logic, NO DynamoDB.
      ▼
Application / domain layer    the generic membership ENGINE: lifecycle state machine,
      │                       declarative-rule evaluation, field resolution (fixed ⊕ overlay),
      │                       scope-access resolution, and CALLS registered tenant hooks.
      │                       Storage-agnostic + testable; builds NO HTTP, writes NO queries.
      ▼
Repository layer (DynamoDB)   the ONLY DynamoDB touch-point: table shape, keys
                              (tenant_id PK + LeadingKeys), queries, conditional writes.
                              TENANT ISOLATION enforced here (every query keyed by tenant_id).
```

Rule: Frontend → Handler → Domain → Repository, downward only, nothing skips a layer. Only
the domain layer is app-specific; the handler edge (verified auth + entitlement) and the
repository (tenant-scoped DynamoDB) are the reusable platform seams — which is exactly what
the Go/No-Go pilot proves for Events/Webshop.

### Parallel-run topology (R5)

```
                      existing h-dcn Members (18 Lambdas)  ──►  h-dcn tables (untouched)
                            ▲  (demo app; kept running in parallel — reference, not live SoR)
   pilot/shadow route ──►  migrated Members module (1 Lambda)  ──►  NEW tenant-scoped tables
                                                                     (tenant_id = "h-dcn")
```

The migrated module runs beside the existing demo app. Routing the pilot tenant/region to
it is a single change limited to that tenant/region and reverts by routing back. (Real
member data is a Google Sheet, so neither app is the live system of record.)

### Where the platform tooling plugs in

- **Handler edge:** `sam/shared/auth_utils.py` (`get_verified_claims`/`get_groups` +
  `get_entitlements`/`has_capability`) and `sam/shared/entitlement_claim.py` (S2 + S4),
  adopted **once**.
- **Entitlement:** `services/module_registry.py` `MODULE_REGISTRY` + `tenant_modules` +
  the S3 one-directional projection (S1/S3).
- **Repository:** `tenant_id` partition + IAM `LeadingKeys` (S3 plan; `database-patterns.md`).
- **Live token entitlement (conditional):** S4 PreTokenGen Lambda + resolver/codec (built +
  tested; trigger wiring deferred to Step 7).

## Components and Interfaces

### C1 — Members module (single SAM Lambda, internal routing) — R1.1
Internal routes = the union of h-dcn's ~18 handler behaviours, grouped:
- **Member CRUD:** create, get-by-id, get-self, list, list-filtered, update, delete, export.
- **Membership lifecycle:** create/get/list/update/delete membership, transition,
  bulk-transition.
- **Delegates:** manage delegates, send delegate invitation.
- **Payments (member-scoped):** get member payments.

The handler for every route follows: `parse → authenticate (verified) → tenant context →
authorize (has_capability + scope) → delegate to domain service → to_http_response`.

### C2 — Membership domain service (the generic engine) — R1.2, R1.3
- `MembershipService` — storage-agnostic, tenant-agnostic. Owns the lifecycle state machine,
  runs declarative rules, resolves fields, and invokes tenant hooks. Never references a
  concrete tenant.
- **Lifecycle state machine:** states + allowed transitions come from tenant **config**
  (e.g. application → pending → active → suspended → lapsed); guards are declarative rules;
  side-effects go through the `on_transition` hook.

### C3 — Field resolution (fixed ⊕ variable) — R2
- `FieldResolver.resolve(tenant_id) -> FieldConfig` = fixed base registry ⊕ per-tenant
  overlay (`tenant_template_config` / `FieldConfigMixin` pattern + h-dcn hybrid registry).
- Exposes a **resolved field config** endpoint the React frontend renders (R2.3); the
  frontend holds no rules.

### C4 — Scope access resolution (generalized region) — R3.3
```
resolve_scope_access(tenant, dimension, user_roles) -> {
  full_access: bool,
  allowed_scopes: [values] | ["*"],
  access_type: "admin" | "all" | "scoped" | "none"
}
```
- admin/all-wildcard → `["*"]`; scoped role → subset; `required_for` capability without a
  grant → `none`/deny; dimension disabled → `["*"]`.
- **Filtering is domain-layer** (a scoped user stays inside their tenant). The repository is
  asked for the tenant's records; the domain narrows by `allowed_scopes` (or pushes the
  filter into the query where the key design allows).
- h-dcn's `determine_regional_access` / `validate_permissions_with_regions` are **reused as
  the body of a Rung-3 hook** if a nuance is not fully declarative.

### C5 — Tenant hook registry (Rung 3) — R4.3
Named extension points the generic core calls, resolved by `tenant_id`:
`validate_member`, `on_transition`, `resolve_visible_regions`, `derive_member_number`
(+ `calculate_fee` for future clubs). h-dcn implementations live in a **tenant-scoped
package** registered for `h-dcn`; **never** a conditional in core. Unregistered hook → a
safe generic default (no-op / pass).

### C6 — Members repository — R3.1
- Only DynamoDB touch-point. Every method takes `tenant_id`; every query is keyed by it.
- `get_member(tenant, id)`, `list_members(tenant, filter)`, `save_member(tenant, record)`,
  counters, member-payments. Uniqueness invariants (member number per tenant) enforced by
  **conditional writes**, not by the domain layer.

### C7 — Module registration + entitlement — R4.2, R6.1
- `members` entry in `MODULE_REGISTRY` (backing: sam); entitle the pilot tenant via
  `tenant_modules`; confirm the S3 projection carries the tenant's `members` module + roles
  and that `has_capability("members", ...)` answers correctly.

### C8 — Membership-type catalog (Lidmaatschap Beheer) — R2.4
A **new coupling** (not in h-dcn today, whose type vocabulary is hardcoded): a tenant-scoped
managed catalog that is the authoritative source of the `membership_type` enum.
- **Entity** (fixed-domain, tenant-scoped): `membership_type` catalog entries keyed by
  `tenant_id`, each `{ code, label (i18n nl/en), active, order }`. Stored in the tenant-scoped
  data layer (`tenant_id` PK + `LeadingKeys`) via the repository (C6) — the only DynamoDB
  touch-point.
- **Reference from the member record:** `membership.membership_type` holds a catalog `code`.
- **Authoritative validation (domain layer):** on member create/update, `MembershipService`
  (C2) validates that `membership_type` references a **live** (`active`) catalog entry for
  the tenant. React's dropdown is convenience only (per steering — never trust the frontend).
- **Dropdown options:** the active catalog entries are surfaced through the resolved
  field-config / catalog read endpoint (C3) so the frontend renders a dropdown listing
  **only** that tenant's active types — no free text, no hardcoded vocabulary.
- **Referential integrity:** retiring a type is a **soft-delete** (`active=false`) — existing
  members keep their value; the type disappears from the dropdown for new/edited members
  (no hard delete → no orphaned historical records).
- **Generic, not h-dcn-specific:** empty-by-default and tenant-owned; h-dcn seeds its own
  types (Erelid/Donateur/Sponsor/…) as **data** (Rung 1). No `if tenant == "h-dcn"`.

## Data Models

### Member record (tenant-scoped) — R2, R3
```jsonc
{
  "tenant_id": "h-dcn",            // PK — hard isolation boundary (LeadingKeys)
  "member_id": "…",               // SK
  // ── fixed base registry (platform-owned, identical every tenant) ──
  "personal":   { "name": "…", "contact": "…", "address": "…", "birthdate": "…" },
  "membership": { "member_number": "…", "status": "active",
                  "membership_type": "erelid",   // → references a Lidmaatschap Beheer catalog code (C8)
                  "joined": "…", "left": null },
  // ── scope (platform-fixed field, tenant values) ──
  "scope_values": { "region": ["Noord"] },   // h-dcn: single-valued region
  // ── variable overlay (per-tenant "club details"; values resolved from field config) ──
  "overlay": { "…tenant-specific fields (e.g. h-dcn Motor)…": "…" }
}
```
- **Fixed** = first-class attributes (same shape for every tenant).
- **Variable** = resolved from the per-tenant field config → adding a tenant needs **no
  schema change** (R2.2).

### Membership-type catalog — Lidmaatschap Beheer (tenant-scoped) — R2.4 (C8)
```jsonc
{
  "tenant_id": "h-dcn",           // PK — isolation boundary (LeadingKeys)
  "type_code": "erelid",          // SK — referenced by member.membership.membership_type
  "label":  { "nl": "Erelid", "en": "Honorary member" },
  "active": true,                 // soft-delete: false → hidden from dropdown, existing members kept
  "order":  10
}
```
- The member's `membership_type` **references** `type_code`; the member-type input is a
  **dropdown of active entries only** for the tenant. Domain layer validates the reference
  authoritatively (C8). h-dcn seeds its types as data (Rung 1) — no code, no `if tenant`.

### Scope dimension config (tenant config) — R3.2, R3.4
```jsonc
scope_dimensions: [                         // a LIST (multi-dimension capable)
  { "key": "region", "label": "Regio", "enabled": true,
    "multi_valued": false,                  // h-dcn: single-valued
    "values": ["Noord","Zuid","Oost","West"],
    "all_wildcard": "Regio_All",
    "required_for": ["Members_CRUD"] }
]
```
- `enabled:false` / no dimension → collapses to tenant-wide (`["*"]`), no code path differs.
- Shape supports `multi_valued:true` and >1 dimension from day one (soccer/hockey teams +
  season) — but h-dcn is wired as the single simple case (no over-build).

### Tenant config (behavior by data, not code) — R4.2
Allowed statuses + transition graph, required/visible fields per context, member-number
format, scope dimension(s), approval-required flags, entitlement via `tenant_modules`.

### New tenant-scoped tables — R5.1
Data account, PAY_PER_REQUEST, managed outside CloudFormation / retain (per
`aws-accounts.md`). `members` (PK `tenant_id`, SK member/membership id), counters,
member-payments as needed. Live h-dcn `MembersTable`/`CountersTable`/`PaymentsTable`
untouched.

## The generic/tenant-specific ladder (governs every difference) — R1.3, R3, R4

| Rung | Mechanism | h-dcn example |
| --- | --- | --- |
| 1 — Config/data (preferred) | tenant config + field overlay values | which fields/statuses, region on, formats |
| 2 — Declarative rules | rule schema the engine interprets | "field X required when status Y"; transition guards; region visibility |
| 3 — Registered hooks | named extension point, impl keyed by tenant | h-dcn regional-access nuance, Motor validation, member-number derivation |
| 4 — Separate service (last resort) | carve-out + **record as Go/No-Go lesson** | (none expected for the pilot) |

Discipline: always try to move a difference **up** (hook → rule → config). The pilot
**counts** the distribution — direct evidence for the Go/No-Go (R8.2).

## Correctness Properties

Properties the design must uphold (each traceable to a requirement); the testing strategy
exercises them:

### Property 1: Tenant isolation is structural (R3.1)
No layer above the repository can read or write another tenant's data: every query is keyed by `tenant_id` (PK) and IAM `LeadingKeys` enforces it, so a bug in the domain layer cannot cross tenants.
### Property 2: Verify-before-trust (R6.1)
Authorization derives only from verified claims/entitlement; no decision is ever made from unverified headers (`X-Enhanced-Groups`).
### Property 3: Fail-safe entitlement (R6.2)
An empty projection yields empty entitlement — a valid, handled outcome that neither crashes nor grants access by default.
### Property 4: Scope deny is the default (R3.3)
A `required_for` capability held without a scope grant resolves to deny (`none`), never to tenant-wide access.
### Property 5: Generic core stays tenant-agnostic (R1.3)
No `if tenant == ...` in core; every difference is config/rule/hook, so adding a tenant is additive.
### Property 6: Uniqueness under concurrency (data integrity)
Member-number uniqueness per tenant holds even with concurrent writers, enforced by DynamoDB conditional writes.
### Property 7: Reversibility (R5.3, R7.2)
At every step the existing h-dcn demo app keeps running in parallel as a behavioural reference; each step reverts (route back / drop new tables) with no data loss.

## Error Handling

- **Tenant isolation (structural):** `tenant_id` PK + IAM `LeadingKeys` in the repository —
  layers above cannot cross tenants even with a bug (R3.1).
- **Verify-before-trust:** authorization only from verified claims/entitlement; unverified
  headers (`X-Enhanced-Groups`) are never trusted (R6.1, ADR 0004).
- **Fail-safe entitlement:** empty projection → empty entitlement is a **valid handled
  outcome** (no crash, no accidental grant); missing hook → safe generic default (R6.2).
- **Scope deny:** a `required_for` capability without a scope grant → deny, not tenant-wide
  access (R3.3).
- **Data invariants:** uniqueness (member number per tenant) via DynamoDB **conditional
  writes**; the domain layer never assumes it holds the only writer.
- **Parity + reversibility:** the existing h-dcn demo app keeps running in parallel as a
  behavioural reference (real data is a Google Sheet, so neither app is the live SoR); every
  step reverts (route back / drop new tables) (R5.3, R7.2).
- **Authoritative validation in Lambda:** React validation is convenience only; the domain
  layer is the authority (per steering).

## Testing Strategy

- **Domain unit tests:** lifecycle transitions, declarative-rule evaluation, field
  resolution (fixed ⊕ overlay), `resolve_scope_access` (admin/all/scoped/none, disabled,
  multi-valued), hook dispatch + default. Storage-agnostic, fast.
- **Repository tests:** tenant isolation (no cross-tenant read/write), conditional-write
  invariants, `LeadingKeys` — against local/`test_` DynamoDB.
- **Handler/contract tests:** verified-auth gate, entitlement gate, route parity with the
  h-dcn API contract; run against the **test pool** (`eu-west-1_xyrlzfqbl`) first (R7.1).
- **Backfill dry-run:** fidelity check vs. live h-dcn data before any real backfill (R5.2).
- **Hands-on validation (Step 6):** exercise the migrated module for one pilot
  tenant/region — authz incl. scope, data, API contract, workflow, and look & feel/UX.
  **Not** a production soak against live traffic (h-dcn is demo-only; real data in a Google
  Sheet) — parity is confirmed by walkthrough, not live-traffic comparison (R7.2 → feeds R8).

## Mapping: Steps → Requirements → Components

| Step (migration-plan / requirements) | Requirements | Components |
| --- | --- | --- |
| 1 — Design + module skeleton + data model | R1, R2.1, R2.4, R3.2, R3.3 | C1 skeleton, C2, C3, C4, C6, C8, data models |
| 2 — Register Members as a module | R4.2, R6.1 | C7 |
| 3 — Read path on myAdmin tooling | R1.2, R2.3, R2.4, R3.1, R3.3, R6.1 | C1 read routes, C2, C3, C4, C6, C8 |
| 4 — New tenant-scoped tables + backfill | R5.1, R5.2 | C6, data models, backfill dry-run |
| 5 — Write path + workflow | R1.4, R2.4, R3.3, R4.3 | C1 write routes, C2, C5, C6, C8 |
| 6 — Exercise module (workflow + look & feel) → Go/No-Go | R7.2, R8 | routing, parity/walkthrough harness, `go-no-go.md` |
| 7 — (conditional) live Pool A trigger | R6.2, R6.3 | S4 PreTokenGen + projection widening |
| 8 — Governance update on completion | R9.1 | steering + ADR (incl. C8 catalog coupling) |

## Deferred (explicit)

- **AWS-footprint consolidation** (S3/SNS/SES/local-DynamoDB → shared portal) — after this
  pilot proves the pattern.
- **Live Pool A PreTokenGen trigger** (S4 T18) — only if the pilot needs live token
  entitlement (Step 7); functions already built + tested; test-pool-validated first.
- **Events / Webshop** migrations — gated on a Go.
- **Frontend consolidation** — backend-first; h-dcn UI stays until parity.
