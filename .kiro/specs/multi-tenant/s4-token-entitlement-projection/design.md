# S4 — Project Resolved Entitlement into the Token (Pre-Token-Generation) — Design

- Status: Complete (functions delivered; live production trigger — T18 — deferred to S5, the first app migration)
- Companion to `requirements.md` (same folder). Implements R1–R7.
- Decision of record: ADR 0003 + ADR 0004 + ADR 0005; S4 authors ADR 0006 (as a task).

## Overview

S4 stamps each user's **resolved per-tenant entitlement** into the Pool A token at
issuance, so the request path — especially a SAM-backed module's Lambda — authorizes
from the **verified token alone**, never querying MySQL per request.

Four pieces, one shared rule:

- **D1 — the pure resolver.** `(user_tenant_roles[], tenant_modules[], module_registry)
  → per-tenant entitlement map`. The single source of the resolution logic (roles ∩
  active modules), reused by the Lambda and by the Flask plane, and covered by
  property-based tests. This is the load-bearing correctness piece.
- **D2 — the Pre-Token-Generation Lambda.** A Cognito trigger on **Pool A** that reads
  the source rows from MySQL (read-only, at issuance), calls the resolver, and stamps a
  compact, versioned **entitlement claim** into the token — additive to the existing
  `cognito:groups` / `custom:tenants` claims, fail-safe, fail-fast on config.
- **D3 — claim shape + size budget.** A compact, versioned per-tenant map with a defined
  encoding and a bounded size budget, and a defined over-budget behavior (never a
  silently truncated claim).
- **D4 — staleness + revocation.** Entitlement is computed at issuance and refreshes on
  token renewal; the staleness window is bounded and documented, with an explicit
  revocation story for urgent downgrades.

S4 is the **Lambda-plane equivalent of `role_cache.py`**: the same resolved answer, in
the token instead of a server-side cache. It fills the per-user half of the S1 "Data
ownership" seam (S3 filled the tenant-level half via the DynamoDB projection).

## Design amendment A — the Lambda reads the S3 DynamoDB projection, not MySQL

> **Status: adopted (supersedes the MySQL-read parts of D2 below).** The original
> D2 had the Pre-Token-Generation Lambda read MySQL directly at issuance. That bends
> the S1 "a module Lambda never opens a MySQL connection" contract and creates a real
> operational risk: the Lambda would have to reach **Railway MySQL** from AWS over its
> public TCP proxy, within Cognito's **5-second** PreTokenGen budget, on every cold
> start. We instead read the **S3 one-directional DynamoDB projection** — the exact
> data plane S3 built for "a Lambda needs tenant/role facts without querying MySQL."

**What changes (only the reader seam; the rule is unchanged):**

- The Lambda's governance reader reads the **`governance_projection` DynamoDB table**
  (S3/D3), not MySQL. It uses `boto3` + an IAM role (no `mysql-connector` in the
  bundle, no Railway egress, no VPC/NAT question, single-digit-ms reads well within
  the 5s budget). This realizes S1's "Data ownership" seam for the per-user path.
- **Read pattern.** The user's tenant list comes from the PreTokenGen event's
  `custom:tenants` claim. For each such tenant `T`, the reader issues one DynamoDB
  `Query` on partition `tenant_id = T` and reconstructs, from the projected items
  (`services.projection_schema` shape):
  - `active_modules_by_tenant[T]` = the `module#<name>` items with `is_active` true;
  - `roles_by_tenant[T]` = the `role#<email>#<role>` items **filtered to the calling
    user's email**.
  It then calls the **unchanged** T1 `resolve_entitlement` and T4 `encode_entitlements`.
- **Empty is valid, not an error.** A tenant with no projected modules/roles (or a
  tenant absent from the projection entirely) yields an **empty** entitlement for that
  tenant; a user with no projectable tenants yields an empty map, which the codec
  encodes as `{v:1,t:{}}`. The token then simply carries "no per-tenant entitlement,"
  which is correct. The reader and handler must handle empty/missing partitions
  gracefully (no raise) — an absent projection is a legitimate state, especially before
  S5 registers real SAM-backed modules (the production projection is empty today).
- **Staleness.** The token now reflects the **projection's** state, which lags MySQL by
  the bounded S3 sync delay (R5.7) plus this issuance. This is within the documented
  bounded-staleness model (S3/R5.8, S4 D4) — named, never unbounded.
