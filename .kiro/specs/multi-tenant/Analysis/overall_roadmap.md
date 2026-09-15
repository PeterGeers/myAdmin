# Overall Roadmap — Independently Executable Steps

> Top-level breakdown for evolving **myAdmin** into the multi-tenant platform that
> hosts additional applications as **modules**, including AWS SAM (Lambda +
> DynamoDB) apps such as the h-dcn domain (the `members`, `events`, and `webshop`
> modules, sharing one SAM stack). This is the **index**: each step
> below is a self-contained workstream that can be executed and shipped on its own,
> applied to myAdmin as it stands at that moment. The `migration_plan.md` (AWS
> account move) is just **one** of these steps.
>
> Companion to the other Analysis docs. This is a plan/outline — no code or
> infrastructure changed by this document itself.

## The settled model (do not relitigate)

- **myAdmin IS the platform base / trunk.** We evolve myAdmin **in place**. There is
  no separate `mysaas` trunk and no "merge two workspaces" step. The earlier plan to
  start a fresh codebase (`mysaas`) was abandoned; work happens here, in myAdmin,
  grounded in real code.
- **Additional apps are imported as platform MODULES, not new trunks.** myAdmin
  already has a live module system — the `tenant_modules` table (keyed by
  `administration`), `module_registry.py` / `MODULE_REGISTRY`, and the provisioning
  services. Today its modules are FIN, ZZP, STR, TENADMIN. The platform work extends
  this so a module can be **backed by an AWS SAM app** (Lambda + DynamoDB) rather
  than only by in-process Flask/MySQL code. The h-dcn domain becomes **three such
  SAM-backed modules — `members`, `events`, `webshop` — sharing one SAM stack** (one
  Lambda/DynamoDB deployment, one API base), each entitled independently via
  `tenant_modules`.
- **myAdmin's existing `.kiro/steering` is the authoritative base governance.** New
  platform concepts are **folded into** the existing steering; they never replace it
  with a fresh, from-scratch governance set.
- Identity remains **two audience-split Cognito pools** (Pool A admin/staff, Pool B
  optional per-tenant end-users), MySQL stays the **system of record** for tenant
  governance, and entitlement is **projected into the token** so the SAM plane never
  queries MySQL per request. Those decisions (below) are unchanged by the pivot.

## Design principle for every step

Each step must be:

- **Independently valuable** — worth doing even if the project paused right after.
- **Independently shippable** — leaves myAdmin (and any live module) working; no
  half-broken intermediate state.
- **Reversible or low-risk** — or, where irreversible (data moves), gated by
  copy-verify-keep-old.
- **Loosely coupled** — depends only on its stated prerequisites, nothing else.

Steps are ordered by dependency and risk, but several can run in parallel (noted).

## Keeping governance current (cross-cutting rule)

Governance — steering, architecture docs, and ADRs — describes the system, and the
system changes at almost every step. If governance goes stale, Kiro steers by rules
that no longer match reality, which is worse than no steering because it is
confidently wrong. So governance is **not** a one-time task that is then frozen, and
it is **not** a periodic "return to S1" sweep. Instead:

**Definition-of-done clause (applies to every step):**

> A step is not complete until any steering, architecture docs, and ADRs it
> invalidates or introduces have been updated to match — governance must reflect the
> system *as it now is*, not the plan.

**Rules:**

- **Fold the update into the step that causes the change** — the person finishing
  the step has the fresh knowledge; do not defer to a later batch pass.
- **Update at step completion, not mid-flight** — the system is temporarily
  in-between during implementation; refresh governance when the new state is stable
  and shippable, not on every intermediate commit.
- **Fold into myAdmin's existing steering; do not fork it.** New platform rules
  extend the current `.kiro/steering` files (or add narrowly-scoped `fileMatch`
  files). Never author a rival governance set.
- **ADRs are append-only** — record one ADR per material decision; supersede old
  ADRs, never rewrite them. ADRs are the durable decision log; steering is the
  active-rules layer that must track current truth.

**Per-step governance delta (which steps change the model):**

