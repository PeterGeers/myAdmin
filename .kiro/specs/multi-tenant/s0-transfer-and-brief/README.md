# Step 0 — Transfer to myAdmin + Decision Brief

- Status: In Progress
- Purpose: carry the multi-tenant analysis **and the decisions made so far** into
  myAdmin, so **Step 1 can be (re)done here in myAdmin, grounded in real code**.
  Step 0 is only the handoff. **The real next work is redoing S1.**

## Why this exists

Earlier analysis was done in a separate `mysaas` workspace under the assumption it
would be a new platform trunk. **That assumption was reversed** (see the pivot
below). Because that worldview is baked through the analysis docs and the earlier
S1, **S1 must be redone** to reflect myAdmin-as-base — and the analysis docs must be
rewritten to match. Doing this in myAdmin (not a separate workspace) is deliberate:
the model (`tenant_modules`, the two-account setup, real steering) must be read from
actual code, not guessed.

## THE PIVOT (decided — do not relitigate)

- **myAdmin IS the platform base / trunk.** We evolve myAdmin in place. There is no
  separate `mysaas` trunk.
- This **replaces** imported `docs/decisions/0001` (new target workspace) and
  `0002` (myAdmin = pattern source, not trunk). S1 records a new ADR (0003) —
  "myAdmin is the platform base; evolve in place; import h-dcn-like apps as platform
  **modules**" — and retires 0001/0002 (their reasoning stays in git history).
- myAdmin's **existing** `.kiro/steering` is the authoritative base governance. New
  concepts are **folded in**, never overwritten by mysaas-era steering.

## THE WORK: REDO S1 (this is the focus)

The earlier S1 ("establish a new mysaas trunk") is void. **Redo S1 as Phase 1:
prepare the current myAdmin environment to receive h-dcn-like apps as multi-tenant
applications.** Generic platform capability only. S1 has two parts:

### Part A — Rewrite the analysis to the new model (do FIRST, in myAdmin)

Every imported analysis doc still speaks the old "mysaas separate trunk" language.
**Rewrite each doc clean** to the settled model — **myAdmin-as-base +
SAM-apps-as-modules** — as if that had always been the plan. Do NOT keep the old
separate-trunk text with supersession markers; remove it. The old worldview is
decided against and does not need to persist in the live docs. (The prior versions
remain recoverable in git history, so rewriting is not lossy — the decision trail
lives in the commit log, not the documents.) Per doc:

- [ ] `overall_roadmap.md` — rewrite: myAdmin is the base; remove the mysaas-trunk
      S1/S1b/S6b "lift into mysaas" framing entirely; steps are changes *to myAdmin*.
- [ ] `second_thoughts.md` — rewrite/remove the workspace-strategy / "new target
      workspace" content; keep only what still holds under the pivot.
- [ ] `myadmin_as_base.md` — largely aligns already; confirm and promote.
- [ ] `migration_plan.md` — rewrite as "into myAdmin," not into a new trunk.
- [ ] `tenant_field_config.md`, `rewrite_vs_refactor.md`, `first_thoughts.md`,
      `frontend_merge.md`, `frontend_ui_standards.md`, `environments_and_testing.md`
      — rewrite each: strip trunk/mysaas-layout references; state the module framing
      directly.
- [ ] Replace ADR 0001/0002 with ADR 0003 (pivot: myAdmin is the base). Delete or
      retire 0001/0002 rather than keeping them as active decisions.

### Part B — Define S1 readiness (author after Part A), five capabilities

1. **Generic Cognito pool** — shared identity plane ready to serve incoming apps.
2. **SAM apps as MODULES (not tenants)** — extend myAdmin's `tenant_modules` so a
   module can be backed by an AWS SAM (Lambda + DynamoDB) app; define the generic
   plug-in contract (register, entitle via `tenant_modules`, authorize from verified
   token, scope by `tenant_id`).
3. **Two-AWS-account share** — identity account (Cognito) + nonprofit infra/data
   account; topology, roles/profiles. Phase 1 = readiness/design.
4. **Refactoring pattern** for h-dcn-like apps to fit myAdmin as SAM applications
   (generic contract only).
5. (Part A's analysis review feeds this.)

## OUT OF SCOPE FOR S1

- **Any h-dcn-specific work** (members, webshop, events, its data). S1 makes myAdmin
  *ready to receive* generic SAM-backed modules.
- Deploying an actual SAM app.
- **S2 (JWT verification) is NOT this step.** The S2 spec was transferred for
  continuity only; it comes *after* a proper S1. Do not start S2 work here.

## WHAT TRANSFERRED (already in this branch)

- `.kiro/specs/multi-tenant/Analysis/` — 10 analysis docs (to be rewritten — Part A).
- `.kiro/specs/multi-tenant/s2-jwt-verification/` — later step; parked, not now.
- `docs/decisions/0001, 0002` — superseded by the pivot.

## HOW TO START (next session, in myAdmin)

Read: this brief → myAdmin's own `.kiro/steering` + `tenant_modules` code → the
imported Analysis. Then **do S1 Part A first** (reconcile the analysis docs), then
Part B (author `.kiro/specs/multi-tenant/s1-prepare-platform/` requirements/design/
tasks) — grounded in real code.

## Step 0 tasks

- [x] Copy Analysis, (parked) S2 spec, and ADRs into myAdmin.
- [x] Write this brief (pivot + redo-S1 focus + analysis-reconcile-first).
- [ ] Commit on a branch; review.
- [ ] (Next session, in myAdmin) redo S1 — Part A rewrite analysis, then Part B.
