# Implementation Plan — Member Overview User Column Chooser (Session Columns)

## Overview

Let a user surface any candidate member field as a column, then filter + sort on
it via the existing shared toolkit — by flattening the surfaced field on the fly
with `valueFor` and registering its key. The chosen columns are **persisted per
user** (mirroring the analytics preferred-list), with `member_number` always
shown first. Built from shared pieces (an extracted `FieldChecklist`, the
unchanged filter/sort hooks, a preferred-list-shaped DynamoDB record).

- Spec: `./requirements.md` (R1–R7), `./design.md` (C1–C8; all OQ resolved).
- Convention: each task is small, testable, leaves the app building; Requirement +
  Design refs in parentheses. Follow steering 32 (frontend), 33/34 (testing),
  35 (SAM module), 41 (shell/WSL). Touches the Members SAM plane (persistence) +
  frontend; no change to `GET /members` or row scope.
- Ordering: decisions → shared checklist extraction (keep MemberFieldPicker green)
  → pure helpers → persistence (mirror the preferred-list) → UI → wire filter/sort
  → verify.

## Task Dependency Graph

Waves run in order; tasks within a wave may proceed in parallel. A task's
`dependsOn` names the tasks that must complete first.

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": [
        { "id": "0.1", "dependsOn": [] }
      ]
    },
    {
      "wave": 2,
      "tasks": [
        { "id": "0.2", "dependsOn": ["0.1"] },
        { "id": "1.1", "dependsOn": ["0.1"] },
        { "id": "2.1", "dependsOn": ["0.1"] },
        { "id": "2.2", "dependsOn": ["0.1"] },
        { "id": "2.5.1", "dependsOn": ["0.1"] }
      ]
    },
    {
      "wave": 3,
      "tasks": [
        { "id": "1.2", "dependsOn": ["1.1"] },
        { "id": "2.5.2", "dependsOn": ["2.5.1"] }
      ]
    },
    {
      "wave": 4,
      "tasks": [
        { "id": "1.3", "dependsOn": ["1.2"] },
        { "id": "3.1", "dependsOn": ["1.1"] },
        { "id": "2.5.3", "dependsOn": ["2.5.2"] }
      ]
    },
    {
      "wave": 5,
      "tasks": [
        { "id": "3.2", "dependsOn": ["3.1"] },
        { "id": "2.5.4", "dependsOn": ["2.5.3"] }
      ]
    },
    {
      "wave": 6,
      "tasks": [
        { "id": "2.5.5", "dependsOn": ["2.5.4"] }
      ]
    },
    {
      "wave": 7,
      "tasks": [
        { "id": "4.1", "dependsOn": ["2.5.5", "3.1"] },
        { "id": "4.2", "dependsOn": ["2.1", "2.2", "3.1"] }
      ]
    },
    {
      "wave": 8,
      "tasks": [
        { "id": "4.3", "dependsOn": ["4.1", "4.2"] },
        { "id": "4.4", "dependsOn": ["4.2"] }
      ]
    },
    {
      "wave": 9,
      "tasks": [
        { "id": "5.1", "dependsOn": ["4.1", "4.2", "4.3", "4.4"] }
      ]
    },
    {
      "wave": 10,
      "tasks": [
        { "id": "5.2", "dependsOn": ["1.3", "2.5.5", "3.2", "5.1"] },
        { "id": "5.3", "dependsOn": ["5.2"] }
      ]
    }
  ]
}
```

Critical path: 0.1 → 1.1 → 1.2 → (persistence 2.5.1→2.5.5) → 4.1 → 4.2/4.3/4.4 →
5.1 → 5.2 → 5.3. The checklist (1.x), helpers (2.x), and persistence (2.5.x)
tracks are independent after 0.1 and can proceed in parallel.

## Tasks

### Phase 0 — Decisions + i18n

- [x] 0.1 Open questions resolved with the stakeholder: OQ-1 (one user-owned
  column set, retained across context switch), OQ-2 (full render-path
  unification), OQ-3 (ALL candidate fields selectable + filterable — core),
  OQ-A (first-time default = admin default/compact set + member_number). No open
  design questions remain.
  - _Requirements: R6.4 | Design: "Resolved decisions"_

- [ ] 0.2 Add bilingual (`nl`/`en`) i18n keys to the `members` namespace for the
  column chooser: button label ("Columns" / "Kolommen"), modal title, filter/empty
  text, "already shown" hint, add/remove affordance. No hardcoded English.
  - _Requirements: R1.5 | Design: C2_

### Phase 1 — Shared `FieldChecklist` (extract, no behaviour change)

- [ ] 1.1 Extract the checklist core from `MemberFieldPicker.tsx` into
  `frontend/src/components/members/FieldChecklist.tsx`: props `fields`,
  `selectedKeys`, `disabledKeys?`, `functionalGroups`, `lang`, `onToggle`. Reuse
  `sectionFields()` + `resolveLabel`; preserve per-field `data-testid`s.
  - _Requirements: R4.1 | Design: C1_

- [ ] 1.2 Refactor `MemberFieldPicker` to render its group/list checklists THROUGH
  `FieldChecklist` (output contract — `PivotConfig` — unchanged). Keep every
  existing `MemberFieldPicker.test.tsx` assertion green.
  - _Requirements: R4.1, R5.1 | Design: C1_

- [ ] 1.3 Unit-test `FieldChecklist`: functional-group sections in catalog order,
  alphabetical within; `disabledKeys` render checked + locked; `onToggle` fires the
  key; bilingual labels.
  - _Requirements: R1.1, R1.4, R5.2 | Design: C1_

### Phase 2 — Pure helpers

- [ ] 2.1 Add `coerceByType(field, value)` (co-located with `fieldValue.ts` or a
  new `columnValue.ts`): `number` → numeric, `date` → sortable form, else
  String-safe. Pure + unit-tested (incl. NaN / empty / bad-date fallbacks).
  - _Requirements: R2.3 | Design: C4_

- [ ] 2.2 Add a `FLAT_ALIASES` constant (the keys `flattenMember` already promotes:
  `member_number, name, email, status, membership_type, region, membership_id`) and
  a helper to exclude them from flattening. Unit-test the exclusion.
  - _Requirements: R3.4 | Design: C4_

### Phase 2.5 — Persistence (SAM, mirror the preferred-list)

- [ ] 2.5.1 Add `sam/members/domain/column_preferences.py` — a `ColumnPreferences`
  frozen dataclass `{ tenant_id, sub, columns, updated_at }` with `validate` /
  `to_item` / `from_item`, modeled 1:1 on `preferred_list.py` (`columns` ↔ `refs`:
  ordered non-blank strings, SHAPE-only validation). Add error codes mirroring
  `PREF_LIST_*`. Unit-test like the preferred-list entity.
  - _Requirements: R6.1, R6.6, R4.5 | Design: C7_

- [ ] 2.5.2 Add to `table_design.py`: `RECORD_TYPE_COLUMN_PREFS = "colprefs"`,
  `column_prefs_sk(sub)` → `colprefs#<sub>`, and `build_column_prefs_item`
  (modeled on `pref_list_sk` / `build_pref_list_item`). Unit-test key + item build.
  - _Requirements: R6.2 | Design: C7_

