# Implementation Plan: Dynamic Pivot Views

## Overview

Phased implementation of the Dynamic Pivot Views feature: backend services (AllowedColumnsRegistry, PivotService, PivotModelStore), API routes, database migration, frontend components (PivotBuilder, PivotResultTable, pivotService.ts), and CSV export. Backend foundation is built and tested first, then the frontend consumes it. Property-based tests validate correctness properties from the design document using Hypothesis (Python) and fast-check (TypeScript).

## Tasks

- [ ] 1. Database migration and backend foundation
  - [ ] 1.1 Create the `pivot_models` database table
    - Write a SQL migration script that creates the `pivot_models` table
    - Columns: `id`, `administration`, `name`, `data_source`, `definition` (JSON), `created_by`, `created_at`, `updated_at`
    - Include unique key `uq_admin_user_name (administration, created_by, name)` and index `idx_administration`
    - Run the migration against dev/test database to create the table
    - _Requirements: 4.2, 4.3, 4.5_

  - [ ] 1.2 Create `AllowedColumnsRegistry` in `backend/src/services/pivot_service.py`
    - Define `SYSTEM_ALLOWED_COLUMNS` dict with `vw_mutaties` and `vw_bnb_total` entries matching the design
    - Define `TENANT_COLUMN_MAP` dict mapping each data source to its tenant isolation column name (e.g., `'vw_mutaties': 'administration'`)
    - Define `DATA_SOURCE_FILTER_CONFIG` dict mapping each data source to its supported filter keys (e.g., `'vw_mutaties': ['years', 'administration', 'profitLoss', 'ledger']`)
    - Implement `get_available_columns(data_source, tenant)` method
    - Implement `get_registered_sources()` method — returns list of all registered data sources with their metadata (name, label, filter keys, tenant column)
    - Resolve tenant-level restrictions from `ParameterService` (namespace `ui.pivot`, key `allowed_columns.<data_source>`)
    - Return intersection of system max and tenant restriction; full system set when no tenant restriction exists
    - Implement `_validate_columns()` to reject columns not in the resolved allowed set
    - Implement `_quote_column(name)` helper for database-portable column name quoting (backticks for MySQL, double quotes for PostgreSQL)
    - Adding a new data source = add one entry to each of the three dicts — no other code changes needed
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ] 1.3 Seed `ui.pivot` parameter entries for existing tenants
    - Create SQL seed script to insert default `allowed_columns.vw_mutaties` and `allowed_columns.vw_bnb_total` parameters at system scope
    - Seed makes the full system-level column lists visible and editable in the ParameterManagement UI
    - Use namespace `ui.pivot`, value_type `json`, scope `system`
    - _Requirements: 6.7_

  - [ ] 1.4 Create `PivotModelStore` in `backend/src/services/pivot_model_store.py`
    - Implement `save_model(tenant, user_email, name, definition)` — INSERT with duplicate name check
    - Implement `update_model(tenant, user_email, model_id, definition)` — UPDATE with timestamp
    - Implement `load_model(tenant, model_id)` — SELECT + JSON deserialization with validation
    - Implement `list_models(tenant)` — SELECT summary list filtered by administration
    - Implement `delete_model(tenant, model_id)` — DELETE with tenant check
    - Implement static `serialize()`, `deserialize()`, `validate_definition()` methods
    - `validate_definition` checks required fields: `data_source`, `group_columns` (non-empty), `aggregate_measures` (non-empty)
    - Use `DatabaseManager` with parameterized queries for all operations
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 10.1, 10.2, 10.3, 10.4_

