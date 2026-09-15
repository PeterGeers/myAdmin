# Overall Roadmap — Independently Executable Steps

> Top-level breakdown for evolving the two current systems (H-DCN portal +
> myAdmin) toward a unified multi-tenant solution. This is the **index**: each
> step below is a self-contained workstream that can be executed and shipped on
> its own, applied to the live/bespoke solution as it stands at that moment. The
> existing `migration_plan.md` (AWS account move) is just **one** of these steps.
>
> Companion to the other Analysis docs. This is a plan/outline — no code or
> infrastructure changed.
>
> **Reconciled forward (2026-09-15):** this roadmap has been updated to match the
> decisions in `second_thoughts.md` and ADRs 0001/0002. Two changes ripple
> through it: (1) the original merge-first **S1a + S1b** (merge the two
> workspaces, then reconcile their `.kiro` governance) is **replaced** by a
> single **S1 — establish the new target workspace `mysaas`** seeded from this
> Analysis folder, with governance *authored* fresh rather than *merged*
> (ADR 0001, ADR 0002); (2) the **single "survivor pool"** identity model is
> **replaced** by the **two-pool, audience-split** model — Pool A (admin/staff,
> always present) and Pool B (end-users, an optional per-tenant capability). See
> `second_thoughts.md` for the authoritative treatment of both.

## Design principle for every step

Each step must be:

- **Independently valuable** — worth doing even if the project paused right after.
- **Independently shippable** — leaves both live systems working; no half-broken
  intermediate state.
- **Reversible or low-risk** — or, where irreversible (data moves), gated by
  copy-verify-keep-old.
- **Loosely coupled** — depends only on its stated prerequisites, nothing else.

Steps are ordered by dependency and risk, but several can run in parallel (noted).

## Keeping governance current (cross-cutting rule)

Governance — steering, architecture docs, and ADRs — describes the system, and
the system changes at almost every step. If governance goes stale, Kiro steers by
rules that no longer match reality, which is worse than no steering because it is
confidently wrong. So governance is **not** a one-time S1b task that is then
frozen, and it is **not** a periodic "return to S1" sweep. Instead:

**Definition-of-done clause (applies to every step):**

> A step is not complete until any steering, architecture docs, and ADRs it
> invalidates or introduces have been updated to match — governance must reflect
> the system *as it now is*, not the plan.

**Rules:**

- **Fold the update into the step that causes the change** — the person finishing
  the step has the fresh knowledge; do not defer to a later batch pass.
- **Update at step completion, not mid-flight** — the system is temporarily
  in-between during implementation; refresh governance when the new state is
  stable and shippable, not on every intermediate commit.
- **ADRs are append-only** — record one ADR per material decision; supersede old
  ADRs, never rewrite them. ADRs are the durable decision log; steering is the
  active-rules layer that must track current truth.

**Per-step governance delta (which steps change the model):**

| Step | Governance to update on completion |
| --- | --- |
| S1 | Establish `mysaas` governance: author fresh steering + skills; record ADRs 0001 (new target workspace) and 0002 (myAdmin = pattern source + admin plane, not trunk). **Skills:** lift `pr-checklist` + `specs-reference` from myAdmin (generalize; not plane-specific) — when convenient. |
| S2 | Auth steering — signature-verified tokens, no trusting unverified headers; ADR |
| S3 | Auth/tenant steering — the claim contract; two-pool (audience-split) identity ADR; **tenant system-of-record (MySQL) + one-directional MySQL→DynamoDB projection** steering + ADR |
| S1b | **`tech.md` (admin, `fileMatch: admin/**`)** — Flask/MySQL conventions, authored when the admin code is lifted (test-environment target) |
| S4 | Architecture steering — entitlement projected into token, not read from MySQL per request; ADR |
| S5 | Schema-driven + DynamoDB steering — `tenant_id` key, isolation, overlay. **`tech.md` (portal, `fileMatch: portal/**`)** — SAM/Lambda/DynamoDB conventions, authored when the first portal slice lands. |
| S6 | Infra steering — nonprofit account, bucket separation incl. myAdmin's bucket; update `migration_plan.md` status |
| S6b | **Flip `structure.md` routing for the admin plane** (keep-the-lights-on → `mysaas/admin/`; legacy repo read-only) — on production CI/CD cutover |
| S7 | **`tech.md` (frontend, `fileMatch: web/**`) + `testing-frontend.md`** — React 19 + Vite + Vitest, `import.meta.env` fail-fast, per D6/D2 in `frontend_ui_standards.md` |
| S8 / S9 | `structure.md` / **frontend UI steering set** (`ui-standards.md`, `i18n.md`, `type-safety.md`, all `fileMatch: web/**`) — distilled from the settled D1–D5 decisions in `frontend_ui_standards.md`; merged layout, routing |
| S10 | Cleanup note; ADR closure; retire `migration-workflow.md` |

