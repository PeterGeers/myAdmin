# SysAdmin Module - Technical Design

**Status**: Draft
**Created**: February 5, 2026
**Last Updated**: February 5, 2026

---

## 1. Architecture Overview

The SysAdmin Module provides platform-level administration through a dedicated UI and API layer. It integrates with AWS Cognito for role management, MySQL for metadata storage, and Railway filesystem for generic template storage.

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SysAdmin Frontend (React)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Tenant     │  │     Role     │  │   Template   │      │
│  │  Management  │  │  Management  │  │  Management  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  SysAdmin API (Flask Blueprint)              │
│  /api/sysadmin/tenants     /api/sysadmin/roles              │
│  /api/sysadmin/templates   /api/sysadmin/config             │
└─────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┼─────────────┐
                ▼             ▼             ▼
         ┌──────────┐  ┌──────────┐  ┌──────────┐
         │  MySQL   │  │ Cognito  │  │ Railway  │
         │ Database │  │  Groups  │  │   Files  │
         └──────────┘  └──────────┘  └──────────┘
```

### 1.2 Component Responsibilities

**Frontend Components:**

- SysAdminDashboard: Main navigation and overview
- TenantManagement: CRUD operations for tenants
- RoleManagement: CRUD operations for roles
- TemplateManagement: Upload and manage generic templates
- PlatformConfig: System-wide settings
- AuditLogs: View platform activity

**Backend Services:**

- SysAdminService: Business logic for platform management
- TenantService: Tenant CRUD operations
- RoleService: Cognito group management
- GenericTemplateService: Template storage and retrieval
- AuditService: Logging and monitoring

**Data Stores:**

- MySQL: Tenant metadata, role allocations, template metadata
- Cognito: User authentication, role definitions
- Railway Filesystem: Generic templates, platform assets

---

## 2. Database Schema

### 2.1 New Tables

#### tenants (extends existing)

```sql
-- Add myAdmin system tenant
INSERT INTO tenants (administration, status, created_at)
VALUES ('myAdmin', 'active', NOW());
```

#### tenant_modules

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

#### generic_templates

```sql
CREATE TABLE generic_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    field_mappings JSON,
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_template_version (template_name, version),
    INDEX idx_type (template_type),
    INDEX idx_active (is_active)
);
```

#### tenant_role_allocation

```sql
CREATE TABLE tenant_role_allocation (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    role_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_role (administration, role_name),
    FOREIGN KEY (administration) REFERENCES tenants(administration),
    INDEX idx_tenant (administration),
    INDEX idx_role (role_name)
);
```

---

## 3. API Specifications

### 3.1 Tenant Management Endpoints

#### POST /api/sysadmin/tenants

Create new tenant

**Request:**

```json
{
  "tenant_name": "NewCorp",
  "contact_email": "admin@newcorp.com",
  "initial_admin_email": "john@newcorp.com",
  "enabled_modules": ["FIN", "STR"]
}
```

**Response:**

```json
{
  "success": true,
  "tenant_id": 123,
  "administration": "NewCorp",
  "status": "inactive",
  "message": "Tenant created successfully. Invitation sent to john@newcorp.com"
}
```

#### GET /api/sysadmin/tenants

List all tenants

**Query Parameters:**

- page: int (default 1)
- per_page: int (default 50)
- status: string (active|inactive|all)
- sort_by: string (name|created_at|user_count)

**Response:**

```json
{
  "success": true,
  "tenants": [
    {
      "administration": "GoodwinSolutions",
      "status": "active",
      "created_at": "2024-01-15T10:30:00Z",
      "user_count": 5,
      "enabled_modules": ["FIN", "STR", "BNB"]
    }
  ],
  "total": 10,
  "page": 1,
  "per_page": 50
}
```

---

## 4. Security Model

### 4.1 Authentication

- All endpoints require AWS Cognito authentication
- SysAdmin role required for all /api/sysadmin/\* endpoints
- JWT token validation on every request

### 4.2 Authorization

- @require_sysadmin decorator on all endpoints
- Verify user has SysAdmin role in Cognito
- Log all authorization failures

### 4.3 Data Access Control

- SysAdmin can only access myAdmin tenant data
- SysAdmin cannot query tenant-specific tables directly
- All tenant data access must go through Tenant Admin

---

## 5. Implementation Details

See TASKS.md for detailed implementation tasks.

---

## 6. Testing Strategy

### 6.1 Unit Tests

- Test all service methods
- Test all API endpoints
- Mock external dependencies (Cognito, database)

### 6.2 Integration Tests

- Test end-to-end workflows
- Test with real database (test environment)
- Test Cognito integration

### 6.3 Security Tests

- Test authorization checks
- Test data isolation
- Test audit logging

---

## 7. Deployment

### 7.1 Phase 3 (Local Development)

- Create myAdmin tenant in local database
- Implement backend APIs
- Implement frontend UI
- Test locally

### 7.2 Phase 5 (Railway Production)

- Deploy to Railway
- Create myAdmin tenant in production
- Upload generic templates to Railway filesystem
- Configure environment variables

---

## 8. Monitoring

### 8.1 Metrics

- API response times
- Error rates
- Tenant creation rate
- Active tenant count

### 8.2 Alerts

- Failed authentication attempts
- Authorization failures
- System errors

---

## 9. Future Enhancements

- Multi-factor authentication for SysAdmin
- Advanced audit log filtering
- Tenant usage analytics dashboard
- Automated tenant provisioning
- Tenant billing integration

---

## 10. Template Retention Policy

### 10.1 Configuration

**Environment Variables**:

```bash
# .env or Railway environment variables
GENERIC_TEMPLATE_RETENTION_MODE=count  # Options: count, days, none
GENERIC_TEMPLATE_RETENTION_COUNT=5     # Keep last N versions (if mode=count)
GENERIC_TEMPLATE_RETENTION_DAYS=90     # Keep versions from last X days (if mode=days)
```

**Database Configuration** (optional - overrides environment):

```sql
-- Platform settings table (future enhancement)
INSERT INTO platform_settings (setting_key, setting_value) VALUES
('template_retention_mode', 'count'),
('template_retention_count', '5');
```

### 10.2 Retention Modes

**Mode 1: Count-based (Default)**

- Keep last N versions (default: 5)
- Active version + 4 previous versions
- Oldest versions deleted when limit exceeded

**Mode 2: Time-based**

- Keep versions from last X days (e.g., 90 days)
- Versions older than X days are deleted
- Active version always preserved

**Mode 3: No Cleanup**

- Keep all versions forever
- No automatic deletion
- Manual cleanup only

### 10.3 Cleanup Logic

**Automatic Cleanup** (triggered on new version upload):

```python
def cleanup_old_template_versions(template_name):
    """
    Clean up old template versions based on retention policy
    """
    mode = os.getenv('GENERIC_TEMPLATE_RETENTION_MODE', 'count')

    if mode == 'none':
        return  # No cleanup

    # Get all versions for this template (ordered by version DESC)
    versions = db.query(GenericTemplate).filter_by(
        template_name=template_name
    ).order_by(GenericTemplate.version.desc()).all()

    # Always keep active version
    active_version = next((v for v in versions if v.is_active), None)
    inactive_versions = [v for v in versions if not v.is_active]

    if mode == 'count':
        # Keep last N versions
        retention_count = int(os.getenv('GENERIC_TEMPLATE_RETENTION_COUNT', 5))
        to_delete = inactive_versions[retention_count:]

    elif mode == 'days':
        # Keep versions from last X days
        retention_days = int(os.getenv('GENERIC_TEMPLATE_RETENTION_DAYS', 90))
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        to_delete = [v for v in inactive_versions if v.created_at < cutoff_date]

    # Delete old versions
    for version in to_delete:
        # Delete file from filesystem
        if os.path.exists(version.file_path):
            os.remove(version.file_path)

        # Delete database record
        db.delete(version)

        # Log deletion
        audit_log(
            action='template_version_deleted',
            details=f'Deleted {template_name} v{version.version} (retention policy)'
        )

    db.commit()
