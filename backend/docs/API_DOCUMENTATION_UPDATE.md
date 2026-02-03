# API Documentation Update - Railway Migration

**Date**: February 3, 2026  
**Status**: ✅ Complete  
**Location**: `backend/src/openapi_spec.yaml`

## Overview

Comprehensive OpenAPI/Swagger documentation has been added for all new endpoints introduced during the Railway migration. The documentation includes detailed request/response schemas, authentication requirements, and error codes.

## New Endpoint Categories

### 1. Tenant Administration (`/api/tenant/*`)

**Role Required**: Tenant_Admin

#### Configuration Management
- `GET /api/tenant/config` - Get tenant configuration
- `POST /api/tenant/config` - Set tenant configuration
- `DELETE /api/tenant/config/{config_key}` - Delete configuration

#### User Management
- `GET /api/tenant/users` - Get tenant users
- `POST /api/tenant/users/{username}/roles` - Assign role to user
- `DELETE /api/tenant/users/{username}/roles/{role}` - Remove role from user

**Allowed Roles for Assignment**:
- Finance_CRUD, Finance_Read, Finance_Export
- STR_CRUD, STR_Read, STR_Export

**Restrictions**:
- Cannot assign/remove SysAdmin or Tenant_Admin roles
- User must belong to the tenant
- Only module-level roles can be managed

### 2. Template Management (`/api/tenant-admin/templates/*`)

**Role Required**: Tenant_Admin

#### Template Operations
- `POST /api/tenant-admin/templates/preview` - Generate template preview with sample data
- `POST /api/tenant-admin/templates/validate` - Validate template (faster, no preview)
- `POST /api/tenant-admin/templates/approve` - Approve and activate template
- `POST /api/tenant-admin/templates/reject` - Reject template with reason

#### AI-Assisted Template Editing
- `POST /api/tenant-admin/templates/ai-help` - Get AI-powered fix suggestions
- `POST /api/tenant-admin/templates/apply-ai-fixes` - Apply AI-suggested fixes

**Supported Template Types**:
- `str_invoice_nl` - Dutch STR invoice
- `str_invoice_en` - English STR invoice
- `btw_aangifte` - VAT declaration
- `aangifte_ib` - Income tax declaration
- `toeristenbelasting` - Tourist tax report
- `financial_report` - Financial reports

**Validation Checks**:
- HTML syntax validation
- Required placeholder validation
- Security validation (no scripts, event handlers)
- File size validation
- External resource warnings

**AI Features**:
- Intelligent error analysis
- Code fix suggestions with examples
- Auto-fixable issues identification
- Token usage and cost tracking
- Fallback to generic help if AI unavailable

### 3. Tenant Module Management (`/api/tenant/modules/*`)

#### Module Access Control
- `GET /api/tenant/modules` - Get tenant module access (authenticated users)
- `POST /api/tenant/modules` - Update module access (Tenant_Admin only)
- `GET /api/tenant/modules/all` - Get all tenant modules (SysAdmin only)

**Available Modules**:
- Finance - Financial transaction management
- STR - Short-term rental management

## Authentication Documentation

### Authentication Flow
1. User authenticates with AWS Cognito
2. Obtain JWT token
3. Include token in `Authorization: Bearer <token>` header
4. Include tenant in `X-Tenant: <tenant_name>` header (for tenant-scoped endpoints)

### Endpoint Types

#### Public Endpoints (No Auth)
- `/health` - Health check
- `/status` - Environment status

#### Authenticated Endpoints (JWT Required)
- Most API endpoints
- Token must be valid and not expired

#### Tenant-Scoped Endpoints (JWT + Tenant Header)
- Endpoints accessing tenant-specific data
- User must have access to specified tenant
- Examples: `/api/reports/*`, `/api/bnb/*`, `/api/tenant/*`

#### Role-Based Endpoints

**SysAdmin Only**:
- Cache management (`/api/cache/*`)
- Scalability monitoring (`/api/scalability/*`)
- All tenant modules (`/api/tenant/modules/all`)

**Tenant_Admin Only**:
- Tenant configuration (`/api/tenant/config`)
- User management (`/api/tenant/users`)
- Template management (`/api/tenant-admin/templates/*`)
- Module access (`/api/tenant/modules`)

**Module-Specific Roles**:
- Finance_CRUD, Finance_Read, Finance_Export
- STR_CRUD, STR_Read, STR_Export

## Request/Response Schemas

### Comprehensive Schema Coverage

All endpoints include:
- Request body schemas with required fields
- Response schemas for success cases
- Error response schemas for all error types
- Example values for all fields
- Field descriptions and constraints

### Schema Categories

1. **Tenant Administration Schemas**
   - TenantConfigResponse
   - TenantConfigSetRequest/Response
   - TenantUsersResponse
   - TenantRoleAssignRequest/Response

2. **Template Management Schemas**
   - TemplatePreviewRequest/Response
   - TemplateValidateRequest/Response
   - TemplateApproveRequest/Response
   - TemplateRejectRequest/Response
   - TemplateAIHelpRequest/Response
   - TemplateApplyFixesRequest/Response

