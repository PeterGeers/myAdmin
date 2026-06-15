# Implementation Plan: Budget Management (fin-budget)

## Overview

Implement a category-based budget vs actuals system for the FIN module. The backend uses Flask with a service layer pattern (Python), and the frontend uses React with TypeScript and Chakra UI. Budget data is stored in MySQL with monthly granularity and rolls up through the existing account hierarchy at query time.

## Tasks

- [x] 1. Database schema and backend foundation
  - [x] 1.1 Create database migration script for budget tables
    - Create `budget_versions`, `budget_templates`, `budget_template_lines`, and `budget_lines` tables
    - Include all indexes, unique constraints, and foreign keys as defined in the design
    - Add `administration` column with standalone index on every table for tenant isolation
    - _Requirements: 1.1, 2.1, 3.4, 8.1_

  - [x] 1.2 Create TypeScript type definitions (`frontend/src/types/budget.ts`)
    - Define interfaces for BudgetVersion, BudgetTemplate, BudgetTemplateLine, BudgetLine, DashboardRow, and API response types
    - Include enums for Status (`Draft`, `Approved`, `Revised`), PeriodMode (`Monthly`, `Annual`), DimensionType (`platform`, `ReferenceNumber`)
    - _Requirements: 1.1, 2.1, 2.2, 3.1, 6.1_

  - [x] 1.3 Create budget service module (`backend/src/services/budget_service.py`)
    - Implement `BudgetService` class with constructor accepting database connection
    - Implement `divide_annual()` helper using `decimal.Decimal` with `ROUND_HALF_EVEN` and remainder adjustment on last month
    - Implement banker's rounding utility for monetary amounts
    - _Requirements: 2.3, 3.2, 3.5_

- [x] 2. Budget Version Management
  - [x] 2.1 Implement version CRUD in budget service
    - `create_version(administration, name, fiscal_year)` — validate unique name per year/tenant, return new version with status Draft
    - `list_versions(administration, year=None)` — list versions filtered by tenant and optional year
    - `delete_version(administration, version_id)` — only allow deletion of Draft versions
    - _Requirements: 1.1, 1.2, 8.2_

  - [x] 2.2 Implement status transitions in budget service
    - `transition_status(administration, version_id, action)` — enforce Draft→Approved→Revised sequence
    - Record `status_changed_at` timestamp on transition
    - For "revise" action: create a copy of the Approved version with all budget lines, set copy status to Revised, preserve original
    - _Requirements: 1.3, 1.4, 1.5_

  - [x] 2.3 Implement version activation in budget service
    - `activate_version(administration, version_id)` — validate status is Approved or Revised, deactivate any previously active version for same year/tenant, set new version as active
    - Enforce at most one active version per fiscal year per tenant
    - _Requirements: 1.6, 1.7, 1.8_

  - [x] 2.4 Create budget version routes (`backend/src/routes/budget_routes.py`)
    - Register Flask Blueprint `budget_bp` with prefix `/api/budget`
    - Implement `GET /versions`, `POST /versions`, `PUT /versions/<id>/status`, `PUT /versions/<id>/activate`, `DELETE /versions/<id>`
    - Apply auth decorators and tenant context filtering
    - _Requirements: 1.1–1.8, 8.2, 8.4_

  - [x] 2.5 Write property tests for status transitions and active version uniqueness
    - **Property 3: Status transition validity** — verify only Draft→Approved→Revised transitions succeed
    - **Property 4: Active version uniqueness** — verify at most one active version per year/tenant after any sequence of activations
    - **Validates: Requirements 1.5, 1.6, 1.8**

- [x] 3. Budget Template Management
  - [x] 3.1 Implement template CRUD in budget service
    - `create_template(administration, name, lines)` — validate unique name per tenant, validate at least one line, validate each account_code exists in `rekeningschema`, reject duplicate account codes within template
    - `get_template(administration, template_id)` — return template with all lines
    - `list_templates(administration)` — list templates for tenant
    - `update_template(administration, template_id, name, lines)` — full replacement of template lines
    - `delete_template(administration, template_id)` — cascade delete template lines
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.2 Create budget template routes in `budget_routes.py`
    - Implement `GET /templates`, `GET /templates/<id>`, `POST /templates`, `PUT /templates/<id>`, `DELETE /templates/<id>`
    - Validate request bodies: name required (max 100 chars), lines array required with at least one entry
    - When `has_detail_dimension` is true, require `dimension_type`
    - _Requirements: 2.1–2.7, 8.2_

  - [x] 3.3 Write unit tests for template validation logic
    - Test duplicate account code rejection
    - Test invalid account code rejection
    - Test duplicate template name rejection
    - Test dimension_type required when has_detail_dimension is true
    - _Requirements: 2.4, 2.5, 2.6, 2.7_

