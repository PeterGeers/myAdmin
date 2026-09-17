# ADR 0005 — Two-pool (audience-split) identity: Pool A now, Pool B deferred; MySQL is the tenant system-of-record; one-directional MySQL→DynamoDB projection

- Status: Accepted
- Date: 2026-09-16
- Relates to: ADR 0003 (myAdmin is the platform base; import apps as SAM-backed
  modules) and ADR 0004 (verified-JWT-only; per-issuer JWKS verification) — S3 builds
  on both: it fills the claim-contract + tenant-data-ownership seam of the module
  contract, on top of S2's verified-token foundation.

## Context

S3 had to settle three things that every later multi-tenant step (S4 token
entitlement, S5 module-plane tenant binding) assumes: **which identity claims the
platform trusts**, **who owns tenant governance data**, and **how the SAM-backed
module plane may read that data without becoming a second writer**.

The pieces were already partly in place. ADR 0003 established the two-plane design
(Flask / MySQL admin+finance plane + SAM / Lambda / DynamoDB module plane) and the
module contract. ADR 0004 made both planes trust only signature-verified tokens and
put pool selection behind an `iss`-keyed, config-not-code issuer→pool registry
(S2). What remained was to **document and ratify** the existing Pool A claim shape
(without rebuilding it), confirm MySQL as the authoritative system-of-record, and
**build** the one-directional projection that lets a Lambda read tenant facts without
a request-time MySQL query.

S3 was executed test-first (standing test pool `eu-west-1_xyrlzfqbl` + Docker MySQL +
local DynamoDB) before any production Pool A touch. This ADR records the settled S3
outcomes; it does not re-derive them — the authoritative text lives in the S3 spec
docs cited under **Related**.

## Decision

**Adopt two-pool (audience-split) identity with Pool A now and Pool B deferred, keep
MySQL as the tenant system-of-record, and let the module plane read tenant facts only
through a one-directional MySQL→DynamoDB projection.**

- **Two-pool, audience-split identity.**
  - **Pool A** is the admin/staff `myAdmin` pool (`eu-west-1_Hdp40eWmu`, identity
    account), **confirmed as-is** in S3 — no pool-side change was needed; S3 documented
    and validated an already-correct shape rather than rebuilding it.
  - **Pool B** is a future greenfield end-user pool (a single `tenant_id` claim, no
    roles, no entitlement projection). It is **deferred** — not built in S3 — and
    explicitly **not precluded**: adding it later is **config-only** via the S2
    issuer→pool registry (a registry entry keyed by `iss`, never a code change). Split
    is by audience only, never per-tenant or per-app.

- **Pool A claim contract.** The Pool A token carries exactly two governance claims,
  and one fact deliberately does not ride the token:
  - `cognito:groups` = **global roles only** — `SysAdmin` / `Administrators` /
    `System_CRUD`. Any other group value is dropped; per-tenant capability never travels
    on the token in S3.
  - `custom:tenants` = the user's **list** of selectable tenants (`administration`
    keys), read only from the verified token; `X-Tenant` selects one and is validated
    against that list (unlisted → 403).
  - **Per-tenant roles live in MySQL `user_tenant_roles`, not the token** — resolved by
    `auth/role_cache.py`. The per-user *entitlement-in-token* projection (roles ∩ enabled
    modules, stamped by a Pre-Token-Generation Lambda) is **S4** — named here, not built
    in S3.

- **MySQL is the tenant system-of-record.** `tenants` / `tenant_modules` /
  `user_tenant_roles` are authoritative for tenant governance across **all** tenants —
  including tenants that will enable SAM-backed modules, not only finance tenants.
  Entitlement is backing-agnostic (`tenant_modules` only; no `backing` awareness).
  Authority **does not move to the module plane** and **no module owns a writable copy**.
  The dead `tenant_role_allocation` table is **retired** (no remaining readers, no
  physical table, no data loss).

