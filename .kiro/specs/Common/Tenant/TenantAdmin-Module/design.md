# Tenant Admin Module - Technical Design (Missing Features)

**Status**: Complete
**Created**: February 5, 2026
**Last Updated**: February 8, 2026

---

## 1. Architecture Overview

The Tenant Admin Module extends the existing TenantAdminDashboard with four new feature areas: User Management, Credentials Management, Storage Configuration, and Tenant Settings.

**Pattern Reuse**: This design follows the patterns established in Phase 2.6 (Template Management). See `.kiro/specs/Common/template-preview-validation/design.md` for reference implementation.

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Tenant Admin Frontend (React)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │Template  │  │   User   │  │Credentials│  │ Storage  │          │
│  │  Mgmt    │  │   Mgmt   │  │   Mgmt    │  │  Config  │          │
│  │(Phase2.6)│  │  (NEW)   │  │   (NEW)   │  │  (NEW)   │          │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS/JSON
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Backend API (Flask)                              │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  tenant_admin_routes.py Blueprint                             │ │
│  │  - Template endpoints (Phase 2.6 - existing)                  │ │
│  │  - User Management endpoints (NEW)                            │ │
│  │  - Credentials Management endpoints (NEW)                     │ │
│  │  - Storage Configuration endpoints (NEW)                      │ │
│  │  - Tenant Settings endpoints (NEW)                            │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Services Layer                                               │ │
│  │  - CredentialService (Phase 1 - existing)                     │ │
│  │  - GoogleDriveService (existing)                              │ │
│  │  - CognitoService (NEW - wraps boto3)                         │ │
│  │  - TenantSettingsService (NEW)                                │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
┌──────────────────────┐        ┌──────────────────────┐
│   MySQL Database     │        │   AWS Cognito        │
│  - tenant_credentials│        │  - User Pool         │
│  - tenants           │        │  - User Groups       │
│  - tenant_settings   │        │  - Users             │
└──────────────────────┘        └──────────────────────┘
                │
                ▼
