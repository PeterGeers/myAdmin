# Implementation Plan

## S5f — SAM Members edge: active-tenant resolution — Tasks

- Requirements: `./requirements.md` (R1–R8) · Design: `./design.md` (D1–D6, P1–P7, OD1–OD2).
- **Purpose:** #1 of 3 s5d-remediation specs and the ONLY blocker of s5d PHASE D. Replace the
  edge's `len(tenant_keys) == 1` gate with per-request active-tenant selection: `X-Tenant`
  validated against the verified `entitlement.tenant_keys` (header SELECTS, never grants).
  Mirrors the proven Flask `tenant_context.py` pattern.
- **Scope discipline (R8.1):** touch ONLY the tenant-selection seam in
  `sam/members/handler/app.py` (+ tests, ADR, steering pointer). NO change to the router,
  repository, domain, `has_capability`, `_resolve_scope_access`, or the frontend (it already
  sends `X-Tenant`).
- Legend: `[ ]` todo · `[H]` human-run/gated (prod deploy / prod re-test) · `(dt)` test-first
  · each task cites the Requirement(s) + design decision it implements.
- **Execution rules (steering):** `34-backend-testing` (SAM plane runs via `sam/pytest.ini`;
  test naming `test_{fn}_{scenario}_{expected}`; extend `sam/tests/`), `35-sam-module-
  architecture-sam` (thin edge; deploy via committed `samconfig.toml` + `deploy-sam-members.yml`),
  `41-shell-environment` (WSL paths; `<<<DONE marker=$?>>>`; account strip for any prod AWS).
- **Verify-before-trust (non-negotiable):** the header may only SELECT among verified tenants;
  never operate under a tenant absent from `entitlement.tenant_keys` (P1/P2/D6).

## Overview

A tight, test-first edit to `_establish_tenant_context`: add a `requested_tenant` parameter,
validate it against `tenant_keys`, keep the single-tenant degenerate case, and deny the
ambiguous absent-header-multi case explicitly (no default-to-first, no fallback). Extract the
`X-Tenant` header case-insensitively at the call site. Extend the auth-edge tests to pin the
multi-tenant contract, record the contract as ADR 0007, and ship through the s5e codified
`sam/members` pipeline. Re-test s5d Phase D end-to-end.

## Phase 0 — OD1 (RESOLVED, no code)

- [x] **0.1 OD1 resolved (user, 2026-09-23): 403 for ALL deny paths.** Explicit deny, no
  default-to-first, no 400/`TenantSelectionRequired` class — via the existing
  `TenantResolutionError` → 403. Rationale (user): the active tenant BOUNDS capability, so a
  tenant granting no members access is a deny, uniform with every tenant-context failure. The
  UI already prevents offering Members for a no-members tenant (`useTenantModules().hasMEMBERS`
  in `MainMenu.tsx`); the edge is the backstop. Recorded in `design.md` D5/OD1. _(R3.1; D5)_

## Phase 1 — The fix (test-first)

