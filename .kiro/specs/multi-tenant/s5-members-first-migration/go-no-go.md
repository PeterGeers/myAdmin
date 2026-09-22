# S5 — Members migration: Go / No-Go decision + lessons learned

- Status: **Recorded (task 6.2)** — evidence + recommendation from the completed pilot
  build (Steps 1–6). Awaits the human reviewer's countersign + the live look & feel/UX
  walkthrough before the gate is final.
- Purpose: the explicit decision point (user requirement) on whether to migrate further
  h-dcn apps (Events, Webshop), plus the lessons that feed a roadmap revision.

> This records the evidence the pilot actually demonstrated in test/local — grounded in
> what was built and exercised, not predicted up front. Migrating further apps is **gated**
> on the Go decision here (R8.3). Steps 1–6 are implemented + tested; the task-6.0
> parity/walkthrough harness emitted the report cited below. What still needs a human is
> called out explicitly (live UX walkthrough; the conditional Step 7 Pool A trigger).

## Decision (to record at the gate)

- **Verdict:** **Conditional-Go** — the pilot proved the platform pattern end-to-end in
  test/local: the generic Members module answers h-dcn's full behavioural contract (24/24
  routes), authz incl. regional scope holds, backfill round-trips, and the lifecycle runs
  through the engine — with the tenant-agnostic core carrying h-dcn as pilot **data**, not
  a code branch. The conditions before this becomes a full Go are the items that need a
  human / live environment, not code that failed: (1) the live **look & feel / UX
  walkthrough** (the one MANUAL parity item), and (2) the conditional **Step 7 Pool A**
  live-token trigger, if the pilot needs live-token entitlement. Further app migrations
  (Events / Webshop) are **gated** on this decision (R8.3).
- **Date / reviewer:** _pending human sign-off_ — this task records the evidence +
  recommendation; the human reviewer owns the final countersign after the live UX
  walkthrough. `Reviewer: __________  Date: __________  Outcome (Go / Conditional-Go /
  No-Go): __________`

## Evidence to gather during the pilot (fill in)

- **Parity** — does the migrated Members module match h-dcn's known behavioural contract
  for the pilot tenant (R8.1)? Evidence: the task-6.0 parity/walkthrough harness
  (`sam/tests/members_parity_harness.py`, driven by `test_members_parity_harness.py` —
  **all asserted checks pass**; MANUAL items are checklist flags, not assertions). The
  harness walks the migrated module end-to-end for tenant `h-dcn` / region `Noord` over the
  same in-memory DynamoDB fake + repository the unit tests use (no live AWS / Google /
  external h-dcn app), and records a PASS/FAIL/MANUAL outcome per behaviour across the four
  R7.1 dimensions. Report shape: per-dimension checks, a summary of `pass`/`fail`/`manual`
  counts, and a `routes_covered` set the tests assert equals the full declared route map.
  - Authorization incl. **regional access**: **PASS.** 401 unauthenticated, 403 unentitled,
    region-scoped caller (`Regio_Noord`) sees/acts only within its region (Property 4),
    admin/`Regio_All` tenant-wide, out-of-scope read → indistinguishable 404, out-of-scope
    write → 403, and verify-before-trust (a body `tenant_id` can never redirect a write).
  - Data correctness (backfill fidelity, tenant-scoping): **PASS.** Fixed base ⊕ h-dcn
    overlay resolves; `scope_values.region` present + canonicalized (`noord`→`Noord`); the
    Lidmaatschap Beheer dropdown lists only ACTIVE types while the management list still
    shows soft-deleted ones; a backfilled member (via the 4.1 `map_hdcn_row` transform on a
    fixture row) round-trips create → read with its historical member number preserved.
  - API contract (frontend sees no difference): **PASS.** All **24/24** declared routes
    answer as designed (never a 404 no-route, never a 501 stub). The route map is the
    **union** of h-dcn's ~18 handler behaviours (member CRUD 8, membership lifecycle 7,
    delegates 2, member payments 1) **plus** the new Lidmaatschap Beheer catalog group (5:
    2 reads + 3 writes) — 19 + 5 = 24. The harness asserts every declared route name is
    exercised (`routes_covered == route_names()`), so a missing route would be a parity gap.
  - Membership workflow (application → transitions → delegates): **PASS.** h-dcn's lifecycle
    (application → pending → active ⇄ suspended → lapsed → left) runs through the engine with
    the declarative guards enforced — an unapproved `application→pending` is denied (409, no
    mutation), activation requires member-number + contact, and an undeclared edge
    (`application→active`) is denied.
  - **Look & feel / UX parity: MANUAL — pending a human walkthrough.** The harness flags
    this as the one MANUAL item (frontend rendering, delegate-invitation email delivery,
    export file formatting): the module serves the contract, but presentation-only frontend
    parity can only be confirmed by a hands-on review. This is the primary condition on the
    Conditional-Go.

