# S3 — Tenant/Role Claims + Tenant System-of-Record + Projection to DynamoDB — Design

- Status: Draft
- Companion to `requirements.md` (same folder). Implements R1–R6.
- Decision of record: ADR 0003 + ADR 0004; S3 authors ADR 0005 (as a task).

## Overview

S3 turns identity claims and tenant governance into a settled, testable contract and
gives the SAM/Lambda module plane a **read-only, one-directional** view of the
tenant-level governance facts it needs — without ever querying MySQL at request time.

Three deliverables, one clean deferral:

- **D1 — Pool A claim contract.** Standardize + *validate* the existing admin/staff
  pool's claim shape (`cognito:groups` = global roles; `custom:tenants` = tenant list),
  reusing the S2 issuer→pool registry (config-not-code) to select and interpret Pool A.
  No new verification code.
- **D2 — MySQL system-of-record.** Ratify + harden `tenants` / `tenant_modules` /
  `user_tenant_roles` as authoritative for all tenants — including tenants that will
  later enable SAM-backed modules (h-dcn once its modules land in S5) — and retire the
  dead `tenant_role_allocation` table (confirmed absent everywhere; DDL file removed).
- **D3 — One-directional MySQL→DynamoDB projection.** Build the sync that copies the
  tenant-level governance subset forward into a DynamoDB projection table the module
  plane reads. This is the build-heavy part and the focus of the correctness properties.
- **Deferred — Pool B.** Not built; S3 must not preclude it (the S2 registry already
  makes it config-only later).

This fills the **Data ownership** seam of the S1 module contract
(`s1-prepare-platform/module-contract.md`): "a SAM module never opens a MySQL
connection; tenant-level facts reach it through a read-only, one-directional
MySQL→DynamoDB projection (S3)."

## Architecture

```
                 Cognito (identity account)
        Pool A  eu-west-1_Hdp40eWmu   ── D1: claim contract (groups=global roles,
          │        (admin/staff)          custom:tenants=list); selected by iss
          │                               via the S2 registry (config-not-code)
   verified token (S2 — done)
          │
          ▼
┌───────────────────────────┐        D2: system of record (authoritative)
│ Flask / MySQL (myAdmin)    │  tenants · tenant_modules · user_tenant_roles
│ role_cache.py: per-tenant  │        (tenant_role_allocation RETIRED)
│ roles from user_tenant_    │
│ roles; global from groups  │
└─────────────┬─────────────┘
              │  D3: on-change sync — WRITE-ONLY, versioned, validated
              │  MySQL ──────────────► DynamoDB   (never the reverse)
              ▼
┌───────────────────────────────────────────┐
│ DynamoDB projection table (test_ first)    │  read-only projection
│ PK = tenant key; tenant-level facts only   │
└─────────────┬─────────────────────────────┘
              │  read only (module never writes back)
              ▼
┌───────────────────────────┐
│ SAM / Lambda module plane  │  reads tenant/module/role facts from the projection;
│ (members/events/webshop)   │  NEVER queries MySQL at request time (S1 contract)
└───────────────────────────┘

DEFERRED: Pool B (new clean end-user pool; singular tenant_id claim) — config-only
to add later via the S2 registry; NOT built in S3.
S4 (separate): per-user resolved answer projected into the TOKEN — different data,
different mechanism; must not be conflated with D3.
```

## D1 — Pool A claim contract (identity claims)

**Pool A** is the audience-role label for the Cognito pool **named `myAdmin`**
(`eu-west-1_Hdp40eWmu`, identity account). S3 does not create or move it; S3
standardizes and validates its claim shape and documents it as the platform contract.

**The claim shape (contract):**

| Claim | Carries | Authority |
| --- | --- | --- |
| `cognito:groups` | **GLOBAL roles only** — SysAdmin / Administrators / System_CRUD | the token |
| `custom:tenants` | the user's **list** of tenants (`administration` keys) | the token (mirrors MySQL) |
| *(per-tenant roles)* | **NOT in the token in S3** | MySQL `user_tenant_roles`, read via `role_cache.py` |

