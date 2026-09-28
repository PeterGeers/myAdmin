# Pool A Claim Contract — the platform identity contract (S3 T3 / D1 / R1.1)

Authoritative contract text for **Pool A's claim shape**. This is a deliverable of
**T3** in `tasks.md`, implements requirement **R1.1**, and realizes design **D1**
("Pool A claim contract"). It is written as **reusable, accurate contract text** so
Phase 6 governance (**T27** — extend `identity.md` / `architecture.md` or a scoped
tenant-data steering file; **T28** — ADR 0005) can fold it in without rework.

> Scope: this documents and *validates* an **existing** shape. S3 adds no verification
> code and no new claim; per-tenant roles and the per-user entitlement claim are out of
> scope here (the latter is **S4**). Grounded in the live code cited in each section.

## The contract (one table)

**Pool A** = the audience-role label for the Cognito pool **named `myAdmin`**
(`eu-west-1_Hdp40eWmu`, identity account). Its token carries exactly two governance
claims, and a third fact deliberately does **not** ride the token:

| Claim | Carries | Authority (source of truth) | Read via |
| --- | --- | --- | --- |
| `cognito:groups` | **GLOBAL roles only** — `SysAdmin` / `Administrators` / `System_CRUD` | the token | `cognito_utils.extract_user_credentials` → `cognito:groups`, then filtered to the three global roles in `cognito_required` |
| `custom:tenants` | the user's **list** of tenants (`administration` keys) | the token (mirrors MySQL) | `cognito_utils.get_verified_tenants` → `_normalize_tenants_claim` |
| *(per-tenant roles)* | **NOT in the token in S3** — the per-tenant role grants (`Finance_*`, `STR_*`, `ZZP_*`, `Tenant_Admin`) | **MySQL `user_tenant_roles`** | `auth/role_cache.py` `get_tenant_roles` (cached MySQL read) |

Effective roles for a request = **global roles (token) ∪ per-tenant roles (MySQL)**.
This union is assembled in `cognito_required`; a route's `required_roles` /
`required_permissions` are checked against it.

## 1. `cognito:groups` = GLOBAL roles only

The **only** roles that come from the token are the three platform-global roles.
`cognito_required` (`backend/src/auth/cognito_utils.py`) filters the token's groups to
exactly this set before doing anything tenant-scoped:

```python
global_roles = [
    r for r in user_roles
    if r in ("SysAdmin", "Administrators", "System_CRUD")
]
```

Their capabilities (from `ROLE_PERMISSIONS` in the same file):

- `Administrators` → wildcard `*` (full access).
- `System_CRUD` → wildcard `*` (full access).
- `SysAdmin` → system config / logs / audit / cache / templates / storage-manage
  **only** — deliberately **no tenant data** access. A `SysAdmin` token does **not**
  open Finance / STR / ZZP / tenant-admin screens; those need per-tenant role rows.

Any *other* group value on the token (e.g. a stray `Finance_CRUD` in `cognito:groups`)
is **not** treated as a global role — it is dropped by the filter above. Per-tenant
capability is granted only through MySQL (section 3), never by a group claim on the
token.

## 2. `custom:tenants` = the user's tenant list

`custom:tenants` is the **list** of tenants (`administration` keys) a Pool A user may
select. It is read only from the **cryptographically verified** token via
`get_verified_tenants`, which normalizes Cognito's several delivery shapes (real list,
JSON-encoded string, escaped-quote string) into a plain list of tenant names
(`_normalize_tenants_claim`). A client-supplied header (e.g. `X-Tenant`,
`X-Enhanced-Groups`) is **never** a source of truth for this list.

Selection: the request's `X-Tenant` header selects one tenant and is validated against
`custom:tenants` (`auth/tenant_context.py`); an unlisted tenant → **403**. So the token
bounds *which* tenants are reachable; it does **not** say what the user may *do* inside
one — that is section 3.

