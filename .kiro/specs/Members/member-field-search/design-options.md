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
session. Once added, the user can filter and sort on it with the existing
per-column `FilterableHeader`.

- **Mechanism:** a field picker that appends chosen fields to the session's
  visible columns (candidates come from `fields.filter(isColumnCandidate)`), plus
  the plumbing to make filter + sort actually work on those fields (see the
  reality check below).
- **Pros:** precise and powerful. Follows the familiar Jira / Airtable "fields"
  pattern. Non-destructive to the admin view contexts (session-only, no
  persistence to integrate). No permission blocker — surfacing a column is pure
  client-side presentation; row scope stays server-enforced.
- **Cons:** more UI than Option 1 (a column-management affordance), and — the
  important correction — filter + sort are **not** free (see below). The user
  also has to know which field they want to surface.
- **Assessment:** user called this "very interesting." Strong candidate as the
  precision complement to Option 1, but a focused multi-day change, not a quick
  win.

### Reality check — "filter + sort work unchanged" is NOT true today

An earlier draft of this note said per-field filtering and sorting would work
"for free / unchanged." Investigation of `MembersPage.tsx` and the shared table
hooks shows that is **not** the case:

- The **cell render** path already resolves any nested field correctly
  (`valueFor` is nested-aware), BUT
- the **filter and sort engines read flat `row[key]` only** — they do not consult
  the field's storage `group`. Calculated / overlay fields live in nested buckets
  (`membership.years_member`, `overlay.*`) and are not promoted to flat aliases.
  So filtering on such a key silently no-ops and sorting pushes every row to the
  end. Today an overlay column is therefore **sortable-but-broken and not
  filterable at all** (its header is rendered without filter wiring, and its key
  is absent from the fixed `INITIAL_FILTERS` allow-list).

This is a real latent defect **independent of Option 2** (the F-003 / F-005 class
in `member-analytics/findings.md`): overlay columns in full view are already
sortable-but-wrong for nested fields.

### What the build actually involves

1. **Nested-aware filter + sort** — the dominant cost. Either pre-flatten the
   chosen session fields onto the rows via `valueFor` / `groupForKey`, or teach
   `useColumnFilters` / `useTableSort` to resolve by group. Pre-flattening only
   the chosen columns is the lower-risk route (hooks untouched).
2. **Dynamic filter key set** — `INITIAL_FILTERS` is a fixed 6-key allow-list; the
   hook already reconciles on a changing key signature (findings F-007), so this
   is wiring, not a rewrite.
3. **Filter wiring on added headers** — the overlay header map passes no
   `filterValue` / `onFilterChange` today; added columns need that.
4. **A column-chooser UI** — a modal of checkboxes over
   `fields.filter(isColumnCandidate)`. The analytics `MemberFieldPicker` is a
   near-perfect pattern to copy (grouped, bilingual, keyboard-accessible), but it
   is NOT imported by `MembersPage` today — so a copy, not a reuse.
5. **Render-path handling** — there are two separate paths (hardcoded default vs
   `contextColumns.map`); added columns must target the active one.
6. **`filterable_columns` exemption** — in a context that defines a filterable
   allow-list, an added key must be exempted or it won't get a filter input.
7. **Session state + tests** — session state is trivial local state; existing
   MembersPage / useFilterableTable / FilterableHeader / fieldValue tests must stay
   green and gain coverage for nested filter/sort.

**Rough size: ~2–4 focused days.** It touches shared table infrastructure, so it
carries more regression surface than the picker UI alone suggests.

### Strategic note

Fixing the nested filter/sort engine (item 1) pays down the existing F-003/F-005
defect **and** unlocks correct filter/sort for *every* column, not only added
ones — so part of this cost is debt paydown, not pure new-feature cost. Option 1,
by contrast, reads values only via `valueFor` to narrow rows and sidesteps the
flat-read filter/sort engines entirely, which is why it stays the genuine quick
win.

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
  the field they care about — budgeting ~2–4 days, since it requires making the
  filter/sort engine nested-aware (which also fixes the existing F-003/F-005
  defect), not just adding a column picker.
- Keep **Option 3** as the persistent/shareable reporting path, and separately
  resolve the open edit-from-row decision before changing that behaviour.

All three are complementary rather than mutually exclusive; the user confirmed
"all 3 are viable."
