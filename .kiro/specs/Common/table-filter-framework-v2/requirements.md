# Requirements Document

## Introduction

The myAdmin application contains 40 table-containing components, of which 24 should use the generic filter framework — but only 12 currently do (50% adoption). The remaining components use ad-hoc standalone `Select`, `Input`, and custom filter implementations. Additionally, common patterns like column filter state management (~25 lines), sort toggle logic (~15 lines), and filter input rendering in `<Th>` elements (~40 lines) are copy-pasted across 6–7 files each, totalling ~590 lines of duplicated boilerplate.

This spec defines a v2 extension of the existing filter framework that introduces reusable hooks (`useColumnFilters`, `useTableSort`, `useFilterableTable`), a standardized `FilterableHeader` component for in-column text search, a parameter-driven `useTableConfig` hook for complex CRUD tables, and a phased migration of all 40 audited components to the new standard. The approach is hybrid: text search filters live in column headers for direct visual association, while dropdown and multi-select filters remain above the table in `FilterPanel`. For complex tables (ChartOfAccounts, ParameterManagement, BankingProcessor), column visibility and filter setup are driven by the existing parameter system, following the same pattern as `useFieldConfig` for form fields.

## Glossary

- **FilterPanel**: Existing Chakra UI container component (`frontend/src/components/filters/FilterPanel.tsx`) that renders multiple `GenericFilter` or `SearchFilterConfig` instances in horizontal, vertical, or grid layout above a table.
- **GenericFilter**: Existing reusable filter component (`frontend/src/components/filters/GenericFilter.tsx`) supporting single-select dropdown and multi-select checkbox menu modes.
- **YearFilter**: Existing specialized wrapper around `GenericFilter` for year selection (`frontend/src/components/filters/YearFilter.tsx`).
- **SearchFilterConfig**: Existing type definition for text-based search filter configuration in `types.ts`.
- **FilterableHeader**: Proposed new component that renders a `<Th>` element containing a column label, an optional sort indicator, and an optional text filter `<Input>`.
- **useColumnFilters**: Proposed new custom React hook that manages column filter state, debounce, and applies case-insensitive text filtering to a data array.
- **useTableSort**: Proposed new custom React hook that manages sort field, sort direction toggle, and applies sorting to a data array.
- **useFilterableTable**: Proposed new custom React hook that composes `useColumnFilters` and `useTableSort` into a single interface for components that need both filtering and sorting.
- **Hybrid_Approach**: The architectural pattern where text search filters are rendered inside column headers (`FilterableHeader`) while dropdown, multi-select, and year filters remain above the table (`FilterPanel`).
- **Column_Filter_Boilerplate**: The repeated ~25-line pattern of `useState` + `useEffect` debounce + `useMemo` filter logic found in 6+ components.
- **Sort_Boilerplate**: The repeated ~15-line pattern of `useState` for sort field/direction + toggle handler found in 7+ components.
- **CRUD_Table**: A table component where rows are clickable and open a modal for create, read, update, or delete operations.
- **Report_Table**: A read-only table component used for displaying financial reports, optionally with expand/collapse rows.
- **Steering_File**: The `.kiro/steering/ui-patterns.md` file that provides AI-assisted development guidance for UI patterns across the application.
- **useTableConfig**: Proposed new custom React hook that reads table column configuration (visible columns, filterable columns, default sort, page size) from the parameter system, enabling tenant-level customization of complex table layouts without code changes.
- **ParameterService**: Existing backend service (`backend/src/services/parameter_service.py`) that resolves flat key-value parameters by walking the scope inheritance chain (user → role → tenant → system) with in-process caching.
- **useFieldConfig**: Existing custom React hook (`frontend/src/hooks/useFieldConfig.ts`) that fetches field visibility/required configuration per entity from the parameter system. Used by ZZP forms (ContactModal, ProductModal, TimeEntryModal, InvoiceDetail) to show/hide fields based on tenant config.

## Requirements