- **Consistency (R4.1) still holds.** Both carriers still run the one T1 resolver; the
  only shift is that the *source rows* the resolver consumes now come from the
  projection instead of MySQL. The Flask plane (T15) may still read MySQL/`role_cache`
  directly; the projection is the sync of that same MySQL truth, so the rule is
  identical and the difference is only *when/whence* the rows were read.
- **The projection must carry the token-relevant governance.** S3's projection builder
  currently gates on SAM-backed-module tenants; for S4 to answer for ordinary Pool A
  tenants, that gate is widened so the governance the token needs is projected. This is
  tracked as an S3/S4 coordination item; until it is, the reader correctly returns empty
  (handled gracefully) rather than failing.

**Account architecture (settled in `aws-accounts.md`, not a new choice).** Cognito
pools live in the **identity account (344561557829)**; Lambda + DynamoDB live in the
**data account (506221081911)** — *"No Cognito pool of record (triggers attach
cross-account)."* So the PreTokenGen Lambda runs in the **data account** with the
`governance_projection` table (same-account read), and Pool A attaches its trigger to
it **cross-account**. This is the intended design and is what T18 implements.

The MySQL-specific text in the original **D2** (below) is retained for history but is
**superseded** by this amendment: substitute "read the DynamoDB projection for the
user's `custom:tenants` partitions" wherever D2 says "read MySQL," and "IAM role for
the projection table" wherever it says "explicit `ENTITLEMENT_DB_*` MySQL config."

## Architecture

```
                 Cognito (identity account) — Pool A  eu-west-1_Hdp40eWmu
                          │
        token issuance ──►│  Pre-Token-Generation Lambda (D2)
                          │     1. read source rows (READ-ONLY) from MySQL:
                          │        user_tenant_roles + tenant_modules (for this user)
                          │     2. resolve via the PURE resolver (D1):
                          │        per tenant: roles ∩ active modules → capabilities
                          │     3. stamp claimsToAddOrOverride:
                          │        custom:entitlements = <compact versioned map> (D3)
                          │     (additive: cognito:groups / custom:tenants unchanged)
                          ▼
                 verified token (S2 verify on both planes)
              ┌───────────┴─────────────┐
              ▼                         ▼
   Flask / MySQL plane            SAM / Lambda module plane
   reads the claim OR             reads the ENTITLEMENT CLAIM from the
   role_cache.py — same           verified token to authorize — NO
   answer (D1 shared, R4.1)       request-time MySQL, NO S3 read needed
                                  for the per-user answer (S3 = tenant-level)

MySQL (S3 system of record) — the SOLE source the resolver reads. The Lambda's read is
at ISSUANCE, not on the API request path (so the S1 "no request-time MySQL from a module
Lambda" rule holds). Zero governance writes from S4.

DEFERRED: Pool B (singular tenant_id, no roles, no entitlement projection) — S4 targets
Pool A only and does not preclude Pool B.
```

## D1 — The pure resolver (single source of truth)

**Interface (pure, no I/O):**

```
resolve_entitlement(
    user_roles_by_tenant: Mapping[str, list[str]],   # tenant -> [role, ...]  (user_tenant_roles)
    active_modules_by_tenant: Mapping[str, list[str]],# tenant -> [module_name, ...] (is_active)
    module_registry: Mapping,                         # MODULE_REGISTRY (module -> required_roles etc.)
) -> EntitlementMap                                    # tenant -> resolved capabilities
```

- For each tenant the user belongs to, the resolved entitlement is the user's roles in
  that tenant **filtered/expanded against the tenant's active modules** and the
  module→role rules in `MODULE_REGISTRY`. A capability is present only if the user holds
  a role that grants it **and** the module that capability belongs to is active for that
  tenant. Roles for inactive modules do not grant access.
- **Backing-agnostic:** the resolver reads `tenant_modules` activity + `MODULE_REGISTRY`
  role rules only; it never inspects a module's `backing` kind (a `sam` module resolves
  exactly like a `flask` one — the S1/S3 rule).
- **Pure + deterministic:** no DB, no clock, no env reads. The Lambda (D2) fetches the
  rows and passes them in; the resolver computes the answer. This makes it PBT-friendly
  (Property tests below) and lets the Flask plane reuse the identical function.