┌──────────────────────┐
│   Google Drive       │
│  - Tenant files      │
│  - Templates         │
└──────────────────────┘
```

### 1.2 Data Flow Example: Create User

1. Tenant Admin fills user creation form
2. Frontend sends POST to `/api/tenant-admin/users`
3. Backend validates request (email, name, role)
4. Backend creates user in Cognito
5. Backend assigns user to tenant (custom:tenants attribute)
6. Backend assigns role to user (Cognito group)
7. Backend sends invitation email via AWS SNS
8. Backend returns success response
9. Frontend displays confirmation

---

## 2. Backend Design

### 2.1 API Endpoints

All endpoints require `@cognito_required(required_roles=['Tenant_Admin'])` and `@tenant_required()` decorators.

#### 2.1.1 User Management Endpoints

**POST /api/tenant-admin/users**

- Create new user in Cognito
- Assign to current tenant
- Assign role
- Send invitation email

Request:

```json
{
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "role": "Finance_CRUD"
}
```

Response:

```json
{
  "success": true,
  "user": {
    "username": "john@example.com",
    "email": "john@example.com",
    "name": "John Doe",
    "status": "FORCE_CHANGE_PASSWORD",
    "tenants": ["GoodwinSolutions"],
    "roles": ["Finance_CRUD"]
  },
  "invitation_sent": true
}
```

**GET /api/tenant-admin/users**

- List users in current tenant
- Filter by role, status
- Paginated results

**Frontend Implementation**: Consider using the generic filter framework (`.kiro/specs/Common/Filters a generic approach/`) for consistent filtering UI across the platform.

Response:

```json
{
  "success": true,
  "users": [
    {
      "username": "john@example.com",
      "email": "john@example.com",
      "name": "John Doe",
      "status": "CONFIRMED",
      "tenants": ["GoodwinSolutions"],
      "roles": ["Finance_CRUD"],
      "created_at": "2026-02-01T10:00:00Z",
      "last_login": "2026-02-08T09:30:00Z"
    }
  ],
  "total": 15,
  "page": 1,
  "per_page": 50
}
```

**PUT /api/tenant-admin/users/<username>/roles**

- Assign/remove roles for user

Request:

```json
{
  "add_roles": ["Finance_Export"],
  "remove_roles": ["Finance_Read"]
}
```

**DELETE /api/tenant-admin/users/<username>**

- Remove user from current tenant
- User data preserved for audit

#### 2.1.2 Credentials Management Endpoints

**POST /api/tenant-admin/credentials**

- Upload Google Drive credentials
- Encrypt and store in database

Request (multipart/form-data):

```
credentials_file: <credentials.json>
token_file: <token.json>
```

Response:

```json
{
  "success": true,
  "credentials": {
    "type": "google_drive",
    "status": "active",
    "created_at": "2026-02-08T10:00:00Z",
    "tested": true,
    "test_result": "Connection successful"
  }
}
```

**GET /api/tenant-admin/credentials**

- List credential status

Response:

```json
{
  "success": true,
  "credentials": [
    {
      "type": "google_drive",
      "status": "active",
      "last_tested": "2026-02-08T09:00:00Z",
      "test_result": "success",
      "expires_at": null
    }
  ]
}
```

**POST /api/tenant-admin/credentials/test**

- Test credential connectivity

Response:

```json
{
  "success": true,
  "test_result": {
    "status": "success",
    "message": "Successfully connected to Google Drive",
    "folders_accessible": 15,
    "tested_at": "2026-02-08T10:05:00Z"
  }
}
```

**POST /api/tenant-admin/credentials/oauth/start**

- Initiate OAuth flow for Google Drive

Response:

```json
{
  "success": true,
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "random_state_token"
}
```

**POST /api/tenant-admin/credentials/oauth/callback**

- Handle OAuth callback

Request:

```json
{
  "code": "oauth_authorization_code",
  "state": "random_state_token"
}
```

#### 2.1.3 Storage Configuration Endpoints

**GET /api/tenant-admin/storage/folders**

- Browse Google Drive folders

Response:

```json
{
  "success": true,
  "folders": [
    {
      "id": "1a2b3c4d5e",
      "name": "Invoices",
      "path": "/myAdmin/Invoices",
      "parent_id": "root"
    }
  ]
}
```

**PUT /api/tenant-admin/storage/config**

- Update storage configuration

Request:

```json
{
  "invoices_folder_id": "1a2b3c4d5e",
  "reports_folder_id": "2b3c4d5e6f",
  "templates_folder_id": "3c4d5e6f7g"
}
```

**POST /api/tenant-admin/storage/test**

- Test folder access

Request:

```json
{
  "folder_id": "1a2b3c4d5e"
}
```

Response:

```json
{
  "success": true,
  "test_result": {
    "accessible": true,
    "writable": true,
    "message": "Folder is accessible and writable"
  }
}
```

**GET /api/tenant-admin/storage/usage**

- Get storage usage statistics

Response:

```json
{
  "success": true,
  "usage": {
    "total_bytes": 1073741824,
    "by_type": {
      "invoices": 536870912,
      "reports": 268435456,
      "templates": 268435456
    },
    "quota_bytes": 10737418240,
    "percentage_used": 10
  }
}
```

#### 2.1.4 Tenant Settings Endpoints

**GET /api/tenant-admin/settings**

- Get tenant settings

Response:

```json
{
  "success": true,
  "settings": {
    "tenant_name": "GoodwinSolutions",
    "contact_email": "admin@goodwin.com",
    "phone": "+31 20 123 4567",
    "address": "Amsterdam, Netherlands",
    "notifications": {
      "enabled": true,
      "frequency": "daily",
      "types": ["errors", "warnings"],
      "recipients": ["admin@goodwin.com"]
    },
    "features": {
      "ai_assistance": true,
      "advanced_reports": true,
      "str_pricing": false
    }
  }
}
```

**PUT /api/tenant-admin/settings**

- Update tenant settings

Request:

```json
{
  "contact_email": "new-admin@goodwin.com",
  "notifications": {
    "frequency": "immediate"
  }
}
```

**GET /api/tenant-admin/activity**

- Get tenant activity logs

Response:

```json
{
  "success": true,
  "activity": {
    "active_users": 5,
    "api_calls_today": 1250,
    "reports_generated_today": 15,
    "invoices_processed_today": 45,
    "by_date": [
      {
        "date": "2026-02-08",
        "api_calls": 1250,
        "reports": 15,
        "invoices": 45
      }
    ]
  }
}
```

### 2.2 Database Schema

**Existing Tables Used** (no new tables needed):

**tenant_credentials** (from Phase 1):

```sql
CREATE TABLE tenant_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    encrypted_value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_cred (administration, credential_type),
    INDEX idx_tenant (administration)
);
```

**tenants** (existing):

```sql
-- Stores tenant metadata
-- Fields: administration, contact_email, phone, address, settings (JSON)
```

**New Column for tenants table**:

```sql
ALTER TABLE tenants ADD COLUMN settings JSON;
-- Stores: notifications, features, preferences
```

### 2.3 Services

#### 2.3.1 CognitoService (NEW)

**Location**: `backend/src/services/cognito_service.py`

**Methods**:

- `create_user(email, first_name, last_name, tenant, role)` - Create user in Cognito
- `list_users(tenant)` - List users for tenant
- `assign_role(username, role)` - Add user to Cognito group
- `remove_role(username, role)` - Remove user from Cognito group
- `remove_user_from_tenant(username, tenant)` - Remove tenant from user's tenants list
- `send_invitation(email, temporary_password)` - Send invitation via SNS

**Pattern**: Wraps boto3 Cognito client, similar to how GoogleDriveService wraps Google API

#### 2.3.2 CredentialService (EXISTING - Phase 1)

**Location**: `backend/src/services/credential_service.py`

**Methods** (already implemented):

- `encrypt_credential(value)` - Encrypt credential
- `decrypt_credential(encrypted_value)` - Decrypt credential
- `store_credential(administration, type, value)` - Store in database
- `get_credential(administration, type)` - Retrieve from database
- `delete_credential(administration, type)` - Delete credential

**Usage**: Reuse for Google Drive credentials

#### 2.3.3 TenantSettingsService (NEW)

**Location**: `backend/src/services/tenant_settings_service.py`

**Methods**:

- `get_settings(administration)` - Get tenant settings
- `update_settings(administration, settings)` - Update settings
- `get_activity(administration, date_range)` - Get activity logs

---

## 3. Frontend Design

### 3.1 Component Architecture

**Pattern Reuse**: Follow Phase 2.6 template management component structure

**Component Hierarchy**:

```
TenantAdminDashboard (existing)
├── TemplateManagement (Phase 2.6 - existing)
├── UserManagement (NEW)
│   ├── UserList
│   ├── UserCreateForm
│   ├── UserRoleEditor
│   └── UserInvitationStatus
├── CredentialsManagement (NEW)
│   ├── CredentialUpload
│   ├── CredentialStatus
│   ├── CredentialTest
│   └── OAuthFlow
├── StorageConfiguration (NEW)
│   ├── FolderBrowser
│   ├── FolderConfig
│   ├── FolderTest
│   └── StorageUsage
└── TenantSettings (NEW)
    ├── GeneralSettings
    ├── NotificationSettings
    ├── FeatureToggles
    └── ActivityDashboard
