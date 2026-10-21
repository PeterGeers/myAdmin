# Design Document

## Overview

This feature bundles four small, independent improvements to the Members area. Three are pure
frontend presentation changes on `frontend/src/pages/MembersPage.tsx` and its modal components;
one is a cross-plane export-naming change that touches both the frontend download path and the
SAM `Mail_Send_Worker` (`sam/members/worker/mail_send_worker.py`); and one is a
navigation/routing change relocating the applications inbox.

The work deliberately **composes existing machinery** rather than rebuilding it:

- Controls-above-the-table is a JSX reordering of the already-extracted presentational pieces
  (`MembersToolbar`, `MembersInboxBar`/its successor, `MembersPaginationBar`, `MembersTable`) —
  no change to `useMembersCursorPaging`, so paging behaviour is unchanged (Req 1.4).
- Edit/view field partitioning reuses the resolved field config and the existing
  `formFields` / `groupFieldsBySection` helpers; the only new logic is a small pure partition
  on the already-present "calculated / read-only" field flag.
- The two-column modal layout is a Chakra responsive `SimpleGrid`/`columns` prop swap in the
  modal bodies.
- Export naming introduces ONE shared naming rule (`{Tenant_Name}-{Pivot_Name}.csv`) applied in
  two places: the frontend `handleExport` download, and the worker's `_build_attachment` /
  `_render_to_fixed` subject. The names must RIDE the send-job envelope (`tenant_id` and
  `set_id` are opaque keys, not display names), so the enqueue side stamps `tenant_name` and
  `pivot_name` onto the job.
- Relocating the applications inbox moves `MembersInboxBar` + `useApplicationsInbox` off
  `MembersPage` and onto a new tenant-admin members-mail route, keeping the `status=application`
  pin and the `DUP` / `NO_NOTIFY` keyword filters intact.

### Scope boundary

The SAM-worker change (Req 5.2, 5.3, 5.5) is the only product-code change outside the frontend.
Per the Flask-plane API conventions note on the service layer it lives on the **SAM module
plane**, not the Flask plane — so the change-with-tests contract applies against the SAM paired
test `sam/tests/test_mail_send_worker.py`, which currently asserts the fixed `members.csv`
filename and MUST be updated in the same change.

## Architecture

```
Frontend (React / Chakra)                         SAM module plane (Lambda)
─────────────────────────                         ─────────────────────────
MembersPage.tsx                                   handler/_dispatch.py (enqueue)
├─ MembersToolbar          (actions)                └─ stamps tenant_name + pivot_name
├─ MembersPaginationBar    (paging)  ── Req 1 ──┐      onto the MailJob envelope   ── Req 5 ──┐
├─ MembersTable            (table)   ───────────┘                                             │
├─ MembersEditModal  ── Req 2,4 ── editable-only, 2-col      SQS                              │
├─ view modal        ── Req 3,4 ── all fields, 2-col          │                               │
└─ handleExport      ── Req 5.1,5.4 {Tenant}-{Pivot}.csv      ▼                               │
                                                  worker/mail_send_worker.py                  │
Tenant-admin route (new)  ── Req 6 ──             ├─ _render_to_fixed  → subject  ◀───────────┘
└─ members > mail                                 │     "{Tenant_Name} - {Pivot_Name}" (Req 5.3)
   └─ ApplicationsInbox (relocated)               └─ _build_attachment → filename
      status=application + DUP/NO_NOTIFY                "{Tenant_Name}-{Pivot_Name}.csv" (Req 5.2,5.5)
```

### Shared naming rule

The filename rule is ONE function used on both planes so a downloaded file and an emailed
attachment for the same tenant+pivot carry the identical name:

```
exportFileName(tenantName, pivotName) = sanitize(tenantName) + "-" + sanitize(pivotName) + ".csv"
```

`sanitize` strips/replaces filesystem-hostile characters (path separators, control chars) and
collapses whitespace, leaving a stable, readable name. The frontend owns its TypeScript copy;
the worker owns its Python copy (the two planes do not share code), but both encode the same
rule and both are pinned by a filename property (P3, P4) so they cannot drift.

## Components and Interfaces

### Requirement 1 — Controls above the table (frontend)