- **Equivalence to `role_cache.py` (R1.3/R4.1):** `role_cache.get_tenant_roles` returns
  a user's raw per-tenant roles; the module gate (`module_registry.has_module` +
  `required_roles`) is what turns roles into an access decision. The resolver composes
  exactly those two steps, so for any `(user, tenant)` its answer equals "what the Flask
  plane would allow." One rule, two carriers (server cache vs token).
- **Global roles (R1.4):** `SysAdmin` / `Administrators` / `System_CRUD` come from
  `cognito:groups` (S3 contract) and are not re-derived here. The resolver produces the
  **per-tenant** answer. (The claim MAY echo global roles for the module plane's
  convenience, but their authority remains the `cognito:groups` claim.)

## D2 — The Pre-Token-Generation Lambda (the projection mechanism)

- **Trigger:** a Cognito **Pre-Token-Generation** Lambda attached to **Pool A**. Use the
  **V2** trigger (adds claims to both ID and access tokens) so the access token the API
  path verifies carries the entitlement claim.
- **Flow (R2.1–R2.3):**
  1. Identify the user from the trigger event (the verified Cognito identity — `email` /
     `sub`).
  2. Read the user's source rows **read-only** from MySQL: their `user_tenant_roles`
     rows and, for the tenants involved, the active `tenant_modules`. This is the single
     MySQL touch, at **issuance** (not on the API request path).
  3. Call the D1 resolver to compute the per-tenant entitlement map.
  4. Encode it compactly (D3) and set it via `response.claimsAndScopeOverrideDetails`
     (V2) / `claimsToAddOrOverride` — **additively**; do not touch `cognito:groups` /
     `custom:tenants` (R2.4).