- [x] **1.1 (dt) Add the multi-tenant test scaffolding** DONE 2026-09-23 — added
  `_multi_entitlement` helper + the multi-tenant matrix to `test_members_auth_edge.py`;
  confirmed **4 RED** against the current `len==1` gate (incl. the core "multi selects h-dcn →
  403" bug). ALSO had to UPDATE two pre-existing tests that encoded the OLD pilot contract
  (would have masked the change): `test_tenant_comes_from_verified_entitlement_not_header`
  (→ split into select-unentitled-denied + single-tenant-absent-header) here, and
  `test_only_the_verified_tenant_partition_is_queried` in `test_members_smoke_routes.py`
  (→ split into unentitled-header-denied-and-never-queried + verified-single-tenant-queried).
  _(R6.1; D1)_
- [x] **1.2 Add `_requested_tenant_from_request` helper** DONE — `app.py`: case-insensitive
  `x-tenant` name lookup (mirrors `_bearer_token_from_event`), list/str tolerant, returns the
  stripped value or `None` (empty/whitespace → `None`); VALUE verbatim. _(R1.3; D2)_
- [x] **1.3 Refactor `_establish_tenant_context(entitlement, requested_tenant)`** DONE — 5-step
  resolution: fallback/overflow deny (R4.1); empty-`tenant_keys` deny (R4.2); `requested_tenant`
  → return IFF in `tenant_keys` else deny (R1.1/R1.2); no header + `len==1` → that tenant
  (R2.1); no header + multiple → deny (R3.1, OD1=403). PURE (no header parsing inside); NO
  hardcoded/env/default tenant (R5). _(R1–R5; D1/D4)_
- [x] **1.4 Wire the call site** DONE — `_authenticate_and_authorize`:
  `requested_tenant = _requested_tenant_from_request(request)` then
  `_establish_tenant_context(entitlement, requested_tenant)`; downstream unchanged, so the
  selected tenant scopes the whole request. _(R1.4; D3)_
- [x] **1.5 (OD1 = 403 — no new class) — SKIPPED (optional).** All deny paths are a uniform 403
  via the existing `TenantResolutionError` (no `TenantSelectionRequired`, no `handler()`
  change). The optional `code: tenant_selection_required` body marker was NOT added — kept the
  fix minimal; can be added later if the SPA wants to distinguish "pick a tenant" from a hard
  deny. _(R3.2; D5)_
- [x] **1.6 Update the tenant-seam docstrings** DONE — `_authenticate_and_authorize` step-2
  docstring + the `TenantResolutionError` class docstring + the module docstring bullet now say
  `X-Tenant` "selects among verified tenants, never grants". No behaviour change. _(D6)_

## Phase 2 — Tests green + guards intact

- [x] **2.1 (dt) Complete the multi-tenant test matrix** DONE (R6.1): (a) `X-Tenant` selects an
  allowed tenant among many → 200; (b) `X-Tenant` NOT in `tenant_keys` → 403; (c) absent header
  + multiple → 403 (OD1); (d) absent header + single → 200 (R2.1); (e) header name `x-tenant`
  (lowercase) → 200. All in `test_members_auth_edge.py`. _(R6.1; D1/D2)_
- [x] **2.2 Assert the request runs under the SELECTED tenant** DONE (R6.2) —
  `test_multi_tenant_selection_flows_the_selected_tenant_into_context` captures the
  `RequestContext` via a `_dispatch` monkeypatch and asserts `ctx.tenant_id == "mytest3"` (the
  selection, not the first tenant); the smoke test asserts the repo is queried only for the
  verified/selected tenant. _(R6.2; P7)_
- [x] **2.3 Confirm the grep-clean + fail-safe guards still pass** DONE (R4.3/R5.2) —
  `test_tenant_fallback_symbols_removed_from_live_code`, the `MEMBERS_LOCAL_TENANT_ID`
  live-reference guard, and the fail-safe 403 tests all GREEN unchanged (no fallback symbol
  introduced). _(R4.3, R5.2)_
- [x] **2.4 Run the SAM suite** DONE — `test_members_auth_edge.py` 30/30 green; the broad
  auth/members/entitlement/parity slice green; the **FULL** `sam/tests` suite green (EXIT=0,
  ~600 tests). Judged by the summary, not the terminal exit code. _(R6.3)_

## Phase 3 — ADR + steering

- [x] **3.1 Write ADR `docs/decisions/0007-active-tenant-resolution-sam-edge.md`** DONE
  2026-09-23 — house ADR format (Status Accepted / Relates-to 0004+0006 / Context / Decision /
  Rationale / Consequences / Related): the `len==1` pilot bug; the decision (active tenant =
  per-request `X-Tenant` validated ∈ verified `tenant_keys`; selects-never-grants; validate
  against `tenant_keys` not `custom:tenants`; case-insensitive name; all denies 403; no
  fallback; single-tenant degenerate); the verify-before-trust rationale; consequences (next
  SAM modules inherit it; deployed via codified pipeline; unblocks s5d Phase D). _(R7.1; D6)_
- [x] **3.2 Reference the ADR from `35-sam-module-architecture-sam.md`** DONE — added an
  "Active-tenant resolution at the edge (the module contract)" bullet in the References section
  summarising the rule + pointing at ADR 0007 and spec s5f, so Events/Webshop resolve tenant
  identically. _(R7.2)_

## Phase 4 — Ship (codified pipeline) + verify s5d Phase D

- [x] **4.1 Commit to a branch + PR to `main`** DONE 2026-09-23 — branch
  `s5f-sam-edge-active-tenant` off `origin/main`, commit `b719e6c` (9 files: app.py + 2 test
  files + ADR 0007 + steering 35 + spec + backlog), pushed (secret scan clean), **PR #18**
  opened → main. On merge, `deploy-sam-members.yml` deploys `sam-members` via OIDC (the
  s5e-codified pipeline) — no hand-typed deploy. _(R8.2)_
- [x] **4.2 [H] Merge → confirm the deploy** DONE 2026-09-23 — PR #18 merged (merge commit
  `75126c1`) → `Deploy SAM Members` run 35931888652 **success** (OIDC, s5e pipeline). Stack
  `sam-members` `UPDATE_COMPLETE` @ 23:07 (a real function/layer update, as expected). Live
  API smoke: `GET /prod/members` with no token → **401 Unauthorized** (authorizer intact,
  edge healthy post-deploy). _(R8.2)_