- [ ] 2. Checkpoint — Database and model layer complete
  - Ensure migration runs cleanly, PivotModelStore and AllowedColumnsRegistry compile without errors
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. PivotService query builder
  - [ ] 3.1 Implement `PivotService` core in `backend/src/services/pivot_service.py`
    - Implement `execute_pivot(tenant, user_tenants, config)` — orchestrates validation, query building, execution
    - Implement `build_pivot_query(config, user_tenants)` — generates parameterized SELECT with GROUP BY
    - Build WHERE clause with `administration IN (%s, %s, ...)` using `user_tenants` list for tenant isolation
    - Apply user-provided filters (years, administration, profit_loss, channel, listing, etc.) as additional WHERE conditions
    - Append `WITH ROLLUP` when `include_rollup` is true
    - Use `%s` placeholders for all user-provided values — no string interpolation
    - Enforce limits: max 5 group columns, max 10 aggregate measures, max 5 column nest levels
    - Validate aggregation functions against allowed set: SUM, COUNT, AVG, MIN, MAX
    - Return `{success, data, columns, row_count}` response structure
    - _Requirements: 1.5, 1.6, 1.7, 1.8, 2.4, 3.1, 3.2, 3.3, 3.9_

  - [ ] 3.2 Implement column pivot query generation
    - When `column_pivot` is set, generate conditional aggregation: `SUM(CASE WHEN pivot_col = %s THEN agg_col ELSE 0 END) AS label`
    - Support `column_nest_levels` for hierarchical column headers
    - Validate column role overlap: same column cannot be row group, column pivot, and column nest level simultaneously
    - Append grand total columns per pivot group
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.7, 9.8, 9.9, 9.10, 9.11_

  - [ ] 3.3 Implement `build_underlying_query(config, user_tenants)`
    - Build query for underlying (non-aggregated) dataset export
    - Apply same filters and tenant isolation but no GROUP BY
    - Return all columns from the data source matching filter criteria
    - _Requirements: 7.4_

  - [ ] 3.4 Write property tests for PivotModelStore serialization (Properties 1, 2)
    - Create `backend/tests/unit/test_pivot_model_serialization.py`
    - **Property 1: Pivot model serialization round-trip** — For any valid definition, serialize then deserialize produces equivalent definition
    - **Property 2: Malformed JSON rejection** — For any invalid/incomplete JSON, deserialization raises descriptive error
    - Use Hypothesis with minimum 100 iterations per property
    - Custom strategies for `PivotModelDefinition` with valid data sources, group columns, aggregate measures
    - **Validates: Requirements 4.2, 4.5, 10.1, 10.2, 10.3, 10.4**

  - [ ] 3.5 Write property tests for pivot config validation (Properties 3, 4)
    - Create `backend/tests/unit/test_pivot_config_validation.py`
    - **Property 3: Incomplete config rejection** — For any config with empty group_columns OR empty aggregate_measures, validation rejects
    - **Property 4: Column role overlap rejection** — For any config where same column appears in multiple roles (row group, column pivot, column nest levels), validation rejects
    - Use Hypothesis with minimum 100 iterations per property
    - **Validates: Requirements 1.6, 9.10**

  - [ ] 3.6 Write property tests for query builder (Properties 5, 6, 13)
    - Create `backend/tests/unit/test_pivot_query_builder.py`
    - **Property 5: Parameterized SQL structure** — For any valid config, generated SQL uses only `%s` placeholders, all filter values in params list, WHERE precedes GROUP BY
    - **Property 6: Tenant isolation** — For any config and user_tenants list, WHERE clause includes `administration IN (...)` with all tenant values in params
    - **Property 13: Column pivot conditional aggregation** — For any config with column_pivot, SQL contains `CASE WHEN` expressions for each pivot value and aggregate measure
    - Use Hypothesis with minimum 100 iterations per property
    - **Validates: Requirements 2.4, 3.1, 3.2, 3.3, 9.7**

  - [ ] 3.7 Write property tests for AllowedColumnsRegistry (Properties 7, 8)
    - Create `backend/tests/unit/test_allowed_columns_registry.py`
    - **Property 7: Column resolution is intersection** — For any system max and tenant restriction (subset of system max), resolved columns equal intersection; no tenant restriction returns full system set
    - **Property 8: Disallowed columns rejected** — For any request with column not in resolved registry, validation raises error
    - Use Hypothesis with minimum 100 iterations per property
    - **Validates: Requirements 6.2, 6.3, 6.5**

- [ ] 4. Pivot API routes
  - [ ] 4.1 Create `backend/src/routes/pivot_routes.py` with Blueprint `pivot_bp`
    - `POST /api/pivot/execute` — execute a pivot query, delegates to `PivotService.execute_pivot()`
    - `GET /api/pivot/columns/<source>` — get available columns for a data source
    - `GET /api/pivot/models` — list saved models for tenant
    - `POST /api/pivot/models` — save a new model
    - `PUT /api/pivot/models/<id>` — update an existing model
    - `GET /api/pivot/models/<id>` — load a specific model
    - `DELETE /api/pivot/models/<id>` — delete a model
    - `POST /api/pivot/export` — export underlying dataset
    - All routes use `@cognito_required(required_permissions=['reports_read'])` and `@tenant_required()`
    - Save/update/delete routes additionally require `reports_export` permission
    - Wrap all routes in try/except with proper error responses per the error handling table
    - _Requirements: 3.1, 3.3, 3.9, 4.4, 5.4, 6.4, 6.5_

  - [ ] 4.2 Register `pivot_bp` in `backend/src/app.py`
    - Import and register the pivot blueprint
    - Initialize `PivotService` and `PivotModelStore` with `set_test_mode()` pattern
    - _Requirements: 3.1_

  - [ ] 4.3 Write unit tests for pivot routes
    - Create `backend/tests/api/test_pivot_routes.py`
    - Test auth enforcement (401 without token, 403 without permission)
    - Test tenant isolation (only returns models for requesting tenant)
    - Test validation error responses (400 for missing columns, disallowed columns, duplicate name)
    - Test successful execute, save, load, update, delete flows
    - Test error response format matches design error handling table
    - _Requirements: 3.9, 4.4, 6.5, 9.10_