Roughly every step except S10 carries a governance delta — which is why it
belongs in each step's definition of done, not in a recurring return to S1.

## Dependency at a glance

```
S1 (new target workspace) ── seed mysaas from analysis, author governance; do first
S1b (lift admin CODE → mysaas/admin, test-env target) ── needs S1; early, no prod risk
S2 (JWT verify)        ── independent, do anytime  ─┐
S3 (tenant claims + MySQL system-of-record + →DynamoDB projection) ── needs S2 │
S4 (token projection)  ── needs S3                  ├─ identity track (in mysaas/admin, on test env)
S5 (H-DCN tenant_id)   ── needs S3 (claims exist)   │
S6b (admin PROD CI/CD cutover → mysaas) ── needs S1b + S2/S3 validated; late, gated
S6 (AWS move)          ── needs Pool A/Pool B decision (from S3 planning)
S7 (H-DCN React19+Vite) ── independent, do anytime ─┐
S8 (shared login+nav)  ── needs S2/S3              ├─ frontend track
S9 (unified SPA)       ── needs S7 + S8            ─┘
S10 (decommission)     ── last, needs S6 stable
```

---

## The steps

### S1 — Establish the new target workspace (`mysaas`)
> Replaces the original merge-first **S1a** (merge the two workspaces) and **S1b**
> (reconcile the two `.kiro` governance trees). Merging first was rejected because
> it means inheriting both codebases' legacy mess and reconciling artifacts of the
> past before deciding what the target should be. See `second_thoughts.md`
> ("Workspace strategy") and ADRs 0001/0002.
- **What:** create a new, clean workspace `mysaas` (at
  `/home/peter/projects/mysaas`) as the target platform **trunk**. Seed it from
  this Analysis folder (`.kiro/specs/multi-tenant/`), not from either legacy
  codebase. Make `mysaas` the definition of record — it owns the roadmap + ADRs
  from day one. Keep the `h-dcn` and `myAdmin` workspaces alive as the live
  systems; they receive only migration-driven or keep-the-lights-on changes, which
  are reflected back into `mysaas` governance.
- **What (governance — authored, not merged):** author **fresh** steering + skills
  for the merged reality rather than reconciling two legacy sets. This dissolves
  the old "reconcile two governances" problem entirely. New steering to author:
  the two-service-plane architecture, the tenant-claim contract, the **two-pool
  (audience-split) identity** model (Pool A admin/staff, Pool B optional
  per-tenant end-users), which datastore owns what (MySQL vs DynamoDB), the
  verified-JWT requirement. New ADRs in `docs/decisions/`: 0001 (new target
  workspace, legacy stays live), 0002 (myAdmin = pattern source + admin-plane code,
  not the single trunk), plus the ones each later step introduces (audience-split
  identity, MySQL system-of-record + token projection, two service planes /
  Railway stays).
- **What (patterns, not code):** lean toward myAdmin's proven multi-tenant
  patterns (tenant key, `@tenant_required`, provisioning, JWT verifier,
  `tenant_modules`, `tenant_template_config`) as the platform's patterns, and pull
  proven code into `mysaas` in thin vertical slices as later steps reach it — the
  admin-plane code largely intact, the portal domain rebuilt tenant-aware on the
  serverless/DynamoDB plane (patterns from myAdmin, not its Flask code).
- **Why first:** it gives every later step a coherent home and correct governance
  before real work starts; without it Kiro steers by rules that do not match the
  target.
- **Risk:** low, reversible (docs/config). The real risk to manage is discipline:
  `mysaas` must be the definition of record from day one or it becomes an
  aspirational graveyard while work stays in the old workspaces.