- **Did the myAdmin toolkit hold?** (what was reusable as-is vs. needed change — R8.1)
  - Verified-auth toolkit (`sam/shared` `get_verified_claims`/`get_groups`): **held.**
    Adopted **once** at the handler edge (task 3.0): parse → authenticate (verified claims,
    no header/body trust) → tenant context → authorize → route. No change needed.
  - Entitlement (`get_entitlements`/`has_capability`, `tenant_modules`, projection): **held.**
    The three-state `has_capability` + the S3 projection answered `members` for the pilot
    tenant (task 2.x verified the projection carries the module + roles and
    `has_capability("members", ...)` resolves). Fail-safe (empty projection → empty
    entitlement) is a valid handled outcome.
  - Tenant-scoping (`tenant_id` PK + `LeadingKeys`): **held.** Every read/write is keyed by
    `tenant_id` in the repository (Property 1 structural isolation), and per-tenant
    member-number uniqueness is enforced with DynamoDB conditional writes (Property 6, tested
    under concurrency).
  - The consolidation (18 handlers → one module): **held.** The single-module,
    internal-routing shape worked — `routes.py` is the auditable **union** of h-dcn's ~18
    behaviours (+ the catalog), routed by `(method, path)` with the auth/entitlement toolkit
    adopted once at the edge. No per-action Lambda sprawl was reproduced.

- **Operational**
  - Per-step deploy + rollback worked: **held (by design; not exercised against live
    traffic).** Every step is additive + reversible — the new `sam-members` table set is
    provisioned separately (task 4.0), the live h-dcn tables are untouched, backfill ran
    dry-run-first + non-destructive (task 4.1), and the pilot route is a **single reversible
    env-var flip** (`MEMBERS_PILOT_ROUTING`, task 6.1). Fail-safe held: empty projection →
    empty entitlement is handled, and the scope-deny default (`required_for` capability with
    no grant → `none`) holds.
  - Cold-start / latency within budget: **not measured — no live deploy.** h-dcn Members is
    demo-only (real data in a Google Sheet), so there was no production soak. Recorded as an
    observation to gather at/after the live pilot, **not a blocker**.
  - Cross-account Pool A trigger (if wired for the pilot) behaved; fail-safe held (no
    broken logins): **deferred to Step 7 (conditional) — not wired for this pilot.** The
    module runs auth against the **test pool**; the live Pool A PreTokenGen trigger is the
    highest-blast-radius change and is gated, test-pool-validated, detach-to-rollback (tasks
    7.0/7.1). It is a condition on the Conditional-Go **only if** the pilot needs live-token
    entitlement; otherwise the module's authoritative fallback stands.

- **Effort / ROI** — is app-by-app worth continuing? **Yes, conditionally.** Qualitative
  only — no hour counts were measured, so none are fabricated. The migration was executable
  in independently-deployable, reversible steps, and the reusable seams (edge
  auth+entitlement adopted once, the tenant-scoped repository, the config/rule/hook ladder)
  mean the next app is essentially "write its domain + repository, reuse the edge +
  tenancy." Recommend continuing app-by-app **after** the live UX walkthrough (and Step 7 if
  needed) clears the Conditional-Go.

## Rung distribution (R8.2) — the key finding

How much of h-dcn landed on each rung of the generic / tenant-specific ladder, from what
was actually built:

- **Rung 1 — config / data.** Tenant scope config (a single `region` dimension:
  values Noord/Zuid/Oost/West, `all_wildcard=Regio_All`, `required_for=Members_CRUD`), the
  lifecycle graph (`HDCN_LIFECYCLE_CONFIG`), the field overlay (**empty** for h-dcn beyond
  the club Motor detail), the Lidmaatschap Beheer catalog **seeded as data** (task 4.2), and
  the membership types. The bulk of h-dcn landed here.
- **Rung 2 — declarative rules.** Lifecycle transition guards (approval flag;
  member-number + contact required to activate; required-field-by-status) and scope-access
  resolution (`resolve_scope_access`: admin/all → `["*"]`, `Regio_*` → subset,
  `required_for` without a grant → deny). h-dcn's `determine_regional_access` generalized
  cleanly into this declarative resolver.