`MembersPage.tsx` renders its children in JSX document order. Today the order is: toolbar,
inbox bar, stats strip, **table**, **pagination bar**. The change reorders so the action
controls and the pagination bar precede the table:

```
MembersToolbar          (Action_Buttons_Row)
MembersStatsStrip
MembersPaginationBar     (Pagination_Controls)   ← moved above the table
MembersTable             (Members_Table)
```

- No change to `useMembersCursorPaging` — `goNext`/`goPrev`/`pageSize` wiring is identical, so
  activating a control still walks the server cursor (Req 1.4).
- `MembersPaginationBar` is purely presentational; it renders in its new position regardless of
  row count (it already early-returns only on `loading`, not on an empty page) (Req 1.3).
- The inbox bar is removed from this page entirely (Req 6.1), so after the reorder the page is:
  toolbar → stats → pagination → table.

### Requirement 2 & 3 — Edit shows editable-only, View keeps all (frontend)

A new pure partition over the resolved field list drives both modals. The field config already
carries, per field, whether it is editable vs calculated/read-only (the edit modal renders
calculated fields *disabled* today — Req 2 trims them out instead of disabling them).

```ts
// frontend/src/components/members/fieldForm.ts (or a sibling helper)
export function isCalculatedField(f: FieldConfigField): boolean {
  // true when the field is derived/read-only (not user-editable)
}

export function editableFields(fields: FieldConfigField[]): FieldConfigField[] {
  return fields.filter(f => !isCalculatedField(f));
}
// view modal keeps the full resolved set (no filter) — every field incl. calculated
```

- **Edit modal** (`MembersEditModal`): builds its sections from `editableFields(formFields(cfg))`
  instead of the full set. Calculated fields are excluded from display (Req 2.2); every editable
  field is shown (Req 2.1). Submit path (`shapeWritePayload` → `updateMember`) is unchanged, so
  saving persists the editable values exactly as before (Req 2.3).
- **View modal** (the read-only `MembersViewBody` on `MembersPage`): unchanged field set — it
  renders the FULL resolved set, so every calculated field and every non-calculated field is
  shown (Req 3.1, 3.2).

### Requirement 4 — Responsive two-column modal layout (frontend)

Both modal bodies wrap their field sections in a Chakra responsive grid rather than a single
vertical `VStack`:

```tsx
<SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
  {/* field groups */}
</SimpleGrid>
```

- `base: 1` → a Narrow_Viewport renders a single column (Req 4.3, 4.4).
- `md: 2` → a Wide_Viewport (≥ Chakra `md` breakpoint) renders two columns (Req 4.1, 4.2).

The breakpoint is the application's existing `md` token (the "defined breakpoint" of the
glossary's Wide/Narrow viewport). Field sections remain grouped by `functional_group`; only the
container layout changes.

### Requirement 5 — Tenant-prefixed export naming (frontend + SAM worker)

**Envelope carries the display names.** `tenant_id` and `set_id` on the send job are opaque
keys. The enqueue side (`handler/_dispatch.py` → the `MailJob` → `_mail_job_to_envelope`) must
additionally stamp:

- `tenant_name` — the active tenant's display name (resolved from the verified tenant context /
  projection at enqueue time; authoritative, never a body value).
- `pivot_name` — the analytics set's display name (`Pivot_Name`).

Both ride the envelope so the worker can name the attachment and compose the subject without a
second lookup.

**Frontend download** (`MembersPage.handleExport`): replace the fixed
`downloadCsv(csv, \`leden-${stamp}.csv\`)` with the shared rule:

```ts
downloadCsv(csv, exportFileName(tenantName, pivotName)); // "{Tenant_Name}-{Pivot_Name}.csv"
```

`tenantName` comes from the auth/tenant context already available on the page; `pivotName` is
the selected pivot's display name. (Req 5.1, 5.4)

**SAM worker** (`mail_send_worker.py`):

- `_build_attachment` takes the tenant + pivot name (threaded from `_render_to_fixed`, read off
  the envelope) and names the CSV `{Tenant_Name}-{Pivot_Name}.csv` instead of the hard-coded
  `"members.csv"` (Req 5.2, 5.5):

