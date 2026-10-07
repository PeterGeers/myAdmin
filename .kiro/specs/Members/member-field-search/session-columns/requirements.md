# Requirements Document

## Member Overview — User Column Chooser (Session Columns)

- Status: **Draft** (requirements phase — check in before design).
- Origin: `.kiro/specs/Members/member-field-search/design-options.md` → **Option 2**
  (promoted to a proper spec). Option 1 (global all-fields search) is already built
  (commit on `test`); this is the precise, per-field complement.
- Parent / reuse (do NOT rebuild): the Members overview as built in
  `.kiro/specs/Members/s5c-members-runnable-in-spa/` (its C-FIELDS / C-VIEW /
  C-SURFACE field + view-context model) and the Member Analytics spec
  (`.kiro/specs/Members/member-analytics/`) whose `MemberFieldPicker` is the
  checklist pattern this spec extracts from.
- Governing steering: `20-platform-architecture`, `32-frontend-ui`,
  `33/34` (testing), `40-spec-workflow`, `41-shell-environment`.

### Problem

The Members overview (`frontend/src/pages/MembersPage.tsx`) shows a compact,
admin-defined column set. A member record has many more fields — overlay
(parameter-driven) and calculated fields. Today a user who wants to see, filter,
or sort by one of those non-default fields has no way to surface it for their own
session: the column set is driven purely by the selected view context (admin
config), and surfaced overlay columns are not even filterable.

We want to let a user **temporarily add any candidate field as a column for their
own session**, after which they can filter and sort on it exactly like the fixed
columns, without changing the admin-authored view contexts.

### Grounding code (verified this session; cited throughout)

- Render + column assembly: `frontend/src/pages/MembersPage.tsx` — two render
  paths (`hasExplicitColumns`): a hand-written default (fixed `COMPACT_FIELD_KEYS`
  + `region` + `overlayColumns.map`) and a uniform `contextColumns.map`;
  `isFilterable()` gated by `selectedContext.filterable_columns`.
- Flat aliases: `flattenMember` in `frontend/src/services/membersApiService.ts`
  promotes exactly `member_number, name, email, status, membership_type, region`
  (+ `membership_id`) to flat top-level keys — the reason those columns filter.
- Value resolution: `frontend/src/components/members/fieldValue.ts` —
  `isColumnCandidate(field)` (`visible !== false`), `valueFor(row, group, key)`
  (nested-first), `renderFieldValue(field, value, lang)`.
- Filter/sort engine: `frontend/src/hooks/useFilterableTable.ts` →
  `useColumnFilters.ts` (flat `row[key]` match, `applyFilters` short-circuits
  `!(key in row) → pass`; key-set reconcile on signature, findings F-007) +
  `useTableSort`.
- Checklist pattern to extract from:
  `frontend/src/components/members/analytics/MemberFieldPicker.tsx`
  (`pickableFields`, `sectionFields` — functional-group sections, alpha within).
- Field catalog: `GET /members/field-config` → `FieldConfig` (`fields`,
  `functional_groups`, `view_contexts`); `FieldConfigField` carries `key`,
  `group`, `label`, `type`, `order`, `visible`, `functional_group`.

### The core technical fact driving these requirements

A field is filterable + sortable on the overview **iff it is a flat top-level key
on the row**. `flattenMember` flattens only the six aliases above. A surfaced
overlay / calculated field lives nested (`membership.*`, `overlay.*`), so without
flattening it would (1) render no filter input and (2) no-op even if wired. The
proven fix is to flatten the surfaced field on the fly via `valueFor` (exactly
what the pivot adapter does for its results), then register its key.

---

## Requirements

### R1 — Surface any candidate field as a session column

**User story:** As a member administrator, I want to add any available member
field as a column to the overview table for my current session, so I can see data
that the default columns omit without an admin changing the view configuration.

#### Acceptance Criteria
1. WHEN the user opens the column chooser THEN the system SHALL list every
   candidate field (`fields.filter(isColumnCandidate)`), grouped by functional
   group in catalog order and alphabetical within each group (reusing the
   `MemberFieldPicker` sectioning), with bilingual labels.
2. WHEN the user checks a field that is not already a column THEN the system SHALL
   add it as a visible column for the session.
