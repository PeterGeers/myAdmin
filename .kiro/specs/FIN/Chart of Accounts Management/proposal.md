# Chart of Accounts Management - Proposal

**Status**: Draft  
**Date**: 2026-02-17  
**Module**: Financial (FIN) - Tenant Admin  
**Priority**: Medium

## Overview

Add a self-service UI for tenants to manage their chart of accounts (`rekeningschema` table) through the Tenant Admin module. Currently, this critical financial configuration data can only be maintained via direct SQL access.

## Business Need

### Current Pain Points

- Chart of accounts must be maintained manually via SQL
- No self-service capability for tenants
- Risk of data corruption from manual SQL edits
- No audit trail for account changes
- Difficult to bulk import/export accounts

### Benefits of Solution

- Self-service account management for tenant admins
- Data validation prevents breaking financial reports
- Audit trail for all changes
- Bulk import/export via Excel
- Consistent with existing tenant admin patterns

## Current State

### Database Table: `rekeningschema`

**Key Columns**:

- `Account` (VARCHAR) - Account number (e.g., "1000", "NL12RABO...")
- `AccountName` (VARCHAR) - Account description
- `AccountLookup` (VARCHAR) - Lookup/mapping code for categorization
- `Belastingaangifte` (VARCHAR) - Tax declaration category
- `administration` (VARCHAR) - Tenant identifier

**Usage**:

- Used in `vw_mutaties` view for transaction categorization
- Referenced in financial reports (P&L, Balance Sheet, Tax declarations)
- Joined with `mutaties` table for account lookups
- Critical for banking processor pattern matching

**Multi-Tenant**:

- ✅ Has `administration` column
- ✅ Tenant-isolated via `administration` filter
- ✅ Each tenant has independent chart of accounts

## Proposed Solution

### Location: Tenant Admin Module

**Why Tenant Admin?**

1. Tenant-specific configuration data
2. Requires admin-level permissions
3. Fits existing pattern (templates, storage, modules)
4. Not transactional data (like invoices or transactions)

### Backend API

**New Routes** (in `backend/src/routes/tenant_admin_routes.py`):

```python
# List all accounts for tenant
GET /api/tenant-admin/chart-of-accounts
Response: {
  "success": true,
  "accounts": [
    {
      "account": "1000",
      "accountName": "Kas",
      "accountLookup": "CASH",
      "belastingaangifte": "Activa",
      "administration": "GoodwinSolutions"
    },
    ...
  ]
}

# Get single account
GET /api/tenant-admin/chart-of-accounts/:account
Response: { "success": true, "account": {...} }

# Create new account
POST /api/tenant-admin/chart-of-accounts
Body: {
  "account": "1100",
  "accountName": "Bank Account",
  "accountLookup": "BANK",
  "belastingaangifte": "Activa"
}
Response: { "success": true, "account": {...} }

# Update account
PUT /api/tenant-admin/chart-of-accounts/:account
Body: { "accountName": "Updated Name", ... }
Response: { "success": true, "account": {...} }

# Delete account
DELETE /api/tenant-admin/chart-of-accounts/:account
Response: { "success": true, "message": "Account deleted" }

# Export to Excel
GET /api/tenant-admin/chart-of-accounts/export
Response: Excel file download

# Import from Excel
POST /api/tenant-admin/chart-of-accounts/import
Body: FormData with Excel file
Response: {
  "success": true,
  "imported": 50,
  "errors": []
}
```

**Validation Rules**:

- Account number must be unique per tenant
- Account number required (not null)
- AccountName required
- Cannot delete account if used in transactions
- Cannot change account number if used in transactions (only update name/lookup)

**Permissions**:

- Requires `tenant_admin` role
- Requires tenant to have **FIN module enabled** in `tenant_modules` table
- Tenant context enforced (can only manage own accounts)

**Module Access Control**:

- Backend: Check `tenant_modules` table for FIN module
- Frontend: Hide/disable Chart of Accounts menu item if FIN not enabled
- API returns 403 if tenant doesn't have FIN module access

### Frontend UI

**New Component**: `frontend/src/pages/TenantAdmin/ChartOfAccounts.tsx`

**Design Patterns** (per `.kiro/steering/specs.md`):

- Use **Generic Filter Framework** (`.kiro/specs/Common/Filters a generic approach/`) for search/filter UI
- Follow **Chakra UI theme** (`frontend/src/theme.js`) for consistent look and feel
- Use **Authentication patterns** (`backend/src/auth/`) for security
- Follow **Multi-tenant patterns** (`backend/src/auth/tenant_context.py`) for data isolation

