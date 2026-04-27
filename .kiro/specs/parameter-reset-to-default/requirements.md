# Requirements Document

## Introduction

The Parameter Management edit modal currently has a "Delete" button for tenant-scope parameters that removes the tenant override, causing the system to fall back to the CODE_DEFAULTS value. While functionally correct, the "Delete" label is misleading — the user is not destroying data, they are reverting to a known default. This feature replaces the Delete button with a "Reset to Default" action that clearly communicates intent and shows the user what default value they are reverting to.

Additionally, the current Actions column in the parameter table (with Customize and Reset inline buttons) is inconsistent with the standard UI pattern used across all other tables, where row-click opens a modal and all actions happen inside the modal. This feature removes the Actions column entirely and consolidates all parameter interactions into the modal.

The backend already supports the core operation (DELETE endpoint removes the tenant override, `get_param()` falls back to CODE_DEFAULTS). The main work is adding a new endpoint to fetch the default value for preview, reworking the frontend modal UX to frame the action as a reset rather than a deletion, and removing the inline action buttons.

## Glossary

- **Parameter_Management_Modal**: The Chakra UI modal dialog opened by clicking a parameter row in the ParameterManagement component, used for viewing and editing parameter values.
- **Parameter_Service**: Python service that resolves flat key-value parameters by walking the scope inheritance chain (user → role → tenant → system) with CODE_DEFAULTS as the final fallback.
- **CODE_DEFAULTS**: In-code Python dictionary in `parameter_service.py` that provides system-scope fallback values for all known parameters. When a tenant override is deleted, `get_param()` returns the CODE_DEFAULT value.
- **Tenant_Override**: A parameter row in the `parameters` table with `scope = 'tenant'` that overrides the system default or CODE_DEFAULT value for a specific tenant.
- **Default_Value**: The value a parameter resolves to when no tenant override exists — either a system-scope DB row or a CODE_DEFAULTS entry.
- **Reset_Confirmation_Dialog**: An AlertDialog that shows the current tenant value alongside the default value, asking the user to confirm the reset action before deleting the tenant override.
- **Parameter_Admin_API**: The Flask Blueprint at `/api/tenant-admin/parameters` providing CRUD endpoints for parameter management.

## Requirements

### Requirement 1: Fetch Default Value Endpoint

**User Story:** As a tenant administrator, I want to see the default value of a parameter before resetting it, so that I can make an informed decision about whether to revert my customization.

#### Acceptance Criteria

1. WHEN a GET request is made to the default value endpoint with a namespace and key, THE Parameter_Admin_API SHALL return the default value for that parameter by resolving the CODE_DEFAULTS entry or system-scope DB row.
2. WHEN a default value exists for the requested namespace and key, THE Parameter_Admin_API SHALL return a response containing the default value, value_type, and the source of the default (code_default or system).
3. WHEN no default value exists for the requested namespace and key, THE Parameter_Admin_API SHALL return a response indicating that no default is available.
4. THE default value endpoint SHALL require the Tenant_Admin role, consistent with other parameter administration endpoints.
5. WHEN the parameter has is_secret set to true, THE Parameter_Admin_API SHALL mask the default value in the response for non-SysAdmin users.

### Requirement 2: Replace Delete Button with Reset to Default in Modal

**User Story:** As a tenant administrator, I want the Delete button in the edit modal replaced with a "Reset to Default" button, so that the action label accurately describes what happens (reverting to the default value rather than destroying data).

#### Acceptance Criteria

1. WHEN a tenant-override parameter is opened in the Parameter_Management_Modal and a default value exists, THE Parameter_Management_Modal SHALL display a "Reset to Default" button instead of the current "Delete" button.
2. WHEN a tenant-override parameter is opened in the Parameter_Management_Modal and no default value exists, THE Parameter_Management_Modal SHALL display a "Delete" button with the current delete behavior (the parameter has no fallback value).
3. WHEN the "Reset to Default" button is clicked, THE Parameter_Management_Modal SHALL fetch the default value from the backend and display the Reset_Confirmation_Dialog before executing the reset.
4. THE Parameter_Management_Modal SHALL NOT display a "Reset to Default" or "Delete" button for system-scope or code_default parameters (parameters without a tenant-scope DB id).

### Requirement 3: Reset Confirmation Dialog with Value Comparison

**User Story:** As a tenant administrator, I want to see my current value compared to the default value before confirming a reset, so that I understand the impact of the action.