| Step | Governance to update on completion |
| --- | --- |
| S1 | Prepare myAdmin as the platform base for SAM-backed modules: extend `architecture.md` / `tech.md` with the module-hosting contract and the two-plane picture; record ADR 0003 (myAdmin is the platform base; evolve in place; import apps as SAM-backed modules). Note the generic SAM-module plug-in contract in steering. |
| S2 | Auth steering — signature-verified tokens on the module plane too, no trusting unverified headers; ADR |
| S3 | Auth/tenant steering — the claim contract; two-pool (audience-split) identity ADR; **tenant system-of-record (MySQL) + one-directional MySQL→DynamoDB projection** steering + ADR |
| S4 | Architecture steering — entitlement projected into token, not read from MySQL per request; ADR |
| S5 | Schema-driven + DynamoDB steering for the SAM module plane — `tenant_id` key, isolation, overlay. **`tech.md` (SAM module, `fileMatch` the module subtree)** — SAM/Lambda/DynamoDB conventions, authored when the first SAM module lands. |
| S6 | Infra steering — nonprofit account, bucket separation incl. myAdmin's bucket; update `migration_plan.md` status |
| S7 | **`tech.md` (frontend) + `testing-frontend.md`** — React 19 + Vite + Vitest, `import.meta.env` fail-fast, per D6/D2 in `frontend_ui_standards.md` |
| S8 / S9 | `structure.md` / **frontend UI steering set** (`ui-standards.md`, `i18n.md`, `type-safety.md`) — distilled from the settled D1–D5 decisions in `frontend_ui_standards.md`; merged layout, routing |
| S10 | Cleanup note; ADR closure; retire the migration workflow doc |

Roughly every step except S10 carries a governance delta — which is why it belongs
in each step's definition of done, not in a recurring return to S1.

## Dependency at a glance

```
S1 (prepare myAdmin for SAM-backed modules) ── do first; extend governance in place
S2 (JWT verify on the module plane)   ── independent, do anytime  ─┐
S3 (tenant claims + MySQL system-of-record + →DynamoDB projection) ── needs S2 │
S4 (token projection)  ── needs S3                                 ├─ identity track
S5 (portal/SAM tenant_id) ── needs S3 (claims exist)               │
S6 (AWS move)          ── needs Pool A/Pool B decision (from S3)
S7 (portal React19+Vite) ── independent, do anytime               ─┐
S8 (shared login+nav)  ── needs S2/S3                              ├─ frontend track
S9 (unified SPA)       ── needs S7 + S8                            ─┘
S10 (decommission)     ── last, needs S6 stable
```

---

## The steps

### S1 — Prepare myAdmin to host SAM-backed modules (do first)
- **What:** make myAdmin's existing module system able to host a module **backed by
  an AWS SAM app** (Lambda + DynamoDB), not only in-process Flask/MySQL code. Define
  the **generic plug-in contract**: how a SAM-backed module registers in
  `MODULE_REGISTRY`, how a tenant is entitled to it via `tenant_modules`, how the
  module authorizes requests from the verified token, and how it scopes data by
  `tenant_id`. Generic platform capability only — **no h-dcn-specific work**.
- **What (governance — folded in, not forked):** extend myAdmin's existing
  `.kiro/steering` (`architecture.md`, `tech.md`) to describe the two-plane picture
  (Flask/MySQL admin+finance plane + SAM/Lambda/DynamoDB module plane) and the
  SAM-module plug-in contract. Record **ADR 0003** — "myAdmin is the platform base;
  evolve in place; import apps as SAM-backed modules" — which supersedes the retired
  0001/0002 (new-trunk / pattern-source ADRs).
- **What (patterns, already present):** lean on myAdmin's proven multi-tenant
  machinery as the platform's machinery — the `administration` tenant key,
  `@tenant_required`, `tenant_context.py`, provisioning, `jwt_verifier.py`,
  `tenant_modules`, `tenant_template_config`. S1 generalizes the module concept; it
  does not reinvent tenancy.
- **Why first:** it gives every later step a coherent home and correct governance in
  the codebase where the work actually happens.
- **Risk:** low, reversible (docs/config + a contract definition).
- **Prereq:** none.
- **Ref:** `myadmin_as_base.md` (two planes, module hosting); ADR 0003;
  `second_thoughts.md` (identity + account model that S3/S6 build on).

### S2 — Verify JWT signatures on both planes
- **What:** verify tokens against the Cognito pool JWKS on the SAM/module plane (a
  fresh SAM module must verify, not base64-decode), and confirm myAdmin's existing
  `jwt_verifier.py` is applied everywhere on the Flask plane. Stop trusting
  unverified headers (e.g. `X-Tenant`, `X-Enhanced-Groups`) as the source of truth.
- **Why independent:** a security hardening that improves the platform as-is, before
  any further multi-tenant module work.
- **Risk:** medium (auth path) but scoped; testable per handler.
- **Prereq:** **a standing test Cognito pool must exist** (see
  `environments_and_testing.md`) so verification is validated against the test pool,
  not production Pool A. Otherwise none — this is the non-negotiable foundation.
- **Ref:** `myadmin_as_base.md` (auth prerequisite), `first_thoughts.md` §1;
  `environments_and_testing.md` (test pool + gated promotion to prod).