- **Fail-safe (R2.3):** on any resolution failure (DB unreachable, malformed rows), the
  Lambda **omits** the entitlement claim (fail-closed for entitlement — the request path
  sees no elevated per-tenant entitlement and falls back to whatever the token's other
  verified claims allow) and logs the failure by user identity (never secrets). It never
  stamps a partial/garbage claim. (Alternative "fail the issuance" is a documented knob;
  default is omit-and-log so a DB blip doesn't lock everyone out.)
- **Fail-fast config (R2.5):** DB connection + any registry config are resolved
  fail-fast (throw on missing) — no fallback that could resolve against the wrong
  database. Reuses the S2/S3 R4.1 discipline. (Superseded by amendment A: the reader is
  DynamoDB, resolved fail-fast via `GOVERNANCE_PROJECTION_TABLE` / `AWS_REGION`.)
- **Deployment (per steering `aws-accounts.md`):** the PreTokenGen Lambda is deployed
  to the **data account (506221081911)** alongside DynamoDB, so its projection read is
  **same-account** (no cross-account data access). Pool A (identity account
  344561557829) attaches its Pre-Token-Generation trigger to that Lambda
  **cross-account** — the trigger *invoke* is cross-account (an `aws_lambda_permission`
  lets Cognito invoke it), the *data* read is not. It does **not** live in the Flask
  request path; the resolver (D1) is shared code the Lambda and Flask plane both import.

## D3 — Claim shape, size budget, and versioning

**Claim (design default — revisit at build):** `custom:entitlements`, a compact JSON
(or a more compact encoding) with a version:

```
custom:entitlements = {
  "v": 1,                          # format version (R3.1) — readers check this
  "t": {                           # per-tenant resolved capabilities
    "<administration>": ["<cap>", ...],   # e.g. "GoodwinSolutions": ["FIN:read","FIN:write","STR:read"]
    ...
  }
}
```

- **Compactness (R3.2):** capabilities use short tokens (module:action) and only
  **active**-module capabilities are included. The encoding + a **bounded size budget**
  (well under Cognito's token-size limit; exact bytes chosen at build) are defined so a
  realistic multi-tenant admin stays within budget.
- **Over-budget behavior (R3.3):** if a user's resolved entitlement would exceed the
  budget, the claim is **not silently truncated**. Instead the Lambda sets a compact
  signal (e.g. `"overflow": true` + the tenant list) telling the reader to consult the
  **S3 DynamoDB projection / a server endpoint** for the full answer, or applies a
  defined compression. Correctness over completeness — a reader must never mistake a
  truncated claim for the whole entitlement.
- **Versioning (R3.1):** `v` lets readers evolve the format; a reader that doesn't
  recognize `v` ignores the claim and falls back (never mis-parses).

## D4 — Staleness and revocation (bounded, documented)

- **Computed at issuance; refreshes on renewal (R4.2):** the claim reflects MySQL at the
  moment the token was issued. An access change (role grant/revoke, module enable/
  disable) takes effect at the **next** token issuance (re-login or refresh). The
  **staleness window = the token lifetime** — bounded and documented, never unbounded.
  This mirrors S3/R5.8's staleness rule.
- **Revocation story (R4.3) — explicit decision (finalize at build):**
  - Keep the **access-token lifetime short** (e.g. matching the existing Pool A
    setting) so an entitlement downgrade is honored within that window naturally.
  - For **security-critical downgrades** that must be honored immediately (e.g. removing
    an admin), define one of: (a) forced global sign-out / token revocation for that
    user, or (b) a thin server-side check for the sensitive capability subset that
    re-validates against MySQL / the S3 projection on the highest-risk actions only.
  - Document which subset (if any) is treated as "check server-side, don't trust the
    token past X" vs "token is authoritative until expiry."
- **Consistency (R4.1):** because the token claim and `role_cache.py` share the D1
  resolver, they cannot disagree for the same MySQL state; the only difference is *when*
  each was computed (staleness), which D4 bounds.

## Components and Interfaces

- **`resolve_entitlement(...)` (D1)** — pure resolver; the single resolution rule.
  Lives in shared backend code (e.g. `backend/src/auth/entitlement_resolver.py`) so both
  the Lambda and the Flask plane import it.
- **PreTokenGen Lambda handler (D2)** — reads MySQL read-only, calls the resolver,
  stamps the claim; fail-safe + fail-fast. Packaged for deployment to the identity
  account and attached to Pool A (test pool first).
- **Claim codec (D3)** — encode/decode + version + size-budget check + over-budget
  signal; used by the Lambda (encode) and by readers (decode).
- **Reader helpers** — module plane (`sam/shared/auth_utils.py`): read + decode the
  entitlement claim from the verified token; Flask plane: optional helper that prefers
  the claim and falls back to `role_cache.py`, guaranteed same decision (R5.3).

## Data Models

Source (MySQL, S3 system of record — read-only here):

```
user_tenant_roles(email, administration, role)     -- the user's per-tenant role grants
tenant_modules(administration, module_name, is_active) -- which modules a tenant enabled
MODULE_REGISTRY (in code)                            -- module -> required_roles / rules
```

Output (token claim, D3): `custom:entitlements` = `{ v, t: { tenant -> [cap,...] }, [overflow] }`.

## Correctness Properties

> Scope: property-based testing applies to the **pure resolver (D1)** — a data
> transformation over a large structured input space (tenants × modules × roles). It
> does **not** apply to the Lambda's Cognito wiring (integration test against the test
> pool), the claim size budget (example + boundary tests), or the revocation policy
> (documented decision + example tests). MySQL is faked/in-memory so properties test
> logic, not the datastore. Library: Hypothesis (Python). Minimum **100 iterations** per
> property. Tag each: **Feature: s4-token-entitlement-projection, Property {N}: {text}**.

### Property 1: Resolver equivalence to the Flask plane
*For any* generated `(user_tenant_roles, tenant_modules, module_registry)` state, the
resolver's decision for every `(user, tenant, capability)` equals the Flask plane's
decision (`role_cache` roles filtered by the module gate). One rule, two carriers.
**Validates: R1.3, R4.1**

### Property 2: Only active-module capabilities are entitled
*For any* state, no capability of an **inactive** (or absent) module for a tenant appears
in that tenant's resolved entitlement; disabling a module removes exactly its
capabilities and nothing else.
**Validates: R1.1**

### Property 3: Tenant isolation of entitlement
*For any* multi-tenant state, a user's resolved capabilities for tenant `T` depend only
on their roles in `T` and `T`'s active modules — never on another tenant's roles/modules.
**Validates: R1.1 (per-tenant scoping)**

### Property 4: Purity / determinism (idempotent resolution)
*For any* state, resolving twice yields an identical entitlement map (no I/O, no order
dependence); the resolver is a deterministic function of its inputs.
**Validates: R1.2**

### Property 5: Compact claim round-trips and respects the budget
*For any* resolved entitlement, encode→decode is identity, the encoded claim either fits
the size budget or sets the over-budget signal (never silently truncates), and a decoder
on an unknown `v` falls back rather than mis-parsing.
**Validates: R3.1, R3.2, R3.3**

## Error Handling

- **Resolution failure in the Lambda (D2):** omit the claim (fail-closed for
  entitlement) + log by user identity; never stamp a partial claim (R2.3).
- **Fail-fast config:** missing DB/registry config throws at Lambda init — no fallback
  to a wrong datastore (R2.5).
- **Over-budget claim:** signal overflow, do not truncate (R3.3).
- **Unknown claim version on read:** reader ignores the claim and falls back
  (Flask → role_cache.py; module → deny/omit or consult S3), never mis-parses.
- **Verification:** unchanged from S2 — entitlement is read only from a
  signature-verified token (R5.1); a verification failure is still 401.

## Testing Strategy

**Property-based (resolver, D1):** Hypothesis, ≥100 iterations, one test per Property
1–5; MySQL faked in-memory; generators produce tenants × modules × roles incl. edge
cases (no tenants, tenant with no active modules, roles for inactive modules, duplicate
roles, unicode emails, a large multi-tenant user for the size budget).

**Unit (example):** the claim codec (encode/decode/version/over-budget boundary); the
fail-safe Lambda path (resolution error → claim omitted, logged); the Flask reader helper
(claim present → same decision as role_cache.py; claim absent → falls back).

**Integration (Cognito, not PBT):** 1–3 examples against the **test pool** — a test-pool
user with seeded `user_tenant_roles` / `tenant_modules` logs in; the issued token carries
the expected `custom:entitlements`; the existing `cognito:groups` / `custom:tenants` are
unchanged; the module plane reads the claim from the verified token and authorizes
correctly. Reuse the S2/S3 test harness.

**Consistency check:** for seeded states, assert the token's resolved answer equals
`role_cache.py` + module gate for the same `(user, tenant)` (R4.1) — the cross-carrier
equivalence, end to end.

**Test-first + gated:** all of the above run against the test pool + Docker MySQL first;
the Pool A trigger is attached only after they pass, with detach-to-rollback.

## Governance delta (R7)

- **Architecture/auth steering** (extend `architecture.md` / `authentication.md`):
  entitlement is projected into the token at issuance (not read from MySQL per request);
  the token is the per-user path, the S3 DynamoDB projection is the tenant-level path
  (do not conflate); the single shared resolver; the bounded-staleness + revocation
  decision.
- **ADR 0006** (next after 0005, append-only): "resolved per-tenant entitlement projected
  into the Pool A token via a Pre-Token-Generation Lambda; one resolver shared with
  `role_cache.py`; bounded staleness + revocation policy; Pool B deferred (no entitlement
  claim)."
- Steering + ADR are authored as **tasks** in `tasks.md`, not by this design.

## Test matrix (drives tasks + acceptance)

| Case | Surface | Expected |
| --- | --- | --- |
| Resolver vs Flask decision | D1 Property 1 | identical decision for every (user, tenant, capability) |
| Inactive module's capabilities | D1 Property 2 | never entitled; disabling removes exactly its caps |
| Cross-tenant independence | D1 Property 3 | tenant T entitlement unaffected by other tenants |
| Resolve twice | D1 Property 4 | identical map (pure/deterministic) |
| Encode/decode + budget | D3 Property 5 | round-trips; fits budget or signals overflow; unknown v → fallback |
| Test-pool login | D2 integration | token carries custom:entitlements; groups/tenants unchanged |
| Module reads claim | R5.2 | authorizes from verified token; no request-time MySQL |
| Resolution failure at issuance | D2 | claim omitted (fail-closed), logged; no partial claim |
| Missing DB/registry config | D2 | fail-fast throw; no wrong-datastore fallback |
| Over-budget user | D3 | overflow signal, not truncation |
| Access change then re-login | D4 | new token reflects change; staleness bounded by token lifetime |
| Security-critical revocation | D4 | honored per the documented revocation policy |
