# Implementation Plan

## Overview

Spec documents only — this plan is for review. Do NOT implement the retirement, delete files,
or run DB/projection writes until the user approves. Write the exploration test BEFORE any
deletion, and run it on the UNFIXED code first. The plan follows the bugfix methodology:
explore (prove the bug) → preserve (baseline) → retire the engine + open the status field →
re-run the same tests → checkpoint.

## Task Dependency Graph

Tasks 1 and 2 (explore + preserve) run first on UNFIXED code. The retirement sub-tasks (3.1 →
3.6) are strictly sequential (leaves first, then shared modules, then the record). 3.7/3.8
re-run the same tests, then the checkpoint.

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "description": "Explore (FAILS on unfixed) + preserve baseline (PASS on unfixed), independent." },
    { "wave": 2, "tasks": ["3.1"], "description": "Remove frontend transition surface (leaf consumers)." },
    { "wave": 3, "tasks": ["3.2"], "description": "Remove transition routes + dispatch + app wiring." },
    { "wave": 4, "tasks": ["3.3"], "description": "Delete engine modules + carve hook registry." },
    { "wave": 5, "tasks": ["3.4"], "description": "Open the status field + remove MembershipStatus." },
    { "wave": 6, "tasks": ["3.5"], "description": "Update/Delete paired tests." },
    { "wave": 7, "tasks": ["3.6"], "description": "Reconcile docstrings + specs." },
    { "wave": 8, "tasks": ["3.7", "3.8"], "description": "Re-run the same exploration + preservation tests." },
    { "wave": 9, "tasks": ["4"], "description": "Checkpoint — all suites green." }
  ]
}
```

## Tasks

- [x] 1. Write the bug-condition exploration test (BEFORE any retirement)
  - **Property 1: Bug Condition** - Status is a tenant-driven open enum; changes are plain edits
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the closed set + engine gatekeep tenant status values. DO NOT fix code when it fails; it encodes the intended post-retirement behavior and will validate the fix once it passes.
  - **GOAL**: Surface counterexamples that prove the bug (from Bug Condition in design §Bug Details).
  - **Scoped PBT approach**: scope to the concrete failing case `status="died"` (label "Overleden") plus one arbitrary extra tenant value.
  - Author a tenant `membership.status` overlay value `died` and assert it survives resolve → projection into the resolved `config#fields` `status.choices` (from Expected Behavior 2.1/2.2).
  - Assert `create_member(... membership.status="died" ...)` succeeds (open-enum validation, 2.3) — on UNFIXED code it raises `FieldValidationError` "must be one of: application, pending, active, suspended, lapsed, left".
  - Assert a status change `active → application` via an ordinary `update_member` succeeds with no graph/guard (2.4) — on UNFIXED code the transition engine blocks it.
  - Run on UNFIXED code. **EXPECTED OUTCOME**: test FAILS (proves the bug).
  - Document the counterexamples (value dropped at projection; create rejected; change denied).
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE any retirement — observation-first)
  - **Property 2: Preservation** - Non-status behavior is unchanged
  - **IMPORTANT**: Observe behavior on UNFIXED code, then write property-based tests asserting it.
  - Observe: public application-form create stamps `membership.status = "application"` → assert it for all generated applicants (from Preservation 3.1).
  - Observe: a tenant `gender` value saves → projects → resolves → validates on a member → assert the same round-trip holds for all generated gender values (3.3) — this is the exact precedent `status` will follow.
  - Observe: member create/get/list/search/update/delete + export behave as today (minus the `lifecycle` block) and stay tenant-keyed → assert for generated members (3.2).
  - Observe: analytics-set / mail / template / schedule / catalog / delegate paths unaffected (3.4); other field-resolver invariants hold (3.5).
  - Run on UNFIXED code. **EXPECTED OUTCOME**: tests PASS (baseline to preserve).
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Retire the lifecycle engine and open the status field
  - **PRECONDITION**: external-consumer sign-off (design §E) — confirm no out-of-repo client posts to `/transition` or `/memberships/transition`.

  - [x] 3.1 Remove the frontend transition surface (leaf consumers — design D)
    - Delete `MembersTransitionModal.tsx`, `MembersBulkTransitionModal.tsx`, `transitionTargets.ts`.
    - Remove `transitionMembership`/`bulkTransition` from `membersResourceApi.ts` + the `membersApiService.ts` re-exports.
    - Remove the two modal mounts, the "Change status" + "Bulk: change status" buttons/handlers, and the transition state from `MembersPage.tsx`.
    - Strip `LifecycleConfigShape` + `FieldConfig.lifecycle?` from `types/members.ts` (keep `status?`, `membership_id?`).
    - Confirm `status` is editable via the existing member edit modal as a plain enum field.
    - _Bug_Condition: isBugCondition(input) where the SPA gatekeeps status via the transition modal_
    - _Expected_Behavior: status changed as an ordinary field edit (Property 1 / 2.4)_
    - _Requirements: 2.4_

  - [x] 3.2 Remove the two transition routes + dispatch + app wiring (design A)
    - Remove the `transition_membership` + `bulk_transition_memberships` `RouteSpec`s; fix the `routes.py` docstring lifecycle count (7 → 5).
    - Remove the two dispatch branches + `_parse_to_state` + `_transition_context` (+ `__all__`) in `_dispatch.py`.
    - Remove `_LIFECYCLE_PROVIDER`, the `lifecycle_config` imports, the `lifecycle_provider=` kwarg, and the `TransitionDenied` import + except handler (+ `errors.transition.denied`) in `app.py`.
    - _Bug_Condition: the transition routes gatekeep status change_
    - _Expected_Behavior: no transition routes; status edited via member update (2.4)_
    - _Requirements: 2.4_

  - [x] 3.3 Delete the engine/domain modules + carve the hook registry (design B)
    - Delete `_membership_lifecycle.py`, `transition_hooks.py`, `lifecycle_config.py`; delete `MembershipService.transition_member`/`bulk_transition_members`, the `LifecycleMixin` base, the `lifecycle_provider`/`_transition_hooks` constructor params, `_serialize_lifecycle` + the `"lifecycle"` field-config key.
    - Replace the write-path initial-state block with a plain `"application"` default literal (preserve 3.1).
    - Carve `tenant_hooks.py`: remove `HookName.ON_TRANSITION`, `default_on_transition`, the `transition_hooks` import, `transition_registry()`; KEEP `validate_member`/`resolve_visible_regions`/`calculate_fee`. Update `tenants/hdcn/hooks.py` to compare the literal `"active"`.
    - Delete `TransitionDenied`/`TransitionResult` from `_membership_errors.py`.
    - _Bug_Condition: the engine gatekeeps status value set + change_
    - _Expected_Behavior: engine retired; status change is a plain edit; `status=application` default preserved_
    - _Requirements: 2.4, 3.1_

  - [x] 3.4 Open the status field + remove `MembershipStatus` (design C)
    - In `fixed_fields.py`: set `status` `choices=None` (open enum, like `gender`); keep a minimal `options` seed (sensible default status values incl. `application`); remove `choices=tuple(s.value for s in MembershipStatus)`.
    - Delete the `MembershipStatus` `Enum` class + its `__all__` entry + every import (all now point to deleted/carved code or a literal).
    - Confirm `validate_fixed_fields`/`_validate_value` take the open-enum path for `status`.
    - _Bug_Condition: closed `MembershipStatus` choices drop/reject tenant values_
    - _Expected_Behavior: status is an open enum; tenant values survive + validate (2.1, 2.2, 2.3, 2.5)_
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.5 Update/Delete all paired tests (design F — change-with-tests)
    - DELETE `test_lifecycle_config.py`, `test_membership_lifecycle.py`, `frontend .../MembersTransitions.test.tsx`.
    - UPDATE `test_tenant_hooks.py` (drop `on_transition`, keep the rest), `test_fixed_fields.py` (status `choices is None`), `test_empty_is_valid_props.py`, `test_attribute_catalog.py`, `test_field_config_endpoint.py` (no `lifecycle`), `members_parity_harness.py` + `test_members_parity_harness.py` (drop transition routes + dimension-4 walk; 22 routes), `test_members_routes.py` (22 routes), `test_analytics_set_routes.py` (drop lifecycle_provider), `membersApiService.test.ts` (drop the 2 cases), `membersApiService.apiError.test.ts` (re-point).
    - Do NOT weaken assertions to go green — assert the intended open/retired behavior.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.6 Reconcile every docstring + spec (design G)
    - Docstrings: `fixed_fields.py`, `field_resolver.py` (drop "NEVER touch the closed status enum"), `tenant_hooks.py`, `tenants/hdcn/hooks.py`, `_membership_writes.py`, `backend/src/services/members_config_validation.py`, `scripts/onboarding/members/h-dcn/ONBOARDING.md`.
    - Specs: `application-app/requirements.md` (R8b.3), `application-app/design-options.md`, `s5-members-first-migration/go-no-go.md` (22 routes; lifecycle retired), `s5-members-first-migration/tasks.md` (task 5.0 superseded pointer), `s5b-members-runnable-in-spa` requirements/design/tasks/walkthrough (transition items superseded).
    - _Requirements: 2.4, 2.5_

  - [x] 3.7 Verify the bug-condition exploration test now passes
    - **Property 1: Expected Behavior** - Status is a tenant-driven open enum; changes are plain edits
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new one.
    - **EXPECTED OUTCOME**: test PASSES (tenant status value survives projection + validates; status change is a plain edit).
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.8 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-status behavior is unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new ones.
    - **EXPECTED OUTCOME**: tests PASS (public-form `status=application` default; gender parity; member CRUD/export; tenant isolation — no regressions).
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the SAM suite (`python -m pytest`) + the parity harness (22 routes, `routes_covered == route_names()`) + the frontend tests. Ask the user if questions arise (especially the deferred welcome-mail follow-up and whether the `active`-requires-member_number+email invariant should be re-added as a plain rule).

## Notes

- **Risk gate (design §E):** task 3 is blocked until the user confirms no out-of-repo client
  posts to `/transition` or `/memberships/transition`. In-repo, the only caller is the SPA.
- **Change-with-tests:** every product edit in task 3 pairs with its test update in 3.5 in the
  same change; never weaken an assertion to go green.
- **Parity-count delta:** retiring 2 routes moves the documented count 24 → 22 (membership
  lifecycle 7 → 5). Reconcile the harness and the Go/No-Go narrative together.
- **Deferred (out of scope):** pivot-based welcome mail on activation; a future state engine
  "when mature"; optionally re-adding `active`-requires-member_number+email as a plain rule.
