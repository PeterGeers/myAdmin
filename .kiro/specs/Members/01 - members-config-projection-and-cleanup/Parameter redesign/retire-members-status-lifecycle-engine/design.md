# Retire Members Status Lifecycle Engine — Bugfix Design

## Overview

Retire the membership status/lifecycle state engine on the SAM Members plane and turn
`membership.status` into a plain, tenant-driven OPEN enum authored like `gender`. After the
fix, a tenant-authored status value (e.g. `died`/"Overleden") survives save → projection →
resolved config → being set on a member with no code change, and status changes are ordinary
field edits (any value → any value) with no transition graph, guards, or transition modal.

The fix is a **deletion + reconciliation** change, not a feature add. The risky part is
scope: the engine has tendrils in the handler route map, the dispatch, the domain service, a
hook registry, the field resolver's projection, the frontend modals/API, the parity harness,
and a large body of docstrings/specs that assert a live lifecycle. This design is primarily a
**complete inventory (A–H)** with a safe deletion order and the parity-count delta, so the
retirement is total and the written record matches reality. **Scope guard:** only h-dcn is a
wired tenant; the SAM Members plane is the whole blast radius. The Flask/MySQL plane only
*authors + projects* the field (it has no transition engine).

**Exclusions from every "caller" list below:** the vendored `sam/members/.aws-sam/build/`
copies are excluded entirely (they are build artifacts regenerated from source); tests are
listed separately in section F, never as product callers.

## Glossary

- **Bug_Condition (C)** — a tenant authors/sets a `membership.status` value the closed
  `MembershipStatus` set rejects, OR a status change the transition graph/guards block.
- **Property (P)** — status is a plain OPEN enum (tenant values win) and status change is an
  ordinary field edit (any → any, no gatekeeping).
- **Preservation** — public-form create still defaults `status=application`; tenant
  isolation; member CRUD/read/export/analytics/mail; `gender` + other open enums; every
  non-status field.
- **The engine** — the membership lifecycle state machine: `LifecycleConfig` + the
  graph/guard evaluator (`lifecycle_config.py`), the pure transition computation
  (`_membership_lifecycle.py`), the `on_transition` hook seam (`transition_hooks.py`), the
  transition write methods, the two transition routes, and the SPA projection + modals.
- **Open enum** — a `FixedField` with `choices=None` whose value list is tenant config
  (`gender` today; `status` after this fix).
- **F / F'** — the system before / after the retirement.

## Bug Details

### Bug Condition

The bug manifests whenever a tenant tries to use its OWN `membership.status` value set, or to
change a member's status outside the declared transition graph. The closed `MembershipStatus`
vocabulary (wired onto the `status` field as `choices`) drops tenant-authored values at
projection and rejects them at validation; the transition engine gatekeeps every status
change behind a declared edge + guards.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input is a status authoring/set/change operation
  OUTPUT: boolean

  PLATFORM_STATUS := {application, pending, active, suspended, lapsed, left}  // the UNFIXED closed set

  RETURN authors_or_sets_or_changes_status(input)
         AND (
               status_value(input) NOT IN PLATFORM_STATUS       // tenant value the closed set rejects
               OR change_not_declared_or_guard_denied(input)    // the transition engine blocks it
             )