3. **Module Management Schemas**
   - TenantModulesResponse
   - TenantModuleUpdateRequest/Response
   - AllTenantModulesResponse

4. **Error Schemas**
   - ValidationErrorResponse
   - AuthenticationErrorResponse
   - AuthorizationErrorResponse
   - NotFoundErrorResponse
   - ServerErrorResponse

## Error Codes and Messages

### HTTP Status Codes

#### 200 OK
- Request successful
- Response contains requested data

#### 400 Bad Request
- Invalid request parameters
- Missing required fields
- Validation failed
- Template validation errors

**Common Messages**:
- "Request body required"
- "template_type is required"
- "config_key and config_value required"
- "Template validation failed"

#### 401 Unauthorized
- Missing/invalid JWT token
- Expired token
- Token verification failed

**Common Messages**:
- "Invalid authorization"
- "Authentication required"
- "Token expired"

#### 403 Forbidden
- Insufficient permissions
- No tenant access
- Cannot perform operation

**Common Messages**:
- "Tenant admin access required"
- "SysAdmin access required"
- "Access denied to administration: {tenant}"
- "Cannot assign this role"

#### 404 Not Found
- Resource does not exist
- User not found

**Common Messages**:
- "User not found: {username}"
- "Resource not found"

#### 500 Internal Server Error
- Database errors
- Google Drive API errors
- AI service errors
- Unexpected errors

**Common Messages**:
- "Internal server error"
- "Database connection failed"
- "AI service unavailable"

#### 503 Service Unavailable
- Service temporarily down
- Scalability manager not initialized

### Error Response Format

Standard format for all errors:
```json
{
  "success": false,
  "error": "Error category",
  "message": "Detailed error message",
  "details": "Additional context (optional)",
  "status": "error"
}
```

### Validation Error Format

Template validation errors:
```json
{
  "success": false,
  "error": "Template validation failed",
  "validation": {
    "is_valid": false,
    "errors": [
      {
        "type": "missing_placeholder",
        "message": "Required placeholder missing",
        "placeholder": "invoice_number"
      }
    ],
    "warnings": [...]
  }
}
```

## Security Headers

All responses include:
- `Content-Security-Policy` - XSS prevention
- `X-Content-Type-Options` - MIME sniffing prevention
- `X-Frame-Options` - Clickjacking prevention
- `X-XSS-Protection` - Browser XSS protection
- `Referrer-Policy` - Referrer control

## Accessing the Documentation

### Swagger UI
- **Local**: http://localhost:5000/apidocs/
- **Production**: https://api.myadmin.com/apidocs/

### OpenAPI Spec File
- **Location**: `backend/src/openapi_spec.yaml`
- **Format**: OpenAPI 3.0.2
- **Validation**: ✅ Valid YAML

## Testing the Documentation

### Validate YAML
```bash
python -c "import yaml; yaml.safe_load(open('backend/src/openapi_spec.yaml', 'r', encoding='utf-8')); print('Valid')"
```

### Start Server
```bash
cd backend
python src/app.py
```

### Access Swagger UI
Open browser to: http://localhost:5000/apidocs/

## Best Practices for API Consumers

1. **Always check `success` field** in responses
2. **Handle all error status codes** (401, 403, 404, 500, 503)
3. **Include proper authentication** (JWT + Tenant header)
4. **Validate request data** before sending
5. **Log errors** with request details
6. **Retry on 503** (service temporarily unavailable)
7. **Refresh token on 401** (token expired)
8. **Check tenant access on 403** (wrong tenant selected)
9. **Display user-friendly error messages** from `message` field
10. **Use `details` field** for debugging

## Changes Summary

### New Tags Added
- Tenant Administration
- Template Management
- Tenant Module Management

### New Endpoints Documented
- 11 Tenant Administration endpoints
- 6 Template Management endpoints
- 3 Module Management endpoints

### New Schemas Added
- 25+ request/response schemas
- 5 error response schemas
- Comprehensive validation schemas

### Documentation Enhancements
- Authentication flow documentation
- Role-based access control details
- Error code reference guide
- Security headers documentation
- Best practices guide

## Related Documentation

- **Railway Migration Tasks**: `.kiro/specs/Common/Railway migration/TASKS.md`
- **Template Preview Spec**: `.kiro/specs/Common/template-preview-validation/`
- **Multi-tenant Architecture**: `.kiro/specs/Common/Multitennant/architecture.md`
- **Backend README**: `backend/README.md`

## Maintenance

### Updating Documentation

When adding new endpoints:
1. Add endpoint definition to `paths` section
2. Add request/response schemas to `components/schemas`
3. Include authentication requirements (`security` section)
4. Document all error responses
5. Add examples for all fields
6. Update tags if needed
7. Validate YAML syntax
8. Test in Swagger UI

### Version Control

- OpenAPI spec is version controlled in Git
- Changes tracked in commit history
- Breaking changes should be documented in CHANGELOG

## Completion Status

✅ All new endpoints documented  
✅ Request/response schemas included  
✅ Authentication requirements documented  
✅ Error codes and messages documented  
✅ YAML validation passed  
✅ Swagger UI accessible  

**Task Status**: Complete
