# S2 — Verify JWT Signatures on Both Backends — Design

- Status: Draft
- Companion to `requirements.md` (same folder). Implements R1–R5.

## Overview

Both planes converge on the same verification contract: **fetch the issuing pool's
JWKS, verify the token's signature + standard claims, then read identity/roles/
tenant only from the verified token.** The admin plane already has the pieces
(`jwt_verifier.py`); the portal plane must gain them (replacing a base64-only
decode). A small shared notion — an issuer→pool registry — makes both planes
multi-pool aware without hard-coding one pool.

## Verification contract (both planes)

Given an incoming access token:

1. Decode the header + unverified `iss` (issuer) only to select the pool.
2. Look up the pool config by `iss` (issuer→pool registry, R3). Unknown issuer →
   reject 401.
3. Fetch that pool's **JWKS** (cached; see below), select the signing key by `kid`.
4. Verify: **RS256 signature**, `iss`, audience/`client_id`, `exp` (and `token_use`
   = `access` where applicable). Any failure → **401, no fallback** (R1.3).
5. Only now read claims: `sub`, `email`, `cognito:groups` (roles),
   `custom:tenants` / `tenant_id` (tenant). Never from headers (R2).

## Issuer → pool registry (R3)

- A small config map: `iss` → `{ jwks_uri, audience/client_id, pool_label }`.
- Populated per environment via fail-fast env vars (missing → throw, no default).
- **Now:** the test pool. **Later:** add Pool A, then Pool B — configuration only,
  no code change (R3.2).
- Both planes read the same conceptual registry (each in its own language).

## JWKS fetch + cache (R3.3)

- Fetch JWKS from the pool's `jwks_uri`; cache in memory keyed by `iss`.
- **Admin (Flask, always-on):** module-level cache with a TTL; refresh on TTL
  expiry or on a `kid` cache-miss (handles key rotation).
- **Portal (Lambda):** cache in the execution-environment/global scope so warm
  invocations reuse it; `kid` miss → refetch once. Never fetch JWKS per request on
  the hot path.
- Rotation: an unknown `kid` triggers exactly one refetch; if still unknown → 401.

## Admin plane (Flask/MySQL, `mysaas/admin/`)

- **Reuse** `jwt_verifier.py` (already checks issuer + app-client id). Extend it to
  the issuer→pool registry so it can verify test-pool tokens now and multiple pools
  later.
- **Audit every authenticated route** for verifier coverage; the auth/tenant
  decorators (`@cognito_required` / `@tenant_required` or equivalent) must sit on
  all of them (R1.1). Close any gaps.
- **Remove header trust:** roles/tenant read from the verified token, not
  `X-Enhanced-Groups` / `X-Tenant` (R2).
- Lands in `mysaas/admin/` (per S1b — written once on the trunk), validated against
  the test pool.

## Portal plane (SAM/Lambda, h-dcn origin) — signature verification only in S2

- **Replace** the base64-only decode in `auth_utils.py` with full JWKS verification
  per the contract above (signature + `iss`/`aud`/`exp`).
- Prefer verification at the **API Gateway Cognito authorizer** where possible, with
  the handler still reading claims only from the verified context; any in-handler
  decode must verify (never base64-only).
- **Drop `X-Enhanced-Groups` trust**; derive groups from the verified token.
- **Tenant-from-token is deferred to S5.** The portal is not tenant-aware yet, so
  there is nothing for a `tenant` claim to bind to. S2 delivers signature
  verification only on the portal; tenant scoping (partition key / LeadingKeys) and
  reading tenant from the token both come with S5.
- Portal production is greenfield/low-stakes (~one real user), so deploying the
  signature-verification change there is low-risk.

## Failure behavior (R1.3)

- Any verification failure → **401 Unauthorized**, generic message, no claim leakage
  in the error, no fallback path. Log the failure reason server-side (not the token).

## Where code lands / environment (R4)

- Admin verification code: `mysaas/admin/` (trunk), per S1b.
- Portal verification code: portal origin (h-dcn) until its own lift; the *contract*
  is identical either way.
- All verification is **developed and validated first** against the **test Cognito
  pool** + Docker MySQL + `test_` DynamoDB.

## Gated promotion to production (R4.2, R6) — makes S2 shippable

Test-first means validate-then-promote, not stop-at-test. After the test matrix
passes:

- **Admin plane → myAdmin production (the shippable outcome).** Promote the
  verified-JWT behavior to production myAdmin, gated on: test matrix green, a
  staging/dry-run pass, and a rollback path. Independent of S6b — ships through
  whatever pipeline currently deploys myAdmin production; the point is the behavior
  reaches real users.
- **Portal plane → its (greenfield) production.** Deploy the signature-verification
  change; low-stakes given ~one real user. Its tenant-claim completion is S5, not a
  blocker for S2.
- **Gate to add Pool A as a verified issuer:** once production myAdmin verifies
  against Pool A's JWKS (not only the test pool), confirm real Pool A tokens pass and
  the header-trust removal has no regression before considering S2 done.

## Governance delta (R5)

- **Auth steering** (extend `identity.md` / `architecture.md` or a dedicated
  `authentication.md`): verified-JWT-only, no unverified-header trust, issuer→pool
  JWKS verification, cached JWKS + rotation.
- **ADR**: "Verified-JWT-only; no unverified-header trust; per-issuer JWKS
  verification." Append-only.

## Test matrix (drives tasks + acceptance)

Per plane, against the test pool:

| Case | Expected |
| --- | --- |
| Valid signature, correct iss/aud, not expired | Accept |
| Tampered / invalid signature | 401 |
| Wrong issuer (unknown pool) | 401 |
| Wrong audience / client_id | 401 |
| Expired token | 401 |
| Unknown `kid` (rotation) | refetch once → accept if now known, else 401 |
| `X-Enhanced-Groups` / `X-Tenant` set on request | ignored — no effect on decision |
