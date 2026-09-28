# Requirements Document

## S4 — Project Resolved Entitlement into the Token (Pre-Token-Generation) — Requirements

- Status: Complete (functions delivered; live production trigger — T18 — deferred to S5, the first app migration)
- Roadmap step: S4 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Depends on: **S2** (verified-JWT-only on both planes; issuer→pool registry config-not-code — **done**), **S3** (Pool A claim contract; MySQL as the tenant system-of-record `tenants`/`tenant_modules`/`user_tenant_roles`; one-directional MySQL→DynamoDB projection — **done**), and the standing **test Cognito pool** (`eu-west-1_xyrlzfqbl`, permanent test fixture mirroring Pool A).
- Decision of record: ADR 0003 (platform base), ADR 0004 (verified-JWT-only), ADR 0005 (two-pool identity; MySQL system-of-record; one-directional projection). S4 authors the **next** ADR (**ADR 0006**) as a task, not in this document.
- Sources: `overall_roadmap.md` (the **S4 section** + the S4 governance-delta row — authoritative scope), `myadmin_as_base.md` ("The fix: system of record + projection"), `s3-claims-and-projection/` (`claim-contract.md`, `system-of-record-ratification.md`), `environments_and_testing.md` (test-first discipline), `identity.md` + `architecture.md` + `authentication.md` (steering).

## Introduction

S4 makes a request's **authorization answer travel in the token**. A Cognito
**Pre-Token-Generation Lambda** computes, at login/token issuance, each user's
**resolved per-tenant entitlement** — for each tenant the user belongs to, their
per-tenant **roles** (`user_tenant_roles`) intersected with that tenant's enabled
**modules** (`tenant_modules`) — and stamps it into the token as a compact claim. The
request path (especially a SAM-backed module's Lambda) then answers *"what may this
user do in this tenant?"* from the **verified token alone**, without a request-time
MySQL query.

S4 is the **Lambda-plane equivalent of the Flask plane's `role_cache.py`**: the same
resolved per-tenant answer, carried in the token instead of a server-side cache. The
Flask monolith can afford a cached MySQL read (`auth/role_cache.py`, 5-min TTL); a
Lambda must not open MySQL per request (the S1 "Data ownership" seam), so the answer
is projected into the token.

## Distinct from S3 (do not conflate)

S3 and S4 are **different data via different mechanisms** — both may be needed:

| | S3 projection | S4 projection (this spec) |
| --- | --- | --- |
| **What** | *tenant-level* governance facts (tenants / tenant_modules / roles as reference data) | the *per-user resolved* per-tenant answer (roles ∩ enabled modules) |
| **Where** | a **DynamoDB projection table** the module reads | the **token** (a compact claim) |
| **When computed** | on change to the source tables (sync) | at token issuance (Pre-Token-Generation Lambda), per user |
| **When read** | request time, from DynamoDB | request time, from the verified token |
| **Scope** | not user-scoped; too large / not per-user for the token | exactly the calling user |

S3 gives a Lambda the tenant's *reference data*; S4 gives it the *calling user's
resolved permissions*. This spec builds only the S4 token path.

## Glossary

- **Pre-Token-Generation (PreTokenGen) Lambda**: a Cognito trigger that runs during
  token issuance and may add/override claims (`claimsToAddOrOverride`) — the V2 trigger
  supports both ID and access tokens.
- **Resolved entitlement**: for one user and one tenant, the set of capabilities =
  the user's `user_tenant_roles` for that tenant **intersected/expanded against** the
  tenant's active `tenant_modules`. "What this user may actually do in this tenant right
  now," not the raw role list.
- **Entitlement claim**: the compact token claim S4 stamps carrying the resolved
  entitlement (shape defined in design; e.g. `custom:entitlements`, a per-tenant map).
- **Pool A**: the admin/staff `myAdmin` pool (`eu-west-1_Hdp40eWmu`) — the pool S4
  targets. **Pool B is deferred** (it carries a singular `tenant_id`, no roles, no
  entitlement projection — S4 must not preclude it).
- **role_cache.py**: the Flask plane's cached per-tenant role reader — the server-side
  analogue of the S4 token claim; S4 keeps the two answers consistent.

## Goal

Stamp each user's **resolved per-tenant entitlement into the token** at issuance via a
Cognito Pre-Token-Generation Lambda, computed **once** from the MySQL system of record
(S3), so both planes — and especially a SAM-backed module's Lambda — authorize from the
**verified token alone**, never querying MySQL on the request path. Ship it **test-first**
(validated on the test pool), then gate promotion to production **Pool A**.

## What already exists (build on this, do not reinvent)

- **MySQL system of record (S3/D2):** `tenants`, `tenant_modules` (`administration`,
  `module_name`, `is_active`), `user_tenant_roles` (`email`, `administration`, `role`)
  — authoritative for the resolution S4 performs.
- **`backend/src/services/module_registry.py`** — `MODULE_REGISTRY` +
  `has_module()` / `module_required()`; the module→required-roles mapping and the
  backing-agnostic entitlement rule (entitlement reads `tenant_modules`).
- **`backend/src/auth/role_cache.py`** — the Flask plane's resolved per-tenant role
  read; the reference implementation of the *same* answer S4 puts in the token.
- **S2 verifier + issuer→pool registry** (`backend/src/auth/`, `sam/shared/auth_utils.py`)
  — reads claims only from a signature-verified token; S4 adds a claim to *read*, not a
  new verification path.
- **Pool A claim contract (S3/D1, `claim-contract.md`)** — `cognito:groups` = global
  roles; `custom:tenants` = tenant list; per-tenant roles in MySQL. S4 adds the resolved
  entitlement claim **without** changing that contract's existing claims.
- **Standing test pool** (`eu-west-1_xyrlzfqbl`) + Docker MySQL — the validation
  environment (identity work is validated here before Pool A).

## Scope

In scope:

- **A Cognito Pre-Token-Generation Lambda** (targeting **Pool A**) that, at token
  issuance, resolves the calling user's per-tenant entitlement from MySQL (roles ∩
  enabled modules, per tenant) and stamps a compact **entitlement claim** into the token.
