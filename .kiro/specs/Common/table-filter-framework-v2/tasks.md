# Implementation Plan: Table Filter Framework v2

## Overview

Phased implementation of the table filter framework v2: new hooks (`useColumnFilters`, `useTableSort`, `useFilterableTable`), `FilterableHeader` component, parameter-driven `useTableConfig` hook, and migration of 16 components across 6 phases. Foundation hooks and components are built and tested first, then used as building blocks for component migrations in priority order.

## Tasks

- [x] 1. Type definitions extension and foundation setup
  - [x] 1.1 Extend type definitions in `frontend/src/components/filters/types.ts`
    - Add `ColumnFilterState` type (`Record<string, string>`)
    - Add `SortDirection` type (`'asc' | 'desc'`)
    - Add `SortConfig` interface with `field` and `direction` properties
    - Add `FilterableHeaderProps` interface matching the component props from design §4
    - Add `UseColumnFiltersOptions` interface with optional `debounceMs`
    - Preserve all existing types — append new types at the end of the file
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 2. Implement useColumnFilters hook
  - [x] 2.1 Create `frontend/src/hooks/useColumnFilters.ts`
    - Accept generic `T extends Record<string, any>` data array and `Record<string, string>` initial filters
    - Return `filters`, `setFilter`, `resetFilters`, `filteredData`, `hasActiveFilters`
    - Implement debounce with configurable delay (default 150ms) using `setTimeout`/`clearTimeout`
    - Case-insensitive substring matching: `String(row[key]).toLowerCase().includes(filterValue.toLowerCase())`
    - Missing field keys on a row treat filter as passing (row not excluded)
    - `resetFilters` sets all values to `''` and returns full data array
    - `hasActiveFilters` is `true` when any filter value is non-empty
    - Import `UseColumnFiltersOptions` from `../components/filters/types`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 2.2 Write unit tests for useColumnFilters
    - Create `frontend/src/hooks/__tests__/useColumnFilters.test.ts`
    - Test: filtering by single field returns matching rows
    - Test: filtering by multiple fields simultaneously (AND logic)
    - Test: case-insensitive matching ("ABC" matches "abc")
    - Test: debounce behavior with jest fake timers (150ms default, custom delay)
    - Test: `resetFilters` clears all filters and returns full data
    - Test: missing field keys don't exclude rows
    - Test: empty data array returns empty result
    - Test: `hasActiveFilters` reflects filter state
    - _Requirements: 12.1_

  - [x] 2.3 Write property test for Filter Correctness (Property 1)
    - Create `frontend/src/hooks/__tests__/useColumnFilters.property.test.ts`
    - **Property 1: Filter Correctness** — For any data array and any set of column filter strings, filtered output contains exactly those rows where every active filter key either does not exist on the row or the row's field value (lowercase string) contains the filter value (lowercase substring)
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 1.4, 1.5**

  - [x] 2.4 Write property test for Filter Reset Round-Trip (Property 2)
    - In same file `frontend/src/hooks/__tests__/useColumnFilters.property.test.ts`
    - **Property 2: Filter Reset Round-Trip** — For any data array and any set of active filter values, calling `resetFilters` then reading `filteredData` returns array identical to original unfiltered data (same elements, same order)
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 1.6, 12.6**