### S3 — Define the tenant/role claims + tenant system-of-record + projection to DynamoDB
- **What (identity claims):** establish the **two-pool** identity model instead of a
  single pool (see `second_thoughts.md`, "Identity model rethink"):
  - **Pool A — admin/staff** (universal, always present): reuse the existing myAdmin
    pool `eu-west-1_Hdp40eWmu`. Rich claims — `cognito:groups` for roles +
    `custom:tenants` (list) + entitlement projection.
  - **Pool B — end-users** (optional per-tenant capability, maps to a
    `tenant_modules` flag): a NEW clean pool. Simple claims — a single `tenant_id`
    (singular), no roles, no entitlement projection.
  Standardize each pool's claim shape and ensure both planes verify against the
  right pool's JWKS and interpret its claims correctly. Legacy pools
  (`eu-west-1_OAT3oPCIm`, `eu-west-1_VtKQHhXGN`, `eu-west-1_fcUkvwjH5`) are
  decommissioned.
- **What (governance system-of-record):** keep the myAdmin admin plane (MySQL)
  authoritative for the tenant governance tables — `tenants`, `tenant_modules`, and
  `user_tenant_roles` (per-user, per-tenant role grants: `email`, `administration`,
  `role`) — covering **SAM-backed modules and their tenants** (e.g. h-dcn as a tenant
  entitled to the `members`/`events`/`webshop` modules), not just finance tenants.
  This is where "which tenants exist,
  which modules each has, and what each user may do in each tenant" lives as truth.
  The Flask plane already reads `user_tenant_roles` via a cached lookup
  (`backend/src/auth/role_cache.py`); only **global** roles (SysAdmin etc.) come from
  `cognito:groups`. (The old `tenant_role_allocation` table is retired.)
- **What (projection to DynamoDB):** build the mechanism that projects this
  **tenant-level** governance data from MySQL into DynamoDB, so a SAM module's
  Lambdas can read tenant/module/role facts they need **without querying MySQL at
  request time**. This is the tenant-level companion to S4's per-user token
  projection — different data, different mechanism (a table projection, not a token),
  and both may be needed.
- **Guardrail — one-directional sync (mandatory):** the projection is **write-only
  from the sync process**. MySQL is the single source of truth; the DynamoDB copy is
  a **read-only projection**, never edited independently. Two-way writes = split
  brain = a cross-tenant/security incident waiting to happen. The sync writes on
  change (versioned) and the module reads the projection; it never writes back.
- **Why this belongs in S3 (a prerequisite, not a later add-on):** S5 makes a SAM
  module tenant-aware and scopes by `tenant_id` — but it has nothing real to resolve
  against until tenant/module/role truth exists in MySQL and is projected to
  DynamoDB. So the system-of-record + projection must be in place with the claims,
  here, not retrofitted.
- **Distinct from S4:** S4 projects the *per-user resolved answer* into the **token**
  (authorization on the request path). S3's projection is *tenant-level governance*
  into a **DynamoDB table** (data a Lambda needs that is not user-scoped or is too
  large for the token). Do not conflate them.
- **Why independent:** establishes the identity contract + its governing data; each
  plane can adopt the claims/projection without the other changing.
- **Risk:** medium — config + provisioning for the pools, plus building the sync
  (write-time validation, versioning, cache invalidation on the read side). Extra
  cost of the two-pool model is bounded: two verifiers + a deliberate rule for the
  admin-and-member person (defer the cross-pool linking/promotion material — not
  core).
- **Prereq:** S2 (verify before trusting claims), and a **standing test Cognito
  pool** (`environments_and_testing.md`) — two-pool provisioning + claim/sync changes
  are validated on the test pool before touching production Pool A. Also fixes the
  Pool A / Pool B decision that `migration_plan.md` Gate 1 needs.
- **Ref:** `second_thoughts.md` (identity model rethink, "Pool B is a per-tenant
  option", "Managing Pool B tenant relationships"); `myadmin_as_base.md` (identity
  plane, balance section).

