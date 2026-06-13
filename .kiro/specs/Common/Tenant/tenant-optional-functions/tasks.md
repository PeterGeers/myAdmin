# Implementation Plan: Tenant Optional Functions

## Overview

Implement a sub-function toggle mechanism allowing tenant administrators to selectively enable/disable optional functions within active modules. This builds on the existing `MODULE_REGISTRY` / `module_required()` pattern, extending it to finer granularity with a `FUNCTION_REGISTRY`, `TenantFunctionService`, `function_guard` decorator, frontend `useTenantFunctions` hook, and admin API endpoints.

## Tasks

- [x] 1. Create Function Registry and startup validation
  - [x] 1.1 Create `backend/src/services/function_registry.py` with `FUNCTION_REGISTRY` dictionary and `validate_function_registry()` function
    - Define `FunctionDefinition` TypedDict with `parent_module`, `label`, `default_enabled`
    - Add initial entries: `assets` (FIN), `str_channel_revenue` (STR), `generate_invoice` (FIN)
    - Implement `validate_function_registry()`: check parent modules exist in `MODULE_REGISTRY`, check for duplicates, validate identifier format (`^[a-z][a-z0-9_]{0,49}$`), validate label length
    - Raise `ValueError` with descriptive messages on validation failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.2 Write property test for registry validation (Property 1)
    - **Property 1: Registry validation rejects invalid parent modules**
    - Use Hypothesis to generate random registry configurations with invalid module references
    - Verify `validate_function_registry()` raises `ValueError` for any invalid parent module
    - **Validates: Requirements 1.4**

  - [x] 1.3 Add `validate_function_registry()` call to `backend/src/app.py` startup
    - Import and call after `MODULE_REGISTRY` is available
    - Application must fail to start if validation fails
    - _Requirements: 1.4, 1.5_

- [x] 2. Create database table and Tenant Function Service
  - [x] 2.1 Create database migration script for `tenant_functions` table
    - Create `backend/scripts/database/apply_tenant_functions_migration.py`
    - Schema: `id INT AUTO_INCREMENT PRIMARY KEY`, `administration VARCHAR(50) NOT NULL`, `function_name VARCHAR(50) NOT NULL`, `is_active BOOLEAN DEFAULT TRUE`, `created_at TIMESTAMP`, `updated_at TIMESTAMP`, `created_by VARCHAR(255)`
    - Add `INDEX idx_administration (administration)` and `UNIQUE KEY uq_admin_function (administration, function_name)`
    - Use `DatabaseMigration` pattern from existing migration scripts
    - _Requirements: 2.1, 2.2_

  - [x] 2.2 Create `backend/src/services/tenant_function_service.py` with `TenantFunctionService` class
    - Implement `get_function_state(tenant, function_name)` — returns effective enabled state
    - Implement `get_all_functions(tenant)` — merges registry with DB overrides + module state
    - Implement `set_function_state(tenant, function_name, is_active, user_email)` — INSERT ON DUPLICATE KEY UPDATE
    - Implement `is_function_enabled(tenant, function_name, module_name)` — checks module + function state
    - Use `DatabaseManager` with parameterized queries; fallback to registry defaults on DB failure
    - _Requirements: 2.3, 2.4, 2.5, 6.1, 6.2, 6.3, 6.4_

  - [x] 2.3 Write property test for default state resolution (Property 2)
    - **Property 2: Default state resolution when no override exists**
    - Use Hypothesis to generate random tenant/function pairs; mock DB to return no rows
    - Verify `get_function_state()` returns `default_enabled` from registry
    - **Validates: Requirements 2.3**

  - [x] 2.4 Write property test for write failure preservation (Property 3)
    - **Property 3: Write failure preserves existing state**
    - Use Hypothesis to generate random states; mock DB write to raise exception
    - Verify subsequent read returns original state unchanged
    - **Validates: Requirements 2.4**

  - [x] 2.5 Write property test for toggle round-trip (Property 8)
    - **Property 8: Toggle round-trip persistence**
    - Use Hypothesis to generate random function names and boolean values
    - Verify after successful `set_function_state`, `get_function_state` returns the new value
    - **Validates: Requirements 5.2**

  - [x] 2.6 Write property test for module deactivation preservation (Property 11)
    - **Property 11: Module deactivation/re-activation preserves function toggles**
    - Use Hypothesis to generate random function states; simulate module deactivation/re-activation cycle
    - Verify stored toggle states remain unchanged and become effective again
    - **Validates: Requirements 6.1, 6.4**

  - [x] 2.7 Write property test for inactive parent module override (Property 12)
    - **Property 12: Inactive parent module overrides function toggle**
    - Use Hypothesis to generate functions with `is_active=True` but inactive parent module
    - Verify effective state is `false`
    - **Validates: Requirements 6.2, 6.3**

