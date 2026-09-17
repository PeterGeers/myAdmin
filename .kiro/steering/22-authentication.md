---
inclusion: auto
---

# Authentication — Verified-JWT-Only

> Active-rules summary. Full reasoning:
> `.kiro/specs/multi-tenant/s2-jwt-verification/` and `Analysis/first_thoughts.md` §1.
> Decision of record: **ADR 0004** (verified-JWT-only; no unverified-header trust;
> per-issuer JWKS verification). Identity model: `21-identity.md`; two-plane picture:
> `20-platform-architecture.md`. Current phase/status: `00-index.md`.

Every backend trusts a request's identity **only** after verifying the JWT signature
against the issuing Cognito pool's JWKS. This holds on **both planes** — the Flask /
MySQL plane (myAdmin) and any SAM-backed module plane.

## Verify before reading any claim

- Verify the JWT **before** reading any claim. No claim (`sub`, `email`,
  `cognito:groups`, `custom:tenants`, …) is trusted until the signature checks out.
- Verification contract: **RS256 signature** against the issuing pool's JWKS, plus
  `iss` (issuer), audience / `client_id` (`aud`), and `exp` (30s leeway).
- **Fail-fast, no dangerous fallback.** Any failed check → **401**. Never fall back
  to an unverified decode, a partial-trust path, or a default identity.

## Issuer → pool registry (config, not code)

- A request's pool is selected by its **`iss`**, then verified against **that** pool's
  JWKS. Unknown issuer → 401.
- Pools are **configuration, not code** — adding a pool (the standing test pool,
  production Pool A, later Pool B) is a registry entry, never a code change. Pool +
  app-client identifiers are documented in `23-aws-accounts.md`.
- The registry is **env-driven and fail-fast**: `COGNITO_POOL_KEYS` lists the pool
  keys; each pool's config comes from per-pool `{KEY}_COGNITO_*` vars. Missing/empty
  required vars → throw at startup (no defaults, no silent skip).

## Cached JWKS + rotation

- JWKS is **fetched and cached** keyed by `iss` — never fetched per request on the
  hot path.
  - Flask plane: module-level cache + TTL.
  - Module plane (Lambda): execution-environment / global scope, reused across warm
    invocations.
- **Rotation:** an unknown `kid` triggers **exactly one** refetch; if the key is still
  unknown after the refetch → 401.

## No unverified-header trust

- `X-Enhanced-Groups`, `X-Tenant`, and any similar client-supplied header are **not**
  a source of truth for identity, roles, or tenant — on **both planes**.
- Roles come only from the verified token's `cognito:groups`.
- Tenant comes only from the verified token's `custom:tenants` (Flask plane).
- `X-Tenant` may act **only** as a *selector* among tenants the verified token already
  grants — never as the grant itself. `X-Enhanced-Groups` is dropped entirely.

## Plane status

Point-in-time status is tracked in `00-index.md`. In summary: the Flask plane is fully
hardened and live in production (signature verification on every authenticated route;
tenant + roles from the verified token; header trust removed), validated against Pool A
(pool `eu-west-1_Hdp40eWmu`, app client `myAdmin-client`, id
`66tp0087h9tfbstggonnu5aghp`). The module (SAM) plane ships signature-verification via
the self-contained `sam/shared` toolkit; reading **tenant** from the token on the module
plane is wired with the first app migration (S5).
