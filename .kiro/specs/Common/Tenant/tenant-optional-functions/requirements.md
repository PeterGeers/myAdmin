# Requirements Document

## Introduction

This feature introduces a sub-function toggle mechanism that allows tenant administrators to selectively enable or disable specific functions within already-active modules. Currently the system supports module-level toggles (FIN, STR, ZZP) but has no granularity within a module. Three initial functions are targeted: Activa beheer (Asset Administration), STR Kanaal omzet (STR Channel Revenue), and Generate Invoice (Missing Invoices). The mechanism must be extensible so future functions can be added with minimal effort.

## Glossary

- **Function_Registry**: An in-code registry defining all optional functions with their identifiers, parent module, descriptions, and default enabled state
- **Tenant_Function_Service**: The backend service responsible for reading and writing per-tenant function activation state
- **Function_Guard**: A backend decorator that checks whether a specific optional function is enabled for the current tenant before allowing route access
- **Function_Hook**: A frontend React hook that exposes which optional functions are enabled for the current tenant, used for conditional rendering of UI elements
- **Tenant_Admin**: A user with the Tenant_Admin role who manages configuration for their tenant
- **Optional_Function**: A discrete piece of functionality within a module that can be independently toggled on or off per tenant
- **Parameter_Service**: The existing service that manages scoped configuration parameters with inheritance (user → role → tenant → system)

## Requirements

### Requirement 1: Function Registry Definition

**User Story:** As a developer, I want a centralized registry of optional functions, so that adding new toggleable functions requires only a registry entry.

#### Acceptance Criteria

1. THE Function_Registry SHALL define each Optional_Function with a unique string identifier (1–50 characters, snake_case), a parent module name, a non-empty human-readable label (maximum 100 characters), and a default enabled state (boolean)
2. WHEN a new Optional_Function is added to the Function_Registry, THE system SHALL support toggling that function via tenant parameters without additional database migrations
3. THE Function_Registry SHALL include the following initial entries: `assets` (parent: FIN, default: enabled), `str_channel_revenue` (parent: STR, default: enabled), `generate_invoice` (parent: FIN, default: enabled)
4. IF any function's parent module does not exist in MODULE_REGISTRY, THEN THE Function_Registry SHALL raise a ValueError at application startup indicating the invalid parent module name
5. IF a duplicate function identifier is defined in the Function_Registry, THEN THE system SHALL raise a ValueError at application startup indicating the conflicting identifier

### Requirement 2: Tenant Function Storage

**User Story:** As a system architect, I want per-tenant function activation persisted in the database, so that function toggles survive application restarts and are tenant-isolated.

#### Acceptance Criteria

1. THE Tenant_Function_Service SHALL store function activation state in a `tenant_functions` table with columns: `administration VARCHAR(50) NOT NULL`, `function_name VARCHAR(50) NOT NULL`, `is_active BOOLEAN DEFAULT TRUE`, `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`, `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`, `created_by VARCHAR(255)`
2. THE `tenant_functions` table SHALL include an index on the `administration` column for tenant isolation and a unique constraint on the combination of `administration` and `function_name`
3. WHEN a function has no row in `tenant_functions` for a given tenant, THE Tenant_Function_Service SHALL treat the function as having its default enabled state as defined in the Function_Registry
4. IF a database write operation to `tenant_functions` fails, THEN THE Tenant_Function_Service SHALL return an error response indicating the persistence failure without modifying the existing activation state
5. THE Tenant_Function_Service SHALL access the `tenant_functions` table exclusively through the DatabaseManager abstraction using parameterized queries

### Requirement 3: Backend Function Guard

**User Story:** As a developer, I want a decorator to protect routes behind a function toggle, so that disabled functions return HTTP 403 without executing business logic.

#### Acceptance Criteria

1. WHEN a request reaches a route decorated with Function_Guard(function_name, module_name) for a function that is disabled for the tenant, THE Function_Guard SHALL return HTTP 403 with a JSON error response identifying the disabled function by name, without executing the route handler
2. WHEN a request reaches a route decorated with Function_Guard(function_name, module_name) for a function that is enabled for the tenant, THE Function_Guard SHALL allow the request to proceed to the route handler without modification
3. WHEN a request reaches a route decorated with Function_Guard, THE Function_Guard SHALL first verify that the parent module identified by module_name is active for the tenant before checking function activation status
4. IF the parent module identified by module_name is not active for the tenant, THEN THE Function_Guard SHALL return HTTP 403 with a JSON error response identifying the inactive module by name, without checking function activation status
5. IF the tenant context is not available in the request kwargs, THEN THE Function_Guard SHALL return HTTP 403 with a JSON error response indicating that tenant context is required

### Requirement 4: Frontend Function Visibility

