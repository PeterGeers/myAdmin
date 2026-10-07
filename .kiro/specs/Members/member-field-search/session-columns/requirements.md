# Requirements Document

## Member Overview — User Column Chooser (Session Columns)

- Status: **Ready** (requirements + design + tasks complete; all open questions
  resolved with the stakeholder — see Design "Resolved decisions").
- Origin: `.kiro/specs/Members/member-field-search/design-options.md` → **Option 2**
  (promoted to a proper spec). Option 1 (global all-fields search) is already built
  (commit on `test`); this is the precise, per-field complement.
- Scope note: originally framed as frontend-only (session columns). Extended at the
  stakeholder's request to **persist the chosen columns per user**, mirroring the
  analytics preferred-list — so this now also touches the Members SAM module
  (DynamoDB) + the `membersApiService` CRUD. See R6/R7 and Design C7/C8.
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
- **Persistence precedent to MIRROR (per-user, tenant-scoped, DynamoDB):** the
  analytics preferred-list.
  - Entity: `sam/members/domain/preferred_list.py` (`PreferredList` — frozen
    dataclass `{ tenant_id, sub, refs, updated_at }`, `validate` / `to_item` /
    `from_item`, keyed by Cognito `sub`, user ≠ member R11.1).
  - Storage: `sam/members/repository/table_design.py` (`pref_list_sk(sub)` →
    `preflist#<sub>`, `build_pref_list_item`) + `members_repository.py`
    (`get_preferred_list` / `save_preferred_list`).
  - Routes: `sam/members/handler/routes.py` — `GET /members/analytics-sets/preferred`
    (members:read) + `PUT …/preferred` (members:write OR members:export), keyed by
    the verified `sub` at the edge, NOT a path param.
  - Client: `frontend/src/services/membersApiService.ts` `getPreferredList` /
    `savePreferredList` (`{ sub, refs, updated_at }`, `{ data }` envelope).

### The core technical fact driving these requirements

A field is filterable + sortable on the overview **iff it is a flat top-level key
on the row**. `flattenMember` flattens only the six aliases above. A surfaced
overlay / calculated field lives nested (`membership.*`, `overlay.*`), so without
flattening it would (1) render no filter input and (2) no-op even if wired. The
proven fix is to flatten the surfaced field on the fly via `valueFor` (exactly
what the pivot adapter does for its results), then register its key.

---

## Requirements

### R1 — Choose which columns to show (ALL candidate fields are selectable)

**User story:** As a member administrator, I want to pick exactly which member
fields are shown as columns — adding any field the default view omits and
removing ones I don't need — so the overview matches how I work, without an admin
changing the view configuration.

#### Acceptance Criteria
1. WHEN the user opens the column chooser THEN the system SHALL list **every**
   candidate field (`fields.filter(isColumnCandidate)`) as a selectable option —
   fixed, overlay, and calculated alike (OQ-3: all columns are selectable is a
   core requirement) — grouped by functional group in catalog order and
   alphabetical within each group (reusing the `MemberFieldPicker` sectioning),
   with bilingual labels.
2. WHEN the chooser opens THEN the currently-shown columns SHALL be flagged
   (checked); every other candidate SHALL be unchecked. member_number is shown
   always-on and NOT toggleable (R7).
3. WHEN the user checks a field THEN it SHALL be added as a column; WHEN the user
   unchecks a currently-shown field THEN it SHALL be removed — the user's
   selection fully determines the shown columns (the only non-removable column is
   member_number). Columns are never duplicated.
4. The user's selection SHALL change the column view immediately (and be persisted
   per R6).
5. The chooser SHALL be keyboard-accessible and resolve all labels from the
   `members` i18n namespace (no hardcoded English).

### R2 — Surfaced columns are filterable + sortable (the real work)

**User story:** As a member administrator, once I surface a field I want to filter
and sort on it just like the built-in columns.

#### Acceptance Criteria
1. EVERY shown column (fixed, overlay, calculated, user-chosen) SHALL render a
   filter input AND be sortable — there SHALL be no display-only column class
   (OQ-3). A newly chosen column SHALL be filterable/sortable identically to a
   fixed one.
2. WHEN the user types in a column's filter THEN the rows SHALL narrow by
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

### R3 — Per-user, non-destructive

**User story:** As a user, my chosen columns should be mine and never alter what
other users or the admin configuration see.

#### Acceptance Criteria
1. The surfaced-column set SHALL be the calling user's own working set, applied as
   client state in-session and persisted per user (R6); it SHALL default to empty
   (no surfaced columns) for a user who has never chosen any.
