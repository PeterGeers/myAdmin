# Requirements Document

## S3 — Tenant/Role Claims + Tenant System-of-Record + Projection to DynamoDB — Requirements

- Status: Draft
- Roadmap step: S3 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Depends on: S2 (`s2-jwt-verification/` — verify-before-trust on both planes, **done**:
  the issuer→pool registry is already config-not-code (`COGNITO_POOL_KEYS`), JWKS is
  cached with rotation handling, and the module-plane verifier ships as `sam/`) **and**
  the standing test Cognito pool (`eu-west-1_xyrlzfqbl`, **done** — permanent test/dev
  fixture mirroring Pool A). S3 also settles the Pool A decision that
  `migration_plan.md` Gate 1 needs (Pool A confirmed = the admin pool; Pool B decision
  deferred).
- Decision of record: ADR 0003 (myAdmin is the platform base; import apps as SAM-backed
  modules) + ADR 0004 (verified-JWT-only; per-issuer JWKS). S3 authors the **next** ADR
  (**ADR 0005**) as a task, not in this document.
- Sources: `overall_roadmap.md` (the **S3 section** + the S3 governance-delta row —
  authoritative scope), `second_thoughts.md` (two-pool identity; "Pool A is the
  platform, Pool B is a per-tenant option"; legacy pools to decommission),
  `environments_and_testing.md` (test-first discipline), `s1-prepare-platform/`
  (`module-contract.md` — the four-seam contract + the *Data ownership* seam S3 fills),
  `migration_plan.md` (Gate 1 Pool A confirmation), `identity.md` +
  `architecture.md` (steering).

## Introduction

S3 establishes the **identity claim contract** and the **tenant governance data plane**
that every later multi-tenant step resolves against. It settles three deliverables — the
Pool A claim contract (D1), MySQL as the tenant system-of-record (D2), and a
one-directional MySQL→DynamoDB projection (D3) — and explicitly defers Pool B. The
detailed goal, scope, deferrals, and requirements follow below.

## Glossary

- **Pool A**: the existing admin/staff Cognito pool named `myAdmin`
  (`eu-west-1_Hdp40eWmu`, identity account); carries `cognito:groups` (global roles) and
  `custom:tenants` (tenant list). The confirmed platform identity pool in S3.
- **Pool B**: a future, greenfield end-user Cognito pool with a singular `tenant_id`
  claim (no roles, no entitlement projection); **deferred** — not built in S3, only not
  precluded.
- **system-of-record**: the authoritative source for a fact. In S3, MySQL
  (`tenants` / `tenant_modules` / `user_tenant_roles`) is the system-of-record for tenant
  governance.
- **projection**: a read-only, one-directional copy of the tenant-level governance subset
  written forward from MySQL into a DynamoDB table the module plane reads (never the
  reverse).
- **tenant_id / administration**: the tenancy key; `tenant_id` on the projection equals
  the MySQL `administration` value — the partition key that bounds a tenant's data.
- **issuer→pool registry**: the S2 config-not-code mapping (`COGNITO_POOL_KEYS` +
  per-pool `{KEY}_COGNITO_*`, fail-fast) that selects and interprets a pool by `iss`.
- **entitlement-in-token**: the per-user resolved per-tenant answer stamped into the
  token by a Pre-Token-Generation Lambda; this is **S4**, named as a dependency and not
  built in S3.

## Goal

Establish the **identity claim contract** and the **tenant governance data plane** that
every later multi-tenant step resolves against:

1. **Pool A claim contract** — standardize and *validate* the shape of the existing
   admin/staff pool's claims, and confirm both planes verify against the right pool's
   JWKS (via the S2 registry) and interpret those claims correctly.
2. **MySQL as the tenant system-of-record** — ratify and harden `tenants`,
   `tenant_modules`, `user_tenant_roles` as authoritative for tenant governance, and
   retire the dead `tenant_role_allocation` table.
3. **One-directional MySQL→DynamoDB projection** — build the mechanism that copies
   *tenant-level* governance facts forward into DynamoDB so a SAM-module Lambda reads
   tenant/module/role facts **without querying MySQL at request time**, under a
   mandatory write-only, no-split-brain guardrail.

S3 is where "which tenants exist, which modules each has enabled, and what each user may
do in each tenant" becomes both **authoritative in MySQL** and **available to the module
plane through a read-only projection** — so S5 (first real module) has something real to
resolve against, rather than retrofitting it later.

**Pool B is deferred** — see "Out of scope / deferred" below. S3 must simply *not
preclude* it; the S2 issuer→pool registry already makes adding Pool B config-only.

## What already exists (build on this, do not reinvent)

- **S2 issuer→pool registry** (`COGNITO_POOL_KEYS` + per-pool `{KEY}_COGNITO_*`,
  fail-fast, no defaults) — both planes already select the pool by `iss` and verify
  against that pool's JWKS. Adding a pool is a config entry, not code.
- **Pool A = the Cognito pool named `myAdmin`** (`eu-west-1_Hdp40eWmu`, identity
  account). Already carries `cognito:groups` and `custom:tenants`.
- **MySQL tenant governance tables**, live and authoritative: `tenants`,
  `tenant_modules` (`administration`, `module_name`, `is_active`), `user_tenant_roles`
  (`email`, `administration`, `role`).
- **`backend/src/auth/role_cache.py`** — the Flask plane already reads
  `user_tenant_roles` via a cached lookup (`SELECT role FROM user_tenant_roles WHERE
  email = %s AND administration = %s`). Only **global** roles (SysAdmin / Administrators
  / System_CRUD) come from `cognito:groups`.
- **`test_`-prefixed DynamoDB** convention + **Docker MySQL** — the non-Cognito halves
  of the test environment (`environments_and_testing.md`).
- **Standing test Cognito pool** (`eu-west-1_xyrlzfqbl`) mirroring Pool A.

S3 standardizes/validates the claim shape, ratifies the system-of-record, and *builds*
the projection. It does not re-derive tenancy, re-verify signatures (S2 did that), or
create Pool B.

## The three deliverables (and the one clean deferral)

S3 has exactly three build/ratify deliverables and one explicitly-deferred item:

- **D1 — Pool A claim contract** (identity claims): standardize + validate.
- **D2 — MySQL system-of-record**: ratify + harden + retire the dead table.
- **D3 — One-directional MySQL→DynamoDB projection**: build (the heavy part).
- **Deferred — Pool B** (end-user pool) and its edge cases: **not built in S3.**

## Scope

In scope:

- **Pool A claim contract (D1):** document and validate Pool A's claim shape —
  `cognito:groups` (GLOBAL roles only) + `custom:tenants` (list). Confirm both planes
  select Pool A by `iss` (S2 registry) and interpret its claims correctly. Per-user,
  per-tenant roles remain in MySQL `user_tenant_roles` (read on the Flask plane via
  `role_cache.py`), **not** in the token in S3.
- **Decommission legacy pools** (`eu-west-1_OAT3oPCIm`, `eu-west-1_VtKQHhXGN`,
  `eu-west-1_fcUkvwjH5`) — **manual, gated, high-risk**, only after confirming no
  dependency (mirror the `aws-accounts.md` / `migration_plan.md` guardrail). Never a
  step that touches Pool A.
- **MySQL system-of-record (D2):** ratify `tenants`, `tenant_modules`,
  `user_tenant_roles` as authoritative for **all** tenants — including tenants that will
  later enable SAM-backed modules (e.g. an h-dcn tenant entitled to
  `members`/`events`/`webshop` once those modules land in S5), not only finance tenants.
  **Retire `tenant_role_allocation`** — confirmed absent in dev (`finance`,
  `testfinance`) and prod, with no code readers; retirement = delete the unused DDL file
  (`backend/sql/create_tenant_role_allocation_table.sql`, already removed).
- **One-directional MySQL→DynamoDB projection (D3):** project the relevant subset of
  tenant-level governance data (`tenants` / `tenant_modules` / `user_tenant_roles`) into
  a DynamoDB projection table; define what is projected, the tenant-scoped key design,
  write-time validation, versioning, cache invalidation on the read side, the on-change
  sync trigger, and how it is tested against `test_` DynamoDB.
- Validation on the **test pool + Docker MySQL + `test_` DynamoDB** first; **gated**
  promotion of any Pool A-side change to production Pool A.

Out of scope / deferred (see the dedicated section below): **Pool B**, entitlement-in-
token projection (S4), per-user token projection, `tenant_id` on real module data /
first real module (S5).

## Out of scope / deferred (explicit)

### Pool B (end-user pool) — DEFERRED to a future requirement

S3 does **not** create, provision, or design Pool B. When it is later specified, it will
entail:

- A **NEW clean end-user pool** (greenfield — create it right, no migration).
- A single **`tenant_id`** claim (**singular**), **no roles, no entitlement
  projection** — a deliberately simpler contract than Pool A's `custom:tenants` list.
- Tenant **stamped at registration** (the portal/shop entered through, with admin
  approval where required, e.g. `verzoek_lid`).
- The member/customer DynamoDB record **is** the relationship — there is **no
  `user_tenant_roles` equivalent** for Pool B.

**S3's only obligation toward Pool B:** do not preclude it. The S2 issuer→pool registry
**already** makes adding Pool B a config-only change later (a registry entry + a claim
interpretation), so no rework is required and S3 must not build machinery that blocks it.

Also deferred (do NOT design in S3): `person_id` linking / member→admin promotion /
cross-pool SSO; multi-tenant Pool B membership.

### Later-step items (named, not built)

- **Entitlement-in-token projection (S4)** — the *per-user resolved answer* stamped into
  the token by a Pre-Token-Generation Lambda. S3 names it as the dependency and keeps
  `user_tenant_roles` authoritative for it; S3 does **not** build it.
- **`tenant_id` on real module data / first real module (S5)** — S3 provides the
  tenant/module/role truth (in MySQL and projected to DynamoDB) that S5 scopes against;
  S3 does not add `tenant_id` to any real module's data.

## Distinct from S4 (do not conflate)

S3's projection and S4's projection are **different data via different mechanisms**:

| | S3 projection | S4 projection |
| --- | --- | --- |
| **What** | *tenant-level* governance facts (tenants / tenant_modules / roles) | the *per-user resolved* per-tenant answer (roles ∩ enabled modules) |
| **Where** | a **DynamoDB projection table** the module reads | the **token** (a compact claim) |
| **When read** | request time, from DynamoDB (not the hot MySQL path) | request time, from the verified token |
| **Scope** | not user-scoped; too large / not per-user for the token | exactly the calling user |

They may **both** be needed and must **not** be conflated. S3 builds the DynamoDB
tenant-level path; S4 builds the token per-user path.

## Why in S3, not later

S5 makes a SAM module tenant-aware and scopes by `tenant_id`, but it has **nothing to
resolve against** until tenant/module/role truth exists in MySQL **and** is projected to
DynamoDB. So the system-of-record ratification (D2) and the projection (D3) must land
**with** the Pool A claim contract (D1), not be retrofitted after a module already
depends on them.

## Requirements

### R1 — Pool A claim contract (identity claims)
- **R1.1** Pool A's claim shape is documented as the platform contract: `cognito:groups`
  carries **GLOBAL roles only** (SysAdmin / Administrators / System_CRUD);
  `custom:tenants` carries the user's **list** of tenants. Per-user, per-tenant roles are
  **not** in the token in S3 — they live in MySQL `user_tenant_roles`.
- **R1.2** Both planes select Pool A by `iss` via the S2 issuer→pool registry (already
  config-not-code) and interpret Pool A claims per R1.1. No new verification code — S3
  standardizes and *validates* the existing S2 path against Pool A's claim shape.
- **R1.3** The Flask plane resolves per-user, per-tenant roles from `user_tenant_roles`
  via `role_cache.py` (cached MySQL read); only global roles come from `cognito:groups`.
  This is confirmed, not changed, in S3.
- **R1.4** Entitlement-projected-into-the-token is **S4** — named as the dependency, not
  built in S3. Nothing in S3 requires a per-tenant role or entitlement claim in the
  token.
- **R1.5** Any change S3 needs on the pool side is validated on the **test pool** first
  and applied to **production Pool A** (`eu-west-1_Hdp40eWmu`) only under a gate
  (R4). If S3 needs no pool-side change (contract already correct), that is recorded and
  Pool A is confirmed as-is.

### R2 — Legacy pool decommission (manual, gated)
- **R2.1** The legacy pools `eu-west-1_OAT3oPCIm`, `eu-west-1_VtKQHhXGN`,
  `eu-west-1_fcUkvwjH5` are decommissioned **only after** confirming no application,
  Railway config, or infrastructure dependency remains on them.
- **R2.2** Decommission is a **manual, human-gated** operation (mirroring the
  `aws-accounts.md` / `migration_plan.md` guardrail), never automated and never batched
  with other changes. A final export/backup precedes deletion.
- **R2.3** The decommission must **never** touch Pool A (`eu-west-1_Hdp40eWmu`) or the
  standing test pool (`eu-west-1_xyrlzfqbl`).

### R3 — MySQL is the tenant system-of-record
- **R3.1** `tenants`, `tenant_modules` (`administration`, `module_name`, `is_active`),
  and `user_tenant_roles` (`email`, `administration`, `role`) are the **authoritative**
  source for which tenants exist, which modules each tenant has enabled, and which
  per-tenant roles each user holds — designed to cover tenants that **will later** enable
  **SAM-backed modules** (e.g. an h-dcn tenant entitled to `members`/`events`/`webshop`
  once those modules exist in S5), not only finance tenants.
- **R3.2** Only **global** roles (SysAdmin / Administrators / System_CRUD) are sourced
  from `cognito:groups`; everything per-tenant is resolved from `user_tenant_roles`.
- **R3.3** The authority for tenant governance does **not** move to the module plane, and
  no module owns a second writable copy. Any module need for these facts is met via the
  token (S4) or the **read-only** projection (R5) — never a request-time MySQL query
  from a Lambda.
- **R3.4** The legacy `tenant_role_allocation` table is **retired**. It was **confirmed
  absent** in dev (`finance`, `testfinance`) and prod, with **no code readers**; available
  roles are derived from `tenant_modules` + Cognito groups (already the settled position
  in the SysAdmin-Module spec). Retirement therefore = **delete the unused DDL file**
  `backend/sql/create_tenant_role_allocation_table.sql` (already removed). No physical
  table or governance data existed to drop.

### R4 — Test-first, then gated promotion
- **R4.1** All S3 changes — claim-contract validation, system-of-record hardening, and
  the projection — are developed and validated **first** against the **test pool
  (`eu-west-1_xyrlzfqbl`) + Docker MySQL + local DynamoDB** (the Phase 0 / T0
  DynamoDB-in-Docker stack is the **preferred** datastore; the cloud `test_` / `-Test`
  DynamoDB tables are the **fallback** when local DynamoDB is unavailable). Env vars are
  fail-fast (a missing pool/table/registry var throws; the DynamoDB endpoint is used only
  when `AWS_ENDPOINT_URL_DYNAMODB` is set — **no dangerous fallback** that could point at
  production).
- **R4.2** Any Pool A-side change is **promoted to production Pool A only after** test
  validation passes, gated (test matrix green, rollback path ready). "Test-first" means
  validate-then-promote, never prod-first.
- **R4.3** The projection's on-change sync and read path are validated against **local
  DynamoDB** (preferred; cloud `test_` / `-Test` tables as fallback) before any production
  projection table is written.

### R5 — One-directional MySQL→DynamoDB projection (the guardrail is the requirement)
- **R5.1 (write-only from the sync process)** The projection flows **MySQL→DynamoDB
  only**. The sync process is the **sole writer** of the projection table. MySQL is the
  single source of truth; the DynamoDB copy is a **read-only projection**.
- **R5.2 (no two-way write / no split brain)** No module and no request path writes
  governance facts back to MySQL, and nothing but the sync process writes the projection
  table. Two-way writes are forbidden — they are a split-brain / cross-tenant incident
  waiting to happen.
- **R5.3 (what is projected)** Only the **tenant-level** subset needed by the module
  plane is projected: the relevant rows of `tenants`, `tenant_modules`, and
  `user_tenant_roles` for tenants that have SAM-backed modules enabled. Data that belongs
  in the token (the per-user resolved answer) is **not** projected here — that is S4.
- **R5.4 (tenant-scoped key design)** The projection table is keyed so every item is
  addressable by tenant (`tenant_id` / `administration` as the partition key), matching
  the module plane's tenant-scoping model (partition key + IAM `LeadingKeys`) so a Lambda
  reads only its own tenant's projected facts.
- **R5.5 (write-time validation)** The sync validates each item before writing (shape,
  required fields, tenant key present); a malformed source row fails the sync loudly
  rather than writing partial/garbage data. No silent partial projection.
- **R5.6 (versioning)** Each projected write carries a version / monotonically-increasing
  marker (e.g. a source revision or updated-at) so a reader can detect staleness and the
  sync is idempotent — re-running the sync for an unchanged source produces no spurious
  change (idempotent projection).
- **R5.7 (on-change sync trigger)** The sync writes **on change** to the source
  governance tables (not a per-request pull), so the projection tracks MySQL within a
  bounded, documented delay. The trigger mechanism is defined in the design.
- **R5.8 (cache invalidation on the read side)** The read side (the module plane's
  DynamoDB reads, and any cache over them) is invalidated/refreshed when the projection
  changes, using the version marker (R5.6). Stale reads are bounded and documented, never unbounded.
- **R5.9 (module reads only)** A module **reads** the projection and **never** writes it
  or writes back to MySQL. This is the module-plane companion to the Flask plane's
  `role_cache.py` for *tenant-level* facts.

### R6 — Governance updated on completion (S3 definition of done)
- **R6.1** Auth/tenant steering records: the **Pool A claim contract** (global roles in
  `cognito:groups`, `custom:tenants` list, per-tenant roles in MySQL); **MySQL as the
  tenant system-of-record**; the **one-directional MySQL→DynamoDB projection** rule
  (write-only, no split brain).
- **R6.2** A new ADR (**ADR 0005**, the next number after 0004) records: "two-pool
  (audience-split) identity — **Pool A now, Pool B deferred**; MySQL is the tenant
  system-of-record; one-directional MySQL→DynamoDB projection." Append-only.
- **R6.3** The steering and ADR are **tasks within S3** (`tasks.md`), authored on
  completion — they are referenced here, not created by this document.

## Acceptance criteria

- **Pool A claim contract (D1):** Pool A's claim shape is documented and *validated* —
  a real Pool A token is selected by `iss` (S2 registry) and its `cognito:groups`
  (global roles) + `custom:tenants` (list) are interpreted correctly on both planes;
  per-tenant roles resolve from `user_tenant_roles` via `role_cache.py`, not the token.
- **System-of-record (D2):** `tenants` / `tenant_modules` / `user_tenant_roles` are the
  authoritative governance source for tenants that will later enable SAM-backed modules
  as well as finance tenants; `tenant_role_allocation` is retired — confirmed absent in
  dev and prod with no code readers, and the unused DDL file removed (no data existed to
  lose).
- **Projection (D3):** the tenant-level subset projects MySQL→DynamoDB **write-only**;
  the sync is the sole writer; write-time validation rejects malformed rows; writes are
  versioned and idempotent; the on-change trigger keeps the projection within a bounded
  delay; the read side invalidates on version change; a module reads the projection and
  never writes back. All validated against `test_` DynamoDB + Docker MySQL first.
- **No dangerous fallback:** a missing pool/registry/table env var fails fast; nothing
  can silently point identity or projection work at production.
- **Gated promotion:** any Pool A-side change reaches production only after test-pool
  validation; legacy-pool decommission is manual, dependency-checked, and never touches
  Pool A or the test pool.
- **Pool B not precluded:** nothing S3 builds prevents adding Pool B later as a
  config-only registry entry with a singular `tenant_id` claim.
- **Governance:** auth/tenant steering + ADR 0005 exist and match the implemented
  behavior.

## Prerequisites (already satisfied)

- **S2 done** — verify-before-trust on both planes; issuer→pool registry config-not-code;
  JWKS cached with rotation; module-plane verifier shipped as `sam/`.
- **Standing test pool done** (`eu-west-1_xyrlzfqbl`), plus Docker MySQL + `test_`
  DynamoDB — the validation environment for all S3 work.
