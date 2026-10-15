# Implementation Plan: Member Analytics Pivot Filter Operators & Grouped Field Selectors

## Overview

Frontend-first, TypeScript. Build the shared types and pure helpers first (data contract + engine + normalization), then the shared `GroupedFieldSelect`, then wire both into `MemberFieldPicker`, add i18n, update the paired tests, and verify the SAM `definition` round-trip is opaque (no backend change). Each task builds on the previous and ends wired into the picker. Property tests use `fast-check`; test sub-tasks are optional (`*`). Honor the change-with-tests contract: update each paired test to the new behavior in the SAME change, keeping it green.

## Tasks

- [x] 1. Define the filter data contract and type→operator mapping
  - [x] 1.1 Add `FilterOperator`, `FilterClause`, and `FilterMap` to `frontend/src/types/pivot.ts`; keep `PivotConfig.filters` as `Record<string, any>` and document that member analytics treats it as `FilterMap`
    - Add `normalizeClause(raw: unknown): FilterClause | null` (legacy scalar → `{op:'eq'}`, unknown op → `eq`, null/undefined → null)
    - _Requirements: 8.1, 8.3_
  - [x] 1.2 Add `operatorsForField(field, fieldConfig)` and `operatorTakesNoValue(op)` as pure helpers (type→operator mapping per the design table); the text set includes `contains, notContains, regex, notRegex`; `notContains`/`notRegex` are value-taking (not in `operatorTakesNoValue`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 1.3 Write property test for the operator mapping
    - **Property 11: Operator availability by field type**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 2. Implement operator-aware `applyDefinitionFilters`
  - [x] 2.1 Rewrite `applyDefinitionFilters` in `analyticsConfig.ts` to normalize each entry via `normalizeClause`, build active clauses (type + storage group), and match per operator (eq/ne/contains/notContains/typed-ordering/regex/notRegex/empty/notEmpty), with `tryCompileRegex` guard shared by `regex` and `notRegex` (invalid pattern → never-match sentinel for BOTH forms), blank-value skip, absent-cell excluded for value-taking ops, AND semantics, order-preserving and pure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.5, 7.6, 8.1, 8.3_
  - [x] 2.2 Update + extend the paired engine test `frontend/src/__tests__/analyticsConfig.test.ts` (eq cases stay green; add operator cases)
    - Keep every existing eq assertion; add legacy-scalar-as-eq, ne, contains, notContains, numeric/date ordering, string fallback, empty/notEmpty, AND, invalid-regex no-match (regex AND notRegex), notRegex valid-pattern exclusion, blank-value no-narrow, absent-cell excluded for notContains/notRegex, non-array rows
    - _Requirements: 5.1, 5.3, 5.12, 5.13, 6.2, 6.4, 7.5, 7.6, 8.1_
  - [x] 2.3 Write property test — eq/ne semantics
    - **Property 1: eq / ne semantics preserved**
    - **Validates: Requirements 5.1, 5.2**
  - [x] 2.4 Write property test — contains substring
    - **Property 2: contains is case-insensitive substring**
    - **Validates: Requirements 5.3**
  - [x] 2.4a Write property test — notContains complement of contains
    - **Property 15: notContains is the exact complement of contains for present values**
    - **Validates: Requirements 5.12, 5.13**
  - [x] 2.5 Write property test — typed ordering
    - **Property 3: Typed ordering comparison**
    - **Validates: Requirements 5.4, 5.5, 5.6**
  - [x] 2.6 Write property test — empty/notEmpty presence partition
    - **Property 4: empty / notEmpty partition rows by presence**
    - **Validates: Requirements 4.1, 5.7, 5.8**
  - [x] 2.7 Write property test — AND across clauses
    - **Property 5: AND across clauses**
    - **Validates: Requirements 5.9**
  - [x] 2.8 Write property test — blank value never narrows
    - **Property 6: Blank value never narrows**
    - **Validates: Requirements 6.1, 6.3**
  - [x] 2.9 Write property test — regex totality
    - **Property 7: Regex is total (valid matches; invalid matches nothing, never throws)**
    - **Validates: Requirements 7.1, 7.2**
  - [x] 2.9a Write property test — notRegex totality
    - **Property 16: notRegex is total (valid is complement of regex for present values; invalid matches nothing, never throws)**
    - **Validates: Requirements 7.5, 7.6**
  - [x] 2.10 Write property test — unknown operator clamps to eq
    - **Property 10: Unknown operator clamps to eq**
    - **Validates: Requirements 8.3**
  - [x] 2.11 Write property test — engine purity and order
    - **Property 13: Engine is pure and order-preserving**
    - **Validates: Requirements 5.10, 5.11, 6.4, 11.4**

- [x] 3. Checkpoint — ensure all engine/type tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update the picker helpers for operators (round-trip + legacy read)
  - [x] 4.1 Extend `FilterDraft` with `op`, and rewrite `toFilterDrafts`/`fromFilterDrafts` in `memberFieldPicker.helpers.ts` to read legacy scalar + object clauses for EVERY key (remove the `RESERVED_FILTER_KEYS` concept entirely — delete the export and stop skipping `years_member` / `joined_after_year`; a legacy scalar `years_member: 25` reads as an editable `eq` row), emit the object form (value only for value-taking ops — including `notContains`/`notRegex`), drop blank rows (a blank-value `notContains`/`notRegex` row drops like `contains`/`regex`), keep valueless empty/notEmpty rows; remove the reserved-key carry from `fromFilterDrafts` and drop its now-unused `base` parameter (its only reason was reserved-key carry) so the composed map is built purely from the editor rows
    - _Requirements: 8.2, 8.4, 8.5, 8.6, 8.9_
  - [x] 4.2 Write unit tests for the helpers (co-located) — FLIP any reserved-key assertion to the new behavior
    - Legacy scalar → op eq row; object clause read; a legacy scalar `years_member: 25` reads as an editable `eq` row (NOT skipped/carried — assert it IS an ordinary editable row and composes generically); blank-row drop; empty/notEmpty valueless keep
    - _Requirements: 8.2, 8.5, 8.9_
  - [x] 4.3 Write property test — filter round-trip
    - **Property 9: Filter round-trip preserves field/op/value**
    - **Validates: Requirements 8.4, 8.5, 8.6, 8.7**
  - [x] 4.4 Write property test — legacy scalar equivalence
    - **Property 8: Legacy scalar is equivalent to object-eq (backward compatibility)**
    - **Validates: Requirements 8.1, 8.2, 8.8**

- [x] 5. Build the shared `GroupedFieldSelect` control
  - [x] 5.1 Create `frontend/src/components/members/GroupedFieldSelect.tsx` — a dark-theme Chakra `Select` rendering `<optgroup>`s from `sectionFields()` (imported from `FieldChecklist`), bilingual labels via `resolveLabel`, placeholder option, `aria-label`, ungrouped fallback
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 11.5_
  - [x] 5.2 Write unit tests for `GroupedFieldSelect`
    - Placeholder first/empty value; aria-label present; onChange key/''; bilingual label; ungrouped fallback renders no-group fields
    - _Requirements: 1.3, 1.4, 1.5, 1.6_
  - [x] 5.3 Write property test — grouping mirrors the checklist
    - **Property 12: GroupedFieldSelect grouping mirrors the checklist**
    - **Validates: Requirements 1.1, 1.2, 2.4**

- [x] 6. Add i18n keys (operators, invalid-pattern, hint) to nl + en members namespaces
  - [x] 6.1 Add `filterOperator`, `operators.*` (all twelve, incl. `operators.notContains` and `operators.notRegex` — nl: "bevat niet", "komt niet overeen met patroon"; en: "does not contain", "does not match pattern"), `filterRegexInvalid`, and update `filtersHint` under `analytics.pivotViews.fieldPicker.*` in both `frontend/src/locales/nl/members.json` and `frontend/src/locales/en/members.json`
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 7. Wire the new control and operators into `MemberFieldPicker`
  - [x] 7.1 Replace the measure-column flat `<Select>` with `GroupedFieldSelect` (placeholder = COUNT-all `''`)
    - _Requirements: 2.2, 2.3, 11.1_
  - [x] 7.2 Replace the filter-row field `<Select>` with `GroupedFieldSelect`, add the operator `<Select>` (from `operatorsForField`, text fields now including `notContains`/`notRegex`), hide the value `Input` for empty/notEmpty (shown for notContains/notRegex), default new rows to `eq`, reset operator to `eq` on incompatible field change, and show the inline `filterRegexInvalid` message on an invalid `regex` OR `notRegex` row
    - _Requirements: 2.1, 3.5, 3.6, 4.1, 4.2, 4.3, 7.3, 7.4, 7.7, 11.5_
  - [x] 7.3 Update `MemberFieldPicker.test.tsx` to the new filter-row shape and grouped selects (keep green) — FLIP the retired reserved-key case
    - Filter row = grouped field + operator + value; text operator list offers notContains/notRegex; value shown for notContains/notRegex and hidden for empty/notEmpty; operator reset on field-type change; invalid notRegex shows filterRegexInvalid; measure/filter selects are grouped; update existing eq assertions to the object shape
    - FLIP the existing case "a reserved year filter … must NOT appear as an editable row" (filters `{ clubblad: 'Papier', years_member: 25 }`): it MUST now assert `years_member` DOES appear as an editable `eq` filter row alongside `clubblad`
    - _Requirements: 2.1, 2.2, 3.3, 3.6, 4.1, 7.3, 7.7, 8.5, 8.9_

- [x] 8. Update the execute-path test and add legacy-compat coverage
  - [x] 8.1 Update the `MemberPivotViews.test.tsx` "applies a saved set's generic DEFINITION filter at execute (issue 3)" test to carry the new object form, and add a NEW case asserting a legacy scalar `{field:value}` set still runs as eq
    - _Requirements: 8.1, 8.8_

- [x] 9. Verify the SAM definition round-trip stays opaque (no backend change)
  - [x] 9.1 Add a Python domain test asserting `AnalyticsSetEntry.to_item`/`from_item` round-trips a `definition.filters` object-valued `{op,value}` entry unchanged, and that `validate` accepts it
    - **Property 14: SAM definition round-trip is opaque to filter shape**
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [x] 10. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP, but the change-with-tests contract means the paired-test updates (2.2, 7.3, 8.1) should ship with their behavior change.
- Each task references specific requirements for traceability.
- Property tests use `fast-check`, minimum 100 iterations, tagged `Feature: member-analytics-pivot-filter-operators, Property N: ...`.
- No backend/SAM source change is expected (task 9 verifies the definition stays opaque); the tenant key on the module plane is `tenant_id`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "5.1", "6.1"] },
    { "id": 1, "tasks": ["1.3", "2.1", "4.1", "5.2", "5.3"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.4a", "2.5", "2.6", "2.7", "2.8", "2.9", "2.9a", "2.10", "2.11", "4.2", "4.3", "4.4", "9.1"] },
    { "id": 3, "tasks": ["7.1", "7.2"] },
    { "id": 4, "tasks": ["7.3", "8.1"] }
  ]
}
```