- [x] **4.3 [H] Re-test s5d PHASE D end-to-end** (R8.3): DONE 2026-09-24 — VERIFIED in the
  browser SPA: a multi-tenant user with `X-Tenant: h-dcn` gets `GET /prod/members` → **200 with
  many h-dcn records shown** (the originally-blocked outcome), confirmed by the user. Also
  verified from here beforehand: full SAM suite green (multi-tenant 200/403 matrix +
  "selection flows into context" ctx.tenant_id==selection); deploy green; live API 401 on
  unauth (healthy). NOTE — the s5f edge fix was necessary but NOT sufficient; real browser
  traffic then surfaced three MORE independent PHASE-D blockers, each fixed via the codified
  pipeline: **s5g** (CORS preflight — `OPTIONS /prod/members` was 401 because the authorizer
  gated preflight; PR #19), **s5h** (Members Lambda had NO DynamoDB IAM policy →
  AccessDeniedException on `governance_projection`; PR #20), **s5i** (`Decimal not JSON
  serializable` in `_response`; PR #21). Post-s5i CloudWatch (verified 2026-09-24 09:38+):
  ZERO Decimal/AccessDenied errors; only the backlogged `field-config` `region`-overlay
  OverlayError remains (Bug 2 — separate call, non-blocking for the member LIST). _(R8.3; P3/P7)_
- [x] **4.4 Unblock + record** DONE 2026-09-23 — s5d rollout plan updated: CE.7 marked
  "EDGE FIX SHIPPED (s5f)" with the resolution note (PR #18 / run 35931888652 / UPDATE_COMPLETE);
  the PHASE D banner flipped from "[BLOCKED until PHASE CE done]" to "[UNBLOCKED 2026-09-23 — s5f
  shipped]", linking this spec + ADR 0007. _(bookkeeping)_

## Done criteria

- Multi-tenant users select their active tenant via `X-Tenant` (validated ∈ `tenant_keys`) and
  reach the Members API; out-of-set selection → 403; ambiguous no-header → explicit deny
  (P1–P4).
- Single-tenant + fail-safe behaviour unchanged; grep-clean/no-fallback guards green (P3/P5/P6).
- The selected tenant scopes the whole request (P7).
- Contract recorded as ADR 0007 and referenced from steering.
- Shipped via the s5e codified `sam/members` pipeline; s5d PHASE D verified end-to-end and
  unblocked.