```

**Manual Cleanup** (SysAdmin can trigger):

```python
@app.route('/api/sysadmin/templates/cleanup', methods=['POST'])
@require_sysadmin
def cleanup_all_templates():
    """
    Manually trigger cleanup for all templates
    """
    templates = db.query(GenericTemplate.template_name).distinct().all()

    for template in templates:
        cleanup_old_template_versions(template.template_name)

    return jsonify({
        'success': True,
        'message': 'Cleanup completed for all templates'
    })
```

### 10.4 Version History Query

**Get version history for a template**:

```python
def get_template_version_history(template_name):
    """
    Get all versions of a template with metadata
    """
    versions = db.query(GenericTemplate).filter_by(
        template_name=template_name
    ).order_by(GenericTemplate.version.desc()).all()

    return [{
        'version': v.version,
        'is_active': v.is_active,
        'created_at': v.created_at,
        'created_by': v.created_by,
        'file_size': os.path.getsize(v.file_path) if os.path.exists(v.file_path) else 0
    } for v in versions]
```

### 10.5 Rollback to Previous Version

**SysAdmin can rollback to a previous version**:

```python
@app.route('/api/sysadmin/templates/<template_name>/rollback/<int:version>', methods=['POST'])
@require_sysadmin
def rollback_template_version(template_name, version):
    """
    Rollback to a previous version (make it active)
    """
    # Deactivate current version
    current = db.query(GenericTemplate).filter_by(
        template_name=template_name,
        is_active=True
    ).first()

    if current:
        current.is_active = False

    # Activate target version
    target = db.query(GenericTemplate).filter_by(
        template_name=template_name,
        version=version
    ).first()

    if not target:
        return jsonify({'error': 'Version not found'}), 404

    target.is_active = True
    db.commit()

    # Log rollback
    audit_log(
        action='template_rollback',
        details=f'Rolled back {template_name} to v{version}'
    )

    return jsonify({
        'success': True,
        'message': f'Rolled back to version {version}'
    })
```

---

## 11. Environment Variables Summary

**Required**:

- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - Database connection
- `CREDENTIALS_ENCRYPTION_KEY` - For tenant credentials

**Optional (SysAdmin Module)**:

- `GENERIC_TEMPLATE_RETENTION_MODE` - Retention mode (count|days|none, default: count)
- `GENERIC_TEMPLATE_RETENTION_COUNT` - Keep last N versions (default: 5)
- `GENERIC_TEMPLATE_RETENTION_DAYS` - Keep versions from last X days (default: 90)

**AWS (existing)**:

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`

---

## 12. Future Enhancements

### 12.1 Template Diff Viewer

- Show differences between template versions
- Highlight changes in HTML/field mappings
- Help SysAdmin understand what changed

### 12.2 Template Testing

- Test template with sample data before activating
- Preview how template will look for tenants
- Validate field mappings

### 12.3 Template Approval Workflow

- Require approval before activating new version
- Multiple approvers for critical templates
- Approval history and audit trail

### 12.4 Template Analytics

- Track which tenants use generic vs custom templates
- Track template usage statistics
- Identify popular templates
