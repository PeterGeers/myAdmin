# myAdmin as the Base — Platform Architecture (Modules unified by identity)

> Core companion doc in the multi-tenant analysis set (with `first_thoughts.md`,
> `rewrite_vs_refactor.md`, `tenant_field_config.md`). It establishes **why myAdmin
> is the platform base and what target architecture results** when additional apps
> are hosted as modules unified by one identity. Analysis grounded in a read of
> `/home/peter/projects/myAdmin`; no code changed by this document.
>
> **Settled model (2026-09-15):** myAdmin **is the platform base, evolved in place**
> — not a pattern source for some other trunk. Additional apps (e.g. the h-dcn
> portal) are imported as **SAM-backed modules** of myAdmin, keeping their
> serverless/DynamoDB stack. Two decisions from `second_thoughts.md` (and ADR 0003)
> apply throughout:
>
> 1. **Identity is two pools, not one.** Where this doc says "one unified Cognito
>    pool" / "one identity plane", read it as the **audience-split** model — **Pool
>    A** (admin/staff: roles + `custom:tenants` + entitlement projection; the
>    universal, always-present plane) and **Pool B** (end-users: a single
>    `tenant_id` claim, no roles; an *optional per-tenant capability* that maps to a
>    `tenant_modules` flag). Both planes still verify signatures and read a
>    consistent claim contract — the linchpin argument here is unchanged; it just
>    spans two pools/issuers. See `second_thoughts.md`, "Identity model rethink".
> 2. **myAdmin is the trunk; the h-dcn domain is imported as SAM-backed modules.**
>    myAdmin's own code is the platform base (ADR 0003). The h-dcn domain is imported
>    as **three SAM-backed modules — `members`, `events`, `webshop` — sharing one SAM
>    stack** (one Lambda/DynamoDB deployment, one API base) on the serverless plane,
>    using myAdmin's multi-tenant patterns — not merged into the Flask/MySQL plane.
>    Each module is entitled independently via `tenant_modules`.

## What myAdmin actually is (verified)

- **Domain:** financial/bookkeeping software — invoice import + AI extraction,
  banking (CSV) processing, short-term-rental (Airbnb/Booking) revenue and
  pricing, P&L / balance-sheet / tax reports. It shares NONE of H-DCN's domain
  (no members, regions, webshop, products, orders, events, club logic).
- **Stack:** Flask (Python 3.11) monolith on **MySQL**, with AWS Cognito, SNS,
  SES, S3, and a little DynamoDB. Railway-style deployment (per migration
  comments). Scale: ~307 backend `.py` files, ~507 frontend TS/TSX files.
- **Shares lineage with H-DCN:** same Cognito admin scripts
  (`assign_hdcn_leden_role_to_existing_users.py`, `fix_webmaster_roles.py`,
  `create_verzoek_lid_group.py`), similar docs layout and role vocabulary
  (`*_Read` / `*_CRUD` / `*_Export`).

## What myAdmin already solves that H-DCN does not

myAdmin is **genuinely, maturely multi-tenant** using a pooled model:

- **Tenant key on every table:** an `administration VARCHAR` column added
  system-wide via `backend/sql/phase1_multitenant_schema.sql` (default backfill
  `'GoodwinSolutions'`). This is the pooled tenant-key model described as
  "Option B" for H-DCN — already built.
- **Tenant metadata + governance tables:** `tenants` (id, `administration`
  unique, display_name, status, contact, plan), `tenant_modules` (which modules a
  tenant has enabled), `user_tenant_roles` (per-user, per-tenant role grants —
  `email`, `administration`, `role`), and `tenant_template_config` (per-tenant
  `template_type` + JSON `field_mappings`, with versioning) — the latter is
  essentially the tenant-field-overlay concept from `tenant_field_config.md`, already
  implemented.
  - **Note (verified 2026-09-15):** the shipped per-tenant-roles feature moved
    per-tenant authorization **out of the JWT into `user_tenant_roles`** (MySQL),
    read via a cached lookup (`backend/src/auth/role_cache.py`, 5-min TTL). Only
    **global** roles (`SysAdmin`, `Administrators`, `System_CRUD`) still come from
    `cognito:groups`. The earlier `tenant_role_allocation` table is **retired** —
    available roles are derived from `tenant_modules` + Cognito groups. Where this
    doc below says "roles come from `cognito:groups`," read it as "global roles from
    the JWT; per-tenant roles from `user_tenant_roles`."
