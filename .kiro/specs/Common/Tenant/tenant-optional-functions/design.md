# Design Document: Tenant Optional Functions

## Overview

This feature introduces a sub-function toggle mechanism that allows tenant administrators to selectively enable or disable specific optional functions within already-active modules. It builds on the existing `MODULE_REGISTRY` and `module_required()` decorator pattern, extending it to a finer granularity.

The system consists of five interconnected components:

1. **Function Registry** — an in-code Python dictionary defining all optional functions
2. **Tenant Function Service** — a backend service managing per-tenant activation state in a `tenant_functions` table
3. **Function Guard** — a route decorator that enforces function-level access control
4. **Function Hook** — a React hook exposing function availability to the frontend
5. **Admin API** — endpoints for Tenant Admins to toggle functions

### Design Rationale

The design mirrors the existing `MODULE_REGISTRY` / `module_required()` pattern to keep cognitive load low for developers. The key differences are:

- Functions live _inside_ modules — a function can only be active if its parent module is active
- Storage uses a dedicated `tenant_functions` table (not `tenant_modules`) to maintain separation of concerns
- Defaults come from the registry; only overrides are stored in the database

## Architecture

```mermaid
graph TD
    subgraph Frontend
        A[App.tsx / Navigation] -->|uses| B[useTenantFunctions hook]
        B -->|fetches| C[GET /api/tenant/functions]
    end

    subgraph Backend
        C --> D[tenant_function_routes.py]
        D -->|reads/writes| E[TenantFunctionService]
        E -->|queries| F[(tenant_functions table)]
        E -->|reads| G[FUNCTION_REGISTRY]
        E -->|checks| H[has_module via module_registry]

        I[Protected Route] -->|decorated with| J[@function_guard]
        J -->|checks module| H
        J -->|checks function| E
    end

    subgraph Admin
        K[Tenant Admin UI] -->|POST| L[POST /api/tenant/functions]
        L --> D
    end
```

### Request Flow

1. User navigates to a page → `useTenantFunctions` hook fetches function state from `GET /api/tenant/functions`
2. Frontend conditionally renders navigation elements based on `hasFunction()` results
3. When user accesses a guarded route → `@function_guard` checks module then function activation
4. Tenant Admin toggles a function → `POST /api/tenant/functions` updates `tenant_functions` table

## Components and Interfaces

### 1. Function Registry (`backend/src/services/function_registry.py`)

```python
from typing import Dict, TypedDict

class FunctionDefinition(TypedDict):
    parent_module: str
    label: str
    default_enabled: bool

FUNCTION_REGISTRY: Dict[str, FunctionDefinition] = {
    'assets': {
        'parent_module': 'FIN',
        'label': 'Activa beheer',
        'default_enabled': True,
    },
    'str_channel_revenue': {
        'parent_module': 'STR',
        'label': 'STR Kanaal omzet',
        'default_enabled': True,
    },
    'generate_invoice': {
        'parent_module': 'FIN',
        'label': 'Generate Invoice',
        'default_enabled': True,
    },
}
```

**Startup Validation** — At application startup (`app.py`), call `validate_function_registry()` which:

- Checks each function's `parent_module` exists in `MODULE_REGISTRY`; raises `ValueError` if not
- Checks for duplicate identifiers; raises `ValueError` if found
- Validates identifier format: 1–50 characters, snake*case (`^[a-z]a-z0-9*]{0,49}$`)
- Validates label is non-empty and ≤ 100 characters

### 2. Tenant Function Service (`backend/src/services/tenant_function_service.py`)

```python
class TenantFunctionService:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_function_state(self, tenant: str, function_name: str) -> bool:
        """Returns effective enabled state for a single function."""

    def get_all_functions(self, tenant: str) -> list[dict]:
        """Returns all functions with effective state, respecting module activation."""

    def set_function_state(self, tenant: str, function_name: str,
                           is_active: bool, user_email: str) -> dict:
        """Persists toggle state. Returns updated record."""

    def is_function_enabled(self, tenant: str, function_name: str,
                            module_name: str) -> tuple[bool, str | None]:
        """Checks module + function state. Returns (enabled, error_reason)."""
```