- **One-directional MySQL→DynamoDB projection (D3).** A module's need for tenant facts
  is met one-directionally, never by a request-time MySQL query from a Lambda:
  - **Write-only, single writer:** the sync is the **sole** writer of the projection
    table and makes **zero** MySQL writes. Data flows MySQL→DynamoDB only, never back —
    no split brain.
  - **Validated, versioned, idempotent:** items are validated at write time (malformed
    rows rejected, no partial write); each item carries a monotonic `version`; re-runs on
    unchanged source are no-ops.
  - **Tenant-scoped:** partition key `tenant_id` (== `administration`), enforced by IAM
    `dynamodb:LeadingKeys`; the module plane reads **only** its own `tenant_id` partition
    and never writes the projection or MySQL.
  - **Bounded, documented staleness:** on-change sync triggers + a periodic reconciliation
    backstop keep it converged within a bounded delay; the read side invalidates on
    `version` change.

## Rationale

- Splitting identity by audience keeps a small, high-privilege admin pool (Pool A)
  separate from a large, low-privilege end-user pool (Pool B), and the S2 registry makes
  the platform multi-pool aware without hard-coding a single pool — so deferring Pool B
  costs nothing and precludes nothing.
- Keeping only global roles on the token and resolving per-tenant roles from MySQL keeps
  the token small and avoids baking per-tenant authority into a credential that refreshes
  only on re-login; it also keeps a single source of truth for grants.
- A single MySQL system-of-record with a one-directional projection gives the serverless
  module plane the tenant facts it needs (offline, no per-request DB hop) while
  structurally preventing a second writer — the "no writable copy / no two-way write"
  invariant holds by construction (the `sam/` plane has no MySQL client at all), not by
  convention.
- Versioned + idempotent + tenant-scoped writes make the projection safe to re-run and
  impossible to cross tenants, and the on-change + reconciliation model bounds staleness
  without a request-time dependency.

## Consequences

- **Pool A is live and unchanged.** S3 required no pool-side change; Pool A is confirmed
  as-is, settling `migration_plan.md` Gate 1. Pool selection stays config-not-code (the
  `PROD_A_COGNITO_*` registry entry already exists from S2).
- **Adding Pool B later is configuration**, not new code — a single S2 registry entry
  (singular `tenant_id` claim, no roles, no entitlement projection). Nothing built in S3
  blocks it.
- **The system of record is exactly three MySQL tables** (`tenants`, `tenant_modules`,
  `user_tenant_roles`); `tenant_role_allocation` is retired non-destructively (a
  negative-assertion guardrail test pins the retirement so a future reader fails loudly).
- **The module plane reads tenant facts only forward** — via the token (S4) or the
  read-only projection (D3) — never a request-time MySQL query.
- **Production table `governance_projection` exists but is empty.** It is created in
  `eu-west-1` (account `506221081911`), `PAY_PER_REQUEST`, managed **outside**
  CloudFormation with retain / human-only-deletion semantics. Because the shipped
  `MODULE_REGISTRY` registers no SAM-backed module, the builder emits zero items — the
  correct, expected state until **S5** registers real SAM modules and the same scoped,
  idempotent sync populates it.
- **Later steps build on this.** S4 stamps the per-user entitlement claim into the token
  (distinct from S3's tenant-level DynamoDB projection — do not conflate); S5 binds the
  module plane to the tenant claim and populates the projection.

## Related

- ADR 0003 (platform base; two-plane design + module contract) and ADR 0004
  (verified-JWT-only; `iss`-keyed config-not-code pool registry) — this ADR builds on
  both.
- Steering: `.kiro/steering/identity.md` (two-pool claim contract, Pool A as-is / Pool B
  deferred), `.kiro/steering/architecture.md` (one-directional projection invariants +
  `governance_projection`), `.kiro/steering/authentication.md`.
- Spec `.kiro/specs/multi-tenant/s3-claims-and-projection/`:
  - `claim-contract.md` (D1 — Pool A claim contract),
  - `system-of-record-ratification.md` (D2 — MySQL system-of-record, `tenant_role_allocation` retirement),
  - `production-promotion.md` (D3 — production `governance_projection` promotion, empty until S5),
  - `requirements.md` + `design.md` (D1–D3).