- **A dedicated tenant-context layer** (`backend/src/auth/tenant_context.py`):
  `get_user_tenants(jwt)`, `get_current_tenant(request)`,
  `validate_tenant_access()`, `is_tenant_admin()`, and a `@tenant_required`
  decorator that extracts the tenant, validates access, and injects
  `tenant` + `user_tenants` into each route. Routes then scope with
  `WHERE administration = %s`.
- **Tenant identity via a Cognito `custom:tenants` claim** — a real multi-tenant
  auth design, versus H-DCN's flat, global Cognito group namespace.

## The two caveats to design around

1. **Different domain.** Building the platform *on* myAdmin means keeping its tenancy
   + auth + admin scaffolding and hosting the h-dcn domain as a **SAM-backed module**
   on the serverless/DynamoDB plane — not rebuilding it inside the Flask/MySQL plane.
   The domain code stays where it is optimal; myAdmin provides the tenancy, identity,
   and module machinery it plugs into.
2. **Same auth security weakness as H-DCN.** `get_user_tenants` base64-decodes the
   JWT **without verifying the signature**, and `get_current_tenant` trusts an
   `X-Tenant` header. The structure is right (tenant claim, validation,
   decorator) but verification is missing — a forged token could claim any
   tenant. (Also: the docstring references
   `.kiro/specs/Common/Multitennant/architecture.md`, which does not exist at
   that path — a stale reference; the implementation itself is real.)

Also note the stack mismatch: myAdmin is Flask+MySQL (always-on server), the portal
is serverless Lambda+DynamoDB (on-demand). This is exactly why the portal is hosted
as a **SAM-backed module** on its own plane rather than folded into Flask/MySQL —
forcing the portal onto MySQL would adopt an always-on cost/connection profile that
does not suit it (see `rewrite_vs_refactor.md`, "Do not switch to SQL"). The two
planes are a feature, not a compromise.

## The unifying assumptions (the platform direction)

The remaining analysis assumes all of the following are in place:

1. **A consistent Cognito identity plane** across both systems. *(Reconciled: this
   is now two audience-split pools — Pool A admin/staff, Pool B optional
   per-tenant end-users — not one unified pool. Both are verified and read through
   a consistent claim contract; see the banner and `second_thoughts.md`.)*
2. **A tenant-claim model** on the token (Pool A: `custom:tenants` list +
   `cognito:groups` roles; Pool B: a single `tenant_id` claim), read consistently
   by both backends per pool.
3. **JWT signature verification** implemented on both backends (verify against the
   pool JWKS; stop trusting client-supplied headers like `X-Tenant` /
   `X-Enhanced-Groups` as the source of truth).
4. **Frontend accesses services by UI need** — one token, calls whichever backend
   owns the screen's domain.

With these, the two hard prerequisites flagged earlier are removed, and the
integration becomes sound.

## Target architecture: one identity plane, two service planes

```
                         ┌──────────────────────────┐
                         │      Cognito (shared)     │
                         │  cognito:groups (roles)   │
                         │  custom:tenants (tenants) │
                         └────────────┬─────────────┘
                                      │ one access token (signature verified)
                 ┌────────────────────┴────────────────────┐
                 │                                          │
        ┌────────▼─────────┐                      ┌─────────▼──────────┐
        │  Frontend (SPA)  │  routes by UI need   │                    │
        └───┬─────────┬────┘                      │                    │
            │         │                                                │
   finance/tenant-admin        member/webshop/event                    │
            │         │                                                │
   ┌────────▼───────┐ │              ┌──────────────▼───────────────┐  │
   │ Flask / MySQL  │ │              │ API Gateway → Lambda (SAM)    │  │
   │ (myAdmin base) │ │              │ / DynamoDB (h-dcn SAM stack:  │  │
   │                │ │              │  members/events/webshop)      │  │
   │ scope: admin.  │ │              │ scope: tenant_id partition key│  │
   └────────────────┘ │              └───────────────────────────────┘ │
            (cross-domain orchestration only when a screen needs both) ─┘
```