- **Prereq:** none.
- **Ref:** `second_thoughts.md` ("Workspace strategy", "myAdmin: base for
  PATTERNS + the admin plane, NOT the single trunk"); ADR 0001; ADR 0002;
  `myadmin_as_base.md` for the architecture decisions to turn into ADRs.

### S1b — Lift myAdmin's admin code into `mysaas/admin/` (test-environment target)
> Early code-lift, right after S1. This is the **code half** of moving the admin
> plane onto the trunk; the **production CI/CD cutover is a separate, late, gated
> step** (S6b). Splitting them is what makes lifting early safe: the lift targets the
> **test environment**, not production, so there is no production risk in doing it up
> front. This lets S2/S3/S4 be authored **once** in `mysaas/admin/` rather than
> written in the legacy repo and re-touched after a later lift.
- **What:** lift myAdmin's admin-plane code (Flask backend + its frontend) largely
  intact into `mysaas/admin/`, as a plane within the platform. It runs against the
  **test environment** — local **Docker MySQL** + `test_`-prefixed **DynamoDB** +
  the **standing test Cognito pool** (`environments_and_testing.md`).
- **Done =** the lifted code **builds and its tests pass in `mysaas` against the
  test environment.** **No production change** — production myAdmin still ships from
  the legacy repo until S6b.
- **Why safe early:** no live cutover, no data move, nothing production-facing —
  purely code relocation validated against test resources.
- **Why now:** makes `mysaas/admin/` the place S2/S3/S4 happen, so the admin auth /
  two-pool / system-of-record / sync code is written once on the trunk.
- **Risk:** low (test-environment only).
- **Prereq:** S1 (workspace + governance); the standing test Cognito pool exists.
- **Governance delta:** author `tech.md` (admin, `fileMatch: admin/**`) —
  Flask/MySQL conventions. (The `structure.md` routing flip is deferred to S6b, when
  production actually cuts over — see S6b.)
- **Ref:** `myadmin_as_base.md` (admin plane); ADR 0002 (myAdmin code as the admin
  plane, not the trunk); `environments_and_testing.md`.

### S2 — Verify JWT signatures on both backends
- **What:** verify tokens against the Cognito pool JWKS on H-DCN
  (`auth_utils.py` currently only base64-decodes) and confirm myAdmin's existing
  `jwt_verifier.py` is applied everywhere. Stop trusting unverified headers
  (`X-Enhanced-Groups`, `X-Tenant`) as the source of truth.
- **Why independent:** a security hardening that improves each system as-is,
  before any multi-tenant work.
- **Risk:** medium (auth path) but scoped; testable per handler.
- **Prereq:** **a standing test Cognito pool must exist** (see
  `environments_and_testing.md`) so verification is validated against the test pool,
  not production Pool A. Otherwise none — this is the non-negotiable foundation.
- **Ref:** `myadmin_as_base.md` (auth prerequisite), `first_thoughts.md` §1;
  `environments_and_testing.md` (test pool + gated promotion to prod).

### S3 — Define the tenant/role claims + tenant system-of-record + projection to DynamoDB
- **What (identity claims):** establish the **two-pool** identity model instead of a
  single survivor pool (see `second_thoughts.md`, "Identity model rethink"):
  - **Pool A — admin/staff** (universal, always present): reuse the existing
    myAdmin pool `eu-west-1_Hdp40eWmu`. Rich claims — `cognito:groups` for roles +
    `custom:tenants` (list) + entitlement projection.
  - **Pool B — end-users** (optional per-tenant capability, maps to a
    `tenant_modules` flag): a NEW clean pool. Simple claims — a single `tenant_id`
    (singular), no roles, no entitlement projection.
  Standardize each pool's claim shape and ensure both service planes verify against
  the right pool's JWKS and interpret its claims correctly. Legacy pools
  (`eu-west-1_OAT3oPCIm`, `eu-west-1_VtKQHhXGN`, `eu-west-1_fcUkvwjH5`) are
  decommissioned.
- **What (governance system-of-record):** make the admin plane (MySQL) authoritative
  for the tenant governance tables — `tenants`, `tenant_modules`,
  `user_tenant_roles` — covering **portal** tenants too (e.g. h-dcn as a tenant),
  not just finance tenants. This is where "which tenants exist, which modules each
  has, who holds which role" lives as truth.
- **What (projection to DynamoDB):** build the mechanism that projects this
  **tenant-level** governance data from MySQL into DynamoDB, so the portal (SAM)
  Lambdas can read tenant/module/role facts they need **without querying MySQL at
  request time**. This is the tenant-level companion to S4's per-user token
  projection — different data, different mechanism (a table projection, not a
  token), and both may be needed.
- **Guardrail — one-directional sync (mandatory):** the projection is **write-only
  from the sync process**. MySQL is the single source of truth; the DynamoDB copy is
  a **read-only projection**, never edited independently. Two-way writes = split
  brain = a cross-tenant/security incident waiting to happen. The sync writes on
  change (versioned) and the portal reads the projection; it never writes back.
- **Why this belongs in S3 (a prerequisite, not a later add-on):** S5 makes the
  portal tenant-aware and scopes by `tenant_id` — but it has nothing real to resolve
  against until tenant/module/role truth exists in MySQL and is projected to
  DynamoDB. So the system-of-record + projection must be in place with the claims,
  here, not retrofitted.
- **Distinct from S4:** S4 projects the *per-user resolved answer* into the **token**
  (authorization on the request path). S3's projection is *tenant-level governance*
  into a **DynamoDB table** (data a Lambda needs that is not user-scoped or is too
  large for the token). Do not conflate them.
- **Why independent:** establishes the identity contract + its governing data; each
  system can adopt the claims/projection without the other changing.
- **Risk:** medium — config + provisioning for the pools, plus building the sync
  (needs write-time validation, versioning, cache invalidation on the read side).
  Extra cost of the two-pool model is bounded: two verifiers + a deliberate rule for
  the admin-and-member person (defer the cross-pool linking/promotion material — not
  core).
- **Prereq:** S2 (verify before trusting claims), and a **standing test Cognito
  pool** (`environments_and_testing.md`) — two-pool provisioning + claim/sync changes
  are validated on the test pool before touching production Pool A. Also fixes the
  Pool A / Pool B decision that `migration_plan.md` Gate 1 needs. Done **after S1b**
  so the system-of-record + sync code lands in `mysaas/admin/` (written once on the
  trunk, validated on the test environment; production cutover is S6b).
- **Ref:** `second_thoughts.md` (identity model rethink, "Pool B is a per-tenant
  option", "Managing Pool B tenant relationships"); `myadmin_as_base.md` (identity
  plane, balance section).

### S4 — Project resolved entitlement into the token (Pre-Token-Generation trigger)
- **What:** a Cognito Pre-Token-Generation Lambda that computes each user's
  resolved tenants + effective modules from MySQL once at login and stamps them
  as claims — so the request path never queries MySQL for entitlement.
- **Why independent:** improves both planes' authorization without changing
  business logic; can ship after claims exist.
- **Risk:** medium; one Lambda + a token-lifetime/revocation decision.
- **Prereq:** S3.
- **Ref:** `myadmin_as_base.md` ("The fix: system of record + projection").

### S5 — Add the tenant dimension to the H-DCN (portal) data
- **What:** add `tenant_id` partition key to H-DCN DynamoDB tables, key + IAM
  `LeadingKeys` isolation, and the tenant-field overlay. Migrate existing H-DCN
  data to carry its own `tenant_id` (dry-run first).
- **Why independent:** makes the portal tenant-aware; H-DCN keeps working as a
  single-tenant instance of the new model.
- **Risk:** medium-high (data migration) — gated by dry-run + backup.
- **Prereq:** S3 (claims exist to scope against).
- **Ref:** `tenant_field_config.md`, `rewrite_vs_refactor.md` (DynamoDB tenancy).

### S6 — Move myAdmin's AWS footprint to the nonprofit account
- **What:** the existing detailed plan — recreate SNS/S3/DynamoDB in nonprofit,
  copy data, handle Cognito, repoint Railway `.env`. Railway/MySQL stay put.
- **Why independent:** infra relocation; once repointed, myAdmin runs unchanged
  from nonprofit resources.
- **Risk:** high (production data) — its own gated plan.
- **Prereq:** Pool A / Pool B decision from S3.
- **Ref:** `migration_plan.md` — this whole step **is** that document, specifically
  its Gate 1 through Phase 5 (Phase 6 is S10, below). That plan tags each phase
  back to this step.

### S6b — Cut production admin CI/CD over to `mysaas` (the production half of the lift)
> The **production half** of the admin lift whose code half was S1b. Deliberately
> **late and gated**: production myAdmin cuts over to deploy from `mysaas` only after
> the trunk code is hardened and validated (S2/S3, and S4 where relevant) on the test
> environment. So production is cut over to *already-tested* code, never raw lifted
> code — which is why S1b could safely happen early.
- **What:** flip production CI/CD so **Railway deploys the admin plane from `mysaas`**,
  not from the legacy myAdmin repo. Railway/MySQL themselves stay put; only the
  deploy source changes.
- **Definition-of-record flip:** on cutover, the `structure.md` routing rule flips
  for the admin plane — admin keep-the-lights-on fixes now happen in `mysaas/admin/`,
  and the legacy myAdmin repo becomes read-only/archived for admin code.
- **Why independent:** a pipeline-source relocation; the running system is unchanged
  except for where its deploys originate. Independent of the AWS footprint move (S6)
  — either can go first.
- **Risk:** medium — production CI/CD cutover. Gate on: green build from `mysaas`,
  S2/S3 validated on the test environment, a staging deploy, and a rollback path
  (legacy pipeline disabled-but-restorable until proven). No data moves here.
- **Prereq:** S1b (code lifted), and S2/S3 validated on the test environment.
- **Governance delta:** flip the `structure.md` admin-plane routing note; mark the
  legacy myAdmin repo read-only for admin code.
- **Ref:** `myadmin_as_base.md`; `structure.md` (routing rule it flips);
  `environments_and_testing.md` (gated promotion test → prod).

### S7 — Upgrade H-DCN frontend to React 19 + Vite
- **What:** upgrade H-DCN from React 18/CRA to React 19 + Vite to match myAdmin;
  map `process.env.REACT_APP_*` → `import.meta.env` with fail-fast checks.
- **Why independent:** modernizes H-DCN's tooling; valuable on its own and the
  pivotal enabler for a single-SPA merge.
- **Risk:** medium; regression-test the H-DCN UI (Chakra v2 runs on React 19).
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
- **What:** combine both frontends into a single React 19 + Vite + Chakra v2 app
  with routing between domains; shared theme/components.
- **Why independent:** the final frontend consolidation; optional if S8 is
  "good enough."
- **Risk:** medium; mostly routing + folder integration once S7 is done.
- **Prereq:** S7 (H-DCN on React 19 + Vite) + S8 (shared identity/nav proven).
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
- **Code-lift track (split):** S1b lifts the admin **code** into `mysaas/admin/`
  early (test-environment target, no prod risk) so S2/S3/S4 are written once on the
  trunk; S6b is the **late, gated production CI/CD cutover** (Railway deploys admin
  from `mysaas`), done only after S2/S3 are validated on the test environment.
  Independent of the infra track (S6).
- **Frontend track:** S7 and S8 can proceed alongside the identity track; S9 after
  both.
- **Infra track:** S6 after the S3 Pool A / Pool B decision; S10 last.
- **S1** comes first and makes the rest easier; it is what gives Kiro correct,
  authored governance in the new target workspace before real work starts.

## Suggested first moves

1. **S1** (establish the `mysaas` target workspace) — seed from this analysis,
   author fresh steering/skills, record ADRs 0001/0002; makes Kiro coherent and
   gives every later step a home.
2. **Stand up the standing test Cognito pool** (`environments_and_testing.md`) —
   the prerequisite that makes all identity work safe (test-first, never prod-first).
3. **S1b** (lift admin code into `mysaas/admin/`, test-environment target) — so the
   identity work below is written once on the trunk, not in the legacy repo.
4. **S2** (JWT verification) — the security foundation everything else assumes.
5. **S3 Pool A / Pool B decision** — unblocks both S6 (AWS move) and the rest of
   the identity track.
   (Production admin CI/CD cutover, S6b, comes later — only after S2/S3 are validated
   on the test environment.)

Everything else sequences off those. Each step, when reached, should get its own
requirements/design spec under `.kiro/specs/multi-tenant/` before execution — this
roadmap is the index that ties them together.

## Note on scope

This roadmap deliberately keeps the two datastores separate (MySQL for finance,
DynamoDB for the portal) and Railway in place. "One system" here means one
identity, one workspace, one AWS account, and (optionally) one SPA — **not** one
database. See `rewrite_vs_refactor.md` and `myadmin_as_base.md` for that rationale.
