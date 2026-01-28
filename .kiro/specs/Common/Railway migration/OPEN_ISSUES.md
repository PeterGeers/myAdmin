# Open Issues for Railway Migration

## Status: Awaiting Decisions

This document tracks open issues that need decisions before proceeding with Railway migration implementation.

---

## Issue #1: Google Drive Tenant-Specific Credentials

**Status**: ⏸️ Awaiting Decision
**Priority**: HIGH
**Blocking**: Railway Migration

### Current State
- Single `credentials.json` and `token.json` used for all tenants
- Not multi-tenant compliant
- All tenants share same Google account

### Questions to Answer
1. Do you want **one Google account with separate folders per tenant**?
2. Or **separate Google accounts per tenant** (each with their own credentials)?
3. How many tenants are currently using the system?
4. Do you have existing data in Google Drive that needs to stay accessible?
5. What's your timeline preference:
   - **Quick fix**: Environment variables (requires Railway config, restart)
   - **Better solution**: Database storage (requires more code, admin UI)

### Proposed Solutions
See [TENANT_SPECIFIC_GOOGLE_DRIVE.md](./TENANT_SPECIFIC_GOOGLE_DRIVE.md) for detailed analysis of 4 options.

**Recommended**: Hybrid approach (Phase 1: env vars, Phase 2: database)

### Impact
- **Files affected**: `backend/src/google_drive_service.py` and all routes that use it
- **Effort**: 1-2 days for Phase 1, 1 week for Phase 2
- **Risk**: MEDIUM → LOW after implementation

---

## Issue #2: STR Invoice Template Storage

**Status**: ⏸️ Awaiting Decision
**Priority**: MEDIUM
**Blocking**: Architecture clarity before Railway migration

### Current State
- `str_invoice_routes.py` uses `GoogleDriveService` to load templates
- Templates stored in Google Drive folder ID: `12FJAYbX5MI3wpGxwahcHykRQfUCRZob1`
- Hardcoded folder ID in code
- Unclear if this needs credentials or should be tenant-specific

### Questions to Answer
1. **Should templates be tenant-specific or shared across all tenants?**
   - Tenant-specific: Each tenant has their own invoice templates
   - Shared: All tenants use the same templates

2. **Where should templates be stored?**
   - Option A: Database (with admin UI for management)
   - Option B: Railway volumes (filesystem)
   - Option C: Google Drive (current approach)

3. **Who manages template updates?**
   - Admin UI for non-technical users
   - Manual file upload by developers
   - Version control (Git)

4. **Do templates contain tenant-specific data?**
   - Company logos, addresses, branding
   - Or just generic HTML structure

### Proposed Solutions

#### Option A: Database Storage (Recommended for Multi-Tenant)
**Pros**:
- ✅ Tenant-specific templates easy to implement
- ✅ Admin UI for template management
- ✅ Version history tracking
- ✅ No external dependencies
- ✅ Works in Railway without extra config

**Cons**:
- ❌ Requires database schema changes
- ❌ Requires admin UI development
- ❌ More complex than filesystem

**Effort**: 2-3 days
**Database Schema**:
```sql
CREATE TABLE invoice_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(100),
    template_name VARCHAR(255),
    template_html TEXT,
    template_type VARCHAR(50), -- 'str_invoice', 'btw_report', etc.
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    INDEX idx_tenant_type (tenant_id, template_type)
);
```

#### Option B: Railway Volumes (Recommended for Single-Tenant)
**Pros**:
- ✅ Simple filesystem access
- ✅ Fast to implement
- ✅ Easy to update (upload files)
- ✅ No database changes

**Cons**:
- ❌ Not easily tenant-specific
- ❌ No version history
- ❌ Manual file management
- ❌ Requires Railway volume configuration

**Effort**: 1 day
**Implementation**:
```python
# Store templates in /app/templates/str_invoices/
template_path = f'/app/templates/str_invoices/{template_name}.html'
with open(template_path, 'r') as f:
    template_html = f.read()
```

#### Option C: Keep Google Drive (Current Approach)
**Pros**:
- ✅ No code changes needed
- ✅ Already working
- ✅ Easy to update templates (upload to Drive)

**Cons**:
- ❌ Requires Google Drive credentials (see Issue #1)
- ❌ External dependency
- ❌ Not clear if tenant-specific
- ❌ Hardcoded folder IDs

**Effort**: 0 days (no change)
**Note**: Still needs to address Issue #1 (tenant-specific credentials)

### Recommended Decision Path

**If Single-Tenant (Personal Use)**:
→ **Option B: Railway Volumes**
- Simple, fast, no database changes
- Store templates in `/app/templates/`
- Update via file upload or Git

**If Multi-Tenant (Multiple Clients)**:
→ **Option A: Database Storage**
- Each tenant can have custom templates
- Admin UI for template management
- Professional solution

**If Keeping Current Approach**:
→ **Option C: Google Drive**
- Must also implement Issue #1 (tenant-specific credentials)
- Clarify if templates should be tenant-specific

### Impact
- **Files affected**: `backend/src/str_invoice_routes.py`
- **Effort**: 1-3 days depending on option
- **Risk**: MEDIUM (architecture decision required)

---

## Issue #3: Tenant Identification in Routes

**Status**: ⏸️ Needs Investigation
**Priority**: HIGH
**Blocking**: Google Drive tenant-specific implementation

### Current State
- Routes use `GoogleDriveService()` without passing tenant context
- No clear pattern for extracting tenant from JWT token

### Questions to Answer
1. How do we currently identify which tenant is making a request?
2. Do we have a decorator or middleware that extracts tenant info from JWT?
3. Is tenant stored in Cognito custom attributes?
4. How is tenant passed to backend routes?

### Investigation Needed
```python
# Need to find:
# 1. How tenant is extracted from JWT token
# 2. Where tenant context is stored in request
# 3. Pattern for passing tenant to services

# Example expected pattern:
@app.route('/api/invoices')
@cognito_required
@tenant_required
def get_invoices():
    tenant_id = get_current_tenant()  # How is this implemented?
    # ...
```

### Impact
- **Files to investigate**: 
  - `backend/src/auth/cognito_utils.py`
  - `backend/src/auth/tenant_context.py`
  - All routes that need tenant isolation
- **Effort**: 1 day investigation + implementation
- **Risk**: HIGH (critical for multi-tenant security)

---

## Decision Matrix

| Issue | Priority | Blocking | Effort | Decision Needed By |
|-------|----------|----------|--------|-------------------|
| #1: Google Drive Credentials | HIGH | Yes | 1-2 days | Before Railway migration |
| #2: Template Storage | MEDIUM | No | 1-3 days | Before Railway migration |
| #3: Tenant Identification | HIGH | Yes | 1 day | Before Issue #1 implementation |

---

## Next Steps

### Immediate (This Week)
1. **Answer questions for Issue #3**: Investigate tenant identification pattern
2. **Answer questions for Issue #1**: Decide on Google Drive strategy
3. **Answer questions for Issue #2**: Decide on template storage approach

### After Decisions (Next Week)
1. Implement chosen solutions
2. Test locally with Docker Compose
3. Proceed with Railway migration

---

## Notes
- All issues documented in `Impact Analysis.md`
- Google Drive solution detailed in `TENANT_SPECIFIC_GOOGLE_DRIVE.md`
- Credential file structure documented in `CREDENTIALS_FILE_STRUCTURE.md`