- **Identity plane (shared):** the shared Cognito identity plane — *reconciled to
  two audience-split pools* (Pool A admin/staff carries roles + `custom:tenants` +
  entitlement projection; Pool B end-users carry a single `tenant_id`). Both planes
  verify the signature and read a consistent claim contract per pool. This is the
  linchpin — "who you are" and "which tenant" are answered consistently everywhere;
  the diagram above shows it as one box for simplicity, but it is two issuers.
- **Service plane A — Flask/MySQL (myAdmin domain):** finance, tenant admin,
  relational/report-heavy work. Scopes by the `administration` key it already
  uses.
- **Service plane B — Lambda/DynamoDB (the h-dcn SAM stack — `members`, `events`,
  `webshop` modules, one shared deployment):** members, webshop, events, orders.
  Scopes by a `tenant_id` partition key (pooled model from
  `tenant_field_config.md` / `rewrite_vs_refactor.md`), ideally with IAM
  `dynamodb:LeadingKeys` defense-in-depth.
- **Frontend:** holds one token, calls Plane A or Plane B directly by domain. No
  proxy hop unless a screen genuinely needs data joined across both planes.

This is a **modular set of services unified by identity** — each domain keeps the
datastore and runtime that suit it (relational + always-on for finance,
serverless + on-demand for the portal), and the verified token is the shared
contract. It directly satisfies "keep Flask limited in scope, keep SAM optimal."

## The right balance between Cognito and MySQL (and impact on the SAM plane)

This is the central design decision, because it determines what the SAM/Lambda
plane can **trust from the token alone** versus what it must **look up
elsewhere** — and a lookup from Lambda into myAdmin's MySQL is the one thing that
would undermine "keep SAM optimal."

### Guiding principle

Put in the **token (Cognito)** the small, slow-changing facts every request needs
to make an authorization decision. Keep in **MySQL** the larger, richer,
faster-changing management/governance data that is queried by its owning domain,
not needed for cross-cutting authorization.

### What belongs in Cognito (the token contract)

Keep this deliberately minimal — it is the shared contract both planes verify.
*(Reconciled: the rich contract below is the **Pool A** (admin/staff) token. The
**Pool B** (end-user) token is deliberately simpler — a single `tenant_id`
(singular), no roles, no entitlement projection; the member/customer DynamoDB row
is the relationship of record. See `second_thoughts.md`, "Managing Pool B tenant
relationships".)*

**Pool A token contract:**

- **Identity**: `sub`, `email`.
- **Roles**: `cognito:groups` (authoritative, as verified in myAdmin).
- **Tenant access**: `custom:tenants` — the list of tenants the user may act in.
- Optionally a single **active-tenant** hint, though active tenant is better sent
  per-request (header) and validated against `custom:tenants`.

Rationale: these are exactly the fields needed to answer "who are you, what may
you do, and in which tenant" — and they must be identical across both planes.
Token size stays small; no per-request DB call is needed for authorization.

### What belongs in MySQL (management / governance mirror)

- Tenant registry and metadata (`tenants`: display name, status, plan, contact).
- Which modules each tenant has enabled (`tenant_modules`).
- **Per-user, per-tenant role grants** (`user_tenant_roles`: `email`,
  `administration`, `role`) — the authoritative "what can this user do in this
  tenant," read on the Flask plane via `role_cache.py`. (`tenant_role_allocation` is
  retired; available roles derive from `tenant_modules` + Cognito groups.)
- Tenant-level configuration and per-tenant field/template overlays
  (`tenant_template_config` today; the tenant-field overlay from
  `tenant_field_config.md`).
- Any rich, relational, or frequently-edited tenant admin data.

Rationale: this data is large, changes often, and is only needed by the domain
that owns it — not by every authorization check. Cognito custom attributes are
also size- and shape-limited (a handful of string attributes), so this data
could not live there even if you wanted it to.

### The sync rule (one direction, at write time)

