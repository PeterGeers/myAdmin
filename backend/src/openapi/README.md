# OpenAPI Documentation Structure

This directory contains the organized OpenAPI 3.0 specification for the myAdmin Backend API.

## Structure

```
openapi/
├── openapi_spec.yaml          # Main OpenAPI spec (references other files)
├── paths/                     # API endpoint definitions
│   ├── health.yaml           # Health check endpoints
│   ├── files.yaml            # File upload endpoints
│   ├── banking.yaml          # Banking processor endpoints
│   ├── str.yaml              # STR (Short-Term Rental) endpoints
│   ├── bnb.yaml              # BNB analytics endpoints
│   ├── reports.yaml          # Financial reporting endpoints
│   ├── sysadmin.yaml         # System Administration endpoints (SysAdmin only)
│   └── tenant_admin.yaml     # Tenant Administration endpoints (Tenant_Admin only)
└── schemas/                   # Request/Response schemas
    ├── common.yaml           # Common schemas (errors, responses)
    ├── files.yaml            # File upload schemas
    ├── banking.yaml          # Banking schemas
    ├── str.yaml              # STR schemas
    ├── bnb.yaml              # BNB schemas
    ├── reports.yaml          # Report schemas
    ├── sysadmin.yaml         # SysAdmin schemas
    └── tenant_admin.yaml     # TenantAdmin schemas
```

## File Organization

### Main Spec File

- **openapi_spec.yaml**: Main entry point that defines API metadata, servers, tags, and references to paths and schemas

### Paths Files

Each paths file contains endpoint definitions for a specific domain:

- Organized by functional area (health, files, banking, etc.)
- Uses anchors (e.g., `#/health`, `#/upload`) for referencing
- Each endpoint includes: tags, summary, description, security, parameters, request/response schemas

### Schema Files

Each schema file contains data models for a specific domain:

- Request bodies
- Response bodies
- Reusable components
- Referenced from paths using `$ref: '../schemas/filename.yaml#/SchemaName'`

## Key Features

### System Administration (SysAdmin role only)

**File**: `paths/sysadmin.yaml`, `schemas/sysadmin.yaml`

Endpoints for system-wide administration:

- **Tenant Management**: Create, list, get, update, delete tenants
- **Module Management**: Enable/disable modules for tenants
- **Role Management**: Create, list, update, delete Cognito groups (roles)
- **Health Monitoring**: System health status for all services

### Tenant User Management (Tenant_Admin role only)

**File**: `paths/tenant_admin.yaml`, `schemas/tenant_admin.yaml`

Endpoints for managing users within assigned tenants:

- **User Management**: Create, list, update, delete users in tenant
- **Role Assignment**: Assign/remove roles based on tenant's enabled modules
- **Available Roles**: Get roles available for tenant

### Template Management (Tenant_Admin role only)

**File**: `paths/tenant_admin.yaml`

Endpoints for template preview, validation, and AI-assisted editing:

- Get active template
- Preview template with sample data
- Validate template syntax
- Approve and activate template
- Get AI-powered fix suggestions

## Usage

### Viewing the Documentation

The API documentation is available at:

- **Swagger UI**: http://localhost:5000/apidocs/
- **OpenAPI JSON**: http://localhost:5000/apispec_1.json

### Adding New Endpoints

1. **Add path definition** to appropriate file in `paths/`:

   ```yaml
   my-new-endpoint:
     get:
       tags:
         - MyTag
       summary: Short description
       description: Detailed description
       security:
         - BearerAuth: []
       responses:
         "200":
           description: Success
           content:
             application/json:
               schema:
                 $ref: "../schemas/myschema.yaml#/MyResponse"
   ```

2. **Add schema definition** to appropriate file in `schemas/`:

   ```yaml
   MyResponse:
     type: object
     properties:
       success:
         type: boolean
       data:
         type: object
   ```

3. **Reference in main spec** (`openapi_spec.yaml`):

   ```yaml
   paths:
     /api/my-endpoint:
       $ref: "./paths/myfile.yaml#/my-new-endpoint"

   components:
     schemas:
       MyResponse:
         $ref: "./schemas/myschema.yaml#/MyResponse"
   ```

### File Size Guidelines

- **Target**: 500 lines per file
- **Maximum**: 1000 lines per file
- If a file exceeds 1000 lines, split it into multiple files by functional area

## Security

### Authentication

- **BearerAuth**: JWT token from AWS Cognito (required for most endpoints)
- **TenantHeader**: X-Tenant header for multi-tenant operations

### Authorization

- **SysAdmin**: Full system access (tenant management, role management, health monitoring)
- **Tenant_Admin**: Tenant-scoped access (user management, template management, configuration)
- **Module Roles**: Finance_CRUD, Finance_Read, Finance_Export, STR_CRUD, STR_Read, STR_Export

## Validation

To validate the OpenAPI spec:

```bash
cd backend
python scripts/validate_openapi_spec.py
```

## Notes

- The old monolithic `openapi_spec.yaml` has been backed up to `openapi_spec.yaml.backup`
- All paths use relative references (`./paths/`, `../schemas/`)
- Schemas are reusable across multiple endpoints
- Each domain (SysAdmin, TenantAdmin, BNB, STR, etc.) has its own files for maintainability
