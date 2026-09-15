# S2 — Verify JWT Signatures on Both Backends — Requirements

- Status: Draft
- Roadmap step: S2 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
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
transfers cleanly to the portal today:

- **Signature verification** (verify signature + `iss`/`aud`/`exp`, read
  `cognito:groups`, stop trusting headers) needs **no tenancy** — it applies to
  **both planes now**.
- **Reading tenant from the verified token** needs a tenant dimension. The **admin
  plane** has it (myAdmin's `custom:tenants` + tenant key), so it lands now. The
  **portal plane is not tenant-aware until S5**, so its tenant-from-token binding is
  **deferred to S5** — S2 gives the portal signature verification only.

## Scope

- **Admin plane** (Flask/MySQL, in `mysaas/admin/`): **full S2** — confirm
  `jwt_verifier.py` on **every** authenticated route; read tenant/roles from the
  verified token; remove header trust. **Ships to myAdmin production** (gated).
- **Portal plane** (SAM/Lambda, h-dcn origin): **signature verification only** —
  replace the base64-only decode in `auth_utils.py`; drop `X-Enhanced-Groups` trust.
  Tenant-from-token binding is **out of scope until S5**. Portal production is
  greenfield/low-stakes (~one real user), so its deploy is low-risk.
- Validation happens against the **standing test Cognito pool** first, never
  directly on production Pool A (see `environments_and_testing.md`).

Out of scope: defining new claims (S3), token entitlement projection (S4), Pool B
creation, and the portal **tenant-claim** binding (S5). S2 only makes existing
tokens *trusted* and ships that to the admin plane's production.

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
- **R2.3 (admin plane, now)** Tenant comes only from the verified token
  (`custom:tenants`). Applies to the admin plane in S2.
- **R2.4 (portal plane, deferred to S5)** The portal reading tenant from the token
  requires tenant-awareness it does not have until S5. In S2 the portal gets
  signature verification only; its tenant-from-token binding is **out of scope until
  S5**.

### R3 — Two issuers (multi-pool aware)
- **R3.1** Each backend determines which pool a token came from (via `iss`) and
  verifies against **that** pool's JWKS.
- **R3.2** S2 must work with the **test pool** now, and be structured so adding
  Pool A / Pool B issuers is configuration, not code change.
- **R3.3** JWKS is fetched and **cached** (not per request), with correct behavior
  on key rotation (cache miss → refetch).

### R4 — Test-environment first, then gated promotion (not test-only)
- **R4.1** All S2 verification is **developed and validated first** against the test
  Cognito pool + Docker MySQL + `test_` DynamoDB.
- **R4.2** After test validation passes, the verified-JWT behavior is **promoted to
  production**, gated. "Test-first" means validate-then-promote — **not** stop at
  test. (This corrects an earlier draft that ended S2 at test.)

### R6 — Shippable: verified JWTs live in myAdmin production
- **R6.1** S2's definition of done includes **deploying** verified-JWT behavior to
  **myAdmin production** (the plane with real users), gated on R4 test validation.
- **R6.2** The portal plane also receives signature verification; its production is
  greenfield/low-stakes, and its **tenant-claim** completion is deferred to S5. So
  S2 leaves both live systems working and improved — the admin plane fully hardened,
  the portal signature-verified.
- **R6.3** S2 does not depend on S6b (the admin CI/CD source cutover). S2 ships
  through whatever pipeline currently deploys myAdmin production; the point is the
  *behavior* reaches production.

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
- **Admin plane:** tenant/roles are read from the verified token; verified-JWT
  behavior is **deployed and live in myAdmin production** (gated on test
  validation). myAdmin keeps working.
- **Portal plane:** signature verification is in place (and deployed to its
  greenfield production); the tenant-from-token binding is explicitly deferred to
  S5 and does **not** block S2's completion.
- Auth steering + ADR exist and match the implemented behavior.

## Prerequisite (handled as task 1, not external)

The standing test Cognito pool must exist to test against. Per decision, **standing
it up is the first task of this spec** (`tasks.md` T1), so S2 is self-contained.
