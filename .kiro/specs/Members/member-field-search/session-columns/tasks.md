# Implementation Plan — Member Overview User Column Chooser (Session Columns)

## Overview

Let a user temporarily surface any candidate member field as a column, then
filter + sort on it via the existing shared toolkit — by flattening the surfaced
field on the fly with `valueFor` and registering its key. Built from shared
pieces (a extracted `FieldChecklist`, the unchanged filter/sort hooks).

- Spec: `./requirements.md` (R1–R5), `./design.md` (C1–C6 + OQ-1..3).
- Convention: each task is small, testable, leaves the app building; Requirement +
  Design refs in parentheses. Follow steering 32 (frontend), 33/34 (testing),
  41 (shell/WSL). Frontend-only — no backend/SAM change.
- Ordering: resolve the open questions, extract the shared checklist with NO
  behaviour change (keep MemberFieldPicker green), build the pure helpers, then the
  UI, then wire filter/sort, then verify.

## Tasks

### Phase 0 — Decisions + i18n

- [ ] 0.1 Resolve design open questions with the stakeholder: OQ-1 (context-switch
  retain vs clear), OQ-2 (full render-path unification vs append-only fallback),
  OQ-3 (generalize to all overlay columns — default: no, scope to surfaced).
  Record the decisions in this spec before coding.
  - _Requirements: R3.3, R4.4 | Design: OQ-1, OQ-2, OQ-3_

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

### Phase 3 — `ColumnChooser` modal

- [ ] 3.1 Build `frontend/src/components/members/ColumnChooser.tsx`: a Chakra modal
  over `fields.filter(isColumnCandidate)` via `FieldChecklist`, with
  `disabledKeys` = already-shown columns and `selectedKeys` = session columns;
  emits the ordered surfaced-key `string[]`. Keyboard accessible.
  - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.5 | Design: C2_

- [ ] 3.2 Component-test `ColumnChooser`: lists candidates, excludes/locks
  already-present, add + remove emit the expected key set, nothing persisted.
  - _Requirements: R1.2, R1.3, R3.1, R5.2 | Design: C2_

### Phase 4 — Wire into `MembersPage`

- [ ] 4.1 Add session-column state (`string[]`) + a toolbar button opening
  `ColumnChooser`. Local state only; resets on reload (no persistence).
  - _Requirements: R3.1, R3.2 | Design: C2, C3_

- [ ] 4.2 Build the unified column model (C3): `columns = base/context ⊕ session`,
  excluding duplicates + flat aliases, rendered by a single header map + cell map
  (or, per OQ-2, the append-only fallback). Every column gets identical
  `FilterableHeader` wiring.
  - _Requirements: R1.2, R1.3, R4.4 | Design: C3_

- [ ] 4.3 Add the on-the-fly flatten memo (C4): promote surfaced non-alias keys to
  flat top-level values via `coerceByType(f, valueFor(row, f.group, f.key))`;
  compose with the Option-1 search (search first, then flatten survivors). Feed the
  result to `useFilterableTable`.
  - _Requirements: R2.2, R2.3, R2.5, R3.4 | Design: C4_

- [ ] 4.4 Extend the filter key set handed to `useFilterableTable` with the
  surfaced keys (empty values); rely on the F-007 reconcile. Exempt surfaced keys
  from a context `filterable_columns` allow-list (C6).
  - _Requirements: R2.1, R2.4, R4.3 | Design: C5, C6_

### Phase 5 — Tests + verification

- [ ] 5.1 Extend `MembersPage.test.tsx`: surface a NESTED field → its filter
  narrows by the resolved value; sort is type-correct (number + date fixtures);
  AND-compose with a column filter and with the global search; no flat-alias
  collision; session-only across a remount; the OQ-1 context-switch rule.
  - _Requirements: R2.2, R2.3, R2.4, R3.3, R3.4, R5.2 | Design: C3, C4, C6_

- [ ] 5.2 Run the full affected suites green: MembersPage, useFilterableTable,
  useColumnFilters, FilterableHeader, fieldValue, MemberFieldPicker. Fix any
  regression (esp. the MemberFieldPicker extraction).
  - _Requirements: R5.1 | Design: C1_

- [ ] 5.3 `tsc --noEmit` clean; grep for hardcoded English in the new components;
  confirm frontend-only (no backend/SAM diff). Clean up any scratch output.
  - _Requirements: R5.3_

## Notes

- Depends on nothing server-side; ships via `npm start` / frontend deploy, not SAM.
- Builds additively on the already-shipped Option 1 global search; the two compose.
- If OQ-2 chooses the append-only fallback, task 4.2 shrinks but leaves the two
  render paths — record that trade-off in `findings.md` and keep the full
  unification as a follow-up.