- **Pool selection is S2's, unchanged.** Both planes select Pool A by `iss` through the
  issuer→pool registry (`COGNITO_POOL_KEYS` + `{KEY}_COGNITO_*`, fail-fast). S3 adds no
  verification code — it validates that Pool A's claim shape is read correctly through
  the existing path.
- **Per-tenant roles stay in MySQL.** The Flask plane resolves "what may this user do in
  tenant T" from `user_tenant_roles` via `role_cache.py`
  (`SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s`, cached).
  Only global roles ride `cognito:groups`.
- **Entitlement-in-token is S4.** S3 names the dependency and deliberately does **not**
  add a per-tenant role or entitlement claim to the token.
- **Pool-side change is gated.** If S3 needs a pool-side change (e.g. tightening a claim),
  it is validated on the **test pool** (`eu-west-1_xyrlzfqbl`) first, then applied to
  Pool A under a gate (R4). If no change is needed, Pool A is confirmed as-is and that is
  recorded.

**Legacy pool decommission (manual, gated).** `eu-west-1_OAT3oPCIm`,
`eu-west-1_VtKQHhXGN`, `eu-west-1_fcUkvwjH5` are decommissioned only after a
dependency check (application, Railway `.env`, IaC), as a **manual, human-gated** step
with a final backup — mirroring the `migration_plan.md` guardrail. The operation
explicitly excludes Pool A and the test pool.

## D2 — MySQL as the tenant system-of-record

`tenants`, `tenant_modules` (`administration`, `module_name`, `is_active`), and
`user_tenant_roles` (`email`, `administration`, `role`) are ratified as authoritative for
tenant governance across **all** tenants — including tenants entitled to SAM-backed
modules (h-dcn → `members`/`events`/`webshop`), not only finance tenants.

- **Authority does not move to the module plane.** No module owns a writable copy. Module
  needs are met via the token (S4) or the read-only projection (D3) — never a
  request-time MySQL query from a Lambda (S1 contract, R3.3).
- **Retire `tenant_role_allocation`.** Verified: **no readers** anywhere under
  `backend/` (incl. `role_cache.py`); the SysAdmin-Module spec already derives available
  roles from `tenant_modules` + Cognito groups; and the table is **absent in dev**
  (`finance`, `testfinance`) **and prod** — the DDL was never applied. The only artifact,
  the DDL file `backend/sql/create_tenant_role_allocation_table.sql`, has been **removed**.
  There was no physical table or data to drop.

**Data models (system of record — existing, ratified):**

```
tenants(administration PK, …)
tenant_modules(administration, module_name, is_active, …)   -- which modules a tenant enabled
user_tenant_roles(email, administration, role)              -- per-user, per-tenant role grants
```

## D3 — One-directional MySQL→DynamoDB projection (build-heavy)

The projection copies the **tenant-level** governance subset forward into a DynamoDB
table the module plane reads. It is the *tenant-level* companion to S4's *per-user token*
projection — different data, different mechanism, and they must not be conflated.

### Components and interfaces

- **`ProjectionSync`** — the sole writer of the projection table. Reads the relevant
  governance rows from MySQL, transforms them into projection items, validates each item,
  and writes (put/delete) to DynamoDB. Issues **no** MySQL writes.
- **`ProjectionItem` builder** — pure transform: `(tenant, tenant_modules[],
  user_tenant_roles[]) -> ProjectionItem` with a `tenant_id` (partition key) and a
  `version`.
- **`ProjectionValidator`** — pure predicate: an item is valid iff the tenant key is
  present and required fields are well-formed. Invalid → raise, do not write.
- **Change trigger** — invokes `ProjectionSync` on change to the source tables (see
  below). Not a per-request pull.
- **Read side (module plane)** — reads the projection item(s) for its own `tenant_id`
  only (partition key + IAM `LeadingKeys`); uses `version` for staleness/invalidation.
  Never writes.

### What is projected (R5.3)

Only the tenant-level subset for tenants that have SAM-backed modules enabled:

- `tenants` → tenant existence + tenant-level attributes needed by modules.
- `tenant_modules` → which modules the tenant has enabled (`is_active`).
- `user_tenant_roles` → the per-tenant role grants **as tenant-level reference data**
  (the tenant's role assignments), *not* the per-user resolved answer that belongs in the
  token (that is S4). If a fact belongs in the token, it is **not** projected here.

### DynamoDB table shape (tenant-scoped key design, R5.4)

```
Table: {ENV_PREFIX}governance_projection      (test_ prefix in test/dev)
  PK  tenant_id            (== administration)   -- partition key = tenancy boundary
  SK  record_type#id       (e.g. "tenant", "module#members", "role#email#role")
  attrs: is_active, role, tenant fields, …
  version: <source revision / updated-at>        -- monotonic per item
```

- Partition key `tenant_id` makes cross-tenant reads unaddressable (correctness); IAM
  `dynamodb:LeadingKeys` restricts a caller's credentials to its own partition (defense
  in depth) — matching the S1 Scope seam.

### Write-time validation (R5.5)

`ProjectionSync` calls `ProjectionValidator` on every item before writing. A source row
missing its tenant key or a required field causes the sync to **fail loudly** for that
item and **not** write partial/garbage data. No silent partial projection.

### Versioning + idempotence (R5.6)

Each projected write carries a `version` (source revision or `updated_at`). The sync is
**idempotent**: re-running against an unchanged source produces no new writes and no
version churn. A conditional write (only write if incoming `version` > stored `version`)
makes re-delivery safe and ordering-tolerant.

### On-change sync trigger (R5.7)

The sync runs **on change** to the source governance tables, not per request. Mechanism
(design decision, revisit at build): the change is signaled by the Flask-plane write path
that already mutates governance (provisioning / module enable-disable / role grant)
enqueuing a sync for the affected `administration`, so the projection tracks MySQL within
a bounded, documented delay. A periodic reconciliation pass (idempotent by R5.6) backstops
missed signals. The projection is eventually-consistent with MySQL within that bound.

### Cache invalidation on the read side (R5.8)

The read side compares the item `version` it holds against the projection's current
`version`; a newer version invalidates/refreshes the cached read. Staleness is bounded by
the sync delay (R5.7) and the read TTL, and is documented — never unbounded.

### One-directional guardrail (R5.1, R5.2, R5.9) — the load-bearing invariant

- The sync writes **only** the projection table; it issues **zero** MySQL writes.
- Nothing but the sync writes the projection table.
- A module **reads** the projection and **never** writes it or writes back to MySQL.

Two-way writes are forbidden: they are a split-brain / cross-tenant incident waiting to
happen. MySQL remains the sole writer of record.

## Components and Interfaces

Consolidated from the D3 "Components and interfaces" subsection above; these are the
components S3 builds and the interfaces between them:

- **`ProjectionSync`** — the sole writer of the projection table. Reads the relevant
  governance rows from MySQL, transforms them into projection items, validates each item,
  and writes (put/delete) to DynamoDB. Issues **no** MySQL writes.
- **`ProjectionItem` builder** — pure transform:
  `(tenant, tenant_modules[], user_tenant_roles[]) -> ProjectionItem` with a `tenant_id`
  (partition key) and a `version`.
- **`ProjectionValidator`** — pure predicate: an item is valid iff the tenant key is
  present and required fields are well-formed. Invalid → raise, do not write.
- **Change trigger** — invokes `ProjectionSync` on change to the source tables (Flask
  write path enqueues a sync for the affected `administration`; periodic reconciliation
  backstops missed signals). Not a per-request pull.
- **Read side (module plane)** — reads the projection item(s) for its own `tenant_id`
  only (partition key + IAM `LeadingKeys`); uses `version` for staleness/invalidation.
  Never writes.

## Data Models

Consolidated from D2 (system-of-record) and D3 (projection) above.

**MySQL system-of-record (existing, ratified):**

