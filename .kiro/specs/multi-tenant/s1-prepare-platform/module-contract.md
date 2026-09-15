# The SAM-Backed Module Plug-In Contract

- Status: Complete
- Roadmap step: S1 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Decision of record: ADR 0003
- Source of truth: `design.md` §2 (four-seam contract) and §3 (two planes, one
  identity, MySQL as system of record), this folder.

## Who this is for

You are integrating a new capability into myAdmin as a **module backed by an AWS SAM
app** (Lambda + API Gateway + DynamoDB), rather than in-process Flask/MySQL code. This
document is the contract you follow.

The one rule that shapes all four seams: **a module never invents its own tenancy or
its own auth.** Tenancy and identity belong to the platform. Your module plugs into
them through four seams — Register, Entitle, Authorize, Scope — and adds only its own
domain behavior on top.

If you find yourself writing code to look up which tenant a request belongs to, to
decide whether a user is allowed in, or to read `tenant_modules` from MySQL on the
request path, stop: that work is the platform's, reached through the seams below.

## The four seams at a glance

| Seam | What the module does | Platform mechanism |
| --- | --- | --- |
| 1 — Register | Declares itself as a `sam`-backed `MODULE_REGISTRY` entry | `MODULE_REGISTRY`, `module_backing()`, `resolve_module_api_base()` |
| 2 — Entitle | Nothing new — tenants enable it like any module | `tenant_modules` row + provisioning + sysadmin module-management |
| 3 — Authorize | Trusts only the verified token; no request-time MySQL | Cognito authorizer + token claims (`cognito:groups`, projected entitlement) |
| 4 — Scope | Scopes every record by `tenant_id` from the token | DynamoDB partition key + IAM `dynamodb:LeadingKeys` |

---

## Seam 1 — Register

A SAM-backed module is a normal entry in `MODULE_REGISTRY`
(`backend/src/services/module_registry.py`), distinguished only by a `backing` block
with `kind = "sam"`. Absence of a `backing` block means `flask` (in-process) — which
is why the four existing modules (FIN, ZZP, STR, TENADMIN) carry no `backing` key and
stay untouched.

```python
"members": {
    "description": "Member management (SAM-backed, h-dcn stack)",
    "depends_on": [],
    "required_roles": [ ... ],
    "backing": {
        "kind": "sam",
        # NAME of the env var that yields the module's API base URL for the
        # current environment. The registry never stores a URL; resolution
        # fails fast if the env var is missing (no dangerous fallback).
        "api_base_env": "HDCN_API_BASE_URL",
        # optional: the DynamoDB table prefix / namespace the module owns.
        "data_namespace": "hdcn",
    },
},
```

**Metadata a `sam` entry declares:**

- `backing.kind` — `"sam"`.
- `backing.api_base_env` — the **name** of the environment variable that yields this
  module's API base URL. Per-module, so each module *can* have its own API base; the
  registry stores the variable name, never a hardcoded URL.
- `backing.data_namespace` (optional) — the DynamoDB table prefix / namespace the
  module owns, for documentation and tooling.

Everything else in a descriptor (`description`, `depends_on`, `required_roles`,
`required_params`, `required_tax_rates`) applies unchanged for both kinds.

**Use the accessors — never inspect the dict shape directly.** Phase 1 (S1) added two
read-only accessors so the descriptor shape stays contained:

- `module_backing(module_name) -> "flask" | "sam"` — returns the backing kind,
  defaulting to `"flask"` when no `backing` block (or no `kind`) is present. Raises
  `ValueError` for an unknown module.
- `resolve_module_api_base(module_name) -> str | None` — for a `sam` module, reads the
  env var named by `api_base_env` and returns the URL; **fails fast** with a
  `ValueError` if that env var is unset/empty or `api_base_env` is not configured.
  Returns `None` for a `flask` module.

A `sam` module is **discoverable exactly like any module** — through the same registry
APIs (`get_tenant_modules`, the sysadmin registry view, `depends_on` resolution). The
backing kind changes how the module runs, not how it is discovered.

## Seam 2 — Entitle

A tenant gains the module through a single `tenant_modules` row (`administration`,
`module_name`, `is_active`) — the **same** mechanism used for every module today. A
SAM-backed module introduces **no new entitlement path**:

- **Provisioning** (`tenant_provisioning_service.py`, `scripts/provision_tenant.py`)
  inserts the `tenant_modules` row exactly as for a Flask module.
- **Sysadmin module-management** routes enable/disable a `sam` module identically to a
  `flask` one.
- `depends_on` and `required_roles` are enforced the same regardless of backing kind.