### Requirement 1: Column Filter Hook

**User Story:** As a frontend developer, I want a reusable hook for column-based text filtering with debounce, so that I can replace the ~25-line boilerplate pattern duplicated across 6+ components with a single hook call.

#### Acceptance Criteria

1. THE useColumnFilters hook SHALL accept a generic data array of type `T extends Record<string, any>` and an initial filters object of type `Record<string, string>`.
2. THE useColumnFilters hook SHALL return the current filter values, a `setFilter` function, a `resetFilters` function, the filtered data array, and a `hasActiveFilters` boolean.
3. WHEN a filter value changes, THE useColumnFilters hook SHALL debounce the filtering operation with a configurable delay defaulting to 150 milliseconds.
4. THE useColumnFilters hook SHALL perform case-insensitive substring matching when applying filters to data fields.
5. WHEN a filter key does not match any field on a data row, THE useColumnFilters hook SHALL treat that filter as passing (not exclude the row).
6. WHEN `resetFilters` is called, THE useColumnFilters hook SHALL set all filter values back to empty strings and return the full unfiltered data array.
7. THE useColumnFilters hook SHALL reside in `frontend/src/hooks/useColumnFilters.ts`.

### Requirement 2: Table Sort Hook

**User Story:** As a frontend developer, I want a reusable hook for table column sorting with toggle behavior, so that I can replace the ~15-line sort boilerplate duplicated across 7+ components with a single hook call.

#### Acceptance Criteria

1. THE useTableSort hook SHALL accept a generic data array of type `T`, an optional default sort field, and an optional default sort direction (`asc` or `desc`).
2. THE useTableSort hook SHALL return the current sort field, sort direction, a `handleSort` function, the sorted data array, and a `getSortIndicator` function.
3. WHEN `handleSort` is called with the currently active sort field, THE useTableSort hook SHALL toggle the sort direction between `asc` and `desc`.
4. WHEN `handleSort` is called with a different field, THE useTableSort hook SHALL set the new field as active and reset the direction to `asc`.
5. THE `getSortIndicator` function SHALL return `'↑'` for ascending, `'↓'` for descending when the field is active, and `''` (empty string) when the field is not the active sort field.
6. THE useTableSort hook SHALL sort strings case-insensitively and numbers numerically.
7. THE useTableSort hook SHALL reside in `frontend/src/hooks/useTableSort.ts`.

### Requirement 3: Combined Filterable Table Hook

**User Story:** As a frontend developer, I want a single hook that composes column filtering and sorting for complex table components, so that I can set up a fully filterable and sortable table with one hook call instead of managing multiple hooks manually.

#### Acceptance Criteria

1. THE useFilterableTable hook SHALL compose `useColumnFilters` and `useTableSort` internally.
2. THE useFilterableTable hook SHALL accept a configuration object containing `initialFilters`, optional `defaultSort` (field and direction), and optional `debounceMs`.
3. THE useFilterableTable hook SHALL return all properties from both `useColumnFilters` and `useTableSort`, plus a `processedData` array that is the result of filtering then sorting.
4. THE useFilterableTable hook SHALL apply filtering before sorting so that sort operates only on the filtered subset.
5. THE useFilterableTable hook SHALL reside in `frontend/src/hooks/useFilterableTable.ts`.

### Requirement 4: Filterable Header Component

**User Story:** As a frontend developer, I want a standardized table header component that renders a column label with an optional text filter input and sort indicator, so that I can replace the repeated `<Th><Input .../></Th>` pattern (found in 3 files, up to 13 columns each) with a single component.

#### Acceptance Criteria