END FUNCTION
```

### Examples

- Tenant saves `status` option `died`/"Overleden" → stored in MySQL overlay, **dropped** at
  projection; resolved `status.choices` still the 6 platform values. (expected: carried
  through, like a `gender` value)
- `create_member`/`update_member` with `membership.status = "died"` → `FieldValidationError`
  "must be one of: application, pending, active, suspended, lapsed, left". (expected: accepted)
- Staff tries to move a member `active → application` → the engine denies it (edge not
  declared). (expected: an ordinary field edit succeeds)
- `application → pending` without `context.approved=True` → `TransitionDenied` 409.
  (expected: a plain status edit, no approval guard)
- A tenant `LifecycleConfig` that lists `died` → `LifecycleConfigError` at wiring time.
  (expected: no lifecycle config exists at all)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Public application-form create still stamps `membership.status = "application"` by default
  — now a plain default literal, not the engine's `initial_state`.
- Tenant isolation: every member read/write stays keyed by `tenant_id`.
- Member CRUD (create/get/list/search/update/delete), export, and the resolved field-config
  read all behave exactly as today (minus the `lifecycle` block they used to carry).
- `gender` and all other OPEN overlay enums save/project/resolve/validate unchanged.
- Analytics-sets, pivots, mail/send-runs, templates, schedules, catalog, delegates — all
  untouched (none depended on the engine).
- Every OTHER field-resolver platform invariant stays (no drop/rename fixed field, no
  required→optional downgrade, no type change, no key collision).

**Scope:**
All inputs that do NOT involve the status value set or a status change are completely
unaffected. The only observable removals are: the two transition routes, the SPA transition
modals/buttons, the `lifecycle` block on the field-config payload, and the closed-set
validation of `status`.

## Hypothesized Root Cause

The root cause is a deliberate design decision now being reversed, not a defect to patch:

1. **Closed status vocabulary.** `MembershipStatus` is an `Enum` wired onto the `status`
   `FixedField` as `choices=tuple(s.value for s in MembershipStatus)`, so validation and the
   resolved choices are a closed 6-value set a tenant overlay cannot extend.
2. **Resolver guard.** `field_resolver.py` explicitly forbids the overlay from touching the
   closed `membership.status` enum, so a tenant-authored value is dropped on resolve/project.
3. **Transition engine gatekeeping.** Status change is routed through the state machine
   (`transition_membership` / `bulk_transition_members` → `_membership_lifecycle.py` →
   `lifecycle_config.py` graph + guards), so a change must be a declared edge whose guards pass.
4. **The engine is unwanted complexity this phase**, and the one wanted feature (welcome mail
   on activation) is deferred to a simpler pivot-based approach.

---

## COMPLETE INVENTORY (A–H) — the retirement backbone

> This is the "eliminate all routes / thorough dependency analysis" deliverable. Every entry
> was confirmed by reading the live source (build copies excluded, tests listed separately).

### A. ROUTES to eliminate

Both transition routes in `sam/members/handler/routes.py` (group `RouteGroup.MEMBERSHIP`):

| Route name | Method | Path | Capability |
|---|---|---|---|
| `transition_membership` | POST | `/members/{member_id}/memberships/{membership_id}/transition` | `members:write` |
| `bulk_transition_memberships` | POST | `/memberships/transition` | `members:admin` |

Wiring that exists ONLY for these two routes:
- **`handler/routes.py`** — the two `RouteSpec` entries; the `routes.py` module docstring
  "Membership lifecycle … transition · bulk-transition (7)" count must drop to (5).
- **`handler/_dispatch.py`** — the two dispatch branches `if name == "transition_membership"`
  and `if name == "bulk_transition_memberships"`; the helpers `_parse_to_state(...)` and
  `_transition_context(...)` (used only by those branches); the `MembershipStatus` import
  there; and `_transition_context` in `__all__`.
- **`handler/app.py`** — `_LIFECYCLE_PROVIDER = StaticLifecycleConfigProvider({"h-dcn":
  HDCN_LIFECYCLE_CONFIG})`; the `from …lifecycle_config import HDCN_LIFECYCLE_CONFIG,
  StaticLifecycleConfigProvider`; the `lifecycle_provider=_LIFECYCLE_PROVIDER` kwarg in the
  `MembershipService(...)` construction; the `TransitionDenied` import and its `except
  TransitionDenied` 409 handler (`errors.transition.denied`); and the lifecycle commentary
  block around `_LIFECYCLE_PROVIDER`.

**Parity-count delta (A ↔ harness):** the Go/No-Go documents **24 routes** = 19 h-dcn
behaviours (member CRUD 8, membership lifecycle **7**, delegates 2, payments 1) + catalog 5.
Removing 2 transition routes makes it **membership lifecycle 5**, i.e. **17 + 5 = 22 routes**.
The parity harness (`members_parity_harness.py`) must drop the two transition entries from
`walk_api_contract`, and `walk_workflow` (dimension 4, the full lifecycle walk) must be
removed or rewritten to a plain "status is a field edit" check (see F). The documented count
everywhere becomes **22** (see G).

### B. ENGINE / DOMAIN modules

| Module | Disposition | Imported by (deletion-order driver) |
|---|---|---|
| `domain/lifecycle_config.py` (LifecycleConfig, providers, `HDCN_LIFECYCLE_CONFIG`, `evaluate_guards`, `evaluate_required_fields`, `RuleOperator`, `GuardRule`, `TransitionRule`, `RequiredFieldRule`, `LifecycleConfigError`) | **DELETE** | `handler/app.py`, `domain/_membership_lifecycle.py`, `domain/_membership_writes.py` (initial-state read + `_serialize_lifecycle`), tests `test_lifecycle_config.py`, `test_analytics_set_routes.py` (fixture import), `test_membership_lifecycle.py` |
| `domain/_membership_lifecycle.py` (`LifecycleMixin`: `transition_membership`, `_current_state`, `_with_status`, `get_lifecycle_config`) | **DELETE** | mixed into `MembershipService`; see membership_service wiring |
| `domain/transition_hooks.py` (`OnTransitionHook`, `TransitionHookRegistry`, `NOOP_TRANSITION_HOOK`, `noop_on_transition`) | **DELETE** | `domain/tenant_hooks.py` (transition view), tests `test_membership_lifecycle.py` / `test_tenant_hooks.py` |
| `domain/tenant_hooks.py` (`TenantHookRegistry`, `HookName`, defaults) | **CARVE — keep, remove only `on_transition`** | It ALSO wires non-lifecycle hooks (`validate_member` — h-dcn Motor check — plus `resolve_visible_regions`, `calculate_fee`). Keep the registry; remove `HookName.ON_TRANSITION`, `default_on_transition`, the `transition_hooks` import, and `transition_registry()`. `validate_member` must keep working. |
| `MembershipService.transition_member` / `bulk_transition_members` (in `domain/_membership_writes.py`) | **DELETE** | `handler/_dispatch.py` (the two branches) |
| `MembershipService.__init__` `lifecycle_provider` / `_transition_hooks` wiring + `LifecycleMixin` base | **CARVE** | `handler/app.py`, all service constructions in tests |
| `domain/_membership_errors.py` `TransitionDenied`, `TransitionResult` | **DELETE** | `handler/app.py` (except handler), `_membership_lifecycle.py`, `_membership_writes.py` |
| `domain/_membership_writes.py` initial-state block (`config = self._lifecycle_provider.get_lifecycle_config(...)` → `membership["status"] = config.initial_state.value`) | **REPLACE** with a plain default literal `"application"` (preserve 3.1) | self |
| `domain/_membership_writes.py` `_serialize_lifecycle(...)` + the `"lifecycle": self._serialize_lifecycle(tenant_id)` key in the field-config read | **DELETE** | the SPA (`fieldConfig.lifecycle`) |

**`error_codes` / i18n:** the `errors.transition.denied` code and any transition-only error
string become dead — remove them with the except handler.

### C. `MembershipStatus` enum disposition — DECISION + justification

**Decision: DOWNGRADE, do not keep as the field's closed `choices`.** Concretely:

1. Make the `status` `FixedField` an **OPEN enum**: `choices=None` (exactly like `gender`), so
   tenant-authored values win end-to-end and `validate_fixed_fields`/`_validate_value` take
   the existing open-enum path ("non-blank string; resolved tenant choices enforce
   membership downstream"). **Remove** `choices=tuple(s.value for s in MembershipStatus)`.
2. Keep a **minimal default-seed list** of sensible starting status options on the field's
   `options` (so a brand-new tenant has reasonable defaults to relabel and so `application`
   is the obvious initial value), authored as plain `EnumOption`s — NOT derived from a code
   `Enum`. This is seed DATA, not a validation gate.
3. **Delete the `MembershipStatus` `Enum` class itself** once its last importer is gone. Its
   only consumers today are the engine modules (being deleted) plus two non-engine sites that
   each need only the literal string `"active"`/`"application"`:
   - `tenants/hdcn/hooks.py` `validate_member` compares `_current_status(record) ==
     MembershipStatus.ACTIVE.value` → change to the literal `"active"`.
   - the write-path initial-state stamp → the literal `"application"` (see B / 3.1).

   Import sites to update (non-test, non-build): `fixed_fields.py` (defines it + the `status`
   field + `__all__` + docstrings), `lifecycle_config.py` (deleted), `transition_hooks.py`
   (deleted), `tenant_hooks.py` (carve), `_membership_lifecycle.py` (deleted),
   `_membership_errors.py` (`TransitionDenied`/`TransitionResult` deleted), `handler/app.py`
   (`# noqa: F401 surface compat` re-export — drop), `handler/_dispatch.py` (deleted
   helpers), `tenants/hdcn/hooks.py` (→ literal). `hdcn_backfill.py` imports
   `validate_fixed_fields`, NOT the enum — unaffected.

