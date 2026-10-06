# Member Field Search — Design Options

## Problem

The Members overview table shows a compact set of default columns
(`member_number`, `name`, `email`, `status`, `membership_type`, `region`).
A member record has many more fields than this — overlay fields from the active
view context and calculated fields resolved via `valueFor`. Today a user who
needs to find rows by a value that lives in a **non-visible** field has no direct
way to do so from the overview.

We want a way to find / inspect member rows based on fields that are not part of
the currently displayed header columns.

## Shared constraints (apply to every option)

- All options operate on the **client-side, scope-authorized** row set that
  `useFilterableTable` already holds. None of them widen data scope — a user
  never sees rows they are not authorized for.
- Field values are resolved through the existing helpers in
  `components/members/fieldValue.ts` (`isColumnCandidate`, `valueFor`,
  `renderFieldValue`), so fixed, overlay, and calculated fields are all reachable
  with the logic already in place.
- **Scale caveat:** these are client-side over the loaded subset. That is fine
  for a scoped slice (hundreds of rows). If a tenant's authorized set grows into
  the thousands, a server-side search endpoint would be the right follow-up —
  out of scope for these three options.

---

## Option 1 — Global all-fields search box (brute force)

A single free-text input placed above the Members overview table. As the user
types, rows are narrowed client-side to those where **any** resolved field
(fixed + overlay + calculated, via `valueFor`) contains the search text.

- **Mechanism:** filter the rows that feed `useFilterableTable` by matching the
  query against every candidate field of each row. Scope-safe — it only ever
  narrows the already-authorized set.
- **Pros:** direct, small, low-risk. Best quick win. No new config surface, no
  per-column UI. Instantly covers hidden fields without the user needing to know
  which column a value lives in.
- **Cons:** blunt — matches across all fields at once, so no "this value in
  *this* field" precision. Pure client-side over the loaded subset.
- **Assessment:** user noted this is "more brute force but can work." Recommended
  as the first thing to ship because it is the cheapest path to covering hidden
  fields.

## Option 2 — User column chooser (session columns)

On top of the existing admin-defined view contexts, let a user **temporarily**
add any field (including overlay / calculated) as a column for their current
session. Once added, the existing per-column `FilterableHeader` filter and sort
work on it unchanged.

- **Mechanism:** a field picker that appends chosen fields to the session's
  visible columns (candidates come from the same `overlayColumns` /
  `isColumnCandidate` logic). Reuses the whole existing filter+sort pipeline — no
  new filtering engine.
- **Pros:** precise and powerful. Follows the familiar Jira / Airtable "fields"
  pattern. Per-field filtering and sorting for free. Non-destructive to the
  admin view contexts (session-only).
- **Cons:** more UI than Option 1 (a column-management affordance). The user has
  to know which field they want to surface.
- **Assessment:** user called this "very interesting." Strong candidate as the
  precision complement to Option 1.

## Option 3 — Analytics filtered-list pivot (already built)

The Member Analytics "list" pivot already produces a saved / shareable
"rows where field X = Y" report, with definition-level filters and CSV export.

- **Mechanism:** exists today. Define a filtered list in Analytics, save it,
  share it, export CSV.
- **Pros:** persistent, shareable, exportable. Good for recurring / reportable
  questions rather than ad-hoc lookups.
- **Cons:** lives in Analytics, not inline on the overview table — a context
  switch for a quick lookup.
- **Open decision to revisit:** it was previously decided that a data row found
  via a list pivot would **not** be editable from the pivot result (no
  edit-from-row). The user has asked whether we should change that decision —
  i.e. allow a found row to raise a change request / be edited directly from the
  pivot result.

  > This is flagged as an **open question**, not decided here. Changing it would
  > turn the list pivot from a read-only report into an actionable work surface,
  > which has permission and audit implications worth designing deliberately.

---

## Recommendation

- Ship **Option 1** first — lowest risk, directly solves "find a value in a
  hidden field," no new config surface.
- Follow with **Option 2** for precise, per-field filtering when the user knows
  the field they care about.
- Keep **Option 3** as the persistent/shareable reporting path, and separately
  resolve the open edit-from-row decision before changing that behaviour.

All three are complementary rather than mutually exclusive; the user confirmed
"all 3 are viable."