- [ ] 5. Checkpoint — Backend complete
  - Ensure all backend services, routes, and tests compile and pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Frontend API client and types
  - [ ] 6.1 Create TypeScript types in `frontend/src/types/pivot.ts`
    - Define `PivotConfig`, `AggregateMeasure`, `AvailableColumns`, `ColumnDef` interfaces
    - Define `PivotResult`, `PivotColumnMeta`, `PivotModelSummary`, `PivotModel` interfaces
    - Define `NumberFormat` type: `'decimal' | 'whole' | 'k-notation'`
    - Define `DisplayMode` type: `'flat' | 'hierarchical'`
    - Define `DataSourceConfig` interface: `{ key, label, filterConfig }` — describes a registered data source for the frontend
    - _Requirements: 1.3, 1.4, 1.5_

  - [ ] 6.2 Create data source registry in `frontend/src/config/pivotDataSources.ts`
    - Define `PIVOT_DATA_SOURCES` array of `DataSourceConfig` objects
    - Each entry specifies: `key` (e.g., `'vw_mutaties'`), `label` (e.g., `'Financial Transactions'`), and `filterConfig` (which filter components to render and their props)
    - PivotBuilder reads this registry to populate the data source dropdown and render the correct filters
    - Adding a new data source on the frontend = add one entry to this array — no component changes needed
    - _Requirements: 1.1, 2.1_

  - [ ] 6.3 Create `frontend/src/services/pivotService.ts`
    - Implement `executePivot(config)` — POST to `/api/pivot/execute`
    - Implement `getAvailableColumns(dataSource)` — GET `/api/pivot/columns/<source>`
    - Implement `listPivotModels()` — GET `/api/pivot/models`
    - Implement `savePivotModel(name, definition)` — POST `/api/pivot/models`
    - Implement `updatePivotModel(id, definition)` — PUT `/api/pivot/models/<id>`
    - Implement `loadPivotModel(id)` — GET `/api/pivot/models/<id>`
    - Implement `deletePivotModel(id)` — DELETE `/api/pivot/models/<id>`
    - Implement `exportUnderlying(config)` — POST `/api/pivot/export`
    - Use `authenticatedGet`, `authenticatedPost`, `authenticatedPut`, `authenticatedDelete` from `apiService.ts`
    - _Requirements: 3.1, 4.1, 5.1, 5.2, 5.3_

- [ ] 7. Shared frontend utilities
  - [ ] 7.1 Create `formatPivotNumber()` in `frontend/src/utils/pivotFormatting.ts`
    - Implement `formatPivotNumber(value, format, locale)` utility function
    - Three modes: decimal (2dp), whole (0dp), k-notation (abbreviated with k/M suffixes)
    - Use `Intl.NumberFormat` with locale parameter
    - Export as reusable utility for PivotResultTable and CSV export
    - _Requirements: 3.6, 3.7_

  - [ ] 7.2 Create `buildHierarchicalTree()` in `frontend/src/utils/pivotTreeBuilder.ts`
    - Extract tree-building logic as a reusable pure function
    - Input: flat result rows + group column names + aggregate column names
    - Output: nested tree structure with rolled-up parent aggregates
    - Reusable for any future hierarchical table display
    - _Requirements: 8.2, 8.3_

  - [ ] 7.3 Create `generateCsv()` in `frontend/src/utils/csvExport.ts`
    - Extract CSV generation as a reusable utility (currently duplicated in MutatiesReport)
    - Input: column headers + data rows + optional number formatter
    - Output: CSV string
    - Handles escaping of commas, quotes, and newlines in cell values
    - Reusable for pivot export and existing report exports
    - _Requirements: 7.2, 7.3_

  - [ ] 7.4 Add i18n translation keys for pivot UI
    - Add translation keys to the appropriate namespace (e.g., `reports` or new `pivot` namespace)
    - Keys for: data source labels, aggregation function names, column labels, button labels (Execute, Save, Load, Delete, Export), display mode labels, number format labels, validation messages, empty state message, error messages
    - Follow conventions in `.kiro/specs/Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md`
    - _Requirements: all UI requirements_