- [x] 4. Budget Line Entry
  - [x] 4.1 Implement budget line CRUD in budget service
    - `create_line(administration, version_id, account_code, period_mode, amounts_or_annual, dimension_type, dimension_value)` — validate no duplicate account+dimension per version, round amounts to 2 decimal places with banker's rounding, auto-divide annual amounts into 12 months
    - `update_line(administration, line_id, amounts_or_annual)` — update monthly amounts
    - `list_lines(administration, version_id)` — list all lines for a version
    - `delete_line(administration, line_id)` — remove a budget line
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 4.2 Create budget line routes in `budget_routes.py`
    - Implement `GET /versions/<id>/lines`, `POST /versions/<id>/lines`, `PUT /lines/<id>`, `DELETE /lines/<id>`
    - Validate monthly mode requires 12-element amounts array, annual mode requires annual_amount field
    - _Requirements: 3.1–3.6, 8.2_

  - [x] 4.3 Write property test for annual division
    - **Property 1: Annual division preserves total** — for any valid annual amount, the 12 monthly amounts (banker's rounding + remainder adjustment) sum exactly to the original
    - **Validates: Requirements 2.3, 3.2**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Draft Generation and Budget Copy
  - [x] 6.1 Implement draft generation in budget service
    - `generate_draft(administration, template_id, fiscal_year, version_name)` — query prior-year actuals from `vw_mutaties`, apply annualization for partial years, create Draft version with pre-filled budget lines
    - For full 12 months of prior data: use actual monthly amounts directly
    - For fewer than 12 months: annualize (total × 12 / N months) then distribute equally with banker's rounding
    - For accounts with no prior actuals: create lines with zero amounts
    - For accounts with detail dimension: create separate lines per dimension value found in actuals
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 6.2 Implement budget copy in budget service
    - `copy_budget(administration, source_version_id, target_fiscal_year, version_name)` — validate source belongs to tenant, validate target year > source year, copy all lines preserving amounts and dimensions, exclude lines for accounts no longer in chart of accounts, return warnings for excluded accounts
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 8.5_

  - [x] 6.3 Create draft generation and copy routes in `budget_routes.py`
    - Implement `POST /generate-draft` and `POST /copy`
    - Validate request bodies and return appropriate error responses
    - _Requirements: 4.1–4.6, 5.1–5.4_

  - [x] 6.4 Write property tests for annualization and copy
    - **Property 7: Annualization preserves proportional correctness** — for any partial-year actuals (1–11 months), the annualized total equals (sum × 12 / N) rounded to 2dp, and 12 distributed amounts sum to that total
    - **Property 9: Budget copy preserves line data** — copying a version preserves all monthly amounts, period modes, and dimension associations exactly
    - **Validates: Requirements 4.2, 5.1, 5.2**

- [x] 7. Dashboard and Hierarchy Rollup
  - [x] 7.1 Implement hierarchy rollup in budget service
    - `get_rollup(administration, version_id, level, parent_code=None, subparent_code=None, months=None)` — join budget_lines to rekeningschema for live hierarchy, aggregate at requested level (parent/subparent/account)
    - Handle unassigned accounts (no SubParent) in a separate "Unassigned" category
    - Apply period selection to sum only the relevant months
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 7.2 Implement dashboard comparison in budget service
    - `get_dashboard(administration, year, level, period, parent_code=None, subparent_code=None, reference_number=None)` — find active version for year, compute budget rollup and actuals rollup, calculate variance (actual - budget)
    - If no active version exists: return zero budgets with notification
    - Support period types: month-N, q1–q4, ytd, full
    - Filter by reference_number when provided (both budget and actuals)
    - _Requirements: 6.1–6.9_

  - [x] 7.3 Create dashboard route in `budget_routes.py`
    - Implement `GET /dashboard` with query parameters: year, level, period, parent_code, subparent_code, reference_number
    - Validate year is required, level defaults to parent, period defaults to ytd
    - _Requirements: 6.1–6.9_

  - [x] 7.4 Write property tests for rollup and variance
    - **Property 2: Rollup invariant** — parent totals equal sum of children at every hierarchy level
    - **Property 6: Variance calculation correctness** — variance exactly equals actual minus budget
    - **Property 8: Period aggregation correctness** — period total equals sum of exactly those months in the selected period
    - **Validates: Requirements 6.2, 6.5, 6.7, 7.1, 7.2**

- [x] 8. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Frontend API Service and Budget Versions Page
  - [x] 9.1 Create frontend budget API service (`frontend/src/services/budgetService.ts`)
    - Implement API calls for all budget endpoints: versions CRUD, templates CRUD, lines CRUD, generate-draft, copy, dashboard
    - Use existing `apiService` patterns for authenticated requests
    - _Requirements: 1.1–8.5_

  - [x] 9.2 Create BudgetVersionsPage (`frontend/src/pages/BudgetVersionsPage.tsx`)
    - Chakra UI Table listing versions with name, fiscal year, status, active badge
    - Row-click opens modal for version details
    - Header actions: "Create Version" button
    - Create modal: name input, fiscal year input
    - Status transition buttons (Approve, Revise) based on current status
    - Activate button (enabled only for Approved/Revised)
    - Delete button (enabled only for Draft)
    - _Requirements: 1.1–1.8_

  - [x] 9.3 Write unit tests for BudgetVersionsPage
    - Test rendering of version list
    - Test status transition button visibility based on current status
    - Test activate button disabled for Draft versions
    - _Requirements: 1.1–1.8_

- [x] 10. Frontend Templates and Lines Pages
  - [x] 10.1 Create BudgetTemplatesPage (`frontend/src/pages/BudgetTemplatesPage.tsx`)
    - Chakra UI Table listing templates with name and line count
    - Row-click opens modal for template editing
    - Template form with name input and dynamic lines list (add/remove)
    - Each line: account code select, period mode toggle, detail dimension checkbox + dimension type select
    - Validation: at least one line, no duplicate account codes
    - _Requirements: 2.1–2.7_

  - [x] 10.2 Create BudgetLinesPage (`frontend/src/pages/BudgetLinesPage.tsx`)
    - Version selector dropdown
    - Table showing budget lines with account code, period mode, dimension, and total
    - Row-click opens modal for line editing
    - Line form: account code, period mode toggle (Monthly shows 12 inputs, Annual shows 1 input), optional dimension type and value
    - Generate Draft button: opens modal for template selection, fiscal year, version name
    - Copy Budget button: opens modal for source version selection, target year, version name
    - _Requirements: 3.1–3.6, 4.1–4.6, 5.1–5.4_

  - [x] 10.3 Write unit tests for BudgetLinesPage
    - Test monthly vs annual input mode switching
    - Test generate draft modal form
    - _Requirements: 3.1, 3.2_

- [x] 11. Frontend Dashboard
  - [x] 11.1 Create BudgetDashboard (`frontend/src/pages/BudgetDashboard.tsx`)
    - Fiscal year selector and period selector (month, quarter, ytd, full)
    - Optional ReferenceNumber filter input
    - Chakra UI Table showing rows with code, name, budget, actual, variance columns
    - Color-code variance: green for under-budget (negative), red for over-budget (positive)
    - Drill-down: clicking a Parent row loads SubParent view, clicking SubParent loads Account view
    - Back navigation breadcrumb for drill-down levels
    - Handle no-active-version notification display
    - All amounts formatted to 2 decimal places
    - _Requirements: 6.1–6.9_

  - [x] 11.2 Write unit tests for BudgetDashboard
    - Test drill-down navigation
    - Test no-active-version notification display
    - Test variance color coding
    - _Requirements: 6.1, 6.8, 6.5_

- [x] 12. Frontend routing and navigation integration
  - [x] 12.1 Register budget pages in application router and navigation
    - Add routes for `/budget/versions`, `/budget/templates`, `/budget/lines`, `/budget/dashboard`
    - Add navigation items to the FIN module sidebar/menu
    - _Requirements: 1.1, 2.1, 3.1, 6.1_

- [x] 13. Tenant isolation enforcement
  - [x] 13.1 Add tenant isolation guards to all budget service methods
    - Ensure every read/write/delete operation filters by `administration` from authenticated user context
    - Return HTTP 403 for cross-tenant access attempts
    - Verify source version tenant ownership in copy and draft generation operations
    - _Requirements: 8.1–8.5_

  - [x] 13.2 Write property test for tenant isolation
    - **Property 5: Tenant isolation** — queries in context of tenant A never return data belonging to tenant B
    - **Validates: Requirements 8.2, 8.4**

- [x] 14. AI-Powered Budget Features (Backend)
  - [x] 14.1 Create BudgetAIService (`backend/src/services/budget_ai_service.py`)
    - Import `resolver` and `RegistryError` from `services.ai_model_registry` — no hardcoded model identifiers
    - Resolve model fallback chain from the `"text_generation"` task profile via `resolver.resolve_profile("text_generation")`
    - Use each `ResolvedModel`'s `timeout` and `max_tokens` for API requests (with optional per-call max_tokens override)
    - Implement `_call_openrouter(system_prompt, user_prompt, administration, max_tokens_override=None)` shared helper that iterates the resolved chain
    - Track usage via `AIUsageTracker` with the successful model's `model_id`
    - Implement graceful degradation: return `{"success": False, "error": "AI service unavailable: ..."}` on RegistryError or when all models fail
    - _Requirements: 9.3, 9.4, 10.4, 11.5_

  - [x] 14.2 Implement narrative generation in BudgetAIService
    - `generate_narrative(dashboard_data, period, year, administration)` — format dashboard rows into compact prompt, request Dutch executive summary
    - Limit payload to max 50 rows; truncate if dashboard has more
    - Prompt instructs model to output 2-4 sentences highlighting largest variances
    - 15-second timeout per model attempt
    - _Requirements: 9.1, 9.2, 9.5, 9.6_

  - [x] 14.3 Implement natural language query translation in BudgetAIService
    - `translate_query(question, year, hierarchy_context, administration)` — include account hierarchy names as context, instruct model to return JSON with dashboard parameters only
    - Validate returned parameters against allowed schema (`year`, `level`, `period`, `parent_code`, `subparent_code`, `reference_number`)
    - Reject parameters containing SQL fragments, semicolons, or values > 100 chars
    - If validation fails, return user-friendly rephrase suggestion
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 14.4 Implement draft adjustment suggestions in BudgetAIService
    - `suggest_adjustments(budget_lines, context_notes, administration)` — accept max 100 budget lines, send with user notes to AI
    - Parse response into structured suggestions: account_code, affected_months, current_amounts, suggested_amounts, reasoning
    - Filter out suggestions referencing account codes not in the provided budget lines
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 14.5 Implement template recommendations in BudgetAIService
    - `recommend_template(chart_of_accounts, prior_actuals, existing_templates, administration)` — send account list with activity data, request ranked recommendations
    - Parse response into structured recommendations: account_code, period_mode, has_detail_dimension, confidence, reason
    - Fallback if no actuals/templates available: return all active accounts with "low" confidence
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 14.6 Create AI routes in `budget_routes.py`
    - Implement `POST /ai/narrative`, `POST /ai/query`, `POST /ai/draft-suggestions`, `POST /ai/template-recommend`
    - Apply auth decorators and tenant context
    - Validate request bodies (year required for narrative/query, version_id for suggestions, scope.parent_code for large versions)
    - _Requirements: 9.1–12.5_

  - [x] 14.7 Write unit tests for BudgetAIService
    - Mock OpenRouter responses for all 4 features
    - Test parameter validation on query translation (Property 10)
    - Test payload size limit enforcement (max 100 lines)
    - Test account code filtering on suggestions
    - Test graceful degradation (API key missing, all models fail)
    - _Requirements: 9.4, 10.2, 11.4, 11.5_

- [x] 15. AI-Powered Budget Features (Frontend)
  - [x] 15.1 Add AI actions to BudgetDashboard
    - "Generate Summary" button — calls `/ai/narrative`, displays result in a collapsible text panel above the table
    - Natural language query input — text field with submit button, calls `/ai/query`, applies returned filters and shows results
    - Loading states and error display for AI calls
    - _Requirements: 9.1, 10.1_

  - [x] 15.2 Add AI actions to BudgetLinesPage
    - "AI Suggestions" button (visible only for Draft versions) — opens modal for context notes input, calls `/ai/draft-suggestions`
    - Display suggestions as a reviewable list with accept/reject per suggestion
    - On accept: populate the budget line form with suggested amounts for user confirmation
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 15.3 Add AI actions to BudgetTemplatesPage
    - "AI Recommend" button — calls `/ai/template-recommend`, displays recommendations with confidence badges
    - "Add to template" button per recommendation to add the account to the template form
    - _Requirements: 12.1, 12.3, 12.4_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with `hypothesis` for property-based testing
- Frontend uses TypeScript with `@fast-check/vitest` for property-based testing
- All monetary calculations use `decimal.Decimal` with `ROUND_HALF_EVEN` (banker's rounding)
- Rollups are computed at query time joining to `rekeningschema` — no materialized rollup tables
- The `divide_annual()` function adjusts the last month for remainder to guarantee sum preservation
- AI features (tasks 14–15) use the centralized AI Model Registry (`services.ai_model_registry`) — resolve the `"text_generation"` task profile for fallback chain, timeouts, and token limits. No hardcoded model identifiers in BudgetAIService.
- AI calls are user-initiated only — no automatic/background calls, keeping costs near zero
- AI service fallback chain order is managed by the registry's task profile definition (free models first, then cheap, then paid)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "9.1"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "3.1"] },
    { "id": 3, "tasks": ["2.4", "2.5", "3.2", "3.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["6.3", "6.4"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "7.4"] },
    { "id": 9, "tasks": ["9.2", "9.3", "10.1"] },
    { "id": 10, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 11, "tasks": ["11.2", "12.1", "13.1"] },
    { "id": 12, "tasks": ["13.2", "14.1"] },
    { "id": 13, "tasks": ["14.2", "14.3", "14.4", "14.5"] },
    { "id": 14, "tasks": ["14.6", "14.7"] },
    { "id": 15, "tasks": ["15.1", "15.2", "15.3"] }
  ]
}
```