**Features**:

1. **Account List Table**
   - Columns: Account, Name, Lookup, Tax Category
   - **Use GenericFilter component** for search/filter (account number or name)
   - **Use FilterPanel component** for filter container
   - Sort by any column
   - Pagination (50 per page)
   - **Click any row to open edit modal** (primary interaction)
   - Add new account button (+ icon or "Add Account" button at top)
   - **Chakra UI Table component** for consistent styling

2. **Add/Edit Account Modal**
   - Opens when clicking any account row (edit mode)
   - Opens when clicking "Add Account" button (create mode)
   - **Chakra UI Modal component** for consistent styling
   - Form fields: Account, Name, Lookup, Tax Category
   - Account number field disabled in edit mode (cannot change)
   - Validation feedback with **Chakra UI FormControl**
   - Save/Cancel buttons
   - Delete button in edit mode (bottom left, with confirmation)
3. **Delete Confirmation**
   - Triggered from delete button within edit modal
   - Warning if account is used in transactions
   - Confirmation dialog

4. **Bulk Operations**
   - Export to Excel button
   - Import from Excel button with file upload
   - Import preview/validation before commit

5. **UI/UX**
   - **Chakra UI components** (consistent with app theme)
   - **Success/error toasts** (Chakra UI useToast)
   - Loading states (Chakra UI Spinner)
   - Responsive design (Chakra UI responsive props)
   - Follows existing Tenant Admin module patterns

### Excel Import/Export Format

**Excel Columns**:

- Account (required)
- AccountName (required)
- AccountLookup (optional)
- Belastingaangifte (optional)

**Import Validation**:

- Check for duplicate account numbers
- Validate required fields
- Show preview before import
- Report errors with row numbers

## Technical Considerations

### Data Integrity

- Prevent deletion of accounts used in transactions
- Prevent account number changes if used in transactions
- Validate unique account numbers per tenant

### Performance

- Index on `(administration, Account)` for fast lookups
- Pagination for large account lists
- Efficient Excel export (streaming for large datasets)

### Audit Trail

- Log all changes to `audit_log` table
- Track: created, updated, deleted accounts
- Include old/new values for updates

### Security

- Tenant context enforced on all operations
- Only tenant admins can access
- **Module access control**: Tenant must have FIN module enabled
- SQL injection prevention (parameterized queries)
- File upload validation (Excel only, size limits)

**Module Access Implementation**:

Backend:

```python
# Check tenant has FIN module before allowing access
def has_fin_module(tenant):
    query = """
        SELECT 1 FROM tenant_modules
        WHERE administration = %s
        AND module_name = 'FIN'
        AND is_active = TRUE
    """
    result = db.execute_query(query, (tenant,))
    return len(result) > 0

# Return 403 if tenant doesn't have FIN module
if not has_fin_module(tenant):
    return jsonify({'error': 'FIN module not enabled'}), 403
```

Frontend:

```typescript
// Get tenant's available modules
const { available_modules } = await getTenantModules();
const hasFIN = available_modules.includes('FIN');

// Hide Chart of Accounts in menu if no FIN
{hasFIN && <MenuItem>Chart of Accounts</MenuItem>}

// Show message if user navigates directly
if (!hasFIN) {
  return <Alert>FIN module not enabled for this tenant</Alert>;
}
```

## Implementation Phases

### Development Workflow

**Branch Strategy**:

1. Create feature branch: `feature/chart-of-accounts-management`
2. Develop and test in feature branch
3. Deploy to test environment for validation
4. Merge to `main` after approval

**Environments**:

- **Development**: Local environment with test database
- **Test/Staging**: Feature branch deployed to Railway (separate service or environment)
- **Production**: Main branch deployed to Railway production

**Testing Process**:

```
Local Dev → Feature Branch → Test Environment → Code Review → Main Branch → Production
   ↓            ↓                ↓                  ↓              ↓            ↓
Test DB    Push to GitHub   Railway Deploy    PR Review    Merge to main   Auto-deploy
```

**Steps**:

1. Create feature branch from `main`
2. Implement Phase 1 (Basic CRUD)
3. Test locally with test database
4. Push to GitHub feature branch
5. Deploy to Railway test environment
6. User acceptance testing (UAT)
7. Implement Phase 2 (Bulk Operations)
8. Test and validate in test environment
9. Implement Phase 3 (Polish & Testing)
10. Final UAT in test environment
11. Create Pull Request to `main`
12. Code review and approval
13. Merge to `main` → Auto-deploy to production

