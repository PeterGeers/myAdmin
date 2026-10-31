# Implementation Plan: Members Overview Tweaks

## Overview

Six focused changes to the Members area. Five are frontend presentation/routing edits on
`frontend/src/pages/MembersPage.tsx` and its modal/inbox components; one is a cross-plane
export-naming change touching the frontend download path and the SAM `Mail_Send_Worker`
(`sam/members/worker/mail_send_worker.py`) plus its enqueue envelope. The plan composes the
already-extracted presentational pieces and the resolved field config rather than rebuilding
them, and each naming change is pinned by a property test so the two planes cannot drift. The
SAM worker change honors the change-with-tests contract by updating
`sam/tests/test_mail_send_worker.py` and its `_to_fixed_envelope` fixture in the same task.

## Tasks

- [x] 1. Reorder MembersPage controls above the table
  - [x] 1.1 Move the action controls and pagination bar above the table in `MembersPage.tsx`
    - Reorder the JSX so document order becomes toolbar → stats strip → `MembersPaginationBar` → `MembersTable`
    - Do NOT touch `useMembersCursorPaging` wiring (`goNext`/`goPrev`/`pageSize`) so paging behaviour is unchanged
    - Keep `MembersPaginationBar` rendering in its new position regardless of row count (its only early return stays `loading`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Write interaction tests for control ordering
    - Render `MembersPage` with zero rows and with many rows; assert the action controls and pagination bar precede the table in DOM order
    - Click next → assert the cursor walk fires and rows update (paging unchanged)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Partition fields for edit vs view modals
  - [x] 2.1 Add the editable/calculated field partition helpers
    - In `frontend/src/components/members/fieldForm.ts` (or sibling helper) add `isCalculatedField(f)` over the existing per-field calculated/read-only flag and `editableFields(fields)` that filters out calculated fields
    - _Requirements: 2.1, 2.2, 3.1, 3.2_

  - [x] 2.2 Write property test for edit partition
    - **Feature: members-overview-tweaks, Property 1: Edit modal shows exactly the editable fields**
    - **Validates: Requirements 2.1, 2.2**
    - Generate field configs with mixed calculated/editable fields (min 100 iterations); assert displayed set equals exactly the editable fields
    - _Requirements: 2.1, 2.2_

  - [x] 2.3 Write property test for view completeness
    - **Feature: members-overview-tweaks, Property 2: View modal shows the complete field set**
    - **Validates: Requirements 3.1, 3.2**
    - Generate field configs with mixed fields (min 100 iterations); assert the view set equals the full resolved visible field set
    - _Requirements: 3.1, 3.2_

  - [x] 2.4 Apply editable-only partition in the edit modal
    - `MembersEditModal` builds its sections from `editableFields(formFields(cfg))` instead of the full set (calculated fields excluded, not disabled)
    - Leave the submit path (`shapeWritePayload` → `updateMember`) unchanged so saving persists editable values exactly as before
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.5 Keep the full field set in the view modal
    - Confirm `MembersViewBody` on `MembersPage` renders the FULL resolved set (every calculated and non-calculated field), applying no partition filter
    - _Requirements: 3.1, 3.2_

  - [x] 2.6 Write interaction test for edit save wiring
    - Submit the edit form → assert `updateMember` is called with the shaped editable-field payload
    - _Requirements: 2.3_

- [x] 3. Responsive two-column modal layout
  - [x] 3.1 Wrap edit and view modal bodies in a responsive SimpleGrid
    - Replace the single vertical `VStack` container in both modal bodies with `<SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>`, keeping field sections grouped by `functional_group`
    - Use the application's existing `md` breakpoint token as the Wide/Narrow boundary
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.2 Write interaction tests for responsive layout
    - Render each modal at a wide and a narrow viewport; assert two-column vs single-column container
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 4. Checkpoint - Ensure frontend presentation tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Tenant-prefixed export naming — shared rule and frontend download
  - [x] 5.1 Add the frontend shared naming rule
    - Add `exportFileName(tenantName, pivotName)` = `sanitize(tenantName) + "-" + sanitize(pivotName) + ".csv"` with `sanitize` stripping path separators/control chars and collapsing whitespace
    - _Requirements: 5.1, 5.4_

  - [x] 5.2 Write property test for frontend filename rule
    - **Feature: members-overview-tweaks, Property 3: Frontend download filename follows the tenant-pivot rule**
    - **Validates: Requirements 5.1, 5.4**
    - Generate tenant/pivot name pairs incl. spaces, punctuation, unicode, empty parts (min 100 iterations); assert the rule, always `.csv`, deterministic, never `members.csv`
    - _Requirements: 5.1, 5.4_

  - [x] 5.3 Use the naming rule in handleExport
    - Replace the fixed download filename in `MembersPage.handleExport` with `downloadCsv(csv, exportFileName(tenantName, pivotName))`
    - Source `tenantName` from the auth/tenant context on the page and `pivotName` from the selected pivot's display name; keep existing empty-result and error toasts
    - _Requirements: 5.1, 5.4_

- [x] 6. Tenant-prefixed export naming — SAM worker and envelope
  - [x] 6.1 Stamp tenant_name and pivot_name onto the send-job envelope
    - In the enqueue path (`handler/_dispatch.py` → `MailJob` → `_mail_job_to_envelope`) add additive `tenant_name` (resolved from the verified tenant context/projection, never a body value) and `pivot_name` fields
    - _Requirements: 5.2, 5.3, 5.5_

  - [x] 6.2 Add the worker Python naming rule with backward-compat fallback
    - Add `_export_file_name(tenant_name, pivot_name)` and `_export_subject(tenant_name, pivot_name)` encoding the same `{Tenant}-{Pivot}` rule with `sanitize` (no path separators/control chars)
    - When `tenant_name`/`pivot_name` is absent or blank, fall back to a safe generic `export.csv` filename and generic subject rather than raising (older in-flight jobs stay compatible)
    - _Requirements: 5.2, 5.3, 5.5_

  - [x] 6.3 Thread the names into _build_attachment and _render_to_fixed
    - `_build_attachment` names the CSV via `export_name` instead of the hard-coded `"members.csv"`
    - `_render_to_fixed` reads the names off the envelope, composes the subject with the tenant name as prefix + pivot name (template-covered subject still takes precedence for the body)
    - _Requirements: 5.2, 5.3, 5.5_

  - [x] 6.4 Write property test for worker filename rule
    - **Feature: members-overview-tweaks, Property 4: Worker attachment filename follows the tenant-pivot rule**
    - **Validates: Requirements 5.2, 5.5**
    - Generate envelopes with varied tenant/pivot names (min 100 iterations, SAM pytest); assert the `{Tenant}-{Pivot}.csv` rule, always `.csv`, never `members.csv`
    - _Requirements: 5.2, 5.5_

  - [x] 6.5 Write property test for subject prefix rule
    - **Feature: members-overview-tweaks, Property 5: Email subject prefixes the tenant name before the pivot name**
    - **Validates: Requirements 5.3**
    - Generate tenant/pivot name pairs (min 100 iterations); assert the composed subject contains the tenant name as a leading prefix followed by the pivot name
    - _Requirements: 5.3_

  - [x] 6.6 Update the paired worker test and fixture (change-with-tests)
    - Add `tenant_name` / `pivot_name` to the `_to_fixed_envelope` fixture in `sam/tests/test_mail_send_worker.py`
    - Update `TestToFixedSend.test_builds_csv_attachment_and_sends_to_fixed_recipients` to assert the new `{Tenant_Name}-{Pivot_Name}.csv` filename and the tenant-prefixed subject (align to new behavior, do not weaken)
    - Run `python -m pytest sam/tests/test_mail_send_worker.py -q` before considering done
    - _Requirements: 5.2, 5.3, 5.5_

- [x] 7. Checkpoint - Ensure export-naming tests pass on both planes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Relocate the applications inbox
  - [x] 8.1 Remove the applications inbox from MembersPage
    - Remove the `<MembersInboxBar>` render block and the `useApplicationsInbox(...)` call from `MembersPage.tsx` so the page is toolbar → stats → pagination → table
    - _Requirements: 6.1_

  - [x] 8.2 Add the tenant-admin members > mail route hosting the inbox
    - Add a tenant-administrator route under members > mail (`Members_Mail_Area`) that renders the relocated applications inbox: the preset bar + a member grid driven by `useApplicationsInbox` (reused verbatim), pinned to `status = application` and retaining the `DUP` / `NO_NOTIFY` keyword quick-filters over `overlay.additional_info`
    - _Requirements: 6.2, 6.3, 6.4_

  - [x] 8.3 Write property test for status pin
    - **Feature: members-overview-tweaks, Property 6: Applications inbox shows only status=application rows**
    - **Validates: Requirements 6.3**
    - Generate member rows with varied statuses (min 100 iterations); assert every displayed row has `status = application` and no application row is dropped
    - _Requirements: 6.3_

  - [x] 8.4 Write property test for keyword filter
    - **Feature: members-overview-tweaks, Property 7: Keyword filter narrows the inbox to matching notes**
    - **Validates: Requirements 6.4**
    - Generate rows with varied statuses and `additional_info` notes and a keyword in `{DUP, NO_NOTIFY}` (min 100 iterations); assert every displayed row's `overlay.additional_info` contains the keyword and the `status = application` pin still holds
    - _Requirements: 6.4_

  - [x] 8.5 Write interaction tests for inbox relocation
    - Assert `MembersPage` no longer renders the inbox bar; assert the tenant-admin members-mail route renders the applications inbox
    - _Requirements: 6.1, 6.2_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP.
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation at plane boundaries (frontend presentation, export naming, routing).
- Property tests validate the input-varying logic (field partitioning, export naming, inbox filtering) at min 100 iterations each, tagged with their design property.
- Interaction tests cover the structural/layout criteria (DOM ordering, responsive columns, routing, save wiring).
- The SAM worker naming change updates its paired test and fixture in the same task (6.6) per the change-with-tests contract.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "5.1", "6.1", "8.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "2.3", "2.4", "2.5", "5.2", "5.3", "6.2"] },
    { "id": 2, "tasks": ["2.6", "3.1", "6.3", "6.4", "8.2"] },
    { "id": 3, "tasks": ["3.2", "6.5", "6.6", "8.3", "8.4", "8.5"] }
  ]
}
```
