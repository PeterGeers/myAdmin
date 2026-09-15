# S1 — Prepare myAdmin to Host SAM-Backed Modules — Design

- Status: Complete
- Roadmap step: S1 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Decision of record: ADR 0003
- Requirements: `requirements.md` (this folder)

## Overview

S1 turns myAdmin's existing module system into a **module-hosting platform** that can
back a module with an AWS SAM app (Lambda + DynamoDB) as well as with in-process
Flask/MySQL code. The change is deliberately small and additive: it extends the
module **descriptor** with a backing kind, documents the **plug-in contract** a
SAM-backed module must honor, and folds the platform governance into myAdmin's
steering. No SAM app is built or deployed in S1.

## Current state (verified)

```
tenant provisioning ──► tenant_modules (MySQL)     MODULE_REGISTRY (module_registry.py)
        │                administration            { FIN, ZZP, STR, TENADMIN }
        │                module_name                each: description, depends_on?,
        │                is_active                        required_params,
        ▼                                                 required_tax_rates,
  has_module(db, tenant, module)                          required_roles
  module_required(module)  ◄── Flask route decorator
  activate_module(...)

authorization (tenant_module_routes.py):
  available = [m for m in user_module_permissions if m in tenant_enabled_modules]
                         ▲ from token                    ▲ from tenant_modules (MySQL)
```

Every module today is **in-process Flask/MySQL**: `module_required` guards Flask
routes, and `tenant_module_routes.py` reads `tenant_modules` from MySQL on the request
(cheap for a monolith connected to MySQL). A Lambda cannot do that read cheaply — which
is exactly the gap the contract closes by pushing entitlement into the token (S4).

## Design

### 1. Module descriptor gains a `backing` (kind)