There is nothing module-specific to build here. If your module needs to be entitled,
it is entitled the way FIN/ZZP/STR/TENADMIN already are.

## Seam 3 — Authorize (from the verified token alone)

Each of the module's Lambda handlers authorizes a request from the **verified Cognito
token, and nothing else.** The module's Lambdas sit behind an API Gateway **Cognito
authorizer**; each handler:

- trusts **only the signature-verified token** — never unverified headers, never a
  claimed identity the gateway has not validated;
- reads **global** roles (e.g. SysAdmin / Administrators / System_CRUD) from
  `cognito:groups`;
- reads its **per-tenant** authorization — the user's per-tenant roles ∩ the tenant's
  enabled modules — from **token claims**, **never** a live MySQL read of
  `user_tenant_roles` / `tenant_modules` on the request path.

**A Lambda must not query MySQL per request.** The Flask plane can afford a cached
MySQL read (`backend/src/auth/role_cache.py`) because it is a monolith sitting next to
MySQL; a Lambda cannot. Instead, the resolved per-tenant answer is projected into the
token at login — the Lambda-plane equivalent of `role_cache.py`. Read authorization
from the claims that projection provides.

The `tenant_id` your handler scopes by (Seam 4) is derived only from this verified
token — not from a path parameter, query string, or request body a caller could forge.

> **Enabling dependencies:** the verified token on this plane and the projected
> entitlement claims are delivered by later roadmap steps (signature verification is
> S2; the entitlement-in-token projection is S4). See the "Enabling dependencies"
> section below for the full mapping and the rule about not building against the module
> plane before those steps land.

## Seam 4 — Scope

Every record the module stores or reads is scoped by `tenant_id`:

- **DynamoDB partition key `tenant_id`** on every table the module owns. The partition
  key is the primary tenancy boundary — cross-tenant reads are simply not addressable.
- **IAM `dynamodb:LeadingKeys`** restricting a caller's credentials to its own tenant
  partition — defense in depth, so a coding mistake cannot read another tenant's data.
- The `tenant_id` used for scoping **derives only from the verified token** (Seam 3),
  never from client-supplied input.

Together the partition key (correctness) and `LeadingKeys` (enforcement) mean a module
cannot accidentally or deliberately cross a tenant boundary.

---

## Enabling dependencies

The Authorize and Scope seams depend on platform capabilities that later roadmap steps
provide. S1 **specifies** these seams and names their dependencies; it does not build
them, and it does not permit a stopgap (such as a request-time MySQL call) in their
place. The mapping below mirrors `design.md` §4 ("What S1 sets up for later steps").

| Seam / need | What S1 provides | Enabling step |
| --- | --- | --- |
| **Authorize** — signature verification on the module plane (Seam 3) | specifies "trust only the signature-verified token" | **S2** |
| **Authorize** — per-tenant entitlement (roles ∩ enabled modules) projected into the token (Seam 3) | requires it so no per-request MySQL read is needed — the Lambda-plane equivalent of `role_cache.py` | **S4** |
| **Tenant-level module data** — facts too large or non-user-scoped for the token (Seam 3 / §3) | designs the read-only claim/projection seam, names the dependency | **S3** (read-only, one-directional MySQL→DynamoDB projection) |
| **Scope** — `tenant_id` on a real module's data (Seam 4) | defines the rule (partition key + `LeadingKeys`) | **S5** (the first real module) |

Read the two Authorize dependencies together: the seam is only usable once **both**
land. **S2** makes the token *trustworthy* (its signature is verified on the module
plane), and **S4** makes the token *sufficient* (the per-tenant entitlement is projected
into it, so a Lambda never has to read `user_tenant_roles` / `tenant_modules` from MySQL
on the request path). One without the other does not complete the seam:

- With S2 but not S4, the token is verified but carries no per-tenant entitlement, so
  there is no cheap, in-token way to answer "what may this user do in this tenant?"
- With S4 but not S2, the entitlement claim exists but the token's signature is not
  verified on this plane, so it cannot be trusted.

Tenant-level module data that does not fit in the token — facts too large or not scoped
to the calling user — is reached only through **S3**'s read-only, one-directional
MySQL→DynamoDB projection, never a request-time MySQL query from a Lambda (see the *Data
ownership* section). And the `tenant_id` a module stamps on its own records (Seam 4)
arrives with **S5**, the first real module.

### The hard rule