**Justification:** keeping `MembershipStatus` as the field's `choices` is the exact gate that
drops tenant values. Keeping it as a dead code constant is the "disabled-but-present" bait the
decision forbids. A minimal `options` seed gives a fresh tenant good defaults without gating,
matching the `gender` precedent (open enum, tenant supplies the real list).

### D. FRONTEND artifacts to remove

| Artifact | Action |
|---|---|
| `frontend/src/components/members/MembersTransitionModal.tsx` | DELETE |
| `frontend/src/components/members/MembersBulkTransitionModal.tsx` | DELETE |
| `frontend/src/components/members/transitionTargets.ts` | DELETE |
| `services/members/membersResourceApi.ts` `transitionMembership(...)` + `bulkTransition(...)` | DELETE |
| `services/membersApiService.ts` re-exports of `transitionMembership`, `bulkTransition` | DELETE |
| `types/members.ts` `LifecycleConfigShape` interface + `FieldConfig.lifecycle?` field + the `membership_id`/`status` lifecycle doc comments | REMOVE lifecycle parts (keep `status?: string` — it is now a plain field; keep `membership_id?`) |
| `pages/MembersPage.tsx` | REMOVE the two modal imports, the `<MembersTransitionModal>` + `<MembersBulkTransitionModal>` mounts, the "Change status" view-modal footer action, the "Bulk: change status" header affordance, and the `isTransitionOpen`/`isBulkOpen` state + handlers (`handleTransitionClose`, `onBulkClose`, open handlers) |