- [ ] 2.5.3 Add `get_column_preferences` / `save_column_preferences` to
  `members_repository.py` (copies of the preferred-list get/save: tenant-match
  guard, full replace, validate-before-persist). Repository tests mirror the
  preferred-list repo tests.
  - _Requirements: R6.5 | Design: C7_

- [ ] 2.5.4 Add the domain CRUD + `GET /members/column-preferences` (members:read)
  and `PUT /members/column-preferences` (members:write OR members:export) to the
  handler/routes, keyed by the verified `sub` at the edge (NOT a path param),
  declared with the literal path so no `{id}` shadows it. The PUT drops
  blank/dupe/non-candidate keys. Route tests mirror the preferred-list route tests
  (gating, sub-from-edge, empty-when-unset, cross-tenant/cross-user isolation).
  - _Requirements: R6.3, R6.4, R6.5, R6.7, R5.3, R5.4 | Design: C7_

- [ ] 2.5.5 Add `getColumnPreferences()` / `saveColumnPreferences(columns)` +
  a `MemberColumnPreferences` type to `membersApiService.ts`, modeled on
  `getPreferredList` / `savePreferredList`. Service tests (envelope unwrap,
  `columns` mapping, empty default).
  - _Requirements: R6.1, R6.4, R4.5, R5.2 | Design: C7_

### Phase 3 — `ColumnChooser` modal

- [ ] 3.1 Build `frontend/src/components/members/ColumnChooser.tsx`: a Chakra modal
  over `fields.filter(isColumnCandidate)` via `FieldChecklist`, with `selectedKeys`
  = the currently-shown columns (checked) and every other candidate unchecked;
  checking/unchecking adds/removes a column (user's selection fully determines the
  shown set). `member_number` is the only `disabledKeys` entry — always-on, not
  toggleable (R7.2). Emits the ordered chosen-key `string[]`. Keyboard accessible.
  - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.5, R7.2 | Design: C2_