Cognito is the **runtime** source of truth; MySQL is the **management** source of
truth. When an admin changes tenant access or role allocation, the change is
written to MySQL **and** pushed into the Cognito attribute
(`admin_update_user_attributes`) in the same operation — exactly what
`sysadmin_provisioning.py` already does. The runtime (both planes) then reads only
the token. This avoids per-request DB lookups for authorization while keeping a
durable, queryable governance record.

Caveat to design for: Cognito attribute changes take effect on **token refresh**,
so there is a propagation delay (typically up to the access-token lifetime). For
access **revocation** that must be immediate, plan a mechanism (short token TTL,
forced re-auth / `globalSignOut`, or a revocation check) — this is a design-phase
detail, not a feasibility blocker.

### Impact on accessing the SAM environment (the key point)

With the balance above, the SAM plane stays clean and self-sufficient:

- **The Lambda authorizer/handlers trust the verified token only.** Tenant access
  (`custom:tenants` / validated active-tenant header) and **global** roles
  (`cognito:groups`) come from the JWT, verified against the pool's JWKS. A Lambda
  does **not** call MySQL to authorize a request. That preserves on-demand scaling,
  avoids the Lambda→RDS connection-pool problem (`rewrite_vs_refactor.md`), and keeps
  the two planes decoupled. **Important:** this is only true once the two
  MySQL-resident facts — the user's **per-tenant roles** (`user_tenant_roles`) and
  the tenant's enabled **modules** (`tenant_modules`) — are projected into the token
  (S4). myAdmin's Flask plane does not do this: it reads per-tenant roles from
  `user_tenant_roles` (cached via `role_cache.py`) and `tenant_modules` from MySQL on
  the request. Cheap for Flask; not available to a Lambda.
- **The SAM plane never reaches into myAdmin's MySQL for tenant data.** If a
  handler needed governance data that lives only in MySQL to do its job, that
  would be a coupling smell — it means the fact was misplaced and probably belongs
  in the token (if authorization) or should be owned by the DynamoDB side (if
  portal-domain data). Keep the token contract sufficient for every SAM
  authorization decision.
- **Preferred access path stays: client → API Gateway (Cognito authorizer) →
  Lambda**, with the tenant enforced as a `tenant_id` partition-key condition
  (plus IAM `LeadingKeys` for defense in depth). Flask→SAM calls, when needed for
  cross-domain orchestration, pass the same user token through — again, no MySQL
  lookup on the SAM side.
- **Provisioning is the only cross-plane write coupling**, and it is
  Cognito-centric: admin action updates MySQL governance + the Cognito attribute.
  Neither runtime plane depends on the other at request time.

## How myAdmin really works today (verified) — and the one gap for SAM

This is the important, plain-language finding. There are **four facts**, in two
places:

| Fact | Lives in | Read from |
| --- | --- | --- |
| Which tenants a user may access | Cognito `custom:tenants` | the token |
| The user's **global** roles (SysAdmin etc.) | Cognito `cognito:groups` | the token |
| The user's **per-tenant** roles (what they may do *in this tenant*) | **MySQL** `user_tenant_roles` | **a cached DB query** (`role_cache.py`) |
| Which modules a tenant actually has | **MySQL** `tenant_modules` | **a live DB query** |

The real authorization combines them: the user's per-tenant roles (intersected with
the tenant's enabled modules) decide what they may do. In `tenant_module_routes.py`
the module part literally does:

```python
available_modules = [m for m in user_module_permissions if m in tenant_modules]
#                        ^ user's effective modules      ^ from a MySQL query
```

and `@cognito_required` merges **global** roles (from the JWT) with **per-tenant**
roles (from `user_tenant_roles`, via `role_cache.py`). So the token **alone is not
enough** in myAdmin — it must ask MySQL both "what may this user do in this tenant?"
and "what modules does this tenant have?" on the request. **For myAdmin that is
fine**, because Flask is connected to MySQL and the role lookup is cached; the cost
is negligible.

**The problem for a combined system:** a Lambda (SAM plane) must NOT query MySQL
on every request (connection limits, cost, coupling — see
`rewrite_vs_refactor.md`). So this one pattern does not transfer to the serverless
side. That is the single gap to close.