```python
def _build_attachment(self, kind, rows, label_options, *, export_name):
    if kind == "csv":
        return {"filename": export_name, "content": _rows_to_csv_bytes(rows),
                "content_type": "text/csv"}
    ...
```

- `_render_to_fixed` composes the subject with the tenant name as a prefix combined with the
  pivot name (Req 5.3), replacing the static `"Member set"` default when a pivot export is
  being sent:

```python
export_name = _export_file_name(tenant_name, pivot_name)   # "{Tenant}-{Pivot}.csv"
subject = _export_subject(tenant_name, pivot_name)         # "{Tenant} - {Pivot}" prefix+pivot
```

A covering-template subject (when a `template_id` is supplied) still takes precedence for the
body; the tenant-prefixed subject is the composed default for a pivot export send.

> **Change-with-tests contract (SAM plane).** `sam/tests/test_mail_send_worker.py`
> currently asserts `att["filename"] == "members.csv"` (in
> `TestToFixedSend.test_builds_csv_attachment_and_sends_to_fixed_recipients`) and its
> `_to_fixed_envelope` fixture carries no `tenant_name` / `pivot_name`. Both MUST be updated in
> the same change: add the two name fields to the fixture and assert the new
> `{Tenant_Name}-{Pivot_Name}.csv` filename and the tenant-prefixed subject. Do not weaken the
> assertion to go green — align it to the intended new name. Run
> `python -m pytest sam/tests/test_mail_send_worker.py -q` before considering the change done.

### Requirement 6 — Relocate the applications inbox (frontend routing)

Move the inbox out of `MembersPage` and into a tenant-administrator members-mail area:

- **Remove** from `MembersPage`: the `<MembersInboxBar>` render block and the
  `useApplicationsInbox(...)` call (Req 6.1).
- **Add** a tenant-admin route under members > mail (the `Members_Mail_Area`) that renders the
  relocated applications inbox (Req 6.2). The inbox there still drives a member grid through the
  Table Filter Framework v2 via `useApplicationsInbox`, pinned to `status = application`
  (Req 6.3), and retains the `DUP` / `NO_NOTIFY` keyword quick-filters over
  `overlay.additional_info` (Req 6.4).

Because `useApplicationsInbox` is self-contained wiring over `setFilter` + the column model, the
relocation reuses it verbatim — the new route hosts the same preset bar + a member grid, rather
than re-implementing the inbox. The SAM-side keyword constants (`DUP`, `NO_NOTIFY`) are
unchanged, so the relocated filters match the same flagged rows.

## Data Models

No persisted schema changes. The only shape change is **additive** on the in-flight send-job
envelope (not stored): two string fields.

```
MailJob / send-job envelope (additive, Req 5)
  tenant_id   : str   (existing — opaque key)
  set_id      : str   (existing — opaque key)
  tenant_name : str   (NEW — Tenant_Name display name, for export naming)
  pivot_name  : str   (NEW — Pivot_Name display name, for export naming)
  ... (unchanged: run_id, mode, recipients, template_id, merge_values, attachment, rows)
```

Field config fields are consumed read-only; the edit/view partition derives from the existing
per-field calculated/read-only flag (no new field added).

## Error Handling

- **Missing display names on the envelope (worker).** If `tenant_name` or `pivot_name` is absent
  or blank (e.g. an older in-flight job enqueued before this change), the worker falls back to a
  safe default name so it never emits an empty or malformed filename — it degrades to a generic
  `export.csv` (and a generic subject) rather than raising. A pivot export never regresses to a
  hard failure over a cosmetic name. This keeps the change backward-compatible with jobs already
  on the queue at deploy time.