1. THE FilterableHeader component SHALL render a Chakra UI `<Th>` element containing the column label text.
2. WHERE a filter is enabled, THE FilterableHeader component SHALL render a Chakra UI `<Input>` element below the label for text-based filtering.
3. WHERE sorting is enabled, THE FilterableHeader component SHALL render a sort direction indicator next to the label.
4. WHEN the sort indicator is clicked, THE FilterableHeader component SHALL call the provided `onSort` callback.
5. THE FilterableHeader component SHALL use the dark theme styling: `bg="gray.700"` for the header, `bg="gray.600"` and `color="white"` for the filter input, and `color="gray.300"` for the label.
6. THE FilterableHeader component SHALL accept an `isNumeric` prop to right-align numeric columns.
7. THE FilterableHeader component SHALL reside in `frontend/src/components/filters/FilterableHeader.tsx`.
8. THE FilterableHeader component SHALL be accessible with proper `aria-label` on the filter input and `aria-sort` on the header element.

### Requirement 5: Type Definitions Extension

**User Story:** As a frontend developer, I want the filter framework type definitions extended to cover the new hooks and components, so that all filter-related types are centralized in one module.

#### Acceptance Criteria

1. THE types module SHALL export a `ColumnFilterState` type representing `Record<string, string>` for column filter values.
2. THE types module SHALL export a `SortDirection` type representing `'asc' | 'desc'`.
3. THE types module SHALL export a `SortConfig` interface with `field` and `direction` properties.
4. THE types module SHALL export a `FilterableHeaderProps` interface matching the props accepted by the FilterableHeader component.
5. THE types module SHALL export a `UseColumnFiltersOptions` interface with optional `debounceMs` number property.
6. THE types module SHALL reside in the existing `frontend/src/components/filters/types.ts` file.

### Requirement 6: Parameter-Driven Table Configuration Hook

**User Story:** As a tenant admin, I want table column visibility, filterable columns, and default sort order to be configurable per tenant through the parameter system, so that complex CRUD tables can be customized without code changes — following the same pattern as `useFieldConfig` for form fields.

**Scope:** This requirement applies only to CRUD tables with many columns: ChartOfAccounts (~8 columns), ParameterManagement (~5 columns), and BankingProcessor mutaties tab (~13 columns). Simple tables and report tables use hardcoded column config.

#### Acceptance Criteria

1. THE useTableConfig hook SHALL accept an entity name (e.g., `'chart_of_accounts'`, `'parameters'`, `'banking_mutaties'`) and fetch table configuration from the parameter system using namespace `ui.tables.{entity}`.
2. THE useTableConfig hook SHALL return: `columns` (ordered array of visible column keys), `filterableColumns` (array of column keys that get a FilterableHeader filter input), `defaultSort` (field and direction), and `pageSize` (number).
3. WHEN no tenant-level parameter exists for a table config key, THE useTableConfig hook SHALL fall back to system-level defaults via the existing ParameterService scope inheritance (tenant → system).
4. THE useTableConfig hook SHALL provide sensible hardcoded defaults when no parameter exists at any scope, so that tables render correctly without any parameter configuration.
5. THE useTableConfig hook SHALL integrate with `useFilterableTable` by providing the `initialFilters` (derived from `filterableColumns`) and `defaultSort` values.
6. THE useTableConfig hook SHALL reside in `frontend/src/hooks/useTableConfig.ts`.
7. THE backend SHALL seed tenant-scope default parameters for the three target tables during deployment, using namespace `ui.tables` with keys: `chart_of_accounts.columns`, `chart_of_accounts.filterable_columns`, `chart_of_accounts.default_sort`, `chart_of_accounts.page_size` (and equivalent for `parameters` and `banking_mutaties`). Parameters are tenant-scoped so they are directly editable in the ParameterManagement UI.
8. THE ParameterManagement UI SHALL allow tenant admins to override table config parameters at tenant scope, using the existing parameter CRUD interface with `value_type: 'json'`.
9. WHEN a tenant admin changes a table config parameter, THE useTableConfig hook SHALL reflect the change on next page load without requiring a code deployment.
10. THE useTableConfig hook SHALL handle loading and error states, returning defaults while loading and logging errors without breaking the table rendering.

### Requirement 7: High-Priority Component Migration