```
tenants(administration PK, …)
tenant_modules(administration, module_name, is_active, …)   -- which modules a tenant enabled
user_tenant_roles(email, administration, role)              -- per-user, per-tenant role grants
```

**DynamoDB projection table (tenant-scoped key design, R5.4):**

```
Table: {ENV_PREFIX}governance_projection      (test_ prefix in test/dev)
  PK  tenant_id            (== administration)   -- partition key = tenancy boundary
  SK  record_type#id       (e.g. "tenant", "module#members", "role#email#role")
  attrs: is_active, role, tenant fields, …
  version: <source revision / updated-at>        -- monotonic per item
```

**`ProjectionItem` shape:** a `tenant_id` (partition key), an `SK` of `record_type#id`,
the projected attributes, and a `version` — produced by the `ProjectionItem` builder from
`(tenant, tenant_modules[], user_tenant_roles[])`.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid
executions of a system — essentially, a formal statement about what the system should do.
Properties serve as the bridge between human-readable specifications and
machine-verifiable correctness guarantees.*

> Scope note: property-based testing applies to the **projection sync's pure logic**
> (D3) — a data transformation with a large, structured input space (tenants × modules ×
> roles). It does **not** apply to D1 (Cognito claim validation → integration tests
> against the test pool), the legacy-pool decommission (manual/IaC), or D2's governance
> ratification (grep + example unit tests). Those are covered in the Testing Strategy.
> The sync's MySQL/DynamoDB I/O is mocked/faked (in-memory tables) so properties test
> logic, not the datastores.

### Property 1: One-directional projection (write-only, no split brain)

*For any* generated governance state and *any* sequence of sync runs, the sync issues
writes **only** to the projection table and **zero** writes to MySQL, and the simulated
module read path issues no writes to either store.

**Validates: Requirements 5.1, 5.2, 5.9**

### Property 2: Projection fidelity (exactly the tenant-level subset)

*For any* generated source state, the set of projected items equals the tenant-level
subset filtered to tenants with SAM-backed modules enabled — nothing extra is projected,
nothing required is missing, and no per-user-token-only data appears in the projection.

**Validates: Requirements 5.3**

### Property 3: Tenant isolation of the projection

*For any* multi-tenant source state, a projection read scoped to tenant `T` returns only
items whose partition key is `T`; no item from another tenant is addressable from `T`'s
scope.

**Validates: Requirements 5.4**

### Property 4: Idempotent, versioned sync

*For any* source state, running the sync twice with the source unchanged leaves the
projection items and their versions identical to the state after the first run (a second
run is a no-op).

**Validates: Requirements 5.6, 5.8**

### Property 5: Write-time validation rejects malformed rows

*For any* source row missing its tenant key or a required field, the sync rejects that
row (raises) and does not write a partial or malformed item; the rest of the projection
is unaffected for a batch, or the batch fails atomically per the design decision.

**Validates: Requirements 5.5**

### Property 6: Convergence after a source change

*For any* change to a projected source fact, after the sync runs a tenant-scoped read of
the projection reflects the changed value (the projection converges to the source).

**Validates: Requirements 5.7, 5.8**

## Error Handling

- **Fail-fast env vars (R4.1).** Missing pool/registry/table env vars throw at startup —
  no default that could silently point identity or projection work at production. Reuses
  the S2 `COGNITO_POOL_KEYS` fail-fast pattern; the projection table name is
  env-resolved with the same discipline (`test_` prefix in test/dev).
- **Verification failures (D1).** Unchanged from S2: any signature/`iss`/`aud`/`exp`
  failure → 401, no fallback.
- **Malformed source row (D3).** The sync raises and does not write; the failure is
  logged (row identity, not secrets) and surfaced. No partial projection.
- **Projection write conflict (D3).** Conditional write on `version`; a stale write is a
  no-op (idempotent), not an error.
- **Decommission guardrail (D1/R2).** The decommission tooling refuses to run against
  Pool A (`eu-west-1_Hdp40eWmu`) or the test pool (`eu-west-1_xyrlzfqbl`) — an assertion,
  not a comment.

## Testing Strategy