- [x] 3. Implement useTableSort hook
  - [x] 3.1 Create `frontend/src/hooks/useTableSort.ts`
    - Accept generic `T extends Record<string, any>` data array, optional default sort field, optional default direction
    - Return `sortField`, `sortDirection`, `handleSort`, `sortedData`, `getSortIndicator`
    - `handleSort(field)`: same field toggles direction; different field sets new field with `'asc'`
    - `getSortIndicator(field)`: `'↑'` for asc, `'↓'` for desc when active, `''` otherwise
    - Sort strings case-insensitively via `localeCompare` with `{ sensitivity: 'base' }`
    - Sort numbers numerically (detect both values are numbers)
    - Null/undefined values sort to end regardless of direction
    - Import `SortDirection` from `../components/filters/types`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.2 Write unit tests for useTableSort
    - Create `frontend/src/hooks/__tests__/useTableSort.test.ts`
    - Test: initial sort state matches defaults
    - Test: toggle direction on same field (asc→desc→asc)
    - Test: new field resets to ascending
    - Test: string sorting is case-insensitive
    - Test: numeric sorting is numeric (not lexicographic)
    - Test: null values sort to end
    - Test: `getSortIndicator` returns correct symbols
    - Test: no sort field returns original order
    - _Requirements: 12.2_

  - [x] 3.3 Write property test for Sort State Determinism (Property 3)
    - Create `frontend/src/hooks/__tests__/useTableSort.property.test.ts`
    - **Property 3: Sort State Determinism** — For any current sort state and any field name: same field toggles direction; different field resets to `'asc'`. `getSortIndicator` returns correct symbol for active/inactive fields.
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x] 3.4 Write property test for Sort Ordering Correctness (Property 4)
    - In same file `frontend/src/hooks/__tests__/useTableSort.property.test.ts`
    - **Property 4: Sort Ordering Correctness** — For any data array, sort field, and direction, every consecutive pair in `sortedData` respects the ordering. Strings case-insensitive, numbers numeric, null/undefined to end.
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 2.6**

- [x] 4. Implement useFilterableTable hook
  - [x] 4.1 Create `frontend/src/hooks/useFilterableTable.ts`
    - Compose `useColumnFilters` and `useTableSort` internally
    - Accept config object with `initialFilters`, optional `defaultSort`, optional `debounceMs`
    - Call `useColumnFilters(data, config.initialFilters, { debounceMs })` first
    - Call `useTableSort(filteredData, defaultSort?.field, defaultSort?.direction)` on filtered output
    - Return all properties from both hooks plus `processedData` (the sorted-filtered result)
    - Filtering applied before sorting so sort operates only on filtered subset
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.2 Write unit tests for useFilterableTable
    - Create `frontend/src/hooks/__tests__/useFilterableTable.test.ts`
    - Test: combined filter + sort produces correct output
    - Test: all delegated properties from sub-hooks are accessible
    - Test: filter applied before sort (verified with specific example)
    - Test: config with only filters (no sort) works
    - Test: config with only sort (no filters) works
    - _Requirements: 12.3_

  - [x] 4.3 Write property test for Filter-Then-Sort Confluence (Property 5)
    - Create `frontend/src/hooks/__tests__/useFilterableTable.property.test.ts`
    - **Property 5: Filter-Then-Sort Confluence** — For any data, filter config, and sort config, `processedData` from `useFilterableTable` is identical to independently filtering then sorting
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 3.3, 3.4, 12.5**

- [x] 5. Implement FilterableHeader component
  - [x] 5.1 Create `frontend/src/components/filters/FilterableHeader.tsx`
    - Render Chakra UI `<Th>` with column label, optional sort indicator, optional text filter `<Input>`
    - Dark theme styling: `bg="gray.700"` for header, `bg="gray.600"` and `color="white"` for input, `color="gray.300"` for label
    - Accept `isNumeric` prop for right-alignment
    - Set `aria-label` on filter input: `Filter by ${label}`
    - Set `aria-sort` on `<Th>`: `ascending`, `descending`, or `none` when sortable
    - Sort indicator click calls `onSort` callback
    - Filter input change calls `onFilterChange` callback
    - Import `FilterableHeaderProps` from `./types`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 5.2 Write unit tests for FilterableHeader
    - Create `frontend/src/components/filters/__tests__/FilterableHeader.test.tsx`
    - Test: renders label text in `<Th>`
    - Test: renders filter input when `filterValue` provided
    - Test: does not render filter input when `filterValue` omitted
    - Test: renders sort indicator when `sortable` and `sortDirection` set
    - Test: calls `onSort` callback on sort click
    - Test: calls `onFilterChange` on input change
    - Test: sets `aria-label` on filter input
    - Test: sets `aria-sort` on `<Th>` element
    - Test: `isNumeric` prop right-aligns content
    - _Requirements: 12.4_

  - [x] 5.3 Write property test for Accessibility Label Propagation (Property 6)
    - Create `frontend/src/components/filters/__tests__/FilterableHeader.property.test.tsx`
    - **Property 6: Accessibility Label Propagation** — For any non-empty label string, `FilterableHeader` renders `aria-label` on filter input containing the label text, and when sorting is enabled, renders valid `aria-sort` on `<Th>` matching current sort direction
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 4.8**