## The fix: system of record + projection (do NOT move tables into Cognito)

Keep it simple with two ideas:

1. **System of record = MySQL.** `tenants`, `tenant_modules`, `user_tenant_roles`
   stay in MySQL, managed by an admin app. This is the truth. Do **not** try to
   move these tables into Cognito — Cognito is an identity store, not a database
   (tiny attributes, no relations, no queries).

2. **Projection = a small, ready-made answer the fast path can read.** At login,
   compute the user's *resolved* per-tenant access **once** — for each tenant, their
   effective permissions = their per-tenant **roles** (`user_tenant_roles`) ∩ the
   tenant's enabled **modules** (`tenant_modules`) — and stamp it into the **token**
   as a compact claim. A **Cognito Pre-Token-Generation trigger** (a Lambda that
   reads MySQL once at login) is the clean way to do this. This is the Lambda-plane
   equivalent of what `role_cache.py` already does for the Flask plane: cache the
   per-tenant role answer so the request path does no live DB lookup — except the
   token carries the pre-resolved answer instead of a server-side cache.

Result: both planes — Flask and SAM — authorize from the **token alone** (Flask may
still use its cached MySQL read; a Lambda uses only the token). No Lambda ever
touches MySQL. MySQL stays authoritative; the token carries the pre-computed answer.

> One accepted trade-off: the token is a snapshot. If an admin changes a tenant's
> modules or a user's roles, it takes effect when the token refreshes. For
> instant revocation, use a short token lifetime or force re-login. This is a
> normal, well-understood trade.

## How far is this from ideal?

- **myAdmin on its own: close to ideal (~80%).** Querying MySQL per request is
  free for a monolith. Its only real gaps are security: the JWT signature is
  **not verified**, and an `X-Tenant` header is trusted. Worth fixing regardless.
- **The combined system: a moderate, well-scoped distance from ideal (~50-60%
  today).** The whole gap collapses to **two moves**:
  1. **Verify the JWT signature** on both planes (against the Cognito JWKS).
  2. **Project entitlement into the token** (Pre-Token-Generation trigger) instead
     of reading `tenant_modules` from MySQL at request time.

Do those two, add a token lifetime/revocation decision, and stop trusting
unverified headers — and the combined system reaches ~90%+ of ideal: MySQL
authoritative, both planes authorizing from a verified token, no Lambda touching
MySQL. The rest (snapshot staleness, running two datastores) is the normal cost
every real system carries.

## Why this is a good approach (with the assumptions in place)

- **The auth objection disappears.** Verified signatures + shared tenant claim let
  both planes independently and safely enforce isolation from the same token. No
  confused-deputy problem; the frontend passing its token to either backend is
  legitimate because both validate properly.
- **Frontend-routes-by-UI-need avoids the proxy anti-pattern.** The client calls
  the owning service directly; Flask only enters the path for genuine
  cross-domain orchestration.
- **Each domain keeps its optimal stack.** No forcing finance into DynamoDB or the
  webshop into MySQL. SAM stays the scaling engine for the portal; Flask/MySQL
  stays optimal for relational reporting.
- **Independent deployability** along real domain lines — a feature, not
  accidental coupling.

## Service-to-service calls (when Flask must call the SAM plane)

For the cross-domain cases, prefer **Flask → API Gateway over HTTPS with the end
user's token passed through** (the Lambda still authorizes the real user against
the shared pool). Avoid `boto3 lambda.invoke` direct calls (bypasses API Gateway
auth/throttling/validation and couples Flask to function internals). Do NOT route
frontend calls through Flask when the frontend can hit API Gateway directly — only
proxy when Flask adds orchestration or a MySQL+DynamoDB join.

## Remaining sharp edges (fewer, but real)

