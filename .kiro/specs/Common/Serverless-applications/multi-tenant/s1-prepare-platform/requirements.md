# S1 — Prepare myAdmin to Host SAM-Backed Modules — Requirements

- Status: Complete
- Roadmap step: S1 (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Decision of record: ADR 0003 (`docs/decisions/0003-myadmin-is-platform-base-modules-as-sam-apps.md`)
- Sources: `overall_roadmap.md` (S1), `myadmin_as_base.md` (two planes, module
  hosting), `second_thoughts.md` (identity + account model), `architecture.md`
  steering ("Platform Evolution").

## Goal

Make myAdmin — the platform base, evolved in place — able to host a **module backed
by an AWS SAM app** (Lambda + DynamoDB), not only by in-process Flask/MySQL code.
S1 defines the **generic plug-in contract** for such a module and prepares the
platform (module registry, governance/steering, ADR) so later steps build on a
coherent foundation.

S1 is **platform capability only**. It does not implement any specific module, does
not touch h-dcn's domain, and does not deploy a SAM app. Its product is: **the
contract, the extended registry metadata, and the governance** that let S2…S9 head
in the right direction — specifically, correcting the earlier drift toward a separate
`mysaas` trunk (see "Why S1 exists now").

## Why S1 exists now (the direction it locks in)

Earlier analysis and an in-progress S2 spec assumed a new `mysaas` workspace was the
platform trunk, with myAdmin's admin code lifted into `mysaas/admin/` and the portal
"rebuilt from h-dcn." **That is reversed (ADR 0003):** myAdmin *is* the base, evolved
in place; incoming apps are imported as SAM-backed **modules**. S1 makes that concrete
so no later step (starting with S2) proceeds on the abandoned assumption. Reconciling
the downstream specs and governance to this model is **part of S1's scope**, not a
side task.

## What already exists (build on this, do not reinvent)

myAdmin already has a working module system, keyed by the `administration` tenant key:

- **`tenant_modules`** table (`administration`, `module_name`, `is_active`, …) —
  which modules a tenant has enabled.
- **`MODULE_REGISTRY`** / `backend/src/services/module_registry.py` — the in-code
  registry. Each module entry has `description`, optional `depends_on`,
  `required_params`, `required_tax_rates`, `required_roles`. Helpers: `has_module()`,
  `module_required()` decorator, `activate_module()`.
- **Provisioning** (`tenant_provisioning_service.py`, `scripts/provision_tenant.py`)
  inserts `tenant_modules` rows.
- **Authorization** is the **intersection** of the user's module permissions (from
  the token) and the tenant's enabled modules (from `tenant_modules`) — see
  `tenant_module_routes.py`.
- Current modules: **FIN, ZZP, STR, TENADMIN** (all in-process Flask/MySQL).

S1 generalizes this so a registry entry can describe a module whose backing is an
**AWS SAM app** rather than in-process Flask code.

## Scope

In scope:

- Define a **module kind / backing** concept so `MODULE_REGISTRY` can describe both
  in-process (Flask/MySQL) modules and **SAM-backed** modules, without breaking the
  four existing modules.
- Define the **generic SAM-backed module plug-in contract**: register, entitle,
  authorize, scope (see R2).
- Fold the platform-level governance into myAdmin's existing `.kiro/steering`
  (identity, AWS accounts, product, module-hosting architecture) — authored under the
  myAdmin-as-base model, salvaging the reusable rules already drafted in the `mysaas`
  workspace steering.
- Record the S1 outcome and correct the downstream specs (S2) to the settled model.

Out of scope (explicit):

- **Any h-dcn-specific work** — members, webshop, events, its data or fields. S1
  makes myAdmin *ready to receive* a generic SAM-backed module.
- **Deploying an actual SAM app** or standing up its Lambda/API Gateway/DynamoDB.
- **S2 (JWT verification on the module plane)** — S1 defines *where* verification
  fits in the contract; implementing it is S2.
- **S3 (claims + system-of-record + DynamoDB projection)**, **S4 (token entitlement
  projection)**, **S5 (portal `tenant_id`)** — S1 states these as the contract's
  dependencies and designs the seams for them, but does not build them.
- Creating Pool B or the standing test pool (identity/infra steps).

## Requirements

### R1 — A module has a declared backing (kind)
- **R1.1** `MODULE_REGISTRY` entries can declare a **backing kind**: `flask`
  (in-process, the current default) or `sam` (backed by an AWS SAM app). Absence of
  the field means `flask` — the four existing modules (FIN/ZZP/STR/TENADMIN) remain
  valid and unchanged in behavior.
- **R1.2** A `sam`-backed entry additionally declares the metadata a client/gateway
  needs to reach it (e.g. an API base identifier resolved per environment), without
  hardcoding environment-specific URLs in the registry (fail-fast env resolution, no
  dangerous fallbacks).
- **R1.3** `depends_on`, `required_roles`, and entitlement via `tenant_modules` work
  identically regardless of backing kind — a SAM-backed module is entitled exactly
  like an in-process one.

### R2 — The generic SAM-backed module plug-in contract
A SAM-backed module MUST integrate through four generic seams (no module may invent
its own tenancy or auth):

- **R2.1 Register** — the module is declared in `MODULE_REGISTRY` with kind `sam`
  and its metadata; it is discoverable exactly like existing modules.
- **R2.2 Entitle** — a tenant gains the module by a `tenant_modules` row
  (`administration`, `module_name`, `is_active`); provisioning and the sysadmin
  module-management paths treat it the same as any module.
- **R2.3 Authorize** — the module authorizes each request from the **verified**
  Cognito token alone. It MUST NOT query MySQL per request. Roles come from
  `cognito:groups`; entitlement is available from the token (projected in S4) rather
  than a live `tenant_modules` read on the request path.