- **Name sanitization (both planes).** `sanitize` guarantees the result contains no path
  separators or control characters, so a tenant/pivot name with `/`, `\`, or newlines cannot
  produce an invalid attachment filename or a header-injecting subject.
- **Frontend export unchanged on failure.** `handleExport` keeps its existing empty-result info
  toast and error toast; only the success filename changes.
- **Inbox relocation.** The relocated route reuses the existing grid + framework error surfaces
  (loading spinner, empty state); no new error paths.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of
a system — essentially, a formal statement about what the system should do. Properties serve as
the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Edit modal shows exactly the editable fields

*For any* resolved field config, the set of fields displayed by the Edit_Modal equals exactly the
set of editable (non-calculated) fields — every editable field is included and every calculated
field is excluded.

**Validates: Requirements 2.1, 2.2**

### Property 2: View modal shows the complete field set

*For any* resolved field config, the set of fields displayed by the View_Modal equals the full
resolved visible field set — it includes every calculated field and every non-calculated field.

**Validates: Requirements 3.1, 3.2**

### Property 3: Frontend download filename follows the tenant-pivot rule

*For any* tenant name and pivot name, the downloaded CSV filename equals
`sanitize(tenantName) + "-" + sanitize(pivotName) + ".csv"`, always ends in `.csv`, is
deterministic, and is never the fixed `members.csv`.

**Validates: Requirements 5.1, 5.4**

### Property 4: Worker attachment filename follows the tenant-pivot rule

*For any* send-job envelope carrying a tenant name and pivot name with a CSV attachment, the
attachment filename the Mail_Send_Worker builds equals the shared
`{Tenant_Name}-{Pivot_Name}.csv` rule, always ends in `.csv`, and is never the fixed
`members.csv`.

**Validates: Requirements 5.2, 5.5**

### Property 5: Email subject prefixes the tenant name before the pivot name

*For any* tenant name and pivot name, the composed pivot-export email subject contains the tenant
name as a leading prefix followed by the pivot name.

**Validates: Requirements 5.3**

### Property 6: Applications inbox shows only status=application rows

*For any* set of member rows, after the Applications_Inbox is activated in the Members_Mail_Area,
every displayed row has `status = application`, and no row with `status = application` is dropped.

**Validates: Requirements 6.3**

### Property 7: Keyword filter narrows the inbox to matching notes

*For any* set of member rows and any keyword in `{DUP, NO_NOTIFY}`, after the keyword filter is
applied every displayed row's `overlay.additional_info` contains that keyword, and the
`status = application` pin still holds.

**Validates: Requirements 6.4**

## Testing Strategy

**Dual approach.** Example/interaction tests cover the structural and layout criteria (DOM
ordering, responsive columns, routing, save wiring); property tests cover the input-varying
logic (field partitioning, export naming, inbox filtering).

### Example / interaction tests

- Controls order (Req 1.1–1.3): render `MembersPage` with zero and with many rows; assert the
  action controls and pagination bar precede the table in DOM order.
- Paging unchanged (Req 1.4): click next → assert the cursor walk fires and rows update.
- Save persists (Req 2.3): submit the edit form → assert `updateMember` is called with the
  shaped editable-field payload.
- Responsive layout (Req 4.1–4.4): render each modal at a wide and a narrow viewport; assert
  two-column vs single-column container.
- Inbox relocation (Req 6.1, 6.2): assert `MembersPage` no longer renders the inbox bar; assert
  the tenant-admin members-mail route renders the applications inbox.

### Property tests

- P1 edit partition, P2 view completeness: generate field configs with mixed calculated/editable
  fields; assert the two displayed field sets.
- P3 frontend filename, P4 worker filename, P5 subject: generate tenant/pivot name pairs
  (including spaces, punctuation, unicode, empty parts) and assert the naming/subject rules.
- P6 status pin, P7 keyword filter: generate member rows with varied statuses and
  `additional_info` notes; assert the inbox filtering invariants.

### Property test configuration

- Minimum **100 iterations** per property test (randomized inputs).
- Each property test references its design property with the tag format
  **Feature: members-overview-tweaks, Property {number}: {property_text}**.
- Frontend property tests use the project's JS property runner (e.g. fast-check) alongside
  vitest; the SAM worker property tests use the SAM plane's pytest (`sam/pytest.ini`).

### Change-with-tests

The worker naming change (Req 5.2, 5.3, 5.5) updates its paired test
`sam/tests/test_mail_send_worker.py` in the same change: the `_to_fixed_envelope` fixture gains
`tenant_name` / `pivot_name`, and `TestToFixedSend` asserts the new
`{Tenant_Name}-{Pivot_Name}.csv` filename and tenant-prefixed subject. Run
`python -m pytest sam/tests/test_mail_send_worker.py -q` to confirm.