```

### 3.2 Component Details

#### 3.2.1 UserManagement.tsx

**Location**: `frontend/src/components/TenantAdmin/UserManagement/UserManagement.tsx`

**State**:

```typescript
interface UserManagementState {
  users: User[];
  loading: boolean;
  error: string | null;
  selectedUser: User | null;
  showCreateForm: boolean;
}
```

**Key Functions**:

- `handleCreateUser(userData)` - Create new user
- `handleAssignRole(username, role)` - Assign role to user
- `handleRemoveUser(username)` - Remove user from tenant
- `handleResendInvitation(username)` - Resend invitation email

**Pattern**: Similar to TemplateManagement.tsx from Phase 2.6

#### 3.2.2 CredentialsManagement.tsx

**Location**: `frontend/src/components/TenantAdmin/CredentialsManagement/CredentialsManagement.tsx`

**State**:

```typescript
interface CredentialsState {
  credentials: Credential[];
  loading: boolean;
  error: string | null;
  uploadProgress: number;
  testResult: TestResult | null;
}
```

**Key Functions**:

- `handleUploadCredentials(files)` - Upload credential files
- `handleTestConnection()` - Test credential connectivity
- `handleOAuthStart()` - Start OAuth flow
- `handleOAuthCallback(code)` - Handle OAuth callback

#### 3.2.3 StorageConfiguration.tsx

**Location**: `frontend/src/components/TenantAdmin/StorageConfiguration/StorageConfiguration.tsx`

**State**:

```typescript
interface StorageState {
  folders: Folder[];
  config: StorageConfig;
  loading: boolean;
  error: string | null;
  selectedFolder: Folder | null;
  usage: StorageUsage | null;
}
```

**Key Functions**:

- `handleBrowseFolders()` - Browse Google Drive folders
- `handleSelectFolder(folderId, type)` - Select folder for type
- `handleTestFolder(folderId)` - Test folder access
- `handleSaveConfig()` - Save storage configuration

#### 3.2.4 TenantSettings.tsx

**Location**: `frontend/src/components/TenantAdmin/TenantSettings/TenantSettings.tsx`

**State**:

```typescript
interface SettingsState {
  settings: TenantSettings;
  loading: boolean;
  error: string | null;
  unsavedChanges: boolean;
}
```

**Key Functions**:

- `handleUpdateSettings(settings)` - Update tenant settings
- `handleTestNotification()` - Send test notification
- `handleToggleFeature(feature)` - Enable/disable feature

### 3.3 Routing

**Add to React Router**:

```typescript
<Route path="/tenant-admin" element={<TenantAdminDashboard />}>
  <Route path="templates" element={<TemplateManagement />} /> {/* Phase 2.6 */}
  <Route path="users" element={<UserManagement />} />
  <Route path="credentials" element={<CredentialsManagement />} />
  <Route path="storage" element={<StorageConfiguration />} />
  <Route path="settings" element={<TenantSettings />} />