- [ ] 8. PivotBuilder component
  - [ ] 8.1 Create `frontend/src/components/pivot/PivotBuilder.tsx`
    - Data source selector dropdown (vw_mutaties, vw_bnb_total)
    - Fetch available columns from API on data source change
    - Group column picker: multi-select from groupable columns, max 5
    - Aggregate measure picker: function dropdown (SUM/COUNT/AVG/MIN/MAX) + column dropdown, max 10
    - Column pivot selector: optional single column from groupable set
    - Column nest level picker: multi-select, max 5, excluding columns already used as row group or column pivot
    - Validation: at least 1 group column + 1 aggregate measure before execute
    - Prevent same column in multiple roles (row group, column pivot, column nest level)
    - Execute button, Save button (prompts for model name), Load model dropdown
    - Display mode toggle (flat/hierarchical) — only shown when 2+ group columns
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 9.1, 9.3, 9.5, 9.8, 9.10, 9.11_

  - [ ] 8.2 Integrate filter controls in PivotBuilder
    - Render filter controls matching the selected data source using existing `FilterPanel`, `YearFilter`, `GenericFilter`
    - For `vw_mutaties`: YearFilter, administration dropdown, profit/loss (VW), ledger account (Reknum)
    - For `vw_bnb_total`: YearFilter, channel dropdown, listing dropdown
    - Pass filter values into pivot config for query execution
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 8.3 Implement saved model management in PivotBuilder
    - Load model list on mount via `listPivotModels()`
    - Populate config from selected saved model via `loadPivotModel(id)`
    - Save current config with user-provided name via `savePivotModel()`
    - Update existing model via `updatePivotModel()` when saving with same name
    - Delete model via `deletePivotModel()` with confirmation
    - Display API errors (duplicate name, not found) as Chakra `Alert`
    - _Requirements: 4.1, 4.4, 5.1, 5.2, 5.3, 5.5, 5.6_

- [ ] 9. PivotResultTable component
  - [ ] 9.1 Create `frontend/src/components/pivot/PivotResultTable.tsx` — flat mode
    - Render standard Chakra `Table` with `FilterableHeader` for sorting on all columns
    - Display group columns as row identifiers, aggregate columns as computed values
    - Format numeric values with appropriate decimal precision (2 for currency, 0 for counts)
    - Display empty state message when zero rows returned
    - Display loading state while query executes
    - _Requirements: 3.4, 3.5, 3.6, 3.8_

  - [ ] 9.2 Implement number format toggle
    - Three-way toggle: decimal (€12,345.67), whole (€12,346), k-notation (€12.3k)
    - Use `formatPivotNumber()` utility from task 7.1
    - Apply formatting to all aggregate measure columns
    - _Requirements: 3.7_

  - [ ] 9.3 Implement hierarchical display mode
    - Use `buildHierarchicalTree()` utility from task 7.2 to build tree from `WITH ROLLUP` result rows
    - First group column = top-level nodes, subsequent = nested children
    - Expand/collapse via row click on parent rows
    - Display rolled-up aggregate values on parent rows
    - Default to hierarchical mode when 2+ group columns
    - Toggle between flat and hierarchical without re-executing query
    - Hide toggle when only 1 group column
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ] 9.4 Implement column-pivoted display mode
    - Render distinct values of column pivot as column headers
    - Spread aggregate measures across pivot columns
    - Render hierarchical column headers for column nest levels via multi-row `<thead>`
    - Append grand total column per pivot group
    - When no column pivot selected, display all group columns on row axis only
    - _Requirements: 9.2, 9.4, 9.6, 9.9_

  - [ ] 9.5 Write property tests for frontend (Properties 9, 10, 11, 12)
    - Create `frontend/src/components/pivot/__tests__/PivotResultTable.property.test.ts`
    - **Property 9: Number format toggle correctness** — For any numeric value and display mode, formatting produces correct output (decimal=2dp, whole=0dp, k-notation=abbreviated)
    - **Property 10: CSV export structure** — For any non-empty result data, CSV has header row matching columns, same row count, consistent field count
    - **Property 11: Hierarchical tree nesting** — For any flat result with 2+ group columns, tree has correct nesting structure
    - **Property 12: Parent row aggregates equal rollup** — For any hierarchical tree, parent aggregate values equal aggregation across children
    - Use fast-check 4.4.0 with minimum 100 iterations per property
    - **Validates: Requirements 3.6, 3.7, 7.2, 7.3, 8.2, 8.3**