- [x] 3. Checkpoint - Backend service layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Function Guard decorator
  - [x] 4.1 Create `backend/src/services/function_guard.py` with `function_guard(function_name, module_name)` decorator
    - Check order: tenant context → module active → function enabled
    - Return 403 with appropriate JSON error messages for each failure case
    - Must be placed after `@tenant_required()` in decorator stack
    - Use `has_module()` from `module_registry` for module check
    - Use `TenantFunctionService.get_function_state()` for function check
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.2 Write property test for guard blocking disabled functions (Property 4)
    - **Property 4: Guard blocks disabled functions**
    - Use Hypothesis to generate random tenant/function combinations where function is disabled
    - Verify decorator returns HTTP 403 without invoking route handler
    - **Validates: Requirements 3.1**

  - [x] 4.3 Write property test for guard passing enabled functions (Property 5)
    - **Property 5: Guard passes enabled functions**
    - Use Hypothesis to generate random tenant/function combinations where both module and function are active
    - Verify decorator invokes route handler with original arguments unmodified
    - **Validates: Requirements 3.2**

  - [x] 4.4 Write property test for guard module priority (Property 6)
    - **Property 6: Guard prioritizes module check over function check**
    - Use Hypothesis to generate random functions with inactive parent modules
    - Verify 403 response identifies inactive module by name regardless of function state
    - **Validates: Requirements 3.3, 3.4**

- [x] 5. Implement Admin API endpoints
  - [x] 5.1 Create `backend/src/routes/tenant_function_routes.py` with GET and POST endpoints
    - Register `tenant_function_bp` blueprint
    - `GET /api/tenant/functions`: return all functions with state for current tenant (any authenticated user)
    - `POST /api/tenant/functions`: toggle function (Tenant_Admin only)
    - POST validation: check Tenant_Admin role, validate function_name in registry, check parent module active, validate request body
    - Response format: `{"success": true, "data": [...]}` per API conventions
    - Use `@cognito_required(required_permissions=[])` and `@tenant_required()` decorators
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.5_

  - [x] 5.2 Register `tenant_function_bp` in `backend/src/app.py`
    - Import and register blueprint alongside existing `tenant_module_bp`
    - _Requirements: 5.1, 5.6_

  - [x] 5.3 Write property test for invalid function name rejection (Property 9)
    - **Property 9: Invalid function name returns 400 with valid names**
    - Use Hypothesis to generate random strings not in `FUNCTION_REGISTRY`
    - Verify POST returns HTTP 400 with list of valid function names
    - **Validates: Requirements 5.4**

  - [x] 5.4 Write property test for GET completeness (Property 10)
    - **Property 10: GET returns complete function state from registry**
    - Use Hypothesis to generate random tenant states
    - Verify GET returns exactly the set of functions in `FUNCTION_REGISTRY` with correct effective states
    - **Validates: Requirements 5.6, 7.3**

  - [x] 5.5 Write unit tests for admin API endpoints
    - Test non-admin user gets 403 on POST
    - Test missing request body returns 400
    - Test parent module inactive during toggle returns 400
    - Test successful toggle returns updated state
    - _Requirements: 5.3, 5.5, 5.7_

- [x] 6. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Frontend hook and conditional rendering
  - [x] 7.1 Create `frontend/src/hooks/useTenantFunctions.ts` with `useTenantFunctions` hook
    - Define `FunctionState` interface with `function_name`, `parent_module`, `label`, `is_active`, `module_active`, `effective`
    - Implement hook following `useTenantModules` pattern: fetch on mount, re-fetch on tenant change
    - Expose `hasFunction(functionName)` returning `effective` state or `false` during loading/error
    - Use `authenticatedGet('/api/tenant/functions')` from existing `apiService`
    - _Requirements: 4.1, 4.6, 4.7, 4.8_

  - [x] 7.2 Write property test for hasFunction logic (Property 7)
    - **Property 7: hasFunction reflects effective state or safe default**
    - Use fast-check to generate random function state arrays and queries
    - Verify `hasFunction` returns `effective` when loaded, `false` during loading/error
    - **Validates: Requirements 4.1, 4.7, 4.8**

  - [x] 7.3 Add conditional rendering for navigation elements using `hasFunction`
    - Hide Activa beheer menu button when `hasFunction('assets')` is false
    - Hide STR Kanaal omzet tab in BankingProcessor when `hasFunction('str_channel_revenue')` is false
    - Hide Generate Invoice menu button when `hasFunction('generate_invoice')` is false
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 7.2, 7.4_

  - [x] 7.4 Write component tests for conditional rendering
    - Test navigation buttons hidden/shown based on function state
    - Test loading state hides gated elements
    - Test error state hides gated elements
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.7, 4.8_

- [x] 8. Apply Function Guard to existing routes
  - [x] 8.1 Add `@function_guard` decorator to protected routes
    - Add `@function_guard('assets', 'FIN')` to asset-related routes
    - Add `@function_guard('str_channel_revenue', 'STR')` to STR channel revenue routes
    - Add `@function_guard('generate_invoice', 'FIN')` to invoice generation routes
    - Ensure decorator placement after `@tenant_required()` in decorator stack
    - _Requirements: 3.1, 3.2, 7.1_

  - [x] 8.2 Write integration tests for guard on actual routes
    - Test guard blocks access when function disabled via test client
    - Test guard passes access when function enabled
    - Test guard returns correct error messages
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 9. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Flask/Python with MySQL, pytest + Hypothesis for testing
- The frontend uses React/TypeScript with Chakra UI, Vitest + fast-check for testing
- Follow existing patterns: `MODULE_REGISTRY`, `module_required()`, `useTenantModules`, tenant isolation via `administration` column
- Database access via `DatabaseManager` with parameterized queries only

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5", "2.6", "2.7", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.4", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "5.5", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "8.1"] },
    { "id": 6, "tasks": ["7.4", "8.2"] }
  ]
}
```
