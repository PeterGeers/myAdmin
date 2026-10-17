# Implementation Plan: Membership-type catalog admin UI

## Overview

Pure frontend work over EXISTING SAM membership-type routes: a write-route service wrapper (task 1),
a TenantAdmin management surface (task 2), and a field-editor pointer so a `reference` field is no
longer a dead end (task 3). Task 4 is the verification checkpoint. No backend/SAM change.
Change-with-tests applies throughout.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"] },
    { "wave": 2, "tasks": ["2", "3"] },
    { "wave": 3, "tasks": ["4"] }
  ],
  "dependencies": {
    "2": ["1"],
    "3": ["1"],
    "4": ["2", "3"]
  }
}
```

- Task 1 (service wrapper) precedes the surfaces that call it (2, 3).
- Tasks 2 and 3 are independent of each other (both depend on 1).
- Task 4 depends on both 2 and 3.

## Tasks

- [x] 1. Add the write-route service wrapper (+ types)
  - [x] 1.1 Add `createMembershipType` / `updateMembershipType` / `deactivateMembershipType` to the
    Members config API client (sibling of `listMembershipTypes` in
    `frontend/src/services/members/membersConfigApi.ts`), hitting `POST /membership-types`,
    `PUT /membership-types/{type_code}`, `DELETE /membership-types/{type_code}`; unwrap the envelope
    and propagate errors. Re-export from `membersApiService.ts`.
  - [x] 1.2 Extend `MembershipType` (and add a write-body type) in `types/members.ts` for
    `label{nl,en}` / `order` / `active`.
  - [x] 1.3 Unit tests: each function hits the right method+path and surfaces errors
    (mirror `membersApiService.test.ts`).
  - _Requirements: 2.5, 4.1_

- [x] 2. Build the TenantAdmin membership-types management surface
  - [x] 2.1 Add a "Lidmaatschapstypes" tab/section under the Members admin area that lists ALL
    entries via `listMembershipTypes()` (no active filter), showing `type_code`/`label`/`active`/
    `order` sorted by `(order, type_code)`; empty state with a create action.
  - [x] 2.2 Create/edit modal: create (`type_code`+`label`+`order`), edit (`label`/`order`/`active`,
    `type_code` locked), retire (soft-delete) — wired to the task-1 wrapper; refresh the list after
    each mutation.
  - [x] 2.3 Client-side pre-submit validation (non-blank `type_code` without `#`; non-blank `nl`
    label; integer `order`); surface server 409 (duplicate) / 404 (absent) / 4xx readably.
  - [x] 2.4 Gate the mutation actions on the Members admin capability (UI UX gate; SAM enforces).
  - [x] 2.5 Component tests (MSW over the SAM routes): list incl. retired; create/edit/retire call
    the right route + refresh; empty state; non-admin sees no mutation actions. (Properties 1–3.)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.6_

- [x] 3. Point the field editor at the catalog manager (no dead end)
  - [x] 3.1 In `MembersConfig/MembersFieldModal.tsx`, for a `reference`-type field render a read-only
    note + a link/button to the membership-types manager INSTEAD of the empty `EnumOptionsEditor`;
    keep presentation-attribute editing. Leave the `enum` path unchanged.
  - [x] 3.2 Change-with-tests: update/extend the `MembersFieldModal` test so a `reference` field
    shows the pointer (no values editor) and an `enum` field still shows `EnumOptionsEditor`.
    (Property 4.)
  - _Requirements: 3.1, 3.2, 3.3_

## Checkpoint

- [ ] 4. Verify before `test` → `main`
  - [x] 4.1 Run the frontend vitest suite (incl. the new service/surface/field-editor tests) — green.
  - [x] 4.2 Run the build typecheck (`tsc -b`) — green (watch for the known pre-existing unrelated
    typecheck errors; do not let this task mask them).
  - [~] 4.3 Manual smoke on `test`: create a type (appears in the member dropdown), edit its label,
    retire it (disappears from the dropdown but stays in the management list). No SAM deploy needed.
  - _Requirements: 4.2, 4.3_

## Notes

- NO backend/SAM change — this consumes the existing `membership-type` CRUD routes (group `CATALOG`,
  `members:admin` for writes). Confirmed present in `sam/members/handler/routes.py`.
- This is the LIVE `reference` field work — distinct from `view_contexts` retirement (the OTHER spec).
- Change-with-tests contract: every new/changed component ships its paired test in the same change.