2. Surfacing columns SHALL NOT modify `view_contexts` or any tenant parameter, and
   SHALL NOT be visible to any other user (private to the owning `sub`).
3. There SHALL be ONE user-owned column set. The chooser shows the current columns
   with the already-shown ones checked; the user checks/unchecks to change their
   view. WHEN the user switches view context THEN their chosen columns SHALL be
   **retained** (the context no longer drives the column set once a user has their
   own list; it still drives `default_sort` / `filterable_columns` / `page_size`).
4. A surfaced column's key SHALL NOT collide with or overwrite an existing flat
   alias (`membership_type`, `region`, …); only non-flat keys are promoted.

### R6 — Persist the chosen columns per user (mirrors the preferred-list)

**User story:** As a member administrator, I want the columns I add to be
remembered the next time I open the overview, so I do not re-pick them every
session — exactly like my preferred pivot list.

#### Acceptance Criteria
1. The system SHALL persist each user's chosen columns as a PRIVATE, per-user,
   tenant-scoped record keyed by the authenticated Cognito `sub` (user ≠ member,
   R11.1) — one record per user — storing an **ordered list of field keys**,
   mirroring the preferred-list entity (`refs` → `columns`).
2. The record SHALL be stored on the Members module's own DynamoDB plane
   (a new sort key `colprefs#<sub>` in the tenant partition), NOT in any tenant
   config and NOT in a view context.
3. The system SHALL expose a `GET` (members:read) + `PUT` (members:write OR
   members:export) route pair keyed by the verified `sub` at the edge — never a
   client-supplied sub or path param — mirroring
   `GET/PUT /members/analytics-sets/preferred`. Proposed path:
   `GET/PUT /members/column-preferences`.
4. WHEN a user has never saved column preferences THEN the GET SHALL return an
   empty set (empty is valid, not an error — mirrors R11.2), and the overview
   SHALL show the first-time default: the admin default/compact set + the fixed
   member_number (OQ-A resolved to option (a)).
5. WHEN the user adds/removes a column THEN the system SHALL persist the full
   updated ordered list (a replace, exactly one record per user), stamping
   `updated_at`; the write SHALL drop blank/duplicate keys and keys that are not
   candidate fields, defensively.
6. The persisted list SHALL store **field keys only** (references into the field
   config), never copies of field metadata or member data — mirroring the
   preferred-list's reference-not-copy rule; a stored key that no longer resolves
   (field removed / hidden) SHALL be skipped on read, never an error.
7. Persistence SHALL NOT widen scope: it stores which columns to show, never any
   row data; row scope stays server-enforced on `GET /members`.

### R7 — member_number is an always-present fixed column

**User story:** As a user, whatever columns I choose, I always want the member
number present so every row is identifiable.

#### Acceptance Criteria
1. The `member_number` column SHALL always be shown as the leading column,
   regardless of the user's chosen columns or the selected view context.
2. The column chooser SHALL present `member_number` as always-on (not removable);
   it SHALL NOT appear as a toggleable candidate the user can uncheck.
3. The persisted column list SHALL NOT need to include `member_number` (it is
   implied); if a stored list omits or includes it, the overview SHALL still render
   it exactly once, first.

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
5. The persistence (R6) SHALL be built by MIRRORING the preferred-list end to end
   — a `ColumnPreferences` entity + `to_item`/`from_item` modeled on
   `PreferredList`, a `colprefs#<sub>` sort key + item builder modeled on
   `pref_list_sk` / `build_pref_list_item`, repository `get/save` methods, a
   route pair modeled on the preferred-list routes, and `getColumnPreferences` /
   `saveColumnPreferences` client wrappers modeled on `getPreferredList` /
   `savePreferredList`. No new storage pattern is invented.
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
   alias; member_number always present + not removable (R7); AND-composition with
   a column filter and with the global search; the persistence round-trip
   (save → reload → same columns) and the empty-default + dangling-key-skip cases.
3. The persistence SHALL have SAM unit tests mirroring the preferred-list suites
   (entity validation, `to_item`/`from_item`, repository get/save, route
   gating + sub-from-edge) and the client wrappers SHALL have service tests.
4. `tsc --noEmit` + the SAM test suite SHALL pass; no new hardcoded English;
   tenant isolation + `sub`-from-edge preserved (no cross-tenant / cross-user
   read or write).

---

## Out of scope

- Sharing a column set between users or promoting one to a tenant view context
  (a user's columns are private; authoring shared contexts stays the admin's
  config path).
- Per-column width / ordering-by-drag persistence beyond the stored key order.
- Server-side search / column projection for very large row sets (client-side over
  the scoped subset only).
- Edit-from-column or any mutation of member data from the overview.
