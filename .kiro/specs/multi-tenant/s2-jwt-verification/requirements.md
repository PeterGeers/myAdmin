# S2 — Verify JWT Signatures on Both Planes — Requirements

- Status: Draft
- Roadmap step: S2 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Depends on: S1 (`s1-prepare-platform/` — the SAM-backed module plug-in contract;
  S2 fills the contract's Authorize seam).
- Decision of record: ADR 0003 (myAdmin is the platform base; import apps as
  SAM-backed modules).
- Sources: `myadmin_as_base.md` (auth prerequisite), `first_thoughts.md` §1,
  `environments_and_testing.md` (test environment), `identity.md` +
  `architecture.md` (steering).

## Goal

Both service planes must trust a request's identity **only** after verifying the
JWT's signature against the issuing Cognito pool. Stop treating unverified,
client-supplied headers as a source of truth. This is the non-negotiable security
foundation every later multi-tenant step assumes.

**S2 ships a product:** verified-JWT behavior **live in myAdmin production**. Per the
roadmap's design principle, a step is not done until its value is deployed and both
live systems keep working — S2 is not "tested code in a branch."

## The per-plane split (important)

Signature verification and tenant-claim handling are separable, and only one
transfers cleanly to the module plane today:

- **Signature verification** (verify signature + `iss`/`aud`/`exp`, read
  `cognito:groups`, stop trusting headers) needs **no tenancy** — it applies to
  **both planes now**.
- **Reading tenant from the verified token** needs a tenant dimension. The **myAdmin
  Flask plane** has it (myAdmin's `custom:tenants` + tenant key), so it lands now. The
  **module plane is not tenant-aware until S5**, so its tenant-from-token binding is
  **deferred to S5** — S2 gives the module plane signature verification only.

## Scope

- **Flask plane** (myAdmin — Flask/MySQL): **full S2** — confirm `jwt_verifier.py` on
  **every** authenticated route; read tenant/roles from the verified token; remove
  header trust. **Ships to myAdmin production** (gated).
- **Module plane** (the h-dcn SAM stack — the `members`, `events`, `webshop` modules
  sharing one SAM/Lambda deployment, code refactored in place): **signature
  verification only** — replace the base64-only decode in `auth_utils.py` (shared by
  the three modules); drop `X-Enhanced-Groups` trust.
  Tenant-from-token binding is **out of scope until S5**. The first module's
  production is greenfield/low-stakes (~one real user), so its deploy is low-risk.
- Validation happens against the **standing test Cognito pool** first, never
  directly on production Pool A (see `environments_and_testing.md`).

Out of scope: defining new claims (S3), token entitlement projection (S4), Pool B
creation, and the module plane's **tenant-claim** binding (S5). S2 only makes existing
tokens *trusted* and ships that to the Flask plane's production.

## Requirements

### R1 — Signature verification on every authenticated request
- **R1.1** Every authenticated route/handler on both planes verifies the JWT
  signature against the issuing pool's **JWKS** before reading any claim.
- **R1.2** Verification checks: signature (RS256 against JWKS), `iss` (issuer),
  audience/app-client (`aud` / `client_id`), and expiry (`exp`).
- **R1.3** A token failing any check is rejected with **401**; no fallback, no
  partial trust (fail-fast, per the no-dangerous-fallbacks guardrail).

### R2 — No trust in unverified headers
- **R2.1** `X-Enhanced-Groups`, `X-Tenant`, and any similar client-supplied header
  are **not** a source of truth for identity, roles, or tenant — **both planes**.
- **R2.2** Roles come only from the verified token's `cognito:groups` — both planes.
- **R2.3 (Flask plane, now)** Tenant comes only from the verified token
  (`custom:tenants`). Applies to the myAdmin Flask plane in S2.
- **R2.4 (module plane, deferred to S5)** The module plane reading tenant from the
  token requires tenant-awareness it does not have until S5. In S2 the module plane
  gets signature verification only; its tenant-from-token binding is **out of scope
  until S5**.

### R3 — Two issuers (multi-pool aware)
> **Pool naming:** "Pool A" / "Pool B" are **audience-role labels**, not pool names.
> Pool A is the existing Cognito pool **named `myAdmin`** (`eu-west-1_Hdp40eWmu`);
> Pool B is a distinct **future** end-user pool (not created in S2). See `identity.md`.
- **R3.1** Each backend determines which pool a token came from (via `iss`) and
  verifies against **that** pool's JWKS.
- **R3.2** A dedicated **standing test pool** is stood up as the *validation
  environment* (see R4, `environments_and_testing.md`), and the verifier is
  structured so pools are **configuration, not code** — adding a pool (the test pool,
  production Pool A, later Pool B) is a registry entry, not a code change. Which pools
  S2 must actually run against, and the requirement to end tested against the current
  production pool (Pool A, `eu-west-1_Hdp40eWmu`), are owned by **R4** (test-first,
  then gated promotion) and **R6** (shippable to production).
- **R3.3** JWKS is fetched and **cached** (not per request), with correct behavior
  on key rotation (cache miss → refetch).

### R4 — Test-environment first, then gated promotion (not test-only)
- **R4.1** All S2 verification is **developed and validated first** against the
  **test/dev environment**: the **standing test Cognito pool** (a permanent fixture of
  test/dev, alongside Docker MySQL + `test_` DynamoDB). The test pool is the
  validation environment for all identity work, never the destination.
- **R4.2** After test-pool validation passes, the verified-JWT behavior is
  **promoted to production and validated against the current production pool
  (Pool A, `eu-west-1_Hdp40eWmu`)** — real Pool A tokens verify against Pool A's JWKS
  in production and header-trust removal causes no regression. Promotion is gated on
  R4.1. "Test-first" means validate-then-promote — **not** stop at the test pool.
  (This corrects an earlier draft that ended S2 at test.)

### R6 — Shippable: the existing myAdmin production pool is updated in place
- **R6.0 (pool model — no new production pool)** S2 makes any required change to the
  **existing** myAdmin production pool — **Pool A**, the audience-role label for the
  Cognito pool **named `myAdmin`** (pool id `eu-west-1_Hdp40eWmu`) — updated
  **in place**. **No new production pool is created.** The standing **test pool**
  (R4/T1) is a **permanent part of the test/dev environment** (not a throwaway) that
  mirrors Pool A's app-client config, claim shapes, groups, and Pre-Token-Generation
  trigger (with throwaway test *users*), so identity work is validated there before it
  touches production Pool A. If S2 needs no pool-side change at all (verifier-only
  work), Pool A is still the pool the change is validated against in production.
- **R6.1** S2's definition of done includes **deploying** verified-JWT behavior to
  **myAdmin production** (the plane with real users) **and confirming it tested
  against the existing production pool (Pool A, `eu-west-1_Hdp40eWmu`)**, gated on R4
  test-pool validation. Deploying without validating against Pool A does not satisfy
  R6.1.
- **R6.2** The module plane also receives signature verification; its production is
  greenfield/low-stakes, and its **tenant-claim** completion is deferred to S5. So
  S2 leaves both live systems working and improved — the Flask plane fully hardened,
  the module plane signature-verified.
- **R6.3** S2 ships through myAdmin's existing production pipeline (myAdmin is the
  platform base, evolved in place — there is no separate trunk to cut over to, and no
  new production pool to migrate to). The point is the *behavior* reaches production
  on the existing pool.

### R5 — Governance updated on completion
- **R5.1** Auth steering records: verified-JWT-only, no unverified-header trust,
  issuer→pool JWKS verification.
- **R5.2** An ADR records the decision ("verified-JWT-only; no unverified-header
  trust; per-issuer JWKS verification").

## Acceptance criteria

- A token with a **valid signature** from the test pool is accepted; a token with a
  **tampered/invalid signature**, **wrong issuer**, **wrong audience**, or
  **expired** is rejected with 401 — on **both** planes (signature verification).
- Setting `X-Enhanced-Groups` / `X-Tenant` on a request has **no effect** on the
  authorization decision — both planes.
- No authenticated route/handler on either plane reads claims from an unverified
  token.
- **Flask plane:** tenant/roles are read from the verified token; verified-JWT
  behavior is **deployed and live in myAdmin production** (gated on test
  validation). myAdmin keeps working.
- **Module plane:** signature verification is in place (and deployed to its
  greenfield production); the tenant-from-token binding is explicitly deferred to
  S5 and does **not** block S2's completion.
- Auth steering + ADR exist and match the implemented behavior.

## Prerequisite (handled as task 1, not external)

The standing test Cognito pool must exist to test against. Per decision, **standing
it up is the first task of this spec** (`tasks.md` T1), so S2 is self-contained.