**User Story:** As a user, I want menu items and tabs for disabled functions to be hidden, so that the interface only shows functionality available to my tenant.

#### Acceptance Criteria

1. THE Function_Hook SHALL expose a `hasFunction(functionName: string)` method that returns true only when the function is enabled for the current tenant, and false when the function is disabled or the function state has not yet been fetched
2. WHEN the Function_Hook reports a function as disabled, THE frontend SHALL not render the corresponding navigation element (menu button or tab) in the DOM
3. WHEN the Function_Hook reports `assets` as disabled, THE frontend SHALL not render the Activa beheer menu button
4. WHEN the Function_Hook reports `str_channel_revenue` as disabled, THE frontend SHALL not render the STR Kanaal omzet tab in BankingProcessor
5. WHEN the Function_Hook reports `generate_invoice` as disabled, THE frontend SHALL not render the Generate Invoice menu button
6. WHEN the active tenant changes, THE Function_Hook SHALL re-fetch function state from the backend before exposing updated values
7. IF the Function_Hook fails to fetch function state from the backend, THEN THE Function_Hook SHALL treat all functions as disabled until a successful fetch occurs
8. WHILE the Function_Hook is fetching function state, THE Function_Hook SHALL report all functions as disabled so that no navigation elements for gated functions are rendered during loading

### Requirement 5: Tenant Admin Configuration

**User Story:** As a Tenant_Admin, I want to toggle optional functions on or off for my tenant, so that I can tailor the application to our business needs.

#### Acceptance Criteria

1. THE system SHALL provide an API endpoint `POST /api/tenant/functions` accepting a JSON payload with required fields `function_name` (string, 1-50 characters) and `is_active` (boolean)
2. WHEN a Tenant_Admin sends a valid toggle request, THE Tenant_Function_Service SHALL persist the new activation state for the specified function and tenant, and return a success response containing the function_name and its new is_active value
3. IF a non-Tenant_Admin user attempts to toggle a function, THEN THE system SHALL return HTTP 403
4. IF the function_name in the request is not present in the Function_Registry, THEN THE system SHALL return HTTP 400 with a list of valid function names
5. IF the parent module of the requested function is not active for the tenant, THEN THE system SHALL return HTTP 400 indicating the parent module must be activated first
6. THE system SHALL provide an API endpoint `GET /api/tenant/functions` that returns the activation state of all optional functions for the current tenant, accessible to any authenticated user who has access to the tenant
7. IF the request body is missing, not valid JSON, or omits the required `function_name` or `is_active` fields, THEN THE system SHALL return HTTP 400 with an error message indicating the missing or invalid fields

### Requirement 6: Function-Module Dependency

**User Story:** As a system architect, I want function toggles to respect module activation, so that a function cannot be enabled when its parent module is disabled.

#### Acceptance Criteria

1. WHEN a module is deactivated for a tenant, THE system SHALL preserve all existing `tenant_functions` rows for that module's functions without modifying their `is_active` value
2. IF the parent module of a function is inactive for the current tenant, THEN THE Function_Hook SHALL return false from `hasFunction()` for that function, even if the function's own toggle is set to enabled
3. IF the parent module of a function is inactive for the current tenant, THEN THE `GET /api/tenant/functions` endpoint SHALL include that function in the response with an effective state of disabled and an indication that the parent module is inactive
4. WHEN a module is re-activated for a tenant, THE system SHALL make the previously stored function toggle states effective again without requiring any manual re-enablement of individual functions
5. IF a module is deactivated while one of its child functions has a pending toggle request via `POST /api/tenant/functions`, THEN THE system SHALL reject the request with HTTP 400 indicating the parent module must be activated first

### Requirement 7: Extensibility

**User Story:** As a developer, I want adding a new optional function to require only a registry entry and a decorator on the route, so that the system scales without repeated boilerplate.

#### Acceptance Criteria

1. WHEN a developer adds a new entry to the Function_Registry and applies the Function_Guard decorator to a route, THE system SHALL enforce the toggle for that function (returning HTTP 403 when disabled, passing through when enabled) without requiring database migrations, new API endpoints, or new backend service code
2. THE frontend SHALL dynamically read the list of available functions and their enabled state from the `GET /api/tenant/functions` API response rather than hardcoding function names in navigation visibility logic
3. WHEN the Function_Registry contains a new function, THE `GET /api/tenant/functions` endpoint SHALL include it in the response with its identifier, parent module, label, and current activation state (defaulting to the registry-defined default when no tenant override exists)
4. WHEN a developer wraps a frontend UI element with a `hasFunction` check referencing a newly registered function name, THE Function_Hook SHALL resolve that function's enabled state from the cached API response without requiring new hook definitions or component-specific logic