- [x] 6. Checkpoint — Foundation complete
  - Ensure all foundation hooks and FilterableHeader component compile without errors
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement useTableConfig hook and seed parameters
  - [x] 7.1 Create `frontend/src/hooks/useTableConfig.ts`
    - Accept entity name (`'chart_of_accounts' | 'parameters' | 'banking_mutaties'`)
    - Fetch table config from parameter system using namespace `ui.tables.{entity}`
    - Return `columns`, `filterableColumns`, `defaultSort`, `pageSize`, `loading`, `error`
    - Fall back to hardcoded defaults via scope inheritance (tenant → system)
    - Provide sensible hardcoded defaults when no parameter exists at any scope
    - Handle loading state (return defaults while loading) and error state (log errors, don't break rendering)
    - Integrate with `useFilterableTable` by providing `initialFilters` (derived from `filterableColumns`) and `defaultSort`
    - Follow same pattern as `useFieldConfig` in `frontend/src/hooks/useFieldConfig.ts`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.10_

  - [x] 7.2 Create seed SQL for system-scope default parameters
    - Create migration or seed script with INSERT statements for 12 parameters (4 per table × 3 tables)
    - Namespace: `ui.tables`, keys: `{entity}.columns`, `{entity}.filterable_columns`, `{entity}.default_sort`, `{entity}.page_size`
    - Values match the hardcoded defaults in the design document
    - Use `scope='tenant'`, `scope_id=@tenant_id` (set per tenant), `value_type='json'` (or `'number'` for page_size)
    - Parameters are tenant-scoped so they are editable in the ParameterManagement UI
    - _Requirements: 6.7_

  - [x] 7.3 Write unit tests for useTableConfig
    - Create `frontend/src/hooks/__tests__/useTableConfig.test.ts`
    - Test: returns correct defaults for each entity
    - Test: merges API response with defaults
    - Test: handles API errors gracefully (returns defaults)
    - Test: loading state transitions correctly
    - Test: partial parameter overrides merge correctly
    - _Requirements: 6.8, 6.9_

  - [x] 7.4 Write property test for Default Config Robustness (Property 7)
    - Create `frontend/src/hooks/__tests__/useTableConfig.property.test.ts`
    - **Property 7: Default Config Robustness** — For any valid entity name, `useTableConfig` returns a `TableConfig` with non-empty `columns`, non-empty `filterableColumns`, valid `defaultSort` (non-empty field, valid direction), and positive `pageSize` — even when parameter API returns no data or error
    - Use fast-check 4.4.0 with minimum 100 iterations
    - **Validates: Requirements 6.4, 6.10**

- [x] 8. Checkpoint — Parameter config complete
  - Ensure useTableConfig hook compiles and tests pass
  - Ensure seed SQL is syntactically valid
  - Ensure all tests pass, ask the user if questions arise. (explain how seeds work)

- [x] 8.1 Deploy seed SQL to production
  - Run `backend/sql/seed_table_config_params.sql` for each tenant in the production database
  - Set `@tenant_id` to each production tenant name before running the script
  - Verify all tenants have 12 `ui.tables` parameters at tenant scope
  - Verify parameters are clickable and editable in the ParameterManagement UI
  - _Requirements: 6.7_

- [x] 9. Exemplary component upgrades (Pattern C: parameter-driven + hooks)
  - [x] 9.1 Upgrade ChartOfAccounts to use useTableConfig + useFilterableTable + FilterableHeader
    - Replace manual `useState` + `useEffect` filter boilerplate with `useFilterableTable`
    - Replace `FilterPanel` with 8 `SearchFilterConfig` entries → `FilterableHeader` in column headers
    - Add `useTableConfig('chart_of_accounts')` for column/filter configuration
    - Column visibility driven by `useTableConfig().columns`
    - Preserve all existing functionality: row-click modal, data fetching, action buttons
    - _Requirements: 10.1, 10.2_

  - [x] 9.2 Upgrade ParameterManagement to use useTableConfig + useFilterableTable + FilterableHeader
    - Replace manual filter boilerplate with `useFilterableTable`
    - Replace `FilterPanel` with 5 `SearchFilterConfig` entries → `FilterableHeader` in column headers
    - Add `useTableConfig('parameters')` for column/filter configuration
    - Preserve all existing functionality: row-click modal (if not system scope), data fetching
    - _Requirements: 10.3, 10.4_

  - [x] 9.3 Upgrade BankingProcessor mutaties tab to use useTableConfig + useFilterableTable + FilterableHeader
    - Replace 13 inline `<Th>` filter inputs and manual sort logic with `useFilterableTable` + `FilterableHeader`
    - Add `useTableConfig('banking_mutaties')` for column/filter configuration
    - Preserve all existing functionality: row-click modal, tab structure, data fetching
    - _Requirements: 10.5_

- [x] 10. Checkpoint — Exemplary upgrades complete
  - Ensure ChartOfAccounts, ParameterManagement, and BankingProcessor compile without errors
  - Verify filters work, sort works, row-click opens correct modal in all three components
  - Ensure all tests pass, ask the user if questions arise.
  - Push to main

- [ ] 11. High-priority component migrations
  - [x] 11.1 Migrate MutatiesReport (Pattern B: hook replacement)
    - Replace `useState`/`useEffect` filter + sort boilerplate with `useFilterableTable`
    - Replace `<Th><Input .../>` patterns with `FilterableHeader`
    - Preserve all existing functionality and identical user-visible behavior
    - _Requirements: 7.1, 7.5_

  - [x] 11.2 Migrate ProfitLoss (Pattern B: hook replacement)
  - Replace inline column filters and sort logic with `useFilterableTable` + `FilterableHeader`
  - Preserve all existing functionality and identical user-visible behavior
  - _Requirements: 7.2, 7.5_

  - [x] 11.3 Remove dead code: ClosedYearsTable and related unused components
    - Investigation revealed `ClosedYearsTable.tsx` is dead code — never rendered in the running app
    - The live year-end closure UI is `YearEndClosureSection.tsx` (embedded in AangifteIbReport), which already has a reopen button with sequential validation
    - Deleted 4 unreachable files: `ClosedYearsTable.tsx`, `YearClosureWizard.tsx`, `YearEndClosure.tsx` (page), `YearEndClosureReport.tsx`
    - No dangling imports — these files only referenced each other
    - _Requirements: 7.3, 7.5 — N/A (component was dead code)_

  - [x] 11.4 Migrate ProvisioningPanel (Pattern E: row-click modal)
    - Remove per-row "Provision" action button and Actions column
    - Add `onClick` to `<Tr>` that opens confirmation/action modal
    - Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to `<Tr>`
    - Preserve provision functionality via modal
    - _Requirements: 7.4, 7.5_

- [x] 12. Checkpoint — High-priority migrations complete
  - Ensure MutatiesReport, ProfitLoss, ClosedYearsTable, ProvisioningPanel compile without errors
  - Verify all migrated components preserve existing functionality
  - Ensure all tests pass, ask the user if questions arise.
  - Push to github main

- [x] 13. Medium-priority component migrations (FilterPanel swaps)
  - [x] 13.1 Migrate ZZPContacts (Pattern A: FilterPanel swap)
    - Replace standalone `Select` for type filter with `FilterPanel` + `GenericFilter`
    - Preserve row-click modal and all existing functionality
    - _Requirements: 8.1, 8.9_

  - [x] 13.2 Migrate ZZPInvoices (Pattern A: FilterPanel swap)
    - Replace standalone `Input` + `Select` with `FilterPanel` + `GenericFilter` + `SearchFilterConfig`
    - Adjust to the standard table handlingight
    - _Requirements: 8.2, 8.9_

  - [x] 13.3 Migrate ZZPTimeTracking (Pattern A: FilterPanel swap)
    - Replace standalone `Select` + `Input` with `FilterPanel` + `GenericFilter` + `SearchFilterConfig`
    - Preserve row-click and card/table view toggle and all existing functionality
    - _Requirements: 8.3, 8.9_

  - [x] 13.4 Migrate TaxRateManagement (Pattern A: FilterPanel swap)
    - Replace standalone `Select` for type filter with `FilterPanel` + `GenericFilter`
    - Preserve row-click modal and all existing functionality
    - _Requirements: 8.4, 8.9_

  - [x] 13.5 Migrate AssetList (Pattern A+B: FilterPanel swap + hook)
    - Replace standalone `Input` + `Select` with `FilterPanel` + `GenericFilter` + `SearchFilterConfig`
    - Add `useTableSort` if sort boilerplate exists
    - Preserve row-click detail modal and all existing functionality
    - _Requirements: 8.5, 8.9_

- [x] 14. Medium-priority component migrations (row-click fixes)
  - [x] 14.1 Migrate UserManagement (Pattern A+D: FilterPanel swap + row-click fix)
    - Replace standalone filters with `FilterPanel`
    - Move `onClick` from email cell `<Td>` to parent `<Tr>` for full row-click
    - Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to `<Tr>`
    - Remove `cursor="pointer"` and underline styling from individual cells
    - Preserve modal behavior and all existing functionality
    - Use the generic table headers with sort and filter options
    - _Requirements: 8.6, 8.9_

  - [x] 14.2 Migrate TenantManagement (Pattern D: row-click fix)
    - Move `onClick` from admin name cell `<Td>` to parent `<Tr>` for full row-click
    - Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to `<Tr>`
    - Remove `cursor="pointer"` and underline styling from individual cells
    - Preserve modal behavior and existing `FilterPanel` usage
    - Use the generic table headers with sort and filter options
    - _Requirements: 8.7, 8.9_

  - [x] 14.3 Migrate RoleManagement (Pattern D: row-click fix)
    - Move `onClick` from role name cell `<Td>` to parent `<Tr>` for full row-click
    - Add `_hover={{ bg: 'gray.700', cursor: 'pointer' }}` to `<Tr>`
    - Remove `cursor="pointer"` and underline styling from individual cells
    - Preserve modal behavior and all existing functionality
    - Use the generic table style and headers with sort and filter options
    - _Requirements: 8.8, 8.9_

- [x] 15. Checkpoint — Medium-priority migrations complete
  - Ensure all 8 medium-priority components compile without errors
  - Verify all migrated components preserve existing functionality
  - Ensure all tests pass, ask the user if questions arise.
  - Push it to main

- [ ] 16. Low-priority migration and documentation
  - [x] 16.1 Migrate BnbFutureReport (Pattern A: FilterPanel swap)
    - Replace standalone `Select` for listing filter with `FilterPanel` + `GenericFilter`
    - Preserve read-only report behavior
      - Use the generic table style and headers with sort and filter options
    - _Requirements: 9.1_

  - [x] 16.2 Create framework reference document
    - Create `.kiro/specs/Common/Filters a generic approach/TABLE_FILTER_FRAMEWORK_V2.md`
    - Include: architecture overview (three layers), all hooks and components with interfaces and usage examples
    - Include: hybrid approach explained with code snippets
    - Include: when to use `useTableConfig` vs hardcoded config
      - Use the generic table style and headers with sort and filter options
    - Include: default dark theme styling values
    - Include: accepted exceptions (wizard UIs, monitoring dashboards, editable line-item tables, small config tables)
    - Include: reference implementations (ZZPProducts, ChartOfAccounts, ProfitLossReport)
    - Include: migration checklist for converting existing components
    - Regular markdown file without steering front-matter
    - _Requirements: 11.4, 11.5_

  - [x] 16.3 Update steering file `.kiro/steering/ui-patterns.md`
    - Keep approximately the same size as current version — no significant expansion
    - Add reference to `TABLE_FILTER_FRAMEWORK_V2.md` in the Filters section
    - Briefly mention hybrid approach and name key components (`FilterPanel`, `FilterableHeader`, `useColumnFilters`, `useTableSort`, `useTableConfig`)
    - Add explicit instruction: "When implementing or modifying tables or filters, read the full framework guide at `.kiro/specs/Common/Filters a generic approach/TABLE_FILTER_FRAMEWORK_V2.md`"
    - _Requirements: 11.1, 11.2, 11.3, 11.6_

- [x] 17. Cleanup deprecated patterns and leftover code
  - [x] 17.1 Remove stale coverage reports for deleted files
    - Delete `frontend/coverage/lcov-report/UnifiedAdminYearFilter.tsx.html`
    - Delete `frontend/coverage/lcov-report/UnifiedAdminYearFilterAdapters.ts.html`
    - Delete `frontend/coverage/lcov-report/src/components/UnifiedAdminYearFilter.tsx.html`
    - Delete `frontend/coverage/lcov-report/src/components/UnifiedAdminYearFilterAdapters.ts.html`

  - [x] 17.2 Verify no remaining standalone filter patterns
    - Search for standalone `<Select>` used as table filters (outside `FilterPanel` or `FilterableHeader`)
    - Search for standalone `<Input>` used as table filters in `<Th>` elements (outside `FilterableHeader`)
    - Search for manual `useState` + `useEffect` debounce patterns for column filtering
    - Search for manual `handleSort` / `setSortField` / `setSortDirection` boilerplate
    - Fix any remaining instances found

  - [x] 17.3 Verify no remaining cell-click patterns
    - Search for `onClick` on `<Td>` elements in CRUD tables (should be on `<Tr>` instead)
    - Search for `cursor="pointer"` on `<Td>` elements (should be in `_hover` on `<Tr>`)
    - Fix any remaining instances found (excluding accepted exceptions: BankConnect, HealthCheck, InvoiceLineEditor)

  - [x] 17.4 Remove unused imports in migrated components
    - After migrations, some components may still import `SearchFilterConfig` or `FilterPanel` that are no longer used (e.g., ChartOfAccounts, ParameterManagement after moving to `FilterableHeader`)
    - Run TypeScript compiler to detect unused imports
    - Clean up any unused imports

  - [x] 17.5 Archive old spec documents
    - Move `.kiro/specs/Common/Filters a generic approach/archive/UnifiedAdminYearFilter-fix-strategy.md` to confirm it's archived
    - Update `.kiro/specs/Common/Filters a generic approach/findings 20260417/table-filter-audit.md` with a note that the migration is complete

- [ ] 18. Final checkpoint — All migrations, cleanup, and documentation complete
  - Ensure all 16 components are migrated and compile without errors
  - Ensure BankConnect and HealthCheck retain their accepted exception patterns (Requirements 9.2, 9.3)
  - Ensure all tests pass, ask the user if questions arise.
  - Verify steering file size has not significantly increased
  - Verify no standalone filter/sort boilerplate remains in migrated components

## Notes

- All tasks are required — no optional tasks
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between phases
- Property tests validate universal correctness properties from the design document (Properties 1–7)
- Unit tests validate specific examples and edge cases
- All property-based tests use fast-check 4.4.0 with minimum 100 iterations
- Each component migration should be its own commit: `refactor(ComponentName): migrate to table-filter-framework-v2`
- BankConnect (Req 9.2) and HealthCheck (Req 9.3) are accepted exceptions — no migration tasks needed