**Railway Configuration**:

- **Option A**: Create separate Railway service for test environment
- **Option B**: Use Railway environments (test vs production)
- **Option C (Recommended)**: Use local Docker containers for development
  - **Backend**: Docker container on `localhost:5000`
  - **Frontend**: Local dev server on `localhost:3000` (npm start)
  - **MySQL**: Docker Desktop container on port 3306
  - **Database**: Local MySQL with test data (for safe development)
  - **Note**: Railway MySQL is the production database, local is for development only
  - **Advantages**:
    - ⚡ Fast iteration (no deployment wait time)
    - 🔧 Full control over environment
    - 🐛 Easy debugging with local tools
    - 💰 No Railway costs during development
    - � Safe to experiment without affecting production data
    - 🔄 Quick restart/rebuild cycles

**Recommended Workflow with Option C**:

```
Phase 1: Local Development (Docker)
├── Start Docker containers (docker-compose up)
├── Backend: localhost:5000 (local MySQL)
├── Frontend: localhost:3000 (npm start)
├── Develop → Test → Debug → Iterate
└── Commit to feature branch

Phase 2: Optional Stakeholder Review
├── Push feature branch to GitHub
├── Deploy to Railway test environment (if needed for remote review)
└── Or: Demo locally via screen share

Phase 3: Production Deployment
├── Create Pull Request to main
├── Code review and approval
├── Merge to main
└── Auto-deploy to Railway production (Railway MySQL)
```

**Docker Commands**:

```bash
# Start local environment
docker-compose up -d

# View logs
docker-compose logs -f backend

# Restart after code changes
docker-compose restart backend

# Stop environment
docker-compose down
```

### Phase 1: Basic CRUD (2-3 days)

- [ ] Backend API endpoints (list, get, create, update, delete)
- [ ] Module access control (FIN module check)
- [ ] Validation logic (unique accounts, required fields, usage checks)
- [ ] Frontend table component with click-to-edit rows
- [ ] Add/Edit modal (opens on row click or Add button)
- [ ] Delete button within edit modal with confirmation
- [ ] Basic testing

### Phase 2: Bulk Operations (1-2 days)

- [ ] Excel export endpoint
- [ ] Excel import endpoint with validation
- [ ] Frontend import/export UI
- [ ] Import preview and error handling

### Phase 3: Polish & Testing (1 day)

- [ ] Audit logging for all changes
- [ ] Comprehensive error handling
- [ ] Loading states and UX polish
- [ ] Module access control testing (FIN enabled/disabled)
- [ ] Integration testing
- [ ] Documentation

**Total Estimate**: 4-6 days

## Alternative Approaches Considered

### 1. Separate "Finance Settings" Module

**Pros**: Dedicated space for all financial configuration  
**Cons**: Adds complexity, tenant admin already exists  
**Decision**: Not recommended - keep in Tenant Admin

### 2. Direct SQL Access Only

**Pros**: No development needed  
**Cons**: Not user-friendly, error-prone, no audit trail  
**Decision**: Not acceptable for production use

### 3. Google Sheets Integration

**Pros**: Familiar interface for users  
**Cons**: Complex sync logic, potential data conflicts  
**Decision**: Excel import/export is simpler and sufficient

## Success Criteria

- [ ] Tenant admins can view all accounts for their tenant
- [ ] Tenant admins can add/edit/delete accounts
- [ ] Validation prevents data integrity issues
- [ ] Excel import/export works reliably
- [ ] All changes are audit logged
- [ ] UI is intuitive and responsive
- [ ] No performance degradation on large account lists
- [ ] **Feature tested in test environment before production deployment**
- [ ] **Code reviewed and approved via Pull Request**
- [ ] **No breaking changes to existing functionality**

## Open Questions

1. Should we support account hierarchies (parent/child accounts)?
2. Should we allow bulk delete with confirmation?
3. Should we show usage count (how many transactions use each account)?
4. Should we support account templates for new tenants?
5. Should we validate account number format (e.g., numeric only, IBAN format)?

## Next Steps

1. Review and approve this proposal
2. Create detailed frontend and backend design document
3. Create TASKS.md with implementation checklist
4. Begin Phase 1 implementation

## References

- Database table: `rekeningschema`
- View: `vw_rekeningschema`
- Related: Banking processor pattern matching
- Related: Financial reports (P&L, Balance Sheet, Tax declarations)