## 3. Per-tenant roles live in MySQL, not the token

The answer to "what may this user do in tenant `T`" is **not** in the token in S3. It is
resolved from MySQL `user_tenant_roles` by `auth/role_cache.py` `get_tenant_roles`:

```sql
SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s
```

(cached per `email:tenant` for 5 minutes; `invalidate_cache(email, tenant)` clears it on
a role change). `user_tenant_roles` (`email`, `administration`, `role`) is the
**system of record** for per-tenant grants — the `Finance_*` / `STR_*` / `ZZP_*` /
`Tenant_Admin` roles all resolve here, keyed by tenant. This is the Flask plane's
per-tenant role source; the module plane gets the tenant-level equivalent from the
read-only DynamoDB projection (D3), never a request-time MySQL query.

**Consequence:** enabling a module for a tenant is not enough — the user also needs the
matching role row in `user_tenant_roles` for that `administration`, and `X-Tenant` must
name a tenant in the verified `custom:tenants`.

## Pool selection is S2's, unchanged (config-not-code)

Both planes select Pool A by the token issuer (`iss`) through the **S2 issuer→pool
registry** (`backend/src/auth/pool_registry.py`): `COGNITO_POOL_KEYS` +
per-pool `{KEY}_COGNITO_ISSUER` / `_JWKS_URI` / `_CLIENT_ID` / `_POOL_LABEL`, **fail-fast,
no defaults**. Adding a pool (production Pool A in Phase 6, Pool B later) is a config
entry, not code. S3 adds **no** verification code — it validates that Pool A's claim
shape is read correctly through this existing path. A misconfigured registry makes
verification *unavailable* (no verifier); it never becomes a token-accepting fallback.

## Boundaries (what this contract deliberately excludes)

- **Entitlement-in-token is S4, not S3.** The *per-user resolved* per-tenant answer
  (roles ∩ enabled modules) stamped into the token by a Pre-Token-Generation Lambda is
  **S4**. S3 names it as a dependency and adds **no** per-tenant role or entitlement
  claim to the token. Do not conflate S4's *token* projection with S3's *tenant-level
  DynamoDB* projection (D3) — different data, different mechanism.
- **Pool B is deferred.** Pool B (a future greenfield end-user pool) would carry a
  **singular** `tenant_id` claim, no roles, no entitlement projection. S3 does not build
  it; the S2 registry already makes adding it config-only, so this contract must not
  preclude it.
- **No new group-as-permission channel.** Only the three global roles are honored from
  `cognito:groups`; per-tenant authority never travels on the token in S3.

## Grounding (verified in code)

- `backend/src/auth/cognito_utils.py` — `ROLE_PERMISSIONS` (global roles + their
  capabilities); `cognito_required` (global-role filter to `SysAdmin` / `Administrators`
  / `System_CRUD`, and the global ∪ per-tenant union); `get_verified_tenants` /
  `_normalize_tenants_claim` (`custom:tenants` as a list, verified-token-only).
- `backend/src/auth/role_cache.py` — `get_tenant_roles` (per-tenant roles from
  `user_tenant_roles`, cached; `invalidate_cache`).
- `backend/src/auth/pool_registry.py` — the S2 issuer→pool registry (select Pool A by
  `iss`, config-not-code, fail-fast).
- `backend/src/auth/tenant_context.py` — `X-Tenant` selection validated against the
  verified `custom:tenants` (unlisted → 403).

## References

- `requirements.md` → **R1.1** (this contract), R1.3 (per-tenant roles in MySQL), R6.1
  (steering records it).
- `design.md` → **D1 "Pool A claim contract"** (the claim-shape table this expands).
- `tasks.md` → **T3** (this task), **T27** (fold into steering), **T28** (ADR 0005).
- Steering to extend in Phase 6: `.kiro/steering/identity.md`,
  `.kiro/steering/architecture.md`, `.kiro/steering/authentication.md`.