**User Story:** As a product owner, I want the four high-priority non-compliant components migrated to the new framework, so that the most visible violations of the table standard are resolved first.

#### Acceptance Criteria

1. WHEN migrated, THE MutatiesReport component SHALL use `useFilterableTable` and `FilterableHeader` for its column filters instead of standalone `<Input>` elements in `<Th>` cells.
2. WHEN migrated, THE ProfitLoss component SHALL use `useFilterableTable` and `FilterableHeader` for its column filters instead of standalone `<Input>` elements in `<Th>` cells.
3. WHEN migrated, THE ClosedYearsTable component SHALL use row-click to open a modal for the "Reopen" action instead of per-row action buttons.
4. WHEN migrated, THE ProvisioningPanel component SHALL use row-click to open a modal for the "Provision" action instead of per-row action buttons.
5. WHEN a high-priority component is migrated, THE component SHALL preserve all existing functionality and produce identical user-visible behavior apart from the UI pattern change.

### Requirement 8: Medium-Priority Component Migration

**User Story:** As a product owner, I want the eight medium-priority components migrated to use `FilterPanel` and the new hooks, so that standalone filter implementations are eliminated across the application.

#### Acceptance Criteria

1. WHEN migrated, THE ZZPContacts component SHALL use `FilterPanel` with `GenericFilter` for its type filter instead of a standalone `Select`.
2. WHEN migrated, THE ZZPInvoices component SHALL use `FilterPanel` with `GenericFilter` and `SearchFilterConfig` for its filters instead of standalone `Input` and `Select` elements.
3. WHEN migrated, THE ZZPTimeTracking component SHALL use `FilterPanel` with `GenericFilter` and `SearchFilterConfig` for its filters instead of standalone `Select` and `Input` elements.
4. WHEN migrated, THE TaxRateManagement component SHALL use `FilterPanel` with `GenericFilter` for its type filter instead of a standalone `Select`.
5. WHEN migrated, THE AssetList component SHALL use `FilterPanel` with `GenericFilter` and `SearchFilterConfig` for its filters instead of standalone `Input` and `Select` elements.
6. WHEN migrated, THE UserManagement component SHALL use `FilterPanel` for its filters and full row-click instead of cell-click on the email column.
7. WHEN migrated, THE TenantManagement component SHALL use full row-click on `<Tr>` instead of cell-click on the admin name column.
8. WHEN migrated, THE RoleManagement component SHALL use full row-click on `<Tr>` instead of cell-click on the role name column.
9. WHEN a medium-priority component is migrated, THE component SHALL preserve all existing functionality and produce identical user-visible behavior apart from the UI pattern change.

### Requirement 9: Low-Priority Component Migration

**User Story:** As a product owner, I want the low-priority components reviewed and migrated where appropriate, so that the entire application reaches consistent table and filter patterns.

#### Acceptance Criteria

1. WHEN migrated, THE BnbFutureReport component SHALL use `FilterPanel` with `GenericFilter` for its listing filter instead of a standalone `Select`.
2. THE BankConnect component SHALL retain its wizard-style per-row action buttons as an accepted exception to the row-click standard.
3. THE HealthCheck component SHALL retain its per-row "View Details" button as an accepted exception for monitoring UI.

### Requirement 10: Exemplary Component Enhancement

**User Story:** As a frontend developer, I want the exemplary components (ChartOfAccounts, ParameterManagement) upgraded to use the new hooks, so that they serve as reference implementations demonstrating the hybrid approach.

#### Acceptance Criteria

