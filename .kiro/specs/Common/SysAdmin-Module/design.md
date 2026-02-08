# SysAdmin Module - Technical Design

**Status**: Updated
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## 1. Architecture Overview

The SysAdmin Module provides platform-level administration through a dedicated UI and API layer. It integrates with AWS Cognito for role management and MySQL for tenant metadata storage.

**Key Principle**: SysAdmin manages platform (tenants, roles, configuration) but does NOT access tenant business data. Tenant_Admin manages their tenant's data and users.

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SysAdmin Frontend (React)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Tenant     │  │     Role     │  │   Module     │      │
│  │  Management  │  │  Management  │  │  Management  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  SysAdmin API (Flask Blueprint)              │
│  /api/sysadmin/tenants     /api/sysadmin/roles              │
│  /api/sysadmin/billing (future)  /api/sysadmin/audit (future)│
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐
         │  MySQL   │  │ Cognito  │  │ Railway  │
         │ Database │  │  Groups  │  │   Logs   │
         └──────────┘  └──────────┘  └──────────┘
```

### 1.2 Component Responsibilities

**Frontend Components:**

- SysAdminDashboard: Main navigation and overview
- TenantManagement: CRUD operations for tenants
- RoleManagement: Manage Cognito groups and user assignments
- AuditLogs: View platform activity
- BillingManagement: Platform billing (future)

**Backend Services:**

- SysAdminService: Business logic for platform management
- TenantService: Tenant CRUD operations
- RoleService: Cognito group management
- AuditService: Logging and monitoring

**Data Stores:**

- MySQL: Tenant metadata (`tenants` table), audit logs
- Cognito: User authentication, groups (roles), custom attributes (tenant access)

---

## 1.3 Role Separation

### SysAdmin Role (Platform Management)

**Access:**

- ✅ Full CRUD on `tenants` table (all tenants)
- ✅ Manage Cognito groups (create/delete roles)
- ✅ Platform billing (future)
- ❌ **Cannot assign users to groups** (that's Tenant_Admin's job)
- ❌ **Cannot access tenant business data** (invoices, transactions, reports)

**Use Cases:**

- Create new tenant "NewCorp"
- Suspend tenant (set status='suspended')
- Delete tenant
- Create new role "Custom_Role"
- View audit logs

### Tenant_Admin Role (Tenant Management)

**Access:**

- ✅ Read THEIR tenant record from `tenants` table
- ✅ Update THEIR tenant record from `tenants` table (contact_email, phone_number, street, city, zipcode, country, display_name only)
- ✅ Manage users for THEIR tenant (create users, assign to groups)
- ✅ Manage templates for THEIR tenant (`tenant_template_config`)
- ✅ Manage credentials for THEIR tenant (`tenant_credentials`)
- ✅ Manage settings for THEIR tenant (`tenant_config`)
- ✅ **Access business data for THEIR tenant** (invoices, transactions, reports)
- ❌ Cannot change `status` or `administration` fields from `tenants` table (only SysAdmin)
- ❌ Cannot see or modify other tenants
- ❌ Cannot create/delete tenants

**Use Cases:**

- Update GoodwinSolutions contact email
- Create new user for GoodwinSolutions
- Assign user to Finance_CRUD group
- Upload template for GoodwinSolutions
- View GoodwinSolutions invoices and reports

**Note:** myAdmin Tenant_Admin works exactly the same way - they manage the myAdmin tenant just like any other Tenant_Admin manages their tenant. The only difference is storage backend (Railway filesystem vs Google Drive), which is handled transparently by the system.

---

## 2. Database Schema

### 2.1 Existing Tables (Used by SysAdmin)

#### tenants

**Already created** - Stores tenant metadata

```sql
CREATE TABLE tenants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    contact_email VARCHAR(255),
    phone_number VARCHAR(50),
    street VARCHAR(255),
    city VARCHAR(100),
    zipcode VARCHAR(20),
    country VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    updated_by VARCHAR(255),
    INDEX idx_status (status),
    INDEX idx_administration (administration),
    INDEX idx_country (country)
);
```

**Access Control:**

- SysAdmin: Full CRUD
- Tenant_Admin: Read + Update (their tenant only, limited fields)

#### tenant_modules

**Already exists** - Tracks which modules are enabled per tenant

```sql
CREATE TABLE tenant_modules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    module_name VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_module (administration, module_name),
    FOREIGN KEY (administration) REFERENCES tenants(administration),
    INDEX idx_tenant (administration)
);
```

**Usage:**

- Stores which modules are enabled for each tenant
- Controls which Cognito groups are shown in the UI when Tenant_Admin manages users for their tenant
- FIN module enabled → Finance_Read, Finance_CRUD, Finance_Export groups shown in UI
- STR module enabled → STR_Read, STR_CRUD, STR_Export groups shown in UI

### 2.2 Tables NOT Used (Simplified Design)

❌ **generic_templates** - Use `tenant_template_config` with `administration='myAdmin'` instead
❌ **tenant_role_allocation** - Derive available roles from `tenant_modules` + Cognito groups

---

## 3. Cognito Integration

### 3.1 Custom Attributes (Per User)

**Active attribute:**

```
custom:tenants  → JSON array of tenant identifiers (max 2048 chars = ~100 tenants)
                  Example: '["GoodwinSolutions", "PeterPrive", "myAdmin"]'
                  Used in JWT token for authorization