</Route>
```

### 3.4 API Integration

**Location**: `frontend/src/services/tenantAdminApi.ts`

**Pattern**: Follow Phase 2.6 templateApi.ts structure

```typescript
// User Management
export const createUser = (userData: CreateUserRequest) =>
  api.post("/api/tenant-admin/users", userData);

export const listUsers = (filters?: UserFilters) =>
  api.get("/api/tenant-admin/users", { params: filters });

export const assignRole = (username: string, role: string) =>
  api.put(`/api/tenant-admin/users/${username}/roles`, { add_roles: [role] });

// Credentials Management
export const uploadCredentials = (files: FormData) =>
  api.post("/api/tenant-admin/credentials", files);

export const testCredentials = () =>
  api.post("/api/tenant-admin/credentials/test");

// Storage Configuration
export const browseFolders = () => api.get("/api/tenant-admin/storage/folders");

export const updateStorageConfig = (config: StorageConfig) =>
  api.put("/api/tenant-admin/storage/config", config);

// Tenant Settings
export const getSettings = () => api.get("/api/tenant-admin/settings");

export const updateSettings = (settings: Partial<TenantSettings>) =>
  api.put("/api/tenant-admin/settings", settings);
```

---

## 4. Authentication & Authorization

### 4.1 Decorators

All endpoints use:

```python
@cognito_required(required_roles=['Tenant_Admin'])
@tenant_required()
def endpoint_function(user_email, user_roles, tenant, user_tenants):
    # Implementation
