# ADR 0004 — Verified-JWT-only; no unverified-header trust; per-issuer JWKS verification

- Status: Accepted
- Date: 2026-09-15
- Relates to: ADR 0003 (myAdmin is the platform base; import apps as SAM-backed
  modules) — S2 fills the Authorize seam of that module contract.

## Context

Both service planes — the Flask / MySQL plane (myAdmin) and the SAM-backed module
plane (the h-dcn stack: members/events/webshop) — needed to establish request
identity before doing anything else. The starting state was insecure:

- The module plane decoded the JWT **base64-only**, reading claims from an
  **unverified** token — the signature was never checked.
- Both planes could be influenced by **client-supplied headers**
  (`X-Enhanced-Groups`, `X-Tenant`) treated as a source of truth for roles/tenant.
  Anything a client can set is trivially forgeable.

This is the non-negotiable security foundation every later multi-tenant step (S3–S5)
assumes, so it had to be settled before building on top of it.

## Decision

**Trust identity only from a signature-verified token; never from unverified
headers.** On **both planes**:

- **Verify before reading any claim.** Check the **RS256 signature** against the
  issuing pool's **JWKS**, plus `iss`, audience / `client_id` (`aud`), and `exp`
  (30s leeway). Read claims (`cognito:groups`, `custom:tenants`, …) only after the
  token verifies.
- **Per-issuer verification via a registry.** A request's pool is selected by its
  `iss` and verified against **that** pool's JWKS. The registry is **configuration,
  not code**, env-driven and **fail-fast** (`COGNITO_POOL_KEYS` + per-pool
  `{KEY}_COGNITO_*`; missing required vars throw at startup). Adding a pool is a
  config entry, never a code change.
- **Cached JWKS with rotation handling.** JWKS is cached by `iss` (not fetched per
  request); an unknown `kid` triggers exactly one refetch, then 401 if still unknown.
- **No dangerous fallback.** Any verification failure → **401**, no partial-trust or
  unverified-decode path.
- **No unverified-header trust.** `X-Enhanced-Groups` is dropped; `X-Tenant` is only a
  *selector* among tenants the verified token already grants, never the grant itself.
  Roles come from verified `cognito:groups`; tenant (Flask plane) from verified
  `custom:tenants`.

## Rationale

- A base64-only decode is not authentication — signature verification against the
  issuing pool's JWKS is the only way to know a token is genuine and unexpired.
- Client-supplied headers are attacker-controlled; using them for authorization is a
  privilege-escalation and tenant-crossing hole.
- Selecting the pool by `iss` and keeping pools in a fail-fast, env-driven registry
  makes the platform multi-pool aware (test pool, Pool A, later Pool B) without
  hard-coding a single pool or shipping code to add one.
- Fail-fast with no fallback keeps failure modes safe: a bad token is rejected, never
  silently downgraded to partial trust.

## Consequences

- **Both planes trust only verified tokens.** The Flask plane is fully hardened and
  **live in myAdmin production** (signature verification on every authenticated route;
  tenant + roles from the verified token; header trust removed), validated against
  production Pool A (`eu-west-1_Hdp40eWmu`, app client `66tp0087h9tfbstggonnu5aghp`) —
  forged/unsigned tokens → 401, real Pool A tokens → 200.
- **Adding a Cognito pool is configuration**, not a deployment of new code — a registry
  entry via env vars.
- **The module plane is signature-verification-only in S2**, delivered through the
  self-contained `sam/` module vendored by SAM-backed modules. Reading **tenant** from
  the token needs tenant-awareness the module plane does not yet have, so the
  **module-plane tenant-from-token binding is deferred to S5**.
- Later steps build on this foundation: new claims (S3), token entitlement projection
  (S4), and the module plane's tenant-claim binding (S5).

## Related

- ADR 0003 (platform base; module contract — S2 implements its Authorize seam).
- Steering: `.kiro/steering/authentication.md`, `identity.md`, `architecture.md`.
- Spec: `.kiro/specs/multi-tenant/s2-jwt-verification/` (requirements + design).