3. WHEN the user unchecks a surfaced field THEN the system SHALL remove that
   column; fields that belong to the active view context / default set SHALL NOT
   be removable via this chooser (it only adds, never strips admin columns).
4. WHEN the chooser lists fields THEN fields already shown (default/context
   columns) SHALL be indicated as already-present (checked + not re-addable),
   never duplicated.
5. The chooser SHALL be keyboard-accessible and resolve all labels from the
   `members` i18n namespace (no hardcoded English).

### R2 — Surfaced columns are filterable + sortable (the real work)

**User story:** As a member administrator, once I surface a field I want to filter
and sort on it just like the built-in columns.

#### Acceptance Criteria
1. WHEN a session column is surfaced THEN its header SHALL render a filter input
   AND be sortable, identical to a fixed column.
2. WHEN the user types in a surfaced column's filter THEN the rows SHALL narrow by
   that field's **resolved** value (nested-aware via `valueFor`), case-insensitive
   substring — including for fields stored in nested buckets.
3. WHEN the user sorts on a surfaced column THEN the ordering SHALL use the field's
   resolved value, coerced by the field's `type` (number → numeric order, date →
   chronological order), not a lexical string sort.
4. The surfaced-column filter/sort SHALL compose (AND) with existing column
   filters, the global search (Option 1), and the current sort.
5. Surfacing a field SHALL be presentation-only and SHALL NOT widen data scope —
   it only adds a column over the already scope-authorized rows (row scope stays
   server-enforced).

### R3 — Session-scoped, non-persistent, non-destructive

**User story:** As a user, my temporary columns should be mine for this session
and never alter what other users or the admin configuration see.

#### Acceptance Criteria
1. The surfaced-column set SHALL be local session state (no backend write, no
   persisted config); it resets on reload.
2. Surfacing columns SHALL NOT modify `view_contexts` or any tenant parameter.
3. WHEN the user switches view context THEN the system SHALL apply a documented,
   consistent rule for surfaced columns (see Design open-question OQ-1) — either
   cleared or retained — chosen deliberately, not incidentally.
4. A surfaced column's key SHALL NOT collide with or overwrite an existing flat
   alias (`membership_type`, `region`, …); only non-flat keys are promoted.

### R4 — Reuse, not rebuild (shared components)

**User story:** As a maintainer, I want this built from shared pieces so the
pivot picker and the overview do not drift into two near-identical widgets.

#### Acceptance Criteria
1. The field checklist SHALL be a **shared** component (extracted from
   `MemberFieldPicker`'s checklist core — `FieldChecklist`) consumed by both the
   pivot picker and the column chooser; the two differ only in output contract
   (`PivotConfig` vs `string[]` of keys).
2. The on-the-fly flatten SHALL reuse the existing `valueFor` / `groupForKey`;
   it SHALL NOT fork a second value-resolution path.
3. The filter/sort SHALL reuse the existing `useFilterableTable` /
   `useColumnFilters` / `useTableSort` / `FilterableHeader` with no change to
   their public contract (the F-007 key-set reconcile already supports a dynamic
   key set).
4. The two overview render paths SHOULD be unified into a single column model so
   fixed / context / session columns flow through identical wiring (see Design
   C3); IF unification is deferred, session columns SHALL still land correctly in
   whichever path is active, with the trade-off documented.

### R5 — Quality bar

#### Acceptance Criteria
1. The change SHALL keep the existing MembersPage / useFilterableTable /
   useColumnFilters / FilterableHeader / fieldValue / MemberFieldPicker test
   suites green.
2. New tests SHALL cover: surfacing a nested field makes it filter + sort
   correctly; type-coerced sort (number/date); no key collision with a flat
   alias; session-only (not persisted); AND-composition with a column filter and
   with the global search.
3. `tsc --noEmit` SHALL pass; no new hardcoded English; frontend-only (no backend
   or SAM change).

---

## Out of scope

- Persisting a user's chosen columns across sessions (would need a per-user store;
  a separate follow-up — the preferred-list DynamoDB store is the nearest
  precedent but is a different concept).
- Fixing nested filter/sort for **all** overlay columns globally (the same
  technique can later be generalized; this spec scopes it to user-surfaced
  columns — see Design "Strategic note").
- Server-side search / column projection for very large row sets (client-side over
  the scoped subset only).
- Edit-from-column or any mutation of member data from the overview.