1. **The tenant claim + per-tenant roles must be authoritative and kept in sync.**
   Verified model in myAdmin (2026-09-15): **the token carries** `custom:tenants`
   (tenant access) and `cognito:groups` (**global** roles only, e.g. SysAdmin).
   **MySQL is the source of truth** for the rest: `tenants` (which tenants exist),
   `tenant_modules` (which modules a tenant has), and `user_tenant_roles` (a user's
   **per-tenant** roles — read on the Flask plane via `role_cache.py`).
   Provisioning (`sysadmin_provisioning.py` / `tenant_provisioning_service.py`)
   writes MySQL and syncs `custom:tenants` into Cognito via
   `admin_update_user_attributes`. The unified design adopts the same split:
   authorization facts live in MySQL; only tenant access + global roles ride the
   token directly; per-tenant roles reach a Lambda via the S4 projection. Note:
   Cognito custom attributes and any projected claim only refresh on token renewal —
   account for propagation delay when access changes. (`tenant_role_allocation` is
   retired — available roles derive from `tenant_modules` + Cognito groups.)
2. **Two isolation implementations must stay equivalent.** Plane A:
   `WHERE administration = %s`; Plane B: `tenant_id` partition key + IAM
   LeadingKeys. Both must be correct; a bug in either is a cross-tenant breach.
   Recommend a shared isolation test checklist both sides run.
3. **Cross-domain reads need an explicit owner.** Joining DynamoDB members with
   MySQL financials is the one place Flask-as-orchestrator earns its keep. Keep
   these cases few and explicit; don't let Flask drift into a general proxy.
4. **Frontend config becomes multi-endpoint.** The client needs both planes' API
   base URLs per environment, as fail-fast env vars (guardrail: no dangerous
   fallbacks). H-DCN's currently-scattered single hardcoded API URL still needs
   centralizing; this grows that slightly.
5. **Two runtimes, two cost models, two on-call surfaces.** The standing
   operational tax of Flask/MySQL alongside Lambda/DynamoDB — justified by domain
   fit, but real.

## Verdict and sequencing

With unified identity, a tenant claim, verified JWTs, and UI-need-based frontend
routing, this is a **sound, pragmatic target architecture** — arguably better than
forcing everything into one stack. It reuses myAdmin's proven multi-tenant
machinery and relational reporting, keeps H-DCN's serverless economics and
existing domain, and binds them with a single identity contract.

The center of gravity is the **unified tenant-claim + verified-JWT contract.**
Everything good here depends on it being correct and kept in sync. Sequencing:

1. **Design and specify the identity/claim contract first** — the two pools (Pool A
   admin/staff, Pool B end-users), `custom:tenants` shape (Pool A) vs single
   `tenant_id` (Pool B), role namespace, JWKS verification against each pool on both
   backends, and the claim-sync write path and source of truth. Test this hardest.
2. **Stand up Plane B tenancy** on H-DCN (add `tenant_id` partition key, key +
   IAM isolation, tenant-field overlay per `tenant_field_config.md`).
3. **Align Plane A** to read the unified claim and verified token (replace the
   base64-only decode and `X-Tenant` trust).
4. **Frontend multi-endpoint routing + fail-fast config.**
5. **Add cross-domain orchestration** endpoints in Flash only where a screen needs
   both planes.

The two service planes are comparatively straightforward once the contract is
solid.

## Relevant files (myAdmin, for reference)

1. `backend/src/auth/tenant_context.py` — tenant extraction/validation +
   `@tenant_required` decorator (structure right; JWT verification missing).
2. `backend/sql/phase1_multitenant_schema.sql` — adds `administration` tenant key
   across all tables.
3. `backend/sql/create_tenants_table.sql` — tenant metadata + seed tenants.
4. `user_tenant_roles` table (`.kiro/specs/Common/Tenant/per-tenant-roles/design.md`)
   + `backend/src/auth/role_cache.py` — per-user, per-tenant role grants read via a
   cached MySQL lookup on the Flask plane. **This is the authorization fact the S4
   token projection carries to the Lambda plane.** (Supersedes the retired
   `tenant_role_allocation`.)
5. `backend/src/services/module_registry.py` — `MODULE_REGISTRY`, `has_module()`,
   `module_required()`; `tenant_modules` table = which modules a tenant has enabled.
6. `backend/sql/create_tenant_template_config_table.sql` — per-tenant template /
   `field_mappings` config with versioning (tenant-field-overlay analogue).