Extend each `MODULE_REGISTRY` entry with an optional `backing` block. Absence means
in-process Flask (today's behavior), so the four existing modules are untouched.

```python
# in-process module (unchanged; backing defaults to flask)
"FIN": {
    "description": "Financial Administration",
    "required_params": { ... },
    "required_roles": ["Finance_CRUD", "Finance_Read", "Finance_Export"],
    # no "backing" key  →  backing = flask
},

# SAM-backed module (the new capability S1 introduces)
# The h-dcn domain arrives as THREE such modules — members, events, webshop —
# that today share ONE SAM stack (one deployment, one API base). Illustrative;
# no h-dcn module ships in S1.
"members": {
    "description": "Member management (SAM-backed, h-dcn stack)",
    "depends_on": [],
    "required_roles": [ ... ],
    "backing": {
        "kind": "sam",
        # how a client/gateway reaches this module's API, resolved per environment.
        # a logical key, never a hardcoded URL — the URL comes from env config
        # (fail-fast; no dangerous fallback). Today all three h-dcn modules resolve
        # this to the SAME value (one shared stack); see the open question below.
        "api_base_env": "HDCN_API_BASE_URL",
        # optional: the DynamoDB table prefix / namespace the module owns, for docs.
        "data_namespace": "hdcn",
    },
},
# "events" and "webshop" follow the same shape, each its own registry entry so it
# can be entitled independently via tenant_modules — currently pointing at the same
# api_base_env and stack.
```

Field notes:

- `backing.kind`: `"flask"` (default when omitted) or `"sam"`.
- `backing.api_base_env`: the **name** of the env var that yields the module's API
  base URL for the current environment. The registry never stores a URL. Resolution
  fails fast if the env var is missing (per the no-dangerous-fallbacks guardrail).
  The field is **per module** so each module *can* have its own API base, but the
  three h-dcn modules currently share one stack and resolve it to the same value.
- Everything else in the descriptor (`description`, `depends_on`, `required_roles`,
  `required_params`, `required_tax_rates`) applies unchanged for both kinds.

> **Open design question (deferred to module migration):** do the h-dcn modules keep
> **one shared API base** (their current single SAM stack) or split into **one API
> base per module** (separate stacks)? S1 does not decide this — the per-module
> `api_base_env` field supports either outcome without a contract change. Decide it
> when the modules are actually migrated (S2/S5-era), based on deployment and
> isolation trade-offs. Until then, treat it as one shared stack.

A tiny accessor (e.g. `module_backing(module_name) -> "flask" | "sam"`) keeps call
sites from reaching into the dict shape, so future backing kinds stay contained.

### 2. The four-seam plug-in contract

A SAM-backed module integrates through exactly four seams. These are the platform's
tenancy/auth; a module never invents its own.

**Seam 1 — Register.** The module is an entry in `MODULE_REGISTRY` with
`backing.kind = "sam"`. It is discoverable by the same registry APIs as any module
(`get_tenant_modules`, the sysadmin registry view, `depends_on` resolution).

**Seam 2 — Entitle.** A tenant gains the module through a `tenant_modules` row
(`administration`, `module_name`, `is_active`). Provisioning
(`tenant_provisioning_service.py`, `provision_tenant.py`) and the sysadmin
module-management routes treat a `sam` module identically to a `flask` one — no new
entitlement mechanism.

**Seam 3 — Authorize (from the verified token alone).** The module's Lambdas sit
behind an API Gateway **Cognito authorizer**; each handler:

- trusts only the **signature-verified** token (implemented in S2 for this plane);
- reads **global** roles from `cognito:groups`;
- reads its **per-tenant** authorization (the user's per-tenant roles ∩ the tenant's
  enabled modules) from **token claims**, not a live MySQL read of `user_tenant_roles`
  / `tenant_modules` — that resolved answer is projected at login by S4 (the
  Lambda-plane equivalent of the Flask plane's `role_cache.py`).

Until S4 lands, a SAM module has no cheap way to learn per-tenant authorization on the
request path; S1 therefore *specifies* this seam and marks S4 as its enabling
dependency rather than implementing a stopgap MySQL call (which the contract forbids).

**Seam 4 — Scope.** All module data is scoped by `tenant_id`:

- DynamoDB partition key `tenant_id` on every table;
- IAM `dynamodb:LeadingKeys` restricting a caller to its own tenant partition
  (defense in depth);
- the `tenant_id` used for scoping derives only from the verified token.

### 3. Two planes, one identity, MySQL as system of record

```
                 ┌───────────────────────────┐
                 │   Cognito (identity acct)  │   two pools by audience
                 │  Pool A admin/staff (rich) │   (see identity.md)
                 │  Pool B end-users (simple) │
                 └─────────────┬─────────────┘
                   verified token (JWKS-checked on both planes)
        ┌───────────────────────┴───────────────────────┐
        ▼                                                ▼
┌──────────────────────┐                    ┌────────────────────────────┐
│ Flask / MySQL         │  system of record  │ SAM / Lambda / DynamoDB     │
│ (myAdmin — the base)  │  tenants,          │ (a SAM-backed module)       │
│ admin, finance,       │  tenant_modules,   │ authorize from token only;  │
│ tenant governance     │  user_tenant_roles │ scope by tenant_id;         │
│ scope: administration │ ─ ─ read-only ─ ─► │ never query MySQL at        │
│                       │  MySQL→DynamoDB     │ request time                │
└──────────────────────┘  projection (S3)    └────────────────────────────┘
```

- **MySQL stays the system of record** for tenant governance (`tenants`,
  `tenant_modules`, `user_tenant_roles`). A SAM module gets what it needs via (a) the
  **token** for authorization, or (b) a **read-only, one-directional** MySQL→DynamoDB
  projection (built in S3) for tenant-level facts too large or non-user-scoped for the
  token. Never a two-way write; never a request-time MySQL query from a Lambda.
- **Per-user, per-tenant authorization** ("what may this user do in this tenant?")
  comes from `user_tenant_roles`. The Flask plane already resolves this via a cached
  MySQL read (`backend/src/auth/role_cache.py`); only **global** roles
  (SysAdmin/Administrators/System_CRUD) ride `cognito:groups`. The module plane cannot
  do that read, so the Authorize seam (below) is filled by **S4 projecting the
  resolved per-tenant answer into the token** — the Lambda-plane equivalent of
  `role_cache.py`.
- **Frontend routes by UI need.** Cross-plane calls pass the user's token through API
  Gateway; no `lambda.invoke`, no MySQL lookup on the module side.

### 4. What S1 sets up for later steps (the seams, not the fill)

| Seam / need | S1 does | Later step fills |
| --- | --- | --- |
| Verified token on the module plane (Seam 3) | specifies it in the contract | **S2** |
| Claim contract + read-only MySQL→DynamoDB projection of tenant-level facts (Seam 3/§3) | designs the seam, names the dependency | **S3** |
| Per-tenant roles + modules resolved into the token — the Lambda-plane equivalent of `role_cache.py` (Seam 3) | requires it so no per-request MySQL | **S4** |
| `tenant_id` on a real module's data (Seam 4) | defines the rule | **S5** (first module) |

### 5. Backward compatibility

- `backing` is optional; omitting it = `flask` = today. FIN/ZZP/STR/TENADMIN entries
  need no change and keep loading, guarding, and authorizing exactly as now.
- Any registry accessor added is read-only and defaults to `flask`.
- If a `tenant_modules` schema touch is ever needed (S1 does not require one), it must
  be **additive** and follow the database-patterns rule (any new tenant-scoped table
  carries `administration VARCHAR(50) NOT NULL` + `idx_administration`; migrations are
  additive; no `IF NOT EXISTS` on MySQL index DDL). S1's registry change is in code
  (`MODULE_REGISTRY`), so no migration is expected.

## Governance refactor (folding mysaas work into myAdmin steering)

The `mysaas` workspace holds good platform governance authored during the abandoned
trunk attempt. S1 salvages the reusable substance into **myAdmin's** steering, under
the myAdmin-as-base model, and drops the trunk framing.

| mysaas source | Fold into myAdmin | Keep | Drop / rewrite |
| --- | --- | --- | --- |
| `steering/identity.md` | new `steering/identity.md` | two-pool audience model, tiers, verification, Pool A/B relationships, deferred edge cases | any "mysaas platform" title framing |
| `steering/aws-accounts.md` | new `steering/aws-accounts.md` | identity vs nonprofit account model, pools, guardrails, tenant keys | nothing structural — already account-based |
| `steering/product.md` | fold platform framing into myAdmin `product.md` | tenant shapes, two audiences, tenant-neutral rule, domains-hosted | "from myAdmin / from H-DCN rebuilt" as-if-external phrasing |
| `steering/architecture.md` | already added to myAdmin `architecture.md` ("Platform Evolution") | two planes, data ownership, cross-plane calls | "this workspace is the trunk" provenance rule |
| `steering/structure.md` | **not** copied | — | trunk / definition-of-record / mysaas layout rules (contradict ADR 0003) |
| `steering/migration-workflow.md` | **not** copied | — | mysaas migration-into-trunk discipline |
| `skills/pr-checklist.md` | merge into myAdmin `skills/pr-checklist.md` | two-plane security items, no-MySQL-from-module rule, test-env validation | `migration-workflow.md` reference |
| `skills/specs-reference.md` | fold into myAdmin `skills/specs-reference.md` | reasoning-vs-ADR-vs-steering convention, roadmap linkage | `admin/backend` `portal/backend` `mysaas` paths; ADR 0001/0002 refs → 0003 |

Rule throughout: **fold in, do not fork.** myAdmin's steering is the definition of
record; new platform files (`identity.md`, `aws-accounts.md`) sit alongside the
existing ones and reference ADR 0003.

## Downstream reconciliation (part of S1)

The parked **S2 spec** is written against the trunk model (`mysaas/admin/`, "portal
rebuilt from h-dcn," S6b CI/CD cutover). S1 corrects it so S2 proceeds correctly:

- "admin plane in `mysaas/admin/`" → "the **myAdmin Flask plane**."
- "portal plane rebuilt from h-dcn into mysaas" → "the **SAM-backed module plane**."
- Remove the S6b CI/CD-source-cutover framing (there is no trunk to cut over to);
  S2 ships through myAdmin's existing pipeline.
- Keep S2's security substance intact (verify signatures, per-issuer JWKS, distrust
  headers, test-environment-first).

Any other parked spec assuming the mysaas trunk gets the same treatment when next
opened.

## Risks and mitigations

- **Risk: the `backing` abstraction is over-designed before a real module exists.**
  Mitigation: keep it to `kind` + `api_base_env` (+ optional `data_namespace`); add
  fields only when the first SAM module (S5) needs them.
- **Risk: a SAM module quietly reaches into MySQL to read entitlement before S4.**
  Mitigation: the contract forbids it explicitly; S1 documents the dependency so no
  module is built against the module plane until S2–S4 provide the token path.
- **Risk: governance drift back toward the trunk model.** Mitigation: S1 removes the
  mysaas-trunk steering from the picture and records ADR 0003 as the single source.