```

**Pattern**: Same as Phase 2.6 template endpoints

### 4.2 Tenant Context

**Validation**: `validate_tenant_access(user_tenants, requested_tenant)`

- Verified in Phase 3.3
- Ensures Tenant Admin can only access their tenant
- Prevents cross-tenant access

**Reference**: `.kiro/specs/Common/Role based access/ROLE_SEPARATION_AND_COMBINATION.md`

### 4.3 Role Checks

**Tenant_Admin Role**:

- Can manage users within their tenant
- Can manage credentials for their tenant
- Can configure storage for their tenant
- Cannot access other tenants
- Cannot access platform settings (SysAdmin only)

**Verified in Phase 3.2/3.3**:

- ✅ Tenant isolation enforced
- ✅ Role separation working correctly
- ✅ Combined roles (TenantAdmin + SysAdmin) work correctly

---

## 5. Integration Points

### 5.1 Phase 2.6 Template Management

**Reuse Patterns**:

- Component structure (upload, preview, validate, approve)
- API integration approach
- Error handling
- Loading states
- Success/error notifications

**Reference**:

- `frontend/src/components/TenantAdmin/TemplateManagement/`
- `backend/src/tenant_admin_routes.py` (template endpoints)

### 5.2 Phase 1 Credentials Infrastructure

**Reuse Services**:

- CredentialService for encryption/decryption
- Database storage in tenant_credentials table
- Encryption key from environment variable

**Reference**:

- `backend/src/services/credential_service.py`
- `.kiro/specs/Common/Credentials/`

### 5.3 Existing TenantAdminDashboard

**Integration**:

- Add new feature cards to dashboard
- Add navigation links
- Maintain consistent UI/UX
- Use existing Chakra UI theme

**Location**: `frontend/src/components/TenantAdmin/TenantAdminDashboard.tsx`

---

## 6. Error Handling

### 6.1 Backend Error Responses

**Standard Error Format**:

```json
{
  "success": false,
  "error": {
    "code": "INVALID_EMAIL",
    "message": "Email address is invalid",
    "details": "Email must be a valid format"
  }
}
```

**Error Codes**:

- `INVALID_EMAIL` - Email format invalid
- `USER_EXISTS` - User already exists
- `ROLE_NOT_FOUND` - Role does not exist
- `CREDENTIAL_INVALID` - Credential file invalid
- `FOLDER_NOT_ACCESSIBLE` - Google Drive folder not accessible
- `UNAUTHORIZED` - User not authorized
- `TENANT_MISMATCH` - Tenant context mismatch

### 6.2 Frontend Error Handling

**Pattern**: Follow Phase 2.6 approach

```typescript
try {
  const response = await createUser(userData);
  showSuccessToast("User created successfully");
} catch (error) {
  if (error.response?.data?.error) {
    showErrorToast(error.response.data.error.message);
  } else {
    showErrorToast("An unexpected error occurred");
  }
}
```

**User Feedback**:

- Toast notifications for success/error
- Inline validation errors
- Loading spinners
- Confirmation dialogs for destructive actions

---

## 7. Testing Strategy

### 7.1 Backend Unit Tests

**Location**: `backend/tests/unit/`

**Test Files**:

- `test_cognito_service.py` - Test CognitoService methods
- `test_tenant_settings_service.py` - Test TenantSettingsService
- `test_tenant_admin_routes.py` - Test API endpoints

**Coverage Target**: 80%+

**Pattern**: Follow Phase 2.6 test structure

### 7.2 Backend Integration Tests

**Location**: `backend/tests/integration/`

**Test Scenarios**:

- Create user → assign role → verify access
- Upload credentials → test connection → verify storage
- Configure folders → test access → verify writes
- Update settings → verify applied

**Pattern**: Use pytest fixtures for database and Cognito mocking

### 7.3 Frontend Unit Tests

**Location**: `frontend/src/components/TenantAdmin/__tests__/`

**Test Files**:

- `UserManagement.test.tsx`
- `CredentialsManagement.test.tsx`
- `StorageConfiguration.test.tsx`
- `TenantSettings.test.tsx`

**Coverage Target**: 80%+

**Pattern**: Follow Phase 2.6 test structure (148 unit tests created)

### 7.4 Frontend Integration Tests

**Location**: `frontend/src/components/TenantAdmin/__tests__/integration/`

**Test Scenarios**:

- Complete user creation flow
- Complete credential upload flow
- Complete storage configuration flow
- Complete settings update flow

**Pattern**: Follow Phase 2.6 integration test structure (11 integration tests)

### 7.5 E2E Tests

**Location**: `frontend/tests/`

**Test Scenarios**:

- End-to-end user management workflow
- End-to-end credential management workflow
- End-to-end storage configuration workflow

**Tool**: Playwright (already configured)

---

## 8. Security Considerations

### 8.1 Credential Security

**Encryption**:

- AES-256 encryption for credentials at rest
- Encryption key from environment variable
- Never expose decrypted credentials to frontend

**Pattern**: Reuse Phase 1 CredentialService

### 8.2 Tenant Isolation

**Enforcement**:

- `@tenant_required()` decorator on all endpoints
- `validate_tenant_access()` checks tenant assignments
- SQL queries filtered by administration column

**Verified**: Phase 3.3 tests confirm isolation works

### 8.3 Role-Based Access

**Enforcement**:

- `@cognito_required(required_roles=['Tenant_Admin'])` on all endpoints
- Cognito groups for role management
- JWT token validation

**Verified**: Phase 3.2 tests confirm role separation works

### 8.4 Input Validation

**Backend**:

- Validate all inputs (email format, file types, folder IDs)
- Sanitize user inputs
- Rate limiting on sensitive endpoints

**Frontend**:

- Client-side validation (immediate feedback)
- Server-side validation (security)
- XSS prevention (React escaping)

---

## 9. Performance Considerations

### 9.1 Response Times

**Targets** (from requirements):

- User list: < 2 seconds
- Credential upload: < 5 seconds
- Folder browsing: < 3 seconds

**Optimization**:

- Pagination for user lists (50 per page)
- Lazy loading for folder trees
- Caching for frequently accessed data

### 9.2 Scalability

**Targets** (from requirements):

- Support 100+ users per tenant
- Support 1000+ folders per tenant
- Handle concurrent credential tests

**Approach**:

- Database indexing on tenant columns
- Connection pooling for Cognito/Google Drive
- Async operations where possible

---

## 10. Deployment Considerations

### 10.1 Environment Variables

**New Variables Needed**:

```bash
# AWS SNS for invitation emails
SNS_INVITATION_TOPIC_ARN=arn:aws:sns:...

# OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://admin.pgeers.nl/oauth/callback
```

**Existing Variables** (reused):

- `COGNITO_USER_POOL_ID` (Phase 3)
- `CREDENTIALS_ENCRYPTION_KEY` (Phase 1)
- `AWS_REGION` (existing)

### 10.2 Database Migrations

**Required**:

```sql
-- Add settings column to tenants table
ALTER TABLE tenants ADD COLUMN settings JSON;

-- No other schema changes needed
```

### 10.3 Railway Deployment

**Phase 5 Tasks**:

- Add new environment variables to Railway
- Run database migration
- Deploy updated backend
- Deploy updated frontend
- Test all features in production

---

## 11. Monitoring & Logging

### 11.1 Logging

**Log Events**:

- User creation/deletion
- Role assignments
- Credential uploads/rotations
- Storage configuration changes
- Settings updates

**Pattern**: Use existing audit_logger from backend

### 11.2 Monitoring

**Metrics to Track**:

- User creation rate
- Credential test success rate
- Storage usage growth
- API error rates

**Tool**: Use existing monitoring infrastructure

---

## 12. Documentation

### 12.1 API Documentation

**Tool**: Flasgger (Swagger) - already configured

**Update**: Add new endpoints to OpenAPI spec

### 12.2 User Documentation

**Create**:

- User Management guide
- Credentials Management guide
- Storage Configuration guide
- Tenant Settings guide

**Location**: `Manuals/` directory (HTML format)

---

## 13. Phase 2.6 Pattern Reuse Summary

**What to Reuse from Template Management**:

1. **Component Structure**:
   - Upload form pattern
   - Validation results display
   - Success/error notifications
   - Loading states

2. **API Integration**:
   - Service layer pattern
   - Error handling approach
   - Response type definitions

3. **Testing Approach**:
   - Unit test structure (148 tests)
   - Integration test structure (11 tests)
   - Mocking patterns

4. **UI/UX Patterns**:
   - Chakra UI components
   - Form validation
   - Confirmation dialogs
   - Toast notifications

**Reference Implementation**:

- `.kiro/specs/Common/template-preview-validation/design.md`
- `frontend/src/components/TenantAdmin/TemplateManagement/`
- `backend/src/tenant_admin_routes.py`

---

## 14. Additional Reusable Patterns & Frameworks

Beyond Phase 2.6 patterns, this design can leverage:

### 14.1 Authentication & Authorization

- **Pattern**: `backend/src/auth/cognito_utils.py` - JWT token validation
- **Pattern**: `backend/src/auth/tenant_context.py` - Tenant context and authorization
- **Decorators**: `@cognito_required`, `@tenant_required`
- **Usage**: All TenantAdmin endpoints use these decorators

### 14.2 Multi-Tenant Data Isolation

- **Pattern**: `tenant_context.py` - Tenant-based query filtering
- **Implementation**: SQL queries filtered by `administration` column
- **Verification**: Phase 3.3 tests confirm isolation works correctly

### 14.3 Frontend Filtering (Recommended)

- **Framework**: `.kiro/specs/Common/Filters a generic approach/`
- **Usage**: User list filtering (role, status, pagination)
- **Benefits**: Consistent UI/UX, reduced code duplication, reusable components
- **Status**: Optional for Phase 4, recommended for consistency

### 14.4 References

- Phase 2.6: Template management patterns
- Phase 3.2: Role separation and combination
- Phase 3.3: Database and Cognito integration tests
- Generic filter framework: `.kiro/specs/Common/Filters a generic approach/`

---

## 15. Revision History

| Version | Date       | Author       | Changes                                 |
| ------- | ---------- | ------------ | --------------------------------------- |
| 0.1     | 2026-02-05 | AI Assistant | Initial draft (incomplete)              |
| 1.0     | 2026-02-08 | AI Assistant | Complete design with Phase 2.6 patterns |
| 1.1     | 2026-02-08 | AI Assistant | Added reusable patterns section         |