- **Rung 3 — registered hooks.** h-dcn registered **only 2 of 5** named hooks:
  - `derive_member_number` — the `L-000042` (`L-` + zero-padded) format (a genuine tenant
    nuance, kept pure: the counter value is threaded in, storage stays in the repository).
  - `validate_member` — an ACTIVE h-dcn member must carry a motorcycle in the overlay
    (`overlay.motor`/`motor_type`); the rule only bites at `status == active`.

  The other three stayed on their **safe defaults**: `on_transition` (no-op — the workflow
  is fully declarative), `resolve_visible_regions` (identity — regional visibility is fully
  declarative via `resolve_scope_access`), and `calculate_fee` (unused — h-dcn has no
  per-record fee). That regional access + the lifecycle stayed **below** Rung 3 is a
  **positive** result: the generic model absorbed h-dcn without leaking those to hooks.
- **Rung 4 — separate service / escape hatch.** **NONE needed.** Nothing about h-dcn
  required carving out a tenant-specific service.

**Summary:** the generic membership model held for h-dcn with **minimal Rung-3 usage (2/5
hooks)** and **zero Rung-4** — strong evidence the generic/tenant-specific ladder is the
right shape.

## Second-club design verdict (R8.2)

A **design-review** verdict (not built) on whether a hypothetical soccer/hockey club fits
the generic model, assessed against what's already built:

- **Teams (multi-valued scope):** fits at **Rung 1–2 as config.** The scope model is
  already a **list** of dimensions, each optionally `multi_valued` — the model was
  deliberately built multi-capable; h-dcn is just wired as the single simple case
  (one single-valued `region`). A `team` dimension with `multi_valued=True` (a member in two
  teams) needs no redesign; `resolve_scope_access` already unions multiple scoped grants.
- **Season (a second scope dimension):** fits at **Rung 1–2 as config.** Because
  `scope_dimensions` is a list, adding a second `season` dimension alongside `team` is
  configuration, not a code change.
- **Per-type fees:** fit at **Rung 3.** The `calculate_fee` named hook **already exists**
  (unused by h-dcn) — a second club plugs its fee-by-type logic into that point without
  touching the core.
- **Family / household membership:** the **one open gap.** This is a
  member-relationship / grouping concept that is **data-model, not just config** — a
  household is an entity linking members, which the current record shape does not model. It
  is flagged as an **open design decision** (promote a generic household entity vs. a Rung-3
  relationship hook) to decide **with evidence** when a real second club arrives.

**Verdict:** a soccer/hockey club **mostly fits** the generic model at Rung 1–3 (teams +
season as config; per-type fees via the existing hook). **Household is the design-now-or-later
flag** — the single concept that may need a data-model decision rather than configuration.

## Lessons learned (fill in)

- **What the platform tooling was missing / needed changing:**
  - The **household / member-relationship** concept for a future multi-member/family club —
    the only second-club dimension that isn't already config-or-hook. Decide the shape (generic
    household entity vs. relationship hook) when a real second club provides the evidence.
  - The conditional **Pool A live-token trigger** (Step 7) is built-but-unvalidated against
    live login — validate on the test pool first, detach-to-rollback.
  - The **live look & feel / UX walkthrough** — the one thing the automated harness cannot
    assert; it must be done by a human before the full Go.
- **What to do differently for Events / Webshop:** reuse the proven recipe — adopt the edge
  auth+entitlement once, key everything by `tenant_id`, express differences up the ladder
  (config → declarative rule → hook), and keep steps additive + reversible with a single
  reversible pilot-route flip. Expect the same low Rung-3 footprint; watch for any concept
  (like household) that is genuinely data-model and decide it up front.
- **Any principle to add to steering / a new ADR:** record the pattern in an ADR (task 8.0):
  the generic membership model, the multi-dimension scope generalization, the fixed/variable
  field model, the Lidmaatschap Beheer catalog coupling, and the **ladder discipline** (a
  difference is only a hook when it is neither config nor a declarative rule; prefer staying
  below Rung 3; Rung 4 is a last resort). The 2-of-5-hooks, zero-Rung-4 outcome is the
  reference point for "did the generic model hold."

## Outcome routing

- **Go →** proceed to the next app migration with the refined tooling; update the roadmap.
- **Conditional-Go → (this pilot's recommendation).** Proceed to Events / Webshop **after**:
  (1) the human **live look & feel / UX walkthrough** confirms frontend parity (the MANUAL
  item), and (2) **if** live-token entitlement is required, the **Step 7 Pool A** trigger is
  wired + test-pool-validated with detach-to-rollback. Open the **household / relationship**
  design decision to be resolved when a real second club arrives (does not block Events /
  Webshop, which have no household concept). Then update the roadmap.
- **No-Go →** not recommended on the evidence — record why + what would change the decision;
  revise the roadmap accordingly.
