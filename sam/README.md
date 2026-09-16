# `sam/` — Module-plane shared auth (S2)

This folder holds the **self-contained module-plane** authentication code for the
h-dcn SAM stack (the `members` / `events` / `webshop` modules, one shared
deployment). It is developed **inside myAdmin** so the two planes stay in lockstep,
then **vendored/imported by h-dcn** (as a shared module or a Lambda layer). The h-dcn
SAM stack workspace itself is external and is **left as-is** — nothing here modifies
it.

## What this is

`sam/shared/auth_utils.py` is the **module-plane JWT verifier** (S2 / T8). It
**replaces the old base64-only decode** with **full JWKS-based RS256 signature
verification**, mirroring the myAdmin Flask plane's verification contract
(`backend/src/auth/`) — but **without importing `backend/src`**. It is a strict
drop-in for the module plane's `auth_utils.py`.

> **Scope (S2, module plane): signature verification only.** Reading tenant from the
> token (tenant-from-token binding) is **deferred to S5** (R2.4). Nothing here reads
> or trusts a tenant claim. Roles (`cognito:groups`) are read from the verified token.

## No client-supplied header is trusted for identity/roles (T9 — R2.1, R2.2)

The module plane trusts **no client-supplied header** as a source of truth for
identity, roles, or tenant. Specifically:

- **`X-Enhanced-Groups` trust is dropped.** The historical module-plane contract that
  let a caller assert its groups via an `X-Enhanced-Groups` header is **gone** — there
  is no code path that reads it (R2.2). Roles come **only** from the verified token's
  `cognito:groups`.
- **`X-Tenant` (and any similar header) is never consulted.** Tenant-from-token is
  **deferred to S5** (R2.4); this module does not read a tenant claim or a tenant
  header at all.
- The **only** request header this module reads is `Authorization` — solely to extract
  the raw bearer token, which is then **fully RS256-verified** (or, preferred, the
  request already passed through the API Gateway Cognito authorizer and the verified
  claims are read from the request context). No header is ever a source of identity or
  roles.

Handlers should obtain identity + roles through **one correct entry point**,
`get_verified_identity(event)`, which composes verified-claims reading with
`get_groups`. This gives a single header-free path and removes any temptation to read
`event["headers"]` for authorization.

## How it mirrors the Flask plane

| Flask plane (`backend/src/auth/`) | This module (`sam/shared/auth_utils.py`) |
| --- | --- |
| `pool_registry.py` (T3) — issuer→pool registry, env-driven, fail-fast, `.require(iss)` | `PoolRegistry` / `load_pool_registry` — same env contract (`COGNITO_POOL_KEYS` + per-pool `{KEY}_COGNITO_*`), same fail-fast, no defaults |
| `jwks_cache.py` (T4) — per-`iss` JWKS cache, single-refetch on `kid` miss, typed errors | `JWKSCache` — same behavior, held in **module/global scope** for warm Lambda reuse |
| `jwt_verifier.py` (T5) — RS256 + `iss` + `aud`/`client_id` + `exp` (30s leeway), unknown issuer/kid → 401, no fallback | `JWTVerifier` — identical verification contract; `get_global_verifier()` gives the warm-reuse singleton |

The **contract is identical**; only the cache lifetime shape differs (Flask =
always-on module cache; Lambda = execution-environment/global scope so warm
invocations reuse it and never fetch JWKS per request).

## Public API

```python
from sam.shared.auth_utils import get_verified_identity

def handler(event, context):
    identity = get_verified_identity(event)   # one correct, header-free entry point
    identity.sub                              # verified subject
    identity.groups                           # roles from verified cognito:groups only
    ...
```

Lower-level building blocks are still available if a handler needs the raw claims:

```python
from sam.shared.auth_utils import get_verified_claims, get_groups

def handler(event, context):
    claims = get_verified_claims(event)   # API-GW-authorizer preferred; else verify bearer
    groups = get_groups(claims)           # roles from verified cognito:groups
    ...
```

- `get_verified_claims(event, verifier=None)` — **prefers the API Gateway Cognito
  authorizer.** If the request passed through a Cognito authorizer, the already
  **verified** claims are read from `event.requestContext.authorizer.claims`
  (REST / HTTP v1) or `authorizer.jwt.claims` (HTTP v2) and returned **without
  re-verification**. Otherwise the raw `Authorization: Bearer` token is **verified
  here** via `JWTVerifier` (full RS256 + iss + aud + exp). **There is no
  base64-only path** — any in-handler decode always verifies.
- `get_groups(claims)` — roles from the verified `cognito:groups` (never from
  `X-Enhanced-Groups`).
- `get_verified_identity(event, verifier=None)` — **the recommended handler entry
  point.** Returns a `VerifiedIdentity(sub, email, groups, claims)` built purely from
  the verified token (composes `get_verified_claims` + `get_groups`). No header is
  consulted for identity/roles; no tenant is read (deferred to S5).
- `JWTVerifier`, `PoolRegistry`, `load_pool_registry`, `get_global_verifier`,
  `reset_global_verifier`, and typed errors (`InvalidTokenError` → 401,
  `ServiceUnavailableError` → 503, `UnknownIssuerError`, `UnknownKidError`,
  `PoolRegistryError`).

## No base64-only trust

The historical "decode the JWT payload and trust it" path is **removed**. Every code
path that yields claims either (a) reads API-Gateway-verified claims, or (b) runs a
full RS256 signature verification. A token that only "looks like" a JWT but is not
signed by the pool's current key is rejected with 401.

## Configuration (fail-fast, no defaults)

Pools are **configuration, not code** (region `eu-west-1`). Set:

```
COGNITO_POOL_KEYS=TEST                 # comma-separated pool keys
TEST_COGNITO_ISSUER=https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xxxxxxxxx
TEST_COGNITO_JWKS_URI=https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xxxxxxxxx/.well-known/jwks.json
TEST_COGNITO_CLIENT_ID=<app-client-id>
TEST_COGNITO_POOL_LABEL=myAdmin-test
```

Adding production Pool A (Phase 6) or Pool B (later) is: append its key to
`COGNITO_POOL_KEYS` and set its four vars. No code change. A missing/blank required
var **throws** — there is no silent default (no-dangerous-fallbacks). These are
public, non-secret Cognito identifiers; **no secrets are committed**.

## Dependencies

`PyJWT`, `cryptography`, `requests` — the same libraries as the Flask plane (see
`sam/shared/requirements.txt`). Ship these to Lambda via a layer or bundled deps.

## Tests

`sam/tests/` — self-contained unit tests (no import from `backend/src`). RS256 keys
are generated in-test and the JWKS fetch is mocked (no real network). Run:

```bash
source backend/.venv/bin/activate
pytest sam/tests -q
```