**Behavior:**

- `get_all_functions` queries `tenant_functions` for the tenant, merges with `FUNCTION_REGISTRY` defaults, and checks `has_module()` for each function's parent
- When no row exists for a function/tenant pair, the registry's `default_enabled` is used
- `set_function_state` uses `INSERT ... ON DUPLICATE KEY UPDATE` pattern

### 3. Function Guard Decorator (`backend/src/services/function_guard.py`)

```python
def function_guard(function_name: str, module_name: str):
    """
    Decorator that checks function activation for the current tenant.
    Must be placed after @tenant_required() in the decorator stack.

    Usage:
        @route_bp.route('/api/fin/assets', methods=['GET'])
        @cognito_required(required_permissions=['finance_read'])
        @tenant_required()
        @function_guard('assets', 'FIN')
        def get_assets(user_email, user_roles, tenant, user_tenants):
            ...
    """
```

**Check Order:**

1. Extract `tenant` from `kwargs` — if missing, return 403 with "Tenant context required"
2. Check `has_module(db, tenant, module_name)` — if inactive, return 403 with module name
3. Check `TenantFunctionService.get_function_state(tenant, function_name)` — if disabled, return 403 with function name

**Response Format:**

```json
{"success": false, "error": "Function 'assets' is disabled for this tenant"}
{"success": false, "error": "Module 'FIN' is not active for this tenant"}
{"success": false, "error": "Tenant context required"}
```

### 4. Frontend Function Hook (`frontend/src/hooks/useTenantFunctions.ts`)

```typescript
export interface FunctionState {
  function_name: string;
  parent_module: string;
  label: string;
  is_active: boolean;
  module_active: boolean;
  effective: boolean; // is_active AND module_active
}

export function useTenantFunctions() {
  // State: functions map, loading, error
  // Re-fetches when currentTenant changes (via useTenant())

  return {
    functions: FunctionState[],
    loading: boolean,
    error: string | null,
    hasFunction: (functionName: string) => boolean,  // returns effective state
  };
}
```

**Behavior:**

- Returns `false` from `hasFunction()` while loading or on error (safe default)
- Re-fetches on tenant change via `useTenant()` context dependency
- Caches response in component state; no global cache (matches `useTenantModules` pattern)

### 5. Admin API Endpoints (`backend/src/routes/tenant_function_routes.py`)

#### GET /api/tenant/functions

Returns all optional functions with their state for the current tenant.

```python
@tenant_function_bp.route('/api/tenant/functions', methods=['GET'])
@cognito_required(required_permissions=[])
@tenant_required()
def get_tenant_functions(user_email, user_roles, tenant, user_tenants):
    ...
```

**Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "function_name": "assets",
      "parent_module": "FIN",
      "label": "Activa beheer",
      "is_active": true,
      "module_active": true,
      "effective": true
    },
    {
      "function_name": "str_channel_revenue",
      "parent_module": "STR",
      "label": "STR Kanaal omzet",
      "is_active": true,
      "module_active": false,
      "effective": false
    }
  ]
}
```

#### POST /api/tenant/functions

Toggles a function for the current tenant. Restricted to Tenant_Admin role.

```python
@tenant_function_bp.route('/api/tenant/functions', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def toggle_tenant_function(user_email, user_roles, tenant, user_tenants):
    ...
```

**Request Body:**

```json
{
  "function_name": "assets",
  "is_active": false
}
```

**Success Response (200):**

```json
{
  "success": true,
  "data": {
    "function_name": "assets",
    "is_active": false
  }
}
```

**Error Responses:**

- 403: Non-Tenant_Admin user
- 400: Invalid function_name (includes list of valid names)
- 400: Parent module inactive
- 400: Missing/invalid request body

## Data Models

### tenant_functions Table

```sql
CREATE TABLE tenant_functions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(50) NOT NULL,
    function_name VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    INDEX idx_administration (administration),
    UNIQUE KEY uq_admin_function (administration, function_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Design Decisions:**

- No foreign key to `tenant_modules` — the relationship is enforced in application logic via `FUNCTION_REGISTRY[fn].parent_module`
- `administration` column included per tenant isolation pattern (defense-in-depth)
- Only _overrides_ are stored; absence of a row means the registry default applies
- When a module is deactivated, `tenant_functions` rows are preserved — the `GET` endpoint reports `effective: false` and the guard blocks access, but stored state is retained for when the module is re-activated

### Function Registry Type (Python)

```python
FUNCTION_REGISTRY: Dict[str, FunctionDefinition]
# Key: function identifier (snake_case, 1-50 chars)
# Value: FunctionDefinition with parent_module, label, default_enabled
```

### Frontend Types

```typescript
interface FunctionState {
  function_name: string;
  parent_module: string;
  label: string;
  is_active: boolean; // stored toggle value (or registry default)
  module_active: boolean; // parent module active for tenant
  effective: boolean; // is_active && module_active
}
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property 1: Registry validation rejects invalid parent modules

_For any_ function definition with a `parent_module` value that does not exist in `MODULE_REGISTRY`, calling `validate_function_registry()` SHALL raise a `ValueError` indicating the invalid parent module name.

**Validates: Requirements 1.4**

### Property 2: Default state resolution when no override exists

_For any_ function in `FUNCTION_REGISTRY` and any tenant that has no corresponding row in `tenant_functions`, `get_function_state()` SHALL return the `default_enabled` value defined in the registry.

**Validates: Requirements 2.3**

### Property 3: Write failure preserves existing state

_For any_ tenant and function with an existing activation state, if a database write operation fails during `set_function_state()`, then a subsequent `get_function_state()` call SHALL return the original state unchanged.

**Validates: Requirements 2.4**

### Property 4: Guard blocks disabled functions

_For any_ function that is disabled for a tenant (either by toggle or by inactive parent module), the `function_guard` decorator SHALL return HTTP 403 without invoking the route handler.

**Validates: Requirements 3.1**

### Property 5: Guard passes enabled functions

_For any_ function that is enabled for a tenant (both function toggle active and parent module active), the `function_guard` decorator SHALL invoke the route handler with the original arguments unmodified.

**Validates: Requirements 3.2**

### Property 6: Guard prioritizes module check over function check

_For any_ function whose parent module is inactive for the tenant, the `function_guard` decorator SHALL return HTTP 403 with an error message identifying the inactive module by name, regardless of the function's own toggle state.

**Validates: Requirements 3.3, 3.4**

### Property 7: hasFunction reflects effective state or safe default

_For any_ function name, `hasFunction()` SHALL return the `effective` state (is_active AND module_active) when function data has been successfully loaded, and SHALL return `false` when the hook is in a loading state or has encountered a fetch error.

**Validates: Requirements 4.1, 4.7, 4.8**

### Property 8: Toggle round-trip persistence

_For any_ valid function name and boolean value, after a successful `set_function_state(tenant, function_name, is_active)`, a subsequent `get_function_state(tenant, function_name)` SHALL return the newly set `is_active` value.

**Validates: Requirements 5.2**

### Property 9: Invalid function name returns 400 with valid names

_For any_ string that is not a key in `FUNCTION_REGISTRY`, the `POST /api/tenant/functions` endpoint SHALL return HTTP 400 with a response body containing the list of valid function names.

**Validates: Requirements 5.4**

### Property 10: GET returns complete function state from registry

_For any_ tenant, the `GET /api/tenant/functions` endpoint SHALL return exactly the set of functions defined in `FUNCTION_REGISTRY`, each annotated with its identifier, parent module, label, and current effective activation state.

**Validates: Requirements 5.6, 7.3**

### Property 11: Module deactivation/re-activation preserves function toggles

_For any_ tenant with function overrides stored in `tenant_functions`, deactivating and then re-activating the parent module SHALL result in the same function toggle states being effective as before deactivation — no manual re-enablement required.

**Validates: Requirements 6.1, 6.4**

### Property 12: Inactive parent module overrides function toggle

_For any_ function whose `is_active` value is `true` in `tenant_functions`, if the function's parent module is inactive for the tenant, the effective state SHALL be `false`.

**Validates: Requirements 6.2, 6.3**

## Error Handling

| Scenario                          | Component             | Response                                                   |
| --------------------------------- | --------------------- | ---------------------------------------------------------- |
| Invalid parent_module in registry | Startup validation    | `ValueError` — application fails to start                  |
| Duplicate function identifier     | Startup validation    | `ValueError` — application fails to start                  |
| DB connection failure on read     | TenantFunctionService | Return registry defaults (graceful degradation)            |
| DB write failure on toggle        | TenantFunctionService | Return 500 with error message; existing state unchanged    |
| Missing tenant context            | function_guard        | HTTP 403: "Tenant context required"                        |
| Inactive parent module            | function_guard        | HTTP 403: "Module '{name}' is not active for this tenant"  |
| Disabled function                 | function_guard        | HTTP 403: "Function '{name}' is disabled for this tenant"  |
| Non-Tenant_Admin toggles          | POST endpoint         | HTTP 403: "Access denied"                                  |
| Invalid function_name             | POST endpoint         | HTTP 400: includes list of valid function names            |
| Parent module inactive on toggle  | POST endpoint         | HTTP 400: "Parent module '{name}' must be activated first" |
| Missing/invalid request body      | POST endpoint         | HTTP 400: indicates missing or invalid fields              |
| Frontend fetch failure            | useTenantFunctions    | All functions report as disabled (safe default)            |
| Frontend loading state            | useTenantFunctions    | All functions report as disabled (safe default)            |

## Testing Strategy

### Property-Based Tests (Backend — pytest + Hypothesis)

Each correctness property above maps to a property-based test with minimum 100 iterations. The property tests target the pure logic layer:

- **Function Registry Validation** (Properties 1): Generate random registry configurations with invalid modules
- **Default Resolution** (Property 2): Generate random tenant/function pairs without DB overrides
- **State Persistence** (Properties 3, 8): Generate random toggle sequences, verify round-trip
- **Guard Logic** (Properties 4, 5, 6): Generate random tenant/function/module state combinations, verify guard behavior with mocked DB
- **Effective State Calculation** (Properties 10, 12): Generate random module/function state matrices, verify effective state computation
- **Module Lifecycle** (Property 11): Generate random function states, simulate module deactivation/re-activation cycle

**Library:** Hypothesis (already used in this project — see `.hypothesis/` directory and existing `test_parameter_service_props.py`)

**Tag format:** `# Feature: tenant-optional-functions, Property {N}: {description}`

### Property-Based Tests (Frontend — Vitest + fast-check)

- **hasFunction Logic** (Property 7): Generate random function state arrays and function name queries, verify correct boolean return
- **Invalid Function Names** (Property 9): Generate random strings, verify rejection behavior

**Library:** fast-check via `@fast-check/vitest` (already configured in this project)

### Unit Tests (Example-Based)

- Initial registry entries exist with correct values (Req 1.3)
- Specific UI elements hidden/shown for each function (Req 4.3, 4.4, 4.5)
- Tenant change triggers re-fetch (Req 4.6)
- Non-admin user gets 403 on POST (Req 5.3)
- Missing request body returns 400 (Req 5.7)
- Module inactive during toggle attempt returns 400 (Req 6.5)

### Integration Tests

- End-to-end toggle flow: POST toggle → GET verifies new state
- Guard decorator on actual Flask route with test client
- Database migration creates table with correct schema and indexes
- New registry entry works without migrations (Req 7.1)

### Component Tests (Frontend — Vitest + React Testing Library)

- `useTenantFunctions` hook fetches on mount and tenant change
- Navigation buttons hidden/shown based on function state
- Loading and error states handled correctly