1. WHEN upgraded, THE ChartOfAccounts component SHALL use `useTableConfig('chart_of_accounts')` to load column configuration, and `useColumnFilters` to replace its manual `useState` + `useEffect` filter boilerplate.
2. WHEN upgraded, THE ChartOfAccounts component SHALL use `FilterableHeader` for its column headers, with filterable columns determined by the `useTableConfig` output instead of hardcoded `FilterPanel` with 8 `SearchFilterConfig` entries above the table.
3. WHEN upgraded, THE ParameterManagement component SHALL use `useTableConfig('parameters')` to load column configuration, and `useColumnFilters` to replace its manual filter boilerplate.
4. WHEN upgraded, THE ParameterManagement component SHALL use `FilterableHeader` for its column headers, with filterable columns determined by the `useTableConfig` output instead of hardcoded `FilterPanel` with 5 `SearchFilterConfig` entries above the table.
5. WHEN upgraded, THE BankingProcessor mutaties tab SHALL use `useTableConfig('banking_mutaties')` and `useFilterableTable` with `FilterableHeader` to replace its 13 inline `<Th>` filter inputs and manual sort logic.

### Requirement 11: Steering File Update and Framework Reference Document

**User Story:** As a frontend developer, I want the `ui-patterns.md` steering file to remain concise (it is loaded into AI context on every frontend file edit) while referencing a detailed framework document, so that I get quick guidance in context and can drill into the full standard when needed.

#### Acceptance Criteria

1. THE Steering_File SHALL remain approximately the same size as the current version — no significant expansion of its content.
2. THE Steering_File SHALL add a reference to a new detailed document: `.kiro/specs/Common/Filters a generic approach/TABLE_FILTER_FRAMEWORK_V2.md`.
3. THE Steering_File Filters section SHALL briefly mention the hybrid approach (text search in column headers, dropdowns above table) and name the key components (`FilterPanel`, `FilterableHeader`, `useColumnFilters`, `useTableSort`, `useTableConfig`) without detailed usage examples.
4. A NEW document `.kiro/specs/Common/Filters a generic approach/TABLE_FILTER_FRAMEWORK_V2.md` SHALL be created containing the full framework reference, including:
   - Architecture overview (three layers: utility functions → hooks → components)
   - All framework components and hooks with their interfaces and usage examples
   - The hybrid approach explained with code snippets
   - When to use `useTableConfig` (parameter-driven) vs hardcoded column config
   - Default dark theme styling values
   - Accepted exceptions (wizard UIs, monitoring dashboards, editable line-item tables, small config tables)
   - Reference implementations: `ZZPProducts.tsx` (simple CRUD), `ChartOfAccounts.tsx` (hybrid + parameter-driven), `ProfitLossReport.tsx` (report table)
   - Migration checklist for converting existing components
5. THE new framework document SHALL be a regular markdown file without steering front-matter (it is not a steering file itself — it is referenced from one).
6. THE Steering_File Filters section SHALL include an explicit instruction: "When implementing or modifying tables or filters, read the full framework guide at `.kiro/specs/Common/Filters a generic approach/TABLE_FILTER_FRAMEWORK_V2.md`" — so that AI-assisted development follows the reference when the task is relevant.

### Requirement 12: Test Coverage for New Hooks and Components

**User Story:** As a frontend developer, I want comprehensive tests for the new hooks and components, so that the framework is reliable and regressions are caught early.

#### Acceptance Criteria

1. THE useColumnFilters hook SHALL have unit tests verifying: filtering by single field, filtering by multiple fields simultaneously, case-insensitive matching, debounce behavior, reset functionality, and handling of missing fields.
2. THE useTableSort hook SHALL have unit tests verifying: initial sort state, sort direction toggle on same field, sort field change resets to ascending, string sorting case-insensitivity, and numeric sorting.
3. THE useFilterableTable hook SHALL have unit tests verifying: filtering is applied before sorting, combined filter and sort produces correct output, and all delegated properties from sub-hooks are accessible.
4. THE FilterableHeader component SHALL have unit tests verifying: rendering with label only, rendering with filter input, rendering with sort indicator, sort click callback, filter change callback, and accessibility attributes.
5. FOR ALL valid data arrays, filtering then sorting via useFilterableTable SHALL produce the same result as sorting the output of useColumnFilters (confluence property).
6. FOR ALL valid filter configurations, applying `resetFilters` then reading `filteredData` SHALL return the original unfiltered data array (round-trip property).