- [ ] 3.2 Component-test `ColumnChooser`: lists candidates, excludes/locks
  already-present, add + remove emit the expected key set, nothing persisted.
  - _Requirements: R1.2, R1.3, R3.1, R5.2 | Design: C2_

### Phase 4 — Wire into `MembersPage`

- [ ] 4.1 Add chosen-column state (`string[]`) + a toolbar button opening
  `ColumnChooser`. On mount (after the field config resolves) seed it from
  `getColumnPreferences()`, skipping dangling keys + `member_number`; empty for a
  first-time user. On a chooser change, update local state AND persist the full
  list via `saveColumnPreferences()` (optimistic; failed save → non-blocking toast,
  keep local change).
  - _Requirements: R3.1, R3.2, R6.4, R6.5, C8 | Design: C8_

- [ ] 4.2 Build the unified column model (C3 — full unification, OQ-2 resolved):
  `columns = [member_number] ⊕ chosenColumns`, where `chosenColumns` is the user's
  saved list (or the admin default/compact set for a first-time user, OQ-A),
  resolved to candidates, de-duped, excluding member_number + flat aliases.
  Replace BOTH legacy render paths with a single header map + cell map;
  member_number always leads and is never removable (R7.1). Every column gets
  identical `FilterableHeader` wiring.
  - _Requirements: R1.2, R1.3, R4.4, R7.1, R7.3 | Design: C3_

- [ ] 4.3 Add the on-the-fly flatten memo (C4): promote chosen non-alias keys to
  flat top-level values via `coerceByType(f, valueFor(row, f.group, f.key))`;
  compose with the Option-1 search (search first, then flatten survivors). Feed the
  result to `useFilterableTable`.
  - _Requirements: R2.2, R2.3, R2.5, R3.4 | Design: C4_

- [ ] 4.4 Extend the filter key set handed to `useFilterableTable` with the chosen
  keys (empty values); rely on the F-007 reconcile. Exempt chosen keys from a
  context `filterable_columns` allow-list (C6).
  - _Requirements: R2.1, R2.4, R4.3 | Design: C5, C6_

### Phase 5 — Tests + verification

- [ ] 5.1 Extend `MembersPage.test.tsx`: surface a NESTED field → its filter
  narrows by the resolved value; sort is type-correct (number + date fixtures);
  AND-compose with a column filter and with the global search; no flat-alias
  collision; member_number always first + not removable; the OQ-1 context-switch
  rule; the persistence round-trip (mock `getColumnPreferences` seeds columns on
  load; a chooser change calls `saveColumnPreferences` with the full list);
  empty-default + dangling-key-skip.
  - _Requirements: R2.2, R2.3, R2.4, R3.3, R3.4, R6.4, R6.5, R7.1, R5.2 | Design: C3, C4, C6, C8_

- [ ] 5.2 Run the full affected suites green: MembersPage, useFilterableTable,
  useColumnFilters, FilterableHeader, fieldValue, MemberFieldPicker (frontend) +
  the new SAM `column_preferences` entity / repository / route suites and the
  preferred-list suites (regression). Fix any regression (esp. the
  MemberFieldPicker extraction).
  - _Requirements: R5.1, R5.3 | Design: C1, C7_

- [ ] 5.3 `tsc --noEmit` clean + SAM test suite green; grep for hardcoded English
  in the new components; confirm tenant isolation + `sub`-from-edge on the new
  routes; no change to `GET /members` / row scope. Clean up any scratch output.
  - _Requirements: R5.3, R5.4 | Design: C7_

## Notes

- **Deploys to two planes now:** the frontend (via `npm start` / frontend deploy)
  AND the Members SAM module (the new `column-preferences` entity + routes deploy
  with the Members Lambda — a push to `test` that touches `sam/` triggers the SAM
  deploy, unlike the pure-frontend Option 1).
- Builds additively on the already-shipped Option 1 global search; the two compose.
- The persistence is a deliberate MIRROR of the analytics preferred-list — reuse
  its code as the template at every layer rather than inventing a new store.
- OQ-2 is resolved to FULL unification: task 4.2 replaces both legacy render paths
  with one column model (the larger diff on the busiest member screen, carried by
  the existing MembersPage tests). No append-only fallback.