**A module MUST NOT be built against the module plane until S2–S4 provide the token
path.** Until signature verification (S2) and the entitlement-in-token projection (S4)
are in place — with S3's projection available for any tenant-level facts the token
cannot carry — there is no correct way to authorize a Lambda request. The contract
**forbids the obvious stopgap**: a module may not fall back to a request-time MySQL read
of `user_tenant_roles` / `tenant_modules` to bridge the gap. If the token path is not
yet there, the module is not yet buildable on this plane — do not implement it against
the module plane, and do not introduce a temporary MySQL call in its place.

## Data ownership (two planes, MySQL as system of record)

The platform runs **two service planes over one identity**. Both verify every request's
token against the issuing Cognito pool's JWKS; neither trusts the other by shared
database access.

```
                 ┌───────────────────────────┐
                 │   Cognito (identity acct)  │   one identity, two pools by audience
                 └─────────────┬─────────────┘
                   verified token (JWKS-checked on BOTH planes)
        ┌───────────────────────┴───────────────────────┐
        ▼                                                ▼
┌──────────────────────┐                    ┌────────────────────────────┐
│ Flask / MySQL         │  system of record  │ SAM / Lambda / DynamoDB     │
│ (myAdmin — the base)  │  tenants,          │ (a SAM-backed module)       │
│ admin, finance,       │  tenant_modules,   │ authorize from token only;  │
│ tenant governance     │  user_tenant_roles │ read its OWN DynamoDB;       │
│                       │ ─ ─ read-only ─ ─► │ never query MySQL at        │
│                       │  MySQL→DynamoDB     │ request time                │
└──────────────────────┘  projection (S3)    └────────────────────────────┘
        ▲                                                ▲
        └──────── cross-plane call: token through ───────┘
                  API Gateway (never lambda.invoke)
```

### MySQL is the system of record

**MySQL stays the system of record** for tenant governance — `tenants`,
`tenant_modules`, and `user_tenant_roles`. These tables define which tenants exist,
which modules each tenant has enabled, and which per-tenant roles each user holds. That
authority does not move to the module plane, and no module owns a second copy of it that
it writes back. (R3.1, R3.2)

### How a module reaches what MySQL owns

A SAM module never opens a MySQL connection. It gets the MySQL-owned facts it needs in
exactly one of two ways, both one-directional:

- **(a) The token — for authorization.** The user's global roles ride `cognito:groups`,
  and the resolved per-tenant entitlement (roles ∩ enabled modules) is projected into
  the token by S4. A Lambda reads authorization from these verified claims (Seam 3) —
  never from a live read of `user_tenant_roles` / `tenant_modules`.
- **(b) A read-only, one-directional MySQL→DynamoDB projection — for tenant-level
  facts too large or non-user-scoped to carry in the token.** Built in S3, this
  projection copies the needed governance facts *forward* into DynamoDB, where the
  module reads its own table at request time.

**Two hard limits apply to both paths:**

- **Never a request-time MySQL query from a Lambda.** The Flask plane can afford a
  cached MySQL read (`backend/src/auth/role_cache.py`) because it is a monolith sitting
  next to MySQL; a Lambda cannot, and the contract forbids the stopgap.
- **Never a two-way write.** The projection flows MySQL→DynamoDB only. A module does not
  write governance facts back to MySQL; MySQL remains the sole writer of record.

### Per-user, per-tenant authorization

The answer to "what may this user do in this tenant?" comes from `user_tenant_roles`.
The two planes resolve it differently, but from the same source of truth:

- **Flask plane** resolves it via a cached MySQL read
  (`backend/src/auth/role_cache.py`), sitting next to the database.
- **Module plane** cannot read MySQL, so it receives the **resolved per-tenant answer
  projected into the token by S4** — the Lambda-plane equivalent of `role_cache.py`.

Only **global** roles (SysAdmin / Administrators / System_CRUD) ride `cognito:groups`
directly; everything per-tenant is resolved from `user_tenant_roles` and reaches the
module plane through the token. (R3.2)

### Cross-plane calls

The **frontend routes by UI need**: admin screens call the Flask plane, module screens
call the module plane. When one plane must call the other, the call **passes the user's
token through API Gateway** and is authorized there like any other request. There is
**no `lambda.invoke`** between planes and **no MySQL lookup on the module side** — the
token is the only thing that crosses the boundary. (R3.3)

## See also

- `design.md` §2–§3 — the authoritative wording this contract reflects.
- `requirements.md` R2 (the four seams), R3 (two planes / system of record).
- `.kiro/steering/architecture.md` — "Platform Evolution" (the platform-level summary
  that links here).
- `backend/src/services/module_registry.py` — `module_backing()`,
  `resolve_module_api_base()`, `MODULE_REGISTRY`.