- **A pure resolver** — `(user_tenant_roles[], tenant_modules[], module_registry) →
  resolved entitlement per tenant` — that is the single source of the resolution logic,
  reused by the Lambda and testable in isolation (property-based).
- **Consistency with `role_cache.py`** — the token's resolved answer for a user+tenant
  matches what the Flask plane's `role_cache.py` + module gate would compute for the same
  inputs (one resolution rule, two carriers).
- **Claim shape + size discipline** — a compact, versioned claim that stays within
  Cognito token-size limits for realistic multi-tenant users; a defined behavior when a
  user's entitlement would exceed the budget.
- **Token lifetime / staleness / revocation decision** — entitlement is computed at
  issuance and only refreshes on token renewal; S4 defines and documents the bounded
  staleness window and how an access change propagates (re-login / token refresh), plus
  how the module plane should treat it (mirrors S3/R5.8's bounded, documented staleness).
- **Both planes read the claim** — the Flask plane may prefer the token claim over a
  MySQL read where appropriate; the module plane (`sam/`) reads the claim from the
  verified token. Reading is additive; existing behavior is preserved.
- **Test-first, then gated** — validated on the **test pool + Docker MySQL** first;
  the Pool A trigger is attached under a gate with a rollback path.
- **MySQL access discipline** — the Lambda's MySQL read is the **only** sanctioned
  request-adjacent MySQL access, and it happens **at token issuance, not on the API
  request path**; it is read-only (zero governance writes). It does not violate the S1
  "no request-time MySQL from a module Lambda" rule because it runs in the identity
  account's token-issuance flow, not in a module's request handler.

Out of scope / deferred:

- **Pool B entitlement** — Pool B carries a singular `tenant_id`, no roles, no
  entitlement projection. S4 targets Pool A only and must not preclude Pool B.
- **The S3 DynamoDB tenant-level projection** — already built; S4 does not modify it.
- **Real SAM module consumption of the claim in production** — a module actually
  gating on the claim in prod is exercised in **S5**; S4 delivers the claim + validates
  a module *can* read it, but does not ship a production module.
- **Changing the existing Pool A claims** (`cognito:groups`, `custom:tenants`) — S4 is
  additive.

## Requirements

### R1 — Resolved-entitlement resolver (pure, single source of truth)
- **R1.1** A pure function resolves, for a given user, a **per-tenant entitlement map**
  from `user_tenant_roles` + `tenant_modules` + the module→role rules in
  `MODULE_REGISTRY`: for each tenant the user has, the capabilities granted by the
  intersection of the user's roles and the tenant's **active** modules.
- **R1.2** The resolver is **pure** (no I/O, deterministic) so it is unit- and
  property-testable; the Lambda supplies the rows, the resolver computes the answer.
- **R1.3** The resolver's answer for a `(user, tenant)` is **equivalent** to what the
  Flask plane computes today (`role_cache.py` per-tenant roles filtered through the
  module gate). One resolution rule, reused — not a second, divergent implementation.
- **R1.4** Global roles (`SysAdmin` / `Administrators` / `System_CRUD`) continue to come
  from `cognito:groups` (S3 contract) and are **not** re-derived by S4; S4 resolves the
  **per-tenant** answer only. (S4 may include global roles in the claim for the module
  plane's convenience only if the design decides to, without changing their authority.)

### R2 — Pre-Token-Generation Lambda (the projection mechanism)
- **R2.1** A Cognito Pre-Token-Generation Lambda attached to **Pool A** stamps the
  resolved entitlement into the token as a compact **entitlement claim** at issuance.
- **R2.2** The Lambda reads the source rows from MySQL **read-only** (zero governance
  writes) and computes the claim via the R1 resolver. It runs at **token issuance**, not
  on the API request path.
- **R2.3** The Lambda is **fail-safe**: if resolution fails (DB unavailable, malformed
  data), it does **not** stamp a partial/garbage entitlement claim — it either omits the
  claim (fail-closed for entitlement; the request path then has no elevated entitlement)
  or fails the token issuance per the design decision, and the failure is logged (user
  identity, not secrets). No silent partial entitlement.
- **R2.4** The Lambda does **not** alter the existing Pool A claims (`cognito:groups`,
  `custom:tenants`); the entitlement claim is **additive**.
- **R2.5** Env/config is **fail-fast** (missing DB/registry config throws; no dangerous
  fallback that could resolve against the wrong data) — consistent with S2/S3 R4.1.

### R3 — Claim shape, size, and versioning
- **R3.1** The entitlement claim has a **defined, documented shape** (per-tenant map of
  resolved capabilities) and a **version** marker so a reader can detect the format and
  staleness.
- **R3.2** The claim is **compact** and stays within Cognito's token-size limits for
  realistic multi-tenant users; the design defines the encoding and a **bounded** budget.
- **R3.3** There is a **defined behavior when entitlement would exceed the budget**
  (e.g. omit + signal "consult the S3 projection / server", or compress) — never a
  silently truncated claim that misrepresents access.

### R4 — Consistency, staleness, and revocation
- **R4.1** For the same MySQL state, the token's resolved answer for a `(user, tenant)`
  **matches** the Flask plane's `role_cache.py` + module-gate answer (R1.3), so the two
  planes never disagree about a user's access.
- **R4.2** Entitlement is computed **at issuance** and refreshes only on **token
  renewal** (re-login / refresh). The **staleness window is bounded and documented**
  (token lifetime); an access change (role grant/revoke, module enable/disable) takes
  effect on the next token issuance. This mirrors S3/R5.8's "bounded, documented, never
  unbounded" rule.
- **R4.3** A **revocation/urgent-change story** is defined: how a security-relevant
  downgrade (e.g. a revoked role) is honored before natural token expiry (e.g. shortened
  token lifetime, forced re-auth, or a server-side check for the sensitive subset) —
  documented as an explicit decision, not left implicit.

### R5 — Both planes read the claim (additive, verified-only)
- **R5.1** The claim is read **only** from a signature-verified token (S2). No
  unverified header ever supplies entitlement.
- **R5.2** The **module plane** (`sam/`) can read the entitlement claim from the verified
  token to authorize a request **without** a MySQL query and **without** the S3 DynamoDB
  read where the token suffices (the token is the per-user path; S3 is the tenant-level
  path).
- **R5.3** The **Flask plane** continues to work unchanged; adopting the token claim in
  place of a `role_cache.py` read is **optional and additive**, and must yield the same
  decision (R4.1). No regression to existing Flask authorization.

### R6 — Test-first, then gated promotion
- **R6.1** The resolver + Lambda are developed and validated **first** against the
  **test pool + Docker MySQL** (test users, seeded `user_tenant_roles` / `tenant_modules`),
  with the resolver covered by **property-based tests** (see design).
- **R6.2** The Pool A Pre-Token-Generation trigger is attached to **production Pool A**
  only **after** test validation passes, **gated** (rollback path ready: detaching the
  trigger restores prior behavior). Never prod-first.
- **R6.3** No dangerous fallback: missing config fails fast; nothing can silently resolve
  entitlement against the wrong environment or stamp a wrong-tenant answer.

### R7 — Governance updated on completion (S4 definition of done)
- **R7.1** Architecture/auth steering records: **entitlement is projected into the token
  at issuance, not read from MySQL per request**; the token is the per-user path, the S3
  DynamoDB projection is the tenant-level path (do not conflate); the bounded-staleness /
  revocation decision.
- **R7.2** A new ADR (**ADR 0006**, next after 0005, append-only) records the decision:
  "resolved per-tenant entitlement projected into the Pool A token via a
  Pre-Token-Generation Lambda; single resolver shared with `role_cache.py`; bounded
  staleness + revocation policy; Pool B deferred."
- **R7.3** The steering + ADR are **tasks within S4** (`tasks.md`), authored on
  completion.

## Acceptance criteria

- **Resolver:** a pure resolver computes each user's per-tenant entitlement (roles ∩
  active modules) identically to the Flask plane's `role_cache.py` + module gate, proven
  by property-based tests over generated tenants × modules × roles.
- **Lambda:** a Pre-Token-Generation Lambda stamps a compact, versioned entitlement
  claim into the token at issuance, reading MySQL read-only, additive to existing Pool A
  claims, fail-safe (no partial/garbage claim), fail-fast on config.
- **Claim discipline:** the claim stays within token-size limits for realistic users,
  with a defined over-budget behavior; never silently truncated.
- **Both planes:** the module plane authorizes from the verified token claim without a
  request-time MySQL query; the Flask plane is unchanged and any adoption of the claim
  yields the same decision.
- **Staleness/revocation:** the staleness window is bounded and documented; the
  revocation story for urgent downgrades is defined.
- **Test-first + gated:** validated on the test pool + Docker MySQL first; the Pool A
  trigger is attached only after validation, with a rollback path; no dangerous fallback.
- **Pool B not precluded:** nothing in S4 blocks Pool B (which carries no entitlement
  claim).
- **Governance:** architecture/auth steering + ADR 0006 exist and match the implemented
  behavior; roadmap S4 status updated.

## Prerequisites (already satisfied)

- **S2 done** — verified-JWT-only; issuer→pool registry config-not-code; module-plane
  verifier shipped as `sam/`.
- **S3 done** — Pool A claim contract; MySQL system-of-record
  (`tenants`/`tenant_modules`/`user_tenant_roles`); one-directional projection.
- **Standing test pool** (`eu-west-1_xyrlzfqbl`) + Docker MySQL — the validation
  environment for all S4 work.