```

**Legacy attributes (defined but not used):**

- custom:tenant_id - Not used (legacy)
- custom:tenant_name - Not used (legacy)
- custom:role - Not used (we use Cognito groups instead)

### 3.2 Groups (Roles)

**Platform Role:**

- SysAdmin - Platform administration

**Tenant Management Role:**

- Tenant_Admin - Tenant administration (manages users, templates, settings for their tenant)

**Module Roles:**

- FIN: Finance_Read, Finance_CRUD, Finance_Export (FIN module)
- STR: STR_Read, STR_CRUD, STR_Export (STR module)
- Additional module roles can be added as new modules are developed

### 3.3 Authorization Logic

**Implementation**: See `backend/src/auth/tenant_context.py`

- `@cognito_required` - Validates JWT token and extracts user info
- `@tenant_required` - Validates tenant access and injects tenant context
- Routes use `tenant` parameter to filter database queries

### 3.4 Available Roles Per Tenant

**Implementation**: UI filtering based on `tenant_modules` table

When Tenant_Admin manages users, the UI shows only Cognito groups for enabled modules:

- FIN module enabled → Show Finance_Read, Finance_CRUD, Finance_Export
- STR module enabled → Show STR_Read, STR_CRUD, STR_Export

---

## 4. API Specifications

### 4.1 Tenant Management Endpoints

---

#### `POST /api/sysadmin/tenants`

**Create new tenant**

**Authorization**: SysAdmin role required

**Request:**

```json
{
  "administration": "NewCorp",
  "display_name": "New Corporation",
  "contact_email": "admin@newcorp.com",
  "phone_number": "+31123456789",
  "street": "Main Street 123",
  "city": "Amsterdam",
  "zipcode": "1012AB",
  "country": "Netherlands",
  "enabled_modules": ["FIN", "STR"],
  "initial_admin_email": "john@newcorp.com"
}
```

**Response:**

```json
{
  "success": true,
  "administration": "NewCorp",
  "display_name": "New Corporation",
  "status": "active",
  "message": "Tenant created successfully. Invitation sent to john@newcorp.com"
}
```

**Errors:**

- 400: Invalid administration format or duplicate
- 401: Not authenticated
- 403: Not SysAdmin role
- 500: Database error

---

#### `GET /api/sysadmin/tenants`

**List all tenants**

**Authorization**: SysAdmin role required

**Query Parameters:**

- page: int (default 1)
- per_page: int (default 50, max 100)
- status: string (active|suspended|inactive|all, default all)
- sort_by: string (administration|display_name|created_at|status, default created_at)
- sort_order: string (asc|desc, default desc)
- search: string (search in administration, display_name, contact_email)

**Frontend Implementation**: Consider using the generic filter framework (`.kiro/specs/Common/Filters a generic approach/`) for consistent filtering UI across the platform.

**Response:**

```json
{
  "success": true,
  "tenants": [
    {
      "administration": "GoodwinSolutions",
      "display_name": "Goodwin Solutions",
      "status": "active",
      "contact_email": "admin@goodwin.com",
      "phone_number": "+31123456789",
      "street": "Main Street 123",
      "city": "Amsterdam",
      "zipcode": "1012AB",
      "country": "Netherlands",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-02-01T14:20:00Z",
      "enabled_modules": ["FIN", "STR"],
      "user_count": 5
    }
  ],
  "total": 10,
  "page": 1,
  "per_page": 50
}
```

**Notes:**

- `enabled_modules`: Derived from `tenant_modules` table
- `user_count`: Count of users with this tenant in `custom:tenants` attribute (requires Cognito query)

**Errors:**

- 401: Not authenticated
- 403: Not SysAdmin role

---

#### `GET /api/sysadmin/tenants/{administration}`

**Get single tenant details**

**Authorization**: SysAdmin role required

**Response:**

```json
{
  "success": true,
  "tenant": {
    "administration": "GoodwinSolutions",
    "display_name": "Goodwin Solutions",
    "status": "active",
    "contact_email": "admin@goodwin.com",
    "phone_number": "+31123456789",
    "street": "Main Street 123",
    "city": "Amsterdam",
    "zipcode": "1012AB",
    "country": "Netherlands",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-02-01T14:20:00Z",
    "created_by": "sysadmin@myadmin.com",
    "updated_by": "sysadmin@myadmin.com",
    "enabled_modules": ["FIN", "STR"],
    "user_count": 5,
    "users": [
      {
        "email": "john@goodwin.com",
        "groups": ["Tenant_Admin", "Finance_CRUD"]
      }
    ]
  }
}
```

**Errors:**

- 401: Not authenticated
- 403: Not SysAdmin role
- 404: Tenant not found

---

#### `PUT /api/sysadmin/tenants/{administration}`

**Update tenant**

**Authorization**: SysAdmin role required

**Request:**

```json
{
  "display_name": "Goodwin Solutions Ltd",
  "status": "suspended",
  "contact_email": "newadmin@goodwin.com",
  "phone_number": "+31987654321",
  "street": "New Street 456",
  "city": "Rotterdam",
  "zipcode": "3011AB",
  "country": "Netherlands"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Tenant updated successfully",
  "tenant": {
    "administration": "GoodwinSolutions",
    "display_name": "Goodwin Solutions Ltd",
    "status": "suspended",
    "updated_at": "2026-02-05T15:30:00Z"
  }
}
```

**Notes:**

- Cannot update `administration` field (immutable)
- Cannot update `created_at`, `created_by` fields
- `updated_by` set to current SysAdmin user email
- `updated_at` set automatically

**Errors:**

- 400: Invalid data
- 401: Not authenticated
- 403: Not SysAdmin role
- 404: Tenant not found

---

#### `DELETE /api/sysadmin/tenants/{administration}`

**Delete tenant (soft delete - sets status to 'deleted')**

**Authorization**: SysAdmin role required

**Response:**

```json
{
  "success": true,
  "message": "Tenant deleted successfully"
}
```

**Notes:**

- Soft delete: Sets `status='deleted'` instead of removing record
- Does NOT delete Cognito users (manual cleanup required)
- Does NOT delete tenant business data (manual cleanup required)
- Prevents accidental data loss

**Errors:**

- 401: Not authenticated
- 403: Not SysAdmin role
- 404: Tenant not found
- 409: Cannot delete tenant with active users

### 4.2 Role Management Endpoints

---

#### `GET /api/sysadmin/roles`

**List all Cognito groups**

**Authorization**: SysAdmin role required

**Response:**

```json
{
  "success": true,
  "roles": [
    {
      "name": "SysAdmin",
      "description": "Platform administration",
      "user_count": 2,
      "category": "platform"
    },
    {
      "name": "Tenant_Admin",
      "description": "Tenant administration",
      "user_count": 5,
      "category": "tenant"
    },
    {
      "name": "Finance_CRUD",
      "description": "Finance module full access",
      "user_count": 10,
      "category": "module",
      "module": "FIN"
    }
  ]
}
```

**Notes:**

- Returns all Cognito groups
- `user_count`: Number of users in this group
- `category`: platform|tenant|module
- `module`: FIN|STR (for module roles only)

---

#### `POST /api/sysadmin/roles`

**Create new Cognito group**

**Authorization**: SysAdmin role required

**Request:**

```json
{
  "name": "Custom_Role",
  "description": "Custom role for special access",
  "category": "module",
  "module": "FIN"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Group created successfully",
  "group": {
    "name": "Custom_Role",
    "description": "Custom role for special access"
  }
}
```

**Errors:**

- 400: Invalid group name or duplicate
- 401: Not authenticated
- 403: Not SysAdmin role

---

#### `DELETE /api/sysadmin/roles/{role_name}`

**Delete Cognito group**

**Authorization**: SysAdmin role required

**Response:**

```json
{
  "success": true,
  "message": "Group deleted successfully"
}
```

**Notes:**

- Group must have zero users before deletion (enforced by 409 error)
- SysAdmin must first remove all users from the group
- Deletion is permanent and cannot be undone
- Consider the impact on tenant operations before deleting module-related groups

**Errors:**

- 401: Not authenticated
- 403: Not SysAdmin role
- 404: Group not found
- 409: Group has active users (remove all users first)

### 4.3 Audit Log Endpoints (Future)

**Status**: Not implemented in Phase 3

Audit logging will be added in a future phase with:

- Database-backed audit trail (`audit_log` table)
- UI-based log viewer with filtering and search
- Actions logged: tenant operations, group management, user assignments, login events
- Advanced features: fuzzy search, date range filtering, export to CSV/Excel

For Phase 3, use Railway server logs for debugging and monitoring.

### 4.4 Module Management Endpoints

---

#### `GET /api/sysadmin/tenants/{administration}/modules`

**Get enabled modules for tenant**

**Authorization**: SysAdmin role required

**Response:**

```json
{
  "success": true,
  "administration": "GoodwinSolutions",
  "modules": [
    {
      "module_name": "FIN",
      "is_enabled": true,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "module_name": "STR",
      "is_enabled": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

#### `PUT /api/sysadmin/tenants/{administration}/modules`

**Update enabled modules for tenant**

**Authorization**: SysAdmin role required

**Request:**

```json
{
  "modules": [
    {
      "module_name": "FIN",
      "is_enabled": true
    },
    {
      "module_name": "STR",
      "is_enabled": false
    }
  ]
}
```

**Response:**

```json
{
  "success": true,
  "message": "Modules updated successfully"
}
```

**Notes:**

- Disabling a module does NOT remove users from module groups
- Tenant_Admin will no longer see disabled module groups in UI

---

### 4.5 AI Usage Monitoring (Future)

**Status**: Not implemented in Phase 3

AI usage monitoring for platform billing and tenant transparency.

**For SysAdmin:**

- View AI usage across all tenants (aggregate and per-tenant)
- Monitor total platform costs
- Export usage data for billing purposes
- Set usage limits per tenant (future)

**For Tenant_Admin:**

- View their own tenant's AI usage
- Track costs and token consumption
- Understand which features use AI (invoice extraction, pricing optimization)

**Data Source**: `ai_usage_log` table

- Fields: administration, feature, tokens_used, cost_estimate, created_at

For Phase 3, AI usage is logged to database but not exposed in UI.

---

## 5. Security Model

### 5.1 Authentication & Authorization

**SysAdmin-specific requirement:**

- SysAdmin role (Cognito group) required for all `/api/sysadmin/*` endpoints

**Generic authentication/authorization:**

- See `backend/src/auth/cognito_utils.py` for JWT token validation
- See `backend/src/auth/tenant_context.py` for tenant context and authorization logic

### 5.2 Data Access Control

- SysAdmin manages `tenants` table (tenant metadata)
- SysAdmin manages Cognito groups (roles)
- SysAdmin views AI usage logs (all tenants, future)
- SysAdmin **cannot** access tenant business data (invoices, transactions, reports)
- Tenant business data access requires Tenant_Admin role + tenant membership

---

## 6. Implementation Details

See TASKS.md for detailed implementation tasks.

---

## 7. Future Enhancements

- Multi-factor authentication for SysAdmin
- Advanced audit log filtering and search
- Tenant usage analytics dashboard
- Automated tenant provisioning workflows
- Platform billing integration
- Tenant health monitoring
- Bulk tenant operations (create/update multiple tenants)
- AI usage monitoring UI (section 4.5)

---

## 8. Reusable Patterns & Frameworks

This design leverages existing patterns and frameworks for consistency and code reuse:

### 8.1 Authentication & Authorization

- **Pattern**: `backend/src/auth/cognito_utils.py` - JWT token validation
- **Pattern**: `backend/src/auth/tenant_context.py` - Tenant context and authorization
- **Decorators**: `@cognito_required`, `@tenant_required`
- **Usage**: All SysAdmin endpoints use these decorators for authentication

### 8.2 Multi-Tenant Data Isolation

- **Pattern**: `tenant_context.py` - Tenant-based query filtering
- **Implementation**: SQL queries filtered by `administration` column
- **Verification**: Phase 3.3 tests confirm isolation works correctly

### 8.3 Frontend Filtering (Recommended)

- **Framework**: `.kiro/specs/Common/Filters a generic approach/`
- **Usage**: Tenant list filtering (status, search, pagination, sorting)
- **Benefits**: Consistent UI/UX, reduced code duplication, reusable components
- **Status**: Optional for Phase 4, recommended for consistency

### 8.4 Template Management (Not Used)

- **Note**: SysAdmin does NOT manage templates
- **Reason**: Templates are managed per-tenant by Tenant_Admin
- **Implementation**: Use `tenant_template_config` with `administration='myAdmin'` for myAdmin templates

### 8.5 References

- Phase 3.2: Role separation and combination (`.kiro/specs/Common/Role based access/ROLE_SEPARATION_AND_COMBINATION.md`)
- Phase 3.3: Database and Cognito integration tests
- Generic filter framework: `.kiro/specs/Common/Filters a generic approach/`