**How status is edited AFTER:** via the existing member **edit modal** — `status` renders as
an ordinary enum field from the resolved `fieldConfig` (its `choices`/`options`), the same
control `gender` uses. This path already exists (the edit modal renders resolved fields), so
no new UI is needed. Confirm during execution that the edit modal lists `status` among the
editable membership fields (it is a non-system membership field, so it should).

### E. EXTERNAL-CONSUMER / contract check (RISK GATE)

Grep of the whole repo (build copies excluded) for `/transition` + `memberships/transition`:
- **Runtime caller: ONLY the SPA** (`membersResourceApi.ts` → `membersApiService.ts`).
- All other hits are **the module's own tests**, the **parity harness**, and
  **spec/walkthrough markdown** (`s5-members-first-migration/*`, `application-app/*`).
- **No** other service, Lambda, script, Postman collection, backfill, or worker calls them.

**Finding:** in-repo, retiring the routes is NOT a cross-service breaking change.
**FLAGGED for explicit sign-off:** any OUT-OF-REPO client that posts to these routes would
break; none was found in-repo, but the user must confirm no external integration exists
before execution.

### F. TESTS — DELETE vs UPDATE (change-with-tests)

| Test file | Behavior it encodes | Classification |
|---|---|---|
| `sam/tests/test_lifecycle_config.py` | the whole engine config model + evaluator | **DELETE** |
| `sam/tests/test_membership_lifecycle.py` | `transition_membership` decision + hook dispatch | **DELETE** |
| `sam/tests/test_tenant_hooks.py` | the unified hook registry incl. `on_transition` | **UPDATE** — remove the `on_transition`/`transition_registry` cases; KEEP `validate_member` / `resolve_visible_regions` / `calculate_fee` cases |
| `sam/tests/test_fixed_fields.py` | `test_status_field_is_the_closed_membership_enum` asserts `set(status.choices) == {MembershipStatus}` | **UPDATE** — assert `status.choices is None` (open enum, like `gender`); update the value-generator helper's closed-enum branch for `status` |
| `sam/tests/test_empty_is_valid_props.py` | status choices snapshot in the property generators | **UPDATE** — status now open (any non-blank string) |
| `sam/tests/test_attribute_catalog.py` | status option tokens in the catalog | **UPDATE** — reflect the seed `options`, not the closed set |
| `sam/tests/test_field_config_endpoint.py` | `lifecycle` block present in the field-config payload | **UPDATE** — assert NO `lifecycle` key |
| `sam/tests/members_parity_harness.py` + `sam/tests/test_members_parity_harness.py` | route coverage incl. the 2 transition routes; dimension-4 full-lifecycle walk | **UPDATE** — drop the transition routes from `walk_api_contract` + the `test_api_contract_*` assertions; remove/rewrite `walk_workflow` + `test_workflow_dimension_walks_full_lifecycle`; the `routes_covered == route_names()` assertion then covers 22 |
| `sam/tests/test_members_routes.py` | route map shape/count | **UPDATE** — reflect 22 routes, no transition specs |
| `sam/tests/test_analytics_set_routes.py` | imports `HDCN_LIFECYCLE_CONFIG`/`StaticLifecycleConfigProvider` only to construct the service | **UPDATE** — drop the lifecycle_provider kwarg/imports once the service no longer takes them |
| `frontend/src/__tests__/MembersTransitions.test.tsx` | the single + bulk transition modals + target derivation | **DELETE** |
| `frontend/src/services/membersApiService.test.ts` | `transitionMembership`/`bulkTransition` URL tests | **UPDATE** — remove those two cases |
| `frontend/src/services/membersApiService.apiError.test.ts` | uses `transitionMembership` to exercise ApiError | **UPDATE** — re-point to a surviving write fn (e.g. `createMember`/`updateMember`) |

