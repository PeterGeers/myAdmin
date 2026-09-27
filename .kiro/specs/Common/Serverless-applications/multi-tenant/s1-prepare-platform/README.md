# S1 — Prepare myAdmin to Host SAM-Backed Modules

- Status: Complete
- Roadmap step: **S1** (`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`)
- Decision of record: **ADR 0003** (`docs/decisions/0003-myadmin-is-platform-base-modules-as-sam-apps.md`)

## What this spec is

The first execution step of the multi-tenant roadmap. It makes **myAdmin — the
platform base, evolved in place** — able to host a module **backed by an AWS SAM app**
(Lambda + DynamoDB), not only by in-process Flask/MySQL code. It defines the generic
plug-in contract, extends the module registry, and folds the platform governance into
myAdmin's steering.

It is **platform capability + governance only**: no h-dcn-specific work, no SAM app
deployed. Its purpose is to lock in the settled direction so later steps (starting
with S2) do not drift back toward the abandoned `mysaas` trunk.

## Reading order

1. `requirements.md` — goal, scope, R1–R7, acceptance criteria, how S1 enables S2.
2. `design.md` — the `backing` (kind) extension to `MODULE_REGISTRY`, the four-seam
   contract (register / entitle / authorize / scope), the two-plane model, and the
   governance-refactor mapping.
3. `tasks.md` — phased checklist (module descriptor → contract doc → steering/skills
   refactor → downstream S2 reconciliation → verify).

## Grounded in real code

- `backend/src/services/module_registry.py` — `MODULE_REGISTRY`, `has_module()`,
  `module_required()`, `activate_module()`.
- `tenant_modules` table (keyed by `administration`); provisioning in
  `tenant_provisioning_service.py` / `scripts/provision_tenant.py`.
- Intersection authorization in `backend/src/tenant_module_routes.py`.
- Current modules: FIN, ZZP, STR, TENADMIN (all in-process Flask/MySQL).

## Enables

- **S2** — JWT verification (the contract's Authorize seam, correct plane model).
- **S3/S4** — claims + read-only MySQL→DynamoDB projection + token entitlement
  (the data-ownership seams).
- **S5** — `tenant_id` on the first real SAM-backed module's data.

## Governance salvage — what was excluded and why (T3.5)

Phase 3 folds the reusable `mysaas` steering into myAdmin (identity, aws-accounts,
product, architecture, and the merged skills). Two `mysaas` steering files are
**deliberately not copied** because they encode the abandoned trunk model that
ADR 0003 supersedes.

- **`mysaas/.kiro/steering/structure.md` — NOT copied.** It defines the trunk /
  "definition of record" model: `mysaas` is the trunk, a `mysaas/` workspace layout
  with `portal/`, `admin/`, and `shared/` directories, "governance authored here, not
  merged / do not import the legacy `.kiro` trees," the legacy-vs-target routing rule,
  and the S6b production cutover (per-plane flip). This directly contradicts ADR 0003:
  **myAdmin IS the platform base, evolved in place** — there is no separate trunk and
  no workspace merge, apps are imported as SAM-backed modules, and governance is
  myAdmin's existing `.kiro/steering` extended in place (fold in, do not fork). Copying
  it would reintroduce the trunk framing S1 exists to lock out.

- **`mysaas/.kiro/steering/migration-workflow.md` — NOT copied.** It is explicitly
  **temporary** migrate-into-trunk discipline: move legacy myAdmin + h-dcn code into
  `mysaas` in thin vertical slices, then retire the file at roadmap S10 when both
  legacy systems are decommissioned. Under ADR 0003 there is no trunk to migrate
  *into*, so the workflow does not apply. Its one reusable idea — the
  "keep-governance-current" definition of done (update steering/ADRs in the change that
  invalidates them, not a later batch) — survives as a general practice and already
  appears in this spec's `tasks.md` header and definition of done; the file itself is
  not folded in.
## Downstream reconciliation sweep (T4.2)

The whole multi-tenant spec tree (`.kiro/specs/multi-tenant/`) was grepped for the
trunk-model terms — `mysaas`, `mysaas/admin`, `S1b`, `S6b`, "rebuilt from h-dcn",
`admin/backend`, `portal/backend`, and the `admin plane` / `portal plane` plane
naming. Every remaining hit is an **intentional abandoned-plan or reconciliation
record**, not a spec still written as if the `mysaas` trunk is live:

- **`Analysis/overall_roadmap.md`** and **`Analysis/second_thoughts.md`** — the
  founding reasoning. Their `mysaas` mentions explicitly say the trunk plan **was
  abandoned** ("start a fresh codebase (`mysaas`) was abandoned"; "That plan is
  abandoned"). Kept on purpose.
- **`s0-transfer-and-brief/README.md`** — the Step-0 handoff/decision brief. Its
  `mysaas` / `S1b` / `S6b` mentions record **THE PIVOT** (myAdmin is the base, there
  is no separate `mysaas` trunk, the earlier S1 is void) and list the analysis docs
  that Part A must rewrite off the trunk framing. It documents the move *away from*
  the trunk model, so it is an abandoned-plan record, not stale trunk content.
- **`s1-prepare-platform/`** (`tasks.md`, `design.md`, `requirements.md`, this
  `README.md`) — describe the salvage/reconciliation work itself (governance fold-in,
  the "not copied" `structure.md` / `migration-workflow.md`, and the S2 correction).
  These name the `mysaas` sources on purpose.

**S2 is reconciled (T4.1 confirmed).** A grep of `s2-jwt-verification/` for
`mysaas` / `mysaas/admin` / `S1b` / `S6b` / "rebuilt from h-dcn" / `admin/backend` /
`portal/backend` returns **no matches**. Its plane naming now reads **Flask plane**
(myAdmin — Flask/MySQL) and **module plane** (the h-dcn SAM stack), and the S6b
CI/CD-cutover framing is gone (ships through myAdmin's existing pipeline). Security
substance intact.

**Other parked specs:** the only step-spec folders under `.kiro/specs/multi-tenant/`
are `s0-transfer-and-brief`, `s1-prepare-platform`, and `s2-jwt-verification`
(plus `Analysis/`). **No other parked spec needs reconciliation** — there is no
step-spec still written on the live-trunk assumption. (The `Analysis/` docs still
carry trunk-era text, but their clean rewrite is already owned by S0 Part A, not by
this downstream-spec sweep.)