### S4 — Project resolved entitlement into the token (Pre-Token-Generation trigger)
- **What:** a Cognito Pre-Token-Generation Lambda that computes each user's resolved
  per-tenant access from MySQL once at login — for each tenant, their per-tenant
  **roles** (`user_tenant_roles`) intersected with the tenant's enabled **modules**
  (`tenant_modules`) — and stamps it into the token as a compact claim, so the
  request path never queries MySQL for authorization. This is what lets a SAM-backed
  module answer "what may this user do in this tenant?" from the token alone. It is
  the **Lambda-plane equivalent of the Flask plane's `role_cache.py`**: the same
  resolved per-tenant answer, carried in the token instead of a server-side cache
  (myAdmin's Flask plane can read/cache MySQL cheaply today; a Lambda must not).
- **Why independent:** improves both planes' authorization without changing business
  logic; can ship after claims exist.
- **Risk:** medium; one Lambda + a token-lifetime/revocation decision.
- **Prereq:** S3.
- **Ref:** `myadmin_as_base.md` ("The fix: system of record + projection").

### S5 — Add the tenant dimension to the h-dcn SAM stack's data
- **What:** for the h-dcn SAM stack (the `members`, `events`, `webshop` modules,
  sharing one deployment), add a `tenant_id` partition key to its DynamoDB tables, key
  + IAM `LeadingKeys` isolation, and the tenant-field overlay. Migrate existing h-dcn
  data to carry its own `tenant_id` (dry-run first).
- **Why independent:** makes the h-dcn modules tenant-aware; they keep working as a
  single-tenant instance of the new model.
- **Risk:** medium-high (data migration) — gated by dry-run + backup.
- **Prereq:** S3 (claims exist to scope against).
- **Ref:** `tenant_field_config.md`, `rewrite_vs_refactor.md` (DynamoDB tenancy).

### S6 — Move myAdmin's AWS footprint to the nonprofit account
- **What:** the existing detailed plan — recreate SNS/S3/DynamoDB in nonprofit, copy
  data, handle Cognito, repoint Railway `.env`. Railway/MySQL stay put.
- **Why independent:** infra relocation; once repointed, myAdmin runs unchanged from
  nonprofit resources.
- **Risk:** high (production data) — its own gated plan.
- **Prereq:** Pool A / Pool B decision from S3.
- **Ref:** `migration_plan.md` — this whole step **is** that document, specifically
  its Gate 1 through Phase 5 (Phase 6 is S10, below). That plan tags each phase back
  to this step.

### S7 — Upgrade the portal frontend to React 19 + Vite
- **What:** upgrade the h-dcn portal frontend from React 18/CRA to React 19 + Vite to
  match myAdmin; map `process.env.REACT_APP_*` → `import.meta.env` with fail-fast
  checks.
- **Why independent:** modernizes the portal's tooling; valuable on its own and the
  pivotal enabler for a single-SPA merge.
- **Risk:** medium; regression-test the portal UI (Chakra v2 runs on React 19).
- **Prereq:** none (can run in parallel with the identity/AWS tracks).
- **Ref:** `frontend_merge.md`.

### S8 — Shared login + shared top navigation (two SPAs, one product feel)
- **What:** both SPAs use the one Cognito pool/token; add a shared top nav so
  crossing domains feels like one product.
- **Why independent:** delivers most of the "one product" experience cheaply,
  without merging code.
- **Risk:** low.
- **Prereq:** S2/S3 (shared verified identity).
- **Ref:** `frontend_merge.md` (Option 3).

### S9 — Merge into one unified SPA
- **What:** combine both frontends into a single React 19 + Vite + Chakra v2 app with
  routing between domains; shared theme/components.
- **Why independent:** the final frontend consolidation; optional if S8 is "good
  enough."
- **Risk:** medium; mostly routing + folder integration once S7 is done.
- **Prereq:** S7 (portal on React 19 + Vite) + S8 (shared identity/nav proven).
- **Ref:** `frontend_merge.md` (Option 1).

### S10 — Decommission the old AWS account resources
- **What:** after a stable soak, tear down the old account's bucket/topic/tables/
  pool. Final backup first.
- **Why independent / last:** the only truly irreversible cleanup.
- **Risk:** high but controlled; only after everything proven.
- **Prereq:** S6 stable in production.
- **Ref:** `migration_plan.md` Phase 6.

---

## Parallel tracks (what can run at once)

- **Identity track:** S2 → S3 → S4 (and S5 after S3).
- **Frontend track:** S7 and S8 can proceed alongside the identity track; S9 after
  both.
- **Infra track:** S6 after the S3 Pool A / Pool B decision; S10 last.
- **S1** comes first and makes the rest easier; it is what gives myAdmin the module
  contract and correct governance before real module work starts.

## Suggested first moves

1. **S1** (prepare myAdmin to host SAM-backed modules) — define the module plug-in
   contract, extend steering, record ADR 0003; makes every later step coherent.
2. **Stand up the standing test Cognito pool** (`environments_and_testing.md`) — the
   prerequisite that makes all identity work safe (test-first, never prod-first).
3. **S2** (JWT verification) — the security foundation everything else assumes.
4. **S3 Pool A / Pool B decision** — unblocks both S6 (AWS move) and the rest of the
   identity track.

Everything else sequences off those. Each step, when reached, should get its own
requirements/design spec under `.kiro/specs/multi-tenant/` before execution — this
roadmap is the index that ties them together.

## Note on scope

This roadmap deliberately keeps the two datastores separate (MySQL for the
admin/finance plane, DynamoDB for SAM-backed modules) and Railway in place. "One
system" here means one identity, one platform base (myAdmin), one AWS account, and
(optionally) one SPA — **not** one database. See `rewrite_vs_refactor.md` and
`myadmin_as_base.md` for that rationale.