**Change-with-tests contract:** every paired test is updated/removed in the SAME change; never
weaken an assertion to go green — assert the intended retired/opened behavior (status open,
no `lifecycle`, 22 routes, status change via edit).

### G. DOCSTRINGS + SPECS to reconcile (stop asserting a live lifecycle)

**Docstrings (product source):**
- `fixed_fields.py` — module docstring ("status uses the platform-canonical **closed**
  `MembershipStatus` set"); the `MembershipStatus` class docstring; the `status` field inline
  comment ("The platform keeps the closed MembershipStatus set"); `validate_fixed_fields`
  docstring ("status one of the closed `MembershipStatus` enum"). → rewrite: **status is an
  OPEN enum; tenant supplies values via overlay; validated against resolved choices.**
- `field_resolver.py` — "it cannot … touch the closed `membership.status` enum." → rewrite:
  **status is open and tenant-authored, exactly like `gender`;** drop the status exception.
- `lifecycle_config.py` / `transition_hooks.py` — deleted (no reconciliation needed).
- `tenant_hooks.py` — remove the `on_transition` bullet + the task-5.0 interop paragraph;
  keep the `validate_member` / `resolve_visible_regions` / `calculate_fee` description.
- `tenants/hdcn/hooks.py` — the `on_transition` "LEFT ON THE SAFE DEFAULT" bullet referencing
  `HDCN_LIFECYCLE_CONFIG` → remove; keep the `validate_member` description (change the enum
  compare to the literal `"active"`).
- `_membership_writes.py` — the initial-state / `_validate_member_record` / `_serialize_lifecycle`
  docstrings → rewrite to "status defaults to `application` as a plain literal on create; no
  lifecycle projection."
- `backend/src/services/members_config_validation.py` — the closed-6 `status` comment near the
  `membership.status` required-key lists → rewrite: **status values are tenant-authored (open
  enum); the validator only checks the field is present/well-formed, not a closed set.**
- `scripts/onboarding/members/h-dcn/ONBOARDING.md` — the `status` row in the bucket-1 table
  ("the **closed** platform set, tenant relabels only … the state *values* are fixed
  (`MembershipStatus`)"); the enforcement table row ("`gender`/`status` enum membership …");
  the `membership.status` overlay JSON comment ("relabel only — do NOT add values … Adding a
  value the domain doesn't know will be rejected"). → rewrite: **status is an open enum;
  tenants may ADD/relabel values exactly like `gender`.** (D6 "default `active`" stays valid.)

**Specs to rewrite (these actively mislead):**
- `.kiro/specs/Members/application-app/requirements.md` — R8b.3 "existing membership status
  transition" + the applicant/closed-enum definition → **a plain status field edit; status is
  an open enum.**
- `.kiro/specs/Members/application-app/design-options.md` — any option predicated on the
  lifecycle engine / closed status → note superseded by this retirement.
- `.kiro/specs/Members/s5-members-first-migration/go-no-go.md` — the "lifecycle runs through
  the engine … **PASS**" narrative (verdict bullet, api-contract bullet, workflow bullet,
  rung-1/rung-2 lifecycle bullets) and the **24-route** count → rewrite to **22 routes; the
  lifecycle engine was retired (pointer to this spec); status is a tenant-driven open enum.**
- `.kiro/specs/Members/s5-members-first-migration/tasks.md` — task **5.0** "[x] Implement the
  lifecycle state machine + declarative rules" → mark **superseded/retired** with a pointer to
  `retire-members-status-lifecycle-engine`; likewise the task-5.2 "transition" mention.
- `s5b-members-runnable-in-spa` requirements/design/tasks/walkthrough — the single/bulk
  transition action items (points 5 & 6, tasks 20.3/20.4) → mark superseded (status edited as
  a plain field).

### H. What is LOST (record so nothing vanishes silently)

Behavior that exists TODAY and is intentionally dropped (captured so the deferred follow-up
has a precise spec of what it replaces):

- **h-dcn guards** (`HDCN_LIFECYCLE_CONFIG`): `application→pending` requires
  `context.approved == True`; `pending→active` requires `membership.member_number` present AND
  `personal.email` present; the state graph `application→pending→active ⇄ suspended, active ⇄
  lapsed, {pending,active,suspended,lapsed}→left`; required-field-by-status rules
  (`member_number` + `email` required when `active`). **After retirement none of these are
  enforced on a status change** — status becomes free movement. If h-dcn still needs the
  "member_number + email required when active" invariant, that is a plain validation rule to
  re-add deliberately (NOT via the engine) — flagged as an open question.
- **`on_transition` hooks**: the seam is unused in-repo today (h-dcn left it on the no-op
  default), but the *intended* use was a welcome mail on activation (`active`). This is the
  one wanted feature — deferred below.

### Deferred / follow-up (explicitly OUT OF SCOPE now)

1. **Pivot-based welcome mail** — re-build "welcome mail on activation" the simple way: a
   pivot over member keys (e.g. members whose `status` just became `active`) → a welcome mail,
   NOT via the engine. A separate spec.
2. **A future state engine "when mature"** — if the team later wants real lifecycle
   enforcement, design it fresh; it is not reinstated here.
3. **Deliberate `active`-requires-member_number+email validation** — if still wanted, add as a
   plain field-validation rule, decided explicitly.

## Correctness Properties

Property 1: Bug Condition — Status is a tenant-driven open enum; changes are plain edits

_For any_ input where the bug condition holds (a tenant authors/sets a status value outside
the old closed set, or changes status in a way the old graph/guards blocked), the fixed system
SHALL carry the tenant-authored value through save → projection → resolved config, SHALL accept
it on a member create/update (open-enum validation), and SHALL allow any value → any value
status change as an ordinary field edit — with no transition graph, guard, or modal.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation — Non-status behavior is unchanged

_For any_ input where the bug condition does NOT hold, the fixed system SHALL produce the same
result as the original system, preserving public-form create defaulting `status=application`,
tenant isolation, member CRUD/read/export/analytics/mail, `gender` + other open enums, every
non-status field, and every other field-resolver platform invariant.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required (safe deletion ORDER)

Delete leaves first so nothing dangles; carve shared modules; reconcile the record last.

1. **Frontend (leaf consumers) — D.** Delete the two modals + `transitionTargets.ts`; remove
   the API fns + re-exports; remove the `MembersPage` mounts/buttons/handlers; strip
   `LifecycleConfigShape` + `FieldConfig.lifecycle`. Delete/Update the frontend tests (F).
2. **Handler routes + dispatch — A.** Remove the two `RouteSpec`s and the two dispatch
   branches + `_parse_to_state`/`_transition_context`; fix `routes.py` docstring count (→5).
3. **Handler app wiring — A.** Remove `_LIFECYCLE_PROVIDER`, the lifecycle imports, the
   `lifecycle_provider=` kwarg, and the `TransitionDenied` import + except handler.
4. **Service transition methods — B.** Delete `transition_member` / `bulk_transition_members`;
   remove the `LifecycleMixin` from `MembershipService`; delete `_membership_lifecycle.py`;
   drop the `lifecycle_provider` / `_transition_hooks` constructor params; delete
   `_serialize_lifecycle` + the `"lifecycle"` field-config key; replace the initial-state block
   with the plain `"application"` default (preserve 3.1).
5. **Hook registry carve — B.** In `tenant_hooks.py` remove `HookName.ON_TRANSITION`,
   `default_on_transition`, the `transition_hooks` import, `transition_registry()`; delete
   `transition_hooks.py`. Keep `validate_member` et al. Update `tenants/hdcn/hooks.py`
   (literal `"active"`).
6. **Errors — B.** Delete `TransitionDenied` / `TransitionResult` and the
   `errors.transition.denied` code.
7. **Open the field — C.** In `fixed_fields.py`: set `status` `choices=None`, keep a minimal
   `options` seed, delete the `MembershipStatus` class + its `__all__` entry + imports.
8. **Config model — B.** Delete `lifecycle_config.py`.
9. **Flask validator — G.** `members_config_validation.py` status comment (no closed-set
   gating; already only checks presence of the required key).
10. **Tests — F.** Delete/Update every paired test (SAM + frontend + parity harness) to the
    intended behavior; run them.
11. **Docstrings + specs — G.** Reconcile every passage listed so the record stops asserting a
    live lifecycle.

## Testing Strategy

### Validation Approach

Two phases: first an exploration test that FAILS on the unfixed code (proving the bug — a
tenant status value is dropped/rejected and status change is gatekept); then preservation
tests observed on the unfixed code for the paths that must stay green.

### Exploratory Bug Condition Checking

**Goal:** surface counterexamples BEFORE the retirement, confirming the closed set + engine
gatekeep tenant status values.

**Test Plan:** author a tenant `membership.status` value (e.g. `died`/"Overleden") in the
overlay and drive it through resolve/project + a member create; attempt a status change the
graph does not declare. Run on the UNFIXED code.

**Test Cases:**
1. **Tenant status value survives projection** — author `died`, project, read resolved
   `status.choices` → expect `died` ABSENT (fails on unfixed).
2. **Member create with tenant status value** — `create_member` with `status="died"` → expect
   `FieldValidationError` "must be one of …" (fails on unfixed).
3. **Status change is a plain edit** — move `active → application` via an ordinary update →
   expect it to be impossible/denied by the engine on unfixed.

**Expected Counterexamples:** value dropped at projection; validation rejects the value;
status change denied because no edge declared.

### Fix Checking

**Goal:** after retirement, for all bug-condition inputs the fixed system opens the enum and
treats status change as a field edit.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  ASSERT tenant_status_value IN resolve_then_project(tenant).status.choices
  ASSERT create_member(status=tenant_value) succeeds
  ASSERT update_member(status: any -> any) succeeds   // no graph/guard
END FOR
```

### Preservation Checking

**Goal:** for all non-bug-condition inputs, F(input) = F'(input).

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT public_form_create().membership.status == "application"
  ASSERT member_crud/read/export/analytics/mail(input) == unchanged
  ASSERT gender_and_other_open_enums(input) == unchanged
END FOR
```

**Testing Approach:** property-based testing for preservation — generate random members /
non-status field edits and assert identical behavior across the input domain, plus the
observed public-form `status=application` default.

**Test Plan:** observe on UNFIXED code first (public-form create defaults `application`;
`gender` round-trips; member CRUD), then write property tests capturing that behavior.

**Test Cases:**
1. **Public-form create default** — a new applicant still gets `status=application`.
2. **Gender parity** — a tenant `gender` value saves/projects/resolves/validates unchanged
   (the exact precedent `status` now follows).
3. **Member CRUD + export** — unchanged minus the `lifecycle` block.

### Unit Tests
- `status` field is an OPEN enum (`choices=None`); open-enum validation accepts tenant values.
- Field-config payload carries NO `lifecycle` key.
- Route map = 22 routes, no transition specs.
- `tenant_hooks` still resolves `validate_member` after the `on_transition` carve.

### Property-Based Tests
- For all tenant-authored status values: survive save → project → resolve → set on member.
- For all non-status field edits: behavior identical to pre-retirement.
- Public-form create: `status == application` for all generated applicants.

### Integration Tests
- Parity harness (22 routes) passes with `routes_covered == route_names()`; the dimension-4
  lifecycle walk is removed/rewritten.
- End-to-end: author `died` in Tenant Admin → projection → resolved config → set on a member →
  read back, with no transition route involved.
