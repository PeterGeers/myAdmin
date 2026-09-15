# Step 0 — Transfer to myAdmin + Decision Brief

- Status: In Progress
- Purpose: carry the multi-tenant analysis **and the decisions made so far** into
  myAdmin, so Step 1 can be authored **here in myAdmin, grounded in real code** —
  not reconstructed from memory in a separate workspace. This spec is the handoff.

## Why this exists

Earlier analysis was done in a separate `mysaas` workspace under the assumption it
would be a new platform trunk. **That assumption was reversed.** Working outside
myAdmin meant the model (e.g. `tenant_modules`) kept being guessed at. Step 0 moves
the artifacts + the settled intent into myAdmin and hands off; Step 1 is authored
here against the actual codebase.

## THE PIVOT (decided — do not relitigate)

- **myAdmin IS the platform base / trunk.** We evolve myAdmin in place. There is no
  separate `mysaas` trunk to build.
- This **supersedes** the imported `docs/decisions/0001` (new target workspace) and
  `0002` (myAdmin = pattern source, not trunk). Those ADRs are kept as history but
  are **superseded** — Step 1 should record a new ADR (0003) stating "myAdmin is the
  platform base; evolve in place; import h-dcn-like apps as platform modules."
- myAdmin's **existing** `.kiro/steering` is the real, authoritative governance of
  the live system. It is the **base**. New multi-tenant/identity concepts are
  **folded in**, not overwritten by the mysaas-era steering.

## WHAT STEP 1 IS (scope — decided)

**Step 1 = Phase 1: prepare the current myAdmin environment to receive h-dcn-like
apps as multi-tenant applications.** Generic platform capability only. Five items:

1. **Generic Cognito pool** — the shared identity plane, ready to serve incoming
   apps (the generic pool capability; not any app's specific users).
2. **SAM apps come in as MODULES of the platform (NOT as tenants).** Extend
   myAdmin's existing `tenant_modules` so a module can be **backed by an AWS SAM
   (Lambda + DynamoDB) application**, alongside existing in-Flask modules. Define the
   generic plug-in contract: how a SAM-backed module registers, is entitled via
   `tenant_modules`, authorizes from the verified token, and scopes data by
   `tenant_id`.
3. **The two-AWS-account share** — identity account (Cognito) + nonprofit infra/data
   account (DynamoDB/S3/SES/etc.): topology, roles/profiles, how they're shared
   across the platform. Phase 1 = readiness/design, not deploying a real SAM app.
4. **Refactoring pattern** for h-dcn-like apps to fit myAdmin as SAM applications —
   the generic contract an incoming portal-style app must satisfy. Generic only.
5. **Review the imported analysis files** — confirm what still holds vs what the
   pivot superseded; mark superseded framing.

## EXPLICITLY OUT OF SCOPE FOR STEP 1

- **Any h-dcn-specific work** — members, webshop, events, its data/domain logic.
  Step 1 is about making myAdmin *ready to receive* generic SAM-backed modules, not
  importing h-dcn.
- Deploying an actual SAM app (that's a later phase).

## WHAT TRANSFERRED (already copied in this branch)

- `.kiro/specs/multi-tenant/Analysis/` — 10 analysis docs (the reasoning).
- `.kiro/specs/multi-tenant/s2-jwt-verification/` — the S2 spec (next after S1).
- `docs/decisions/0001, 0002` — ADRs (now superseded by the pivot; see above).

## OPEN / TO DECIDE IN STEP 1 (grounded in real myAdmin code)

- Exactly how `tenant_modules` is extended for SAM-backed modules (read the real
  schema + code first).
- Governance reconciliation: keep myAdmin's steering as base; fold in the *new*
  concepts (two-pool `identity`, `environments-and-testing`, SAM-module contract) —
  file by file, not wholesale.
- Archive plan: where stale material goes (candidates: the killed `Commerce` spec,
  root `*_COMPLETE.md` status docs, mysaas-era trunk framing). Confirm against the
  real tree.
- Standing test Cognito pool (S2 prerequisite) — S2 code (`jwt_verifier.py`) already
  lives in myAdmin.

## HOW TO START STEP 1

Open a session **in the myAdmin workspace**. Read: this brief, the imported
Analysis, and myAdmin's own `.kiro/steering` + `tenant_modules` code. Then author
`.kiro/specs/multi-tenant/s1-prepare-platform/` (requirements / design / tasks) with
the scope above — grounded in the real code, not re-derived.

## Step 0 tasks

- [x] Copy Analysis, S2 spec, and ADRs into myAdmin.
- [x] Write this brief (pivot + Step 1 scope + out-of-scope).
- [ ] Commit on a branch; review.
- [ ] (Next session, in myAdmin) author the Step 1 spec grounded in real code.