**Dual approach.** Unit/integration tests for the non-PBT surface; property-based tests
for the projection sync logic. All identity and projection work is validated against the
**test pool + Docker MySQL + `test_` DynamoDB** first, then gated to production (R4).

**Property-based tests (D3 sync logic).**
- Library: a property-based testing library for the backend's language (Python →
  Hypothesis). Do not hand-roll generators/shrinking.
- Minimum **100 iterations** per property.
- Each property test is tagged: **Feature: s3-claims-and-projection, Property {N}:
  {property text}**.
- Implement **one** property-based test per correctness property (Properties 1–6).
- MySQL source and DynamoDB projection are **faked in-memory** so properties test logic,
  not the datastores; generators produce tenants × modules × roles including edge cases
  (empty tenant, tenant with no modules, missing keys, unicode emails, duplicate roles).

**Integration tests (D1 — Cognito, not PBT).**
- 1–3 examples against the **test pool**: a test-pool token selects the right pool via
  the S2 registry and its `cognito:groups` (global roles) + `custom:tenants` (list) are
  interpreted correctly on both planes. Reuse the S2 verification harness.

**Unit tests (D2 + read side, examples/edge cases).**
- `role_cache.py`: seeded `user_tenant_roles` rows → correct per-tenant role set; global
  roles come from `cognito:groups` (R1.3).
- Read-side staleness: a reader holding version `v` detects `v' > v` and refreshes (R5.8).
- Fail-fast: a missing projection/pool env var throws (no fallback).

**Governance / manual checks (not tests).**
- `tenant_role_allocation` retirement: grep confirms **no readers** before removal (R3.4).
- Legacy-pool decommission: manual dependency checklist + backup; guardrail excludes Pool
  A and the test pool (R2).

**Projection integration smoke (against `test_` DynamoDB).**
- One end-to-end run of the sync against Docker MySQL → `test_` projection table, then a
  tenant-scoped read, to confirm the wiring (not a per-input property).

## Governance delta (R6)

- **Auth/tenant steering** (extend `identity.md` / `architecture.md`, or a scoped
  tenant-data steering file): the **Pool A claim contract** (global roles in
  `cognito:groups`, `custom:tenants` list, per-tenant roles in MySQL); **MySQL as the
  tenant system-of-record**; the **one-directional MySQL→DynamoDB projection** rule
  (write-only, versioned, no split brain, module reads only).
- **ADR 0005** (next after 0004, append-only): "Two-pool (audience-split) identity —
  **Pool A now, Pool B deferred**; MySQL is the tenant system-of-record; one-directional
  MySQL→DynamoDB projection." Records that adding Pool B later is config-only via the S2
  registry.
- Steering + ADR are authored as **tasks** in `tasks.md` (T-Governance phase), not by
  this design.

## Test matrix (drives tasks + acceptance)

| Case | Surface | Expected |
| --- | --- | --- |
| Test-pool token, correct `iss` | D1 (integration) | selected as Pool A; groups=global roles, `custom:tenants`=list read correctly |
| `custom:tenants` list interpreted as tenant list | D1 | tenants read from the list; per-tenant roles NOT taken from the token |
| Per-tenant role lookup | D2 (`role_cache.py`) | role resolved from `user_tenant_roles`, not from `cognito:groups` |
| `tenant_role_allocation` readers | D2 | none — safe to retire |
| Sync run (any source) | D3 Property 1 | writes only the projection table; zero MySQL writes |
| Projected set vs source | D3 Property 2 | equals the filtered tenant-level subset; no token-only data |
| Read scoped to tenant T | D3 Property 3 | only tenant-T items addressable |
| Sync run twice, source unchanged | D3 Property 4 | second run is a no-op; versions unchanged |
| Malformed source row | D3 Property 5 | rejected, no partial write |
| Source fact changed → sync → read | D3 Property 6 | read reflects the change (convergence) |
| Missing pool/table env var | D1/D3 | fail-fast throw; no production fallback |
| Legacy-pool decommission targets Pool A / test pool | D1/R2 | refused by guardrail |