- **R2.4 Scope** — the module scopes all its data by `tenant_id` (DynamoDB partition
  key + IAM `LeadingKeys`). The tenant identity on the request derives only from the
  verified token.

### R3 — Two service planes, one identity, separate datastores
- **R3.1** The contract preserves two planes: the **Flask/MySQL plane** (myAdmin —
  admin, finance, tenant governance) and the **SAM/Lambda/DynamoDB plane** (modules).
  Both verify tokens against the issuing Cognito pool's JWKS.
- **R3.2** MySQL remains the **system of record** for tenant governance (`tenants`,
  `tenant_modules`, `user_tenant_roles`). Any data a SAM module needs from MySQL is
  reached via the token (authorization) or a **read-only, one-directional**
  MySQL→DynamoDB projection (S3) — never a live cross-plane MySQL query from a Lambda.
- **R3.3** The frontend routes by UI need (admin screens → Flask plane; module
  screens → module plane); cross-plane calls, when required, pass the user's token
  through API Gateway — never `lambda.invoke`, never a MySQL lookup on the module side.

### R4 — Backward compatibility (do no harm)
- **R4.1** The four existing modules and every current `tenant_modules` row,
  provisioning path, `has_module()` / `module_required()` call site, and the
  intersection-authorization in `tenant_module_routes.py` continue to work unchanged.
- **R4.2** Any registry/schema change is additive (new optional fields/columns);
  no destructive migration to existing module data.

### R5 — Governance folded into myAdmin steering (not forked)
- **R5.1** myAdmin's `.kiro/steering` gains the platform-level rules, authored under
  the myAdmin-as-base model: the two-pool identity model, the two-AWS-account model,
  the platform/tenant product framing, and the module-hosting architecture (the last
  already added to `architecture.md`).
- **R5.2** These rules are **salvaged and refactored** from the `mysaas`-workspace
  steering (`identity.md`, `aws-accounts.md`, `product.md`, `architecture.md`) —
  keeping the reusable substance, stripping every "mysaas is the trunk / rebuilt from
  h-dcn / lift into mysaas/admin" assumption, and referencing ADR 0003.
- **R5.3** No rival governance set is created; the durable "definition of record" is
  myAdmin's own steering. Trunk-era artifacts (`structure.md` trunk rule,
  `migration-workflow.md`) are NOT copied verbatim.
- **R5.4 Skills** — the `mysaas` skills carry reusable platform content that folds
  into myAdmin's existing skills:
  - `pr-checklist.md`: the mysaas version is a superset (two-plane security —
    verified-JWT/JWKS, DynamoDB `tenant_id` + IAM `LeadingKeys`, API Gateway
    authorizer; the "portal/module handlers never query MySQL at request time" rule;
    test-environment validation). Merge these into myAdmin's `pr-checklist.md`,
    reframed as "Flask plane + SAM-backed module plane," dropping the
    `migration-workflow.md` reference (trunk-era).
  - `specs-reference.md`: fold in the reasoning-vs-ADR-vs-steering convention and the
    roadmap-linkage pattern; correct paths (no `admin/backend`, `portal/backend`,
    `mysaas`) and ADR references (0003, not 0001/0002).

### R6 — Downstream specs reconciled (so the next step is correct)
- **R6.1** The S2 spec is corrected to the settled model: the "admin plane" is the
  **myAdmin Flask plane** (not `mysaas/admin/`), the "portal plane" is a **SAM-backed
  module plane** (not "rebuilt from h-dcn into mysaas"), and the S6b CI/CD-cutover
  framing is removed (there is no trunk to cut over to). S2's security substance
  (verify signatures, distrust headers, per-issuer JWKS) is preserved.
- **R6.2** Any other parked spec that assumes the mysaas trunk is flagged for the
  same reconciliation when it is next picked up.

### R7 — Decision recorded
- **R7.1** ADR 0003 already records the pivot; S1's completion confirms the module
  contract is consistent with it. If S1 makes any material sub-decision (e.g. the
  concrete `backing`/`kind` field name and shape), it is captured in the S1 design and,
  if architectural, an appended ADR.

## Acceptance criteria

- `MODULE_REGISTRY` can express a `sam`-backed module (kind + reach metadata) and the
  four existing modules still load and enforce exactly as before (R1, R4).
- The plug-in contract (register/entitle/authorize/scope) is documented such that a
  future module author can integrate a SAM app without inventing tenancy or auth, and
  without any Lambda querying MySQL per request (R2, R3).
- myAdmin steering contains the two-pool identity, two-account, product, and
  module-hosting rules, authored under myAdmin-as-base, with no residual mysaas-trunk
  framing and referencing ADR 0003 (R5).
- The S2 spec no longer references `mysaas/admin/`, "rebuilt from h-dcn," or S6b, and
  reads as "myAdmin Flask plane + SAM-backed module plane" while keeping its security
  requirements intact (R6).
- No change regresses an existing module, provisioning path, or authorization check
  (R4).

## How S1 enables S2 (and beyond)

- **S2** verifies JWT signatures on both planes. S1 gives S2 the correct plane model
  (Flask plane = myAdmin; module plane = SAM-backed) and the authorize seam (R2.3)
  that S2 fills in — with no trunk/cutover confusion.
- **S3/S4** slot into the contract's data-ownership seams (R3.2): S3 builds the
  read-only MySQL→DynamoDB projection and the claim contract; S4 projects entitlement
  into the token so R2.3's "no per-request MySQL" holds.
- **S5** adds `tenant_id` to the first real SAM-backed module's data, satisfying R2.4
  for that module.