- [ ] 10. Checkpoint — Core UI complete
  - Ensure PivotBuilder and PivotResultTable compile without errors
  - Verify end-to-end flow: select data source → pick columns → execute → see results
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. CSV export, wiring, and remaining tests
  - [ ] 11.1 Implement CSV export in PivotResultTable
    - Use `generateCsv()` utility from task 7.3
    - Pivot result export: iterate data array, format numbers per current display mode, generate CSV, trigger download
    - Underlying dataset export: call `exportUnderlying()` API, generate CSV with full-precision numbers
    - Offer choice between pivot result and underlying dataset export
    - Disable export actions when no data
    - Use existing `Blob` + `URL.createObjectURL` + anchor click pattern from `MutatiesReport.tsx`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 11.2 Integrate PivotBuilder as a tab in TenantAdminDashboard
    - Add a new "📊 Pivot Views" tab in `frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`
    - Render `PivotBuilder` component inside the new tab panel, passing `tenant={currentTenant}`
    - Tenant admins use this tab to create, edit, save, load, and delete pivot model definitions
    - Tab visibility: always shown (pivot views work across FIN and STR modules)
    - _Requirements: 1.1, 4.1, 5.1_

  - [ ] 11.3 Add PivotResultTable tab to FinancialReportsGroup
    - Add a new "📊 Pivot Views" tab in `frontend/src/components/reports/FinancialReportsGroup.tsx`
    - Create a `PivotViewsTab` wrapper component that loads saved models filtered to `data_source = 'vw_mutaties'`
    - Render a model selector dropdown + `PivotResultTable` — user picks a saved model, clicks execute, sees results
    - Reuses the same `PivotResultTable` component as the STR tab
    - _Requirements: 3.4, 5.1, 5.2_

  - [ ] 11.4 Add PivotResultTable tab to BnbReportsGroup
    - Add a new "📊 Pivot Views" tab in `frontend/src/components/reports/BnbReportsGroup.tsx`
    - Create a `PivotViewsTab` wrapper component that loads saved models filtered to `data_source = 'vw_bnb_total'`
    - Render a model selector dropdown + `PivotResultTable` — same pattern as the FIN tab
    - Reuses the same `PivotResultTable` component and `PivotViewsTab` wrapper (parameterized by data source)
    - _Requirements: 3.4, 5.1, 5.2_

  - [ ] 11.5 Write unit tests for PivotBuilder
    - Create `frontend/src/components/pivot/__tests__/PivotBuilder.test.tsx`
    - Test: renders data source selector with options
    - Test: fetches and displays columns on data source change
    - Test: validation prevents execute without group column + aggregate measure
    - Test: save flow prompts for name and calls API
    - Test: load model populates config
    - Test: filter controls match selected data source
    - _Requirements: 1.1, 1.2, 1.6, 2.1, 4.1, 5.2_

  - [ ] 11.6 Write unit tests for PivotResultTable
    - Create `frontend/src/components/pivot/__tests__/PivotResultTable.test.tsx`
    - Test: renders flat table with correct columns and data
    - Test: renders empty state message when no data
    - Test: number format toggle switches display mode
    - Test: hierarchical mode renders expandable rows
    - Test: export buttons disabled when no data
    - _Requirements: 3.4, 3.7, 3.8, 7.6, 8.1_

  - [ ] 11.7 Write unit tests for pivotService.ts
    - Create `frontend/src/services/__tests__/pivotService.test.ts`
    - Test all API client functions with MSW mocks
    - Test error handling for failed requests
    - _Requirements: 3.1, 4.1, 5.1_

- [ ] 12. Final checkpoint — All implementation complete
  - Ensure all backend and frontend code compiles without errors
  - Ensure all tests pass, ask the user if questions arise.
  - Verify full flow: configure pivot → execute → view results → save model → load model → export CSV
  - Verify tenant isolation: models and data scoped to current tenant
  - Verify column access control: only allowed columns shown and accepted

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between phases
- Property tests validate universal correctness properties from the design document (Properties 1–13)
- Backend property tests use Hypothesis; frontend property tests use fast-check 4.4.0
- Unit tests validate specific scenarios, UI interactions, and edge cases
- All property-based tests run minimum 100 iterations
- Backend follows existing `ReportingService` patterns (parameterized queries, `@cognito_required`, `@tenant_required`)
- Frontend reuses existing `FilterPanel`, `YearFilter`, `GenericFilter`, `FilterableHeader`, `useFilterableTable`
- CSV export reuses existing `Blob` + `URL.createObjectURL` pattern from `MutatiesReport.tsx`