#### Acceptance Criteria

1. WHEN the Reset_Confirmation_Dialog is displayed, THE Reset_Confirmation_Dialog SHALL show the parameter's namespace and key as a heading.
2. WHEN the Reset_Confirmation_Dialog is displayed, THE Reset_Confirmation_Dialog SHALL show the current tenant value labeled as "Current value".
3. WHEN the Reset_Confirmation_Dialog is displayed, THE Reset_Confirmation_Dialog SHALL show the default value labeled as "Default value".
4. WHEN the parameter value_type is json, THE Reset_Confirmation_Dialog SHALL format both the current and default values as indented JSON for readability.
5. WHEN the parameter has is_secret set to true, THE Reset_Confirmation_Dialog SHALL display masked values (showing '**\*\*\*\***') for non-SysAdmin users.
6. WHEN the user confirms the reset in the Reset_Confirmation_Dialog, THE system SHALL call the existing DELETE endpoint to remove the tenant override, then refresh the parameter list.
7. WHEN the user cancels the reset in the Reset_Confirmation_Dialog, THE system SHALL close the dialog without making any changes.

### Requirement 4: Remove Actions Column, Add Button, and Consolidate into Modal

**User Story:** As a tenant administrator, I want all parameter actions (edit, reset, customize) accessible through the row-click modal, consistent with the standard table UI pattern used across all other tables in the application.

#### Acceptance Criteria

1. THE parameter table SHALL NOT display an Actions column with inline Customize or Reset buttons.
2. THE parameter table SHALL NOT display an "Add Parameter" button, since all parameters are defined in CODE_DEFAULTS and tenant admins customize existing parameters through the modal.
3. WHEN a system-scope or code_default parameter row is clicked, THE Parameter_Management_Modal SHALL open in read-only mode with a "Customize" button that creates a tenant-scope copy (replacing the former inline Customize button).
4. WHEN a tenant-override parameter row is clicked, THE Parameter_Management_Modal SHALL open in edit mode with Save and Reset to Default (or Delete) buttons.
5. ALL parameter rows SHALL be clickable to open the modal, regardless of scope_origin.

### Requirement 5: JSON Value Validation and Formatting in Modal

**User Story:** As a tenant administrator, I want real-time validation and formatting assistance when editing JSON parameters, so that I cannot accidentally save invalid JSON that breaks table configurations or other JSON-driven features.

#### Acceptance Criteria

1. WHEN a parameter with value_type json is being edited in the Parameter_Management_Modal, THE modal SHALL validate the JSON on every change and display an error message below the textarea when the JSON is invalid.
2. WHEN the JSON in the textarea is invalid, THE Parameter_Management_Modal SHALL disable the Save button to prevent saving broken JSON.
3. WHEN the JSON in the textarea is invalid, THE Parameter_Management_Modal SHALL display a descriptive error message indicating the parse error (e.g., "Invalid JSON: Unexpected token at position 42").
4. WHEN the JSON in the textarea is valid, THE Parameter_Management_Modal SHALL clear any error message and enable the Save button.
5. THE Parameter_Management_Modal SHALL provide a "Format" button next to the JSON textarea that re-indents the current JSON content for readability, enabled only when the JSON is valid.

### Requirement 6: Frontend API Service Extension

**User Story:** As a developer, I want a frontend service function to fetch the default value for a parameter, so that the reset confirmation dialog can display the default value preview.

#### Acceptance Criteria

1. THE parameterService module SHALL export a function to fetch the default value for a given namespace and key from the default value endpoint.
2. WHEN the default value fetch succeeds, THE function SHALL return the default value, value_type, and source.
3. WHEN the default value fetch fails or returns no default, THE function SHALL return a result indicating no default is available.

### Requirement 6: Post-Reset Feedback

**User Story:** As a tenant administrator, I want clear feedback after resetting a parameter, so that I know the action completed successfully and the parameter now shows its default value.

#### Acceptance Criteria

1. WHEN a parameter is successfully reset to its default, THE system SHALL display a success toast notification indicating the parameter was reset.
2. WHEN a parameter reset fails, THE system SHALL display an error toast notification with the error message.
3. WHEN a parameter is successfully reset, THE system SHALL refresh the parameter list so the parameter row reflects the new scope_origin (system or code_default) and the default value.
4. WHEN a parameter is successfully reset from within the edit modal, THE system SHALL close the modal and the confirmation dialog after the reset completes.
