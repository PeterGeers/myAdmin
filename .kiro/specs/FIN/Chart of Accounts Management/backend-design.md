# Chart of Accounts Management - Design Document

**Status**: Draft  
**Date**: 2026-02-17  
**Module**: Financial (FIN) - Tenant Admin  
**Related**: proposal.md

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Design](#database-design)
3. [Backend API Design](#backend-api-design)
4. [Frontend Component Design](#frontend-component-design)
5. [Security & Access Control](#security--access-control)
6. [Data Flow](#data-flow)
7. [Error Handling](#error-handling)
8. [Testing Strategy](#testing-strategy)

---

## Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────────┐
│                     Chart of Accounts                        │
│                    Management Feature                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Frontend (React/TypeScript)                                │
│  ├── ChartOfAccounts.tsx (main component)                   │
│  ├── AccountModal.tsx (add/edit modal)                      │
│  └── Uses: GenericFilter, FilterPanel, Chakra UI            │
│                                                              │
│  Backend (Flask/Python)                                     │
│  ├── tenant_admin_routes.py (API endpoints)                 │
│  ├── chart_of_accounts_service.py (business logic)          │
│  └── Uses: DatabaseManager, audit_logger                    │
│                                                              │
│  Database (MySQL)                                           │
│  └── rekeningschema table (existing)                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

- **Frontend**: React 19.2.0, TypeScript 4.9.5, Chakra UI 2.8.2
- **Backend**: Flask 2.3.3, Python 3.11
- **Database**: MySQL 8.0 (Railway production, Docker local)
- **Authentication**: AWS Cognito with JWT
- **Deployment**: Railway (production), Docker (local development)

---

## Database Design

### Existing Table: `rekeningschema`

**Schema**:

```sql
CREATE TABLE rekeningschema (
    Account VARCHAR(50) NOT NULL,
    AccountName VARCHAR(255),
    AccountLookup VARCHAR(50),
    Belastingaangifte VARCHAR(100),
    administration VARCHAR(50) NOT NULL,
    PRIMARY KEY (Account, administration),
    INDEX idx_administration (administration),
    INDEX idx_lookup (AccountLookup)
);
```

**Columns**:

- `Account`: Account number (e.g., "1000", "NL12RABO...")
- `AccountName`: Human-readable account description
- `AccountLookup`: Category/lookup code for grouping
- `Belastingaangifte`: Tax declaration category
- `administration`: Tenant identifier (multi-tenant isolation)

**Constraints**:

- Composite primary key: (Account, administration)
- Account must be unique per tenant
- Cannot be null: Account, administration

**Indexes**:

- Primary key index on (Account, administration)
- Index on administration for tenant filtering
- Index on AccountLookup for category queries

### No Schema Changes Required

The existing table structure is sufficient. No migrations needed.

### Data Integrity Rules

1. **Unique Account per Tenant**: Enforced by primary key
2. **Cannot Delete if Used**: Check `mutaties` table before delete
3. **Cannot Change Account Number if Used**: Only allow name/lookup updates
4. **Required Fields**: Account, administration (enforced by NOT NULL)

---

## Backend API Design

### Route: `/api/tenant-admin/chart-of-accounts`

**Blueprint**: `tenant_admin_routes.py`  
**Base Path**: `/api/tenant-admin`

### Endpoints

#### 1. List All Accounts

```python
@tenant_admin_bp.route('/chart-of-accounts', methods=['GET'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def list_accounts(user_email, user_roles, tenant, user_tenants):
    """
    Get all accounts for current tenant

    Query Parameters:
        - search: string (optional) - Search in account or name
        - sort_by: string (optional) - Column to sort by
        - sort_order: string (optional) - 'asc' or 'desc'
        - page: int (optional) - Page number (default: 1)
        - limit: int (optional) - Items per page (default: 50)

    Returns:
        {
            "success": true,
            "accounts": [...],
            "total": 150,
            "page": 1,
            "limit": 50,
            "pages": 3
        }
    """
```

**Implementation**:

```python
# Check FIN module access
if not has_fin_module(tenant):
    return jsonify({'error': 'FIN module not enabled'}), 403

# Get query parameters
search = request.args.get('search', '')
sort_by = request.args.get('sort_by', 'Account')
sort_order = request.args.get('sort_order', 'asc')
page = int(request.args.get('page', 1))
limit = int(request.args.get('limit', 50))

# Build query
query = """
    SELECT Account, AccountName, AccountLookup, Belastingaangifte
    FROM rekeningschema
    WHERE administration = %s
"""

params = [tenant]

if search:
    query += " AND (Account LIKE %s OR AccountName LIKE %s)"
    search_pattern = f"%{search}%"
    params.extend([search_pattern, search_pattern])

# Add sorting
valid_columns = ['Account', 'AccountName', 'AccountLookup', 'Belastingaangifte']
if sort_by in valid_columns:
    order = 'ASC' if sort_order == 'asc' else 'DESC'
    query += f" ORDER BY {sort_by} {order}"

# Add pagination
offset = (page - 1) * limit
query += " LIMIT %s OFFSET %s"
params.extend([limit, offset])

# Execute query
accounts = db.execute_query(query, params)

# Get total count
count_query = """
    SELECT COUNT(*) as total
    FROM rekeningschema
    WHERE administration = %s
"""
count_params = [tenant]
if search:
    count_query += " AND (Account LIKE %s OR AccountName LIKE %s)"
    count_params.extend([search_pattern, search_pattern])

total = db.execute_query(count_query, count_params)[0]['total']

return jsonify({
    'success': True,
    'accounts': accounts,
    'total': total,
    'page': page,
    'limit': limit,
    'pages': (total + limit - 1) // limit
})
```

#### 2. Get Single Account

```python
@tenant_admin_bp.route('/chart-of-accounts/<account>', methods=['GET'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def get_account(user_email, user_roles, tenant, user_tenants, account):
    """Get single account details"""

    # Check FIN module
    if not has_fin_module(tenant):
        return jsonify({'error': 'FIN module not enabled'}), 403

    query = """
        SELECT Account, AccountName, AccountLookup, Belastingaangifte
        FROM rekeningschema
        WHERE administration = %s AND Account = %s
    """

    result = db.execute_query(query, [tenant, account])

    if not result:
        return jsonify({'error': 'Account not found'}), 404

    return jsonify({'success': True, 'account': result[0]})
```

#### 3. Create Account

```python
@tenant_admin_bp.route('/chart-of-accounts', methods=['POST'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def create_account(user_email, user_roles, tenant, user_tenants):
    """Create new account"""

    # Check FIN module
    if not has_fin_module(tenant):
        return jsonify({'error': 'FIN module not enabled'}), 403

    data = request.get_json()

    # Validate required fields
    account = data.get('account', '').strip()
    account_name = data.get('accountName', '').strip()

    if not account:
        return jsonify({'error': 'Account number required'}), 400
    if not account_name:
        return jsonify({'error': 'Account name required'}), 400

    # Check if account already exists
    check_query = """
        SELECT 1 FROM rekeningschema
        WHERE administration = %s AND Account = %s
    """
    exists = db.execute_query(check_query, [tenant, account])

    if exists:
        return jsonify({'error': 'Account already exists'}), 409

    # Insert account
    insert_query = """
        INSERT INTO rekeningschema
        (Account, AccountName, AccountLookup, Belastingaangifte, administration)
        VALUES (%s, %s, %s, %s, %s)
    """

    db.execute_query(
        insert_query,
        [
            account,
            account_name,
            data.get('accountLookup', ''),
            data.get('belastingaangifte', ''),
            tenant
        ],
        fetch=False,
        commit=True
    )

    # Audit log
    audit_logger.log_action(
        user_email=user_email,
        action='CREATE_ACCOUNT',
        resource_type='chart_of_accounts',
        resource_id=account,
        tenant=tenant,
        details={'account': account, 'name': account_name}
    )

    return jsonify({
        'success': True,
        'account': {
            'account': account,
            'accountName': account_name,
            'accountLookup': data.get('accountLookup', ''),
            'belastingaangifte': data.get('belastingaangifte', '')
        }
    }), 201
```

#### 4. Update Account

```python
@tenant_admin_bp.route('/chart-of-accounts/<account>', methods=['PUT'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def update_account(user_email, user_roles, tenant, user_tenants, account):
    """Update existing account"""

    # Check FIN module
    if not has_fin_module(tenant):
        return jsonify({'error': 'FIN module not enabled'}), 403

    data = request.get_json()

    # Check if account exists
    check_query = """
        SELECT Account, AccountName, AccountLookup, Belastingaangifte
        FROM rekeningschema
        WHERE administration = %s AND Account = %s
    """
    existing = db.execute_query(check_query, [tenant, account])

    if not existing:
        return jsonify({'error': 'Account not found'}), 404

    old_values = existing[0]

    # Update account (cannot change account number)
    update_query = """
        UPDATE rekeningschema
        SET AccountName = %s,
            AccountLookup = %s,
            Belastingaangifte = %s
        WHERE administration = %s AND Account = %s
    """

    db.execute_query(
        update_query,
        [
            data.get('accountName', old_values['AccountName']),
            data.get('accountLookup', old_values['AccountLookup']),
            data.get('belastingaangifte', old_values['Belastingaangifte']),
            tenant,
            account
        ],
        fetch=False,
        commit=True
    )

    # Audit log
    audit_logger.log_action(
        user_email=user_email,
        action='UPDATE_ACCOUNT',
        resource_type='chart_of_accounts',
        resource_id=account,
        tenant=tenant,
        details={
            'old': old_values,
            'new': data
        }
    )

    return jsonify({'success': True, 'account': data})
```

#### 5. Delete Account

```python
@tenant_admin_bp.route('/chart-of-accounts/<account>', methods=['DELETE'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def delete_account(user_email, user_roles, tenant, user_tenants, account):
    """Delete account (only if not used in transactions)"""

    # Check FIN module
    if not has_fin_module(tenant):
        return jsonify({'error': 'FIN module not enabled'}), 403

    # Check if account is used in transactions
    usage_query = """
        SELECT COUNT(*) as count
        FROM mutaties
        WHERE administration = %s
        AND (Debet = %s OR Credit = %s)
    """

    usage = db.execute_query(usage_query, [tenant, account, account])

    if usage[0]['count'] > 0:
        return jsonify({
            'error': 'Cannot delete account that is used in transactions',
            'usage_count': usage[0]['count']
        }), 409

    # Delete account
    delete_query = """
        DELETE FROM rekeningschema
        WHERE administration = %s AND Account = %s
    """

    db.execute_query(delete_query, [tenant, account], fetch=False, commit=True)

    # Audit log
    audit_logger.log_action(
        user_email=user_email,
        action='DELETE_ACCOUNT',
        resource_type='chart_of_accounts',
        resource_id=account,
        tenant=tenant
    )

    return jsonify({'success': True, 'message': 'Account deleted'})
```

#### 6. Export to Excel

```python
@tenant_admin_bp.route('/chart-of-accounts/export', methods=['GET'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def export_accounts(user_email, user_roles, tenant, user_tenants):
    """Export all accounts to Excel"""

    # Check FIN module
    if not has_fin_module(tenant):
        return jsonify({'error': 'FIN module not enabled'}), 403

    # Get all accounts
    query = """
        SELECT Account, AccountName, AccountLookup, Belastingaangifte
        FROM rekeningschema
        WHERE administration = %s
        ORDER BY Account
    """

    accounts = db.execute_query(query, [tenant])

    # Create Excel file
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Chart of Accounts"

    # Headers
    ws.append(['Account', 'AccountName', 'AccountLookup', 'Belastingaangifte'])

    # Data
    for account in accounts:
        ws.append([
            account['Account'],
            account['AccountName'],
            account['AccountLookup'],
            account['Belastingaangifte']
        ])

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    # Audit log
    audit_logger.log_action(
        user_email=user_email,
        action='EXPORT_ACCOUNTS',
        resource_type='chart_of_accounts',
        tenant=tenant,
        details={'count': len(accounts)}
    )

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'chart_of_accounts_{tenant}_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )
```

#### 7. Import from Excel

```python
@tenant_admin_bp.route('/chart-of-accounts/import', methods=['POST'])
@cognito_required(required_permissions=['tenant_admin'])
@tenant_required()
def import_accounts(user_email, user_roles, tenant, user_tenants):
    """Import accounts from Excel"""

    # Check FIN module
    if not has_fin_module(tenant):
        return jsonify({'error': 'FIN module not enabled'}), 403

    # Get uploaded file
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']

    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Invalid file type. Must be Excel file'}), 400

    # Parse Excel
    import openpyxl

    wb = openpyxl.load_workbook(file)
    ws = wb.active

    # Validate headers
    headers = [cell.value for cell in ws[1]]
    expected = ['Account', 'AccountName', 'AccountLookup', 'Belastingaangifte']

    if headers != expected:
        return jsonify({
            'error': 'Invalid Excel format',
            'expected_headers': expected,
            'found_headers': headers
        }), 400

    # Parse rows
    accounts_to_import = []
    errors = []

    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        account, name, lookup, tax = row

        # Validate
        if not account:
            errors.append(f"Row {row_num}: Account number required")
            continue
        if not name:
            errors.append(f"Row {row_num}: Account name required")
            continue

        accounts_to_import.append({
            'account': str(account).strip(),
            'name': str(name).strip(),
            'lookup': str(lookup).strip() if lookup else '',
            'tax': str(tax).strip() if tax else ''
        })

    if errors:
        return jsonify({
            'success': False,
            'errors': errors,
            'parsed': len(accounts_to_import)
        }), 400

    # Import accounts (upsert)
    imported = 0
    updated = 0

    for acc in accounts_to_import:
        # Check if exists
        check_query = """
            SELECT 1 FROM rekeningschema
            WHERE administration = %s AND Account = %s
        """
        exists = db.execute_query(check_query, [tenant, acc['account']])

        if exists:
            # Update
            update_query = """
                UPDATE rekeningschema
                SET AccountName = %s, AccountLookup = %s, Belastingaangifte = %s
                WHERE administration = %s AND Account = %s
            """
            db.execute_query(
                update_query,
                [acc['name'], acc['lookup'], acc['tax'], tenant, acc['account']],
                fetch=False,
                commit=True
            )
            updated += 1
        else:
            # Insert
            insert_query = """
                INSERT INTO rekeningschema
                (Account, AccountName, AccountLookup, Belastingaangifte, administration)
                VALUES (%s, %s, %s, %s, %s)
            """
            db.execute_query(
                insert_query,
                [acc['account'], acc['name'], acc['lookup'], acc['tax'], tenant],
                fetch=False,
                commit=True
            )
            imported += 1

    # Audit log
    audit_logger.log_action(
        user_email=user_email,
        action='IMPORT_ACCOUNTS',
        resource_type='chart_of_accounts',
        tenant=tenant,
        details={'imported': imported, 'updated': updated}
    )

    return jsonify({
        'success': True,
        'imported': imported,
        'updated': updated,
        'total': imported + updated
    })
```

---

## Security & Access Control

### Module Access Control

```python
def has_fin_module(tenant):
    """Check if tenant has FIN module enabled"""
    query = """
        SELECT 1 FROM tenant_modules
        WHERE administration = %s
        AND module_name = 'FIN'
        AND is_active = TRUE
    """
    result = db.execute_query(query, [tenant])
    return len(result) > 0
```

**Applied to all endpoints**: Every endpoint checks FIN module access before proceeding.

### Authentication & Authorization

**Decorators**:

- `@cognito_required(required_permissions=['tenant_admin'])` - Validates JWT token
- `@tenant_required()` - Extracts and validates tenant context

**Tenant Isolation**:

- All queries filter by `administration = %s` (tenant)
- User can only access their own tenant's data
- Enforced at database query level

### Input Validation

**Account Number**:

- Required, not null
- Trimmed of whitespace
- Unique per tenant (enforced by primary key)

**Account Name**:

- Required, not null
- Trimmed of whitespace

**SQL Injection Prevention**:

- All queries use parameterized statements
- No string concatenation in SQL
- Example: `query = "... WHERE Account = %s"` with `params = [account]`

### File Upload Security

**Excel Import**:

- File type validation (`.xlsx`, `.xls` only)
- File size limit (handled by Flask config)
- Header validation before processing
- Row-by-row validation with error collection

---

## Error Handling

### HTTP Status Codes

- `200 OK` - Successful GET/PUT/DELETE
- `201 Created` - Successful POST (create)
- `400 Bad Request` - Validation error, missing required fields
- `403 Forbidden` - FIN module not enabled, no tenant access
- `404 Not Found` - Account doesn't exist
- `409 Conflict` - Account already exists, account in use (cannot delete)
- `500 Internal Server Error` - Database error, unexpected error

### Error Response Format

```json
{
  "error": "Human-readable error message",
  "details": {
    "field": "account",
    "reason": "Account already exists"
  }
}
```

### Validation Errors

**Create Account**:

- Missing account number → 400
- Missing account name → 400
- Duplicate account → 409

**Update Account**:

- Account not found → 404

**Delete Account**:

- Account not found → 404
- Account in use → 409 with usage count

**Import**:

- Invalid file type → 400
- Invalid headers → 400 with expected/found headers
- Row validation errors → 400 with error list

---

## Testing Strategy

### Unit Tests

**Location**: `backend/tests/unit/test_chart_of_accounts.py`

**Test Cases**:

```python
class TestChartOfAccountsService:
    def test_list_accounts_success(self):
        """Test listing accounts for tenant"""

    def test_list_accounts_with_search(self):
        """Test search functionality"""

    def test_list_accounts_pagination(self):
        """Test pagination"""

    def test_create_account_success(self):
        """Test creating new account"""

    def test_create_account_duplicate(self):
        """Test duplicate account returns 409"""

    def test_create_account_missing_fields(self):
        """Test validation for required fields"""

    def test_update_account_success(self):
        """Test updating account"""

    def test_update_account_not_found(self):
        """Test updating non-existent account"""

    def test_delete_account_success(self):
        """Test deleting unused account"""

    def test_delete_account_in_use(self):
        """Test cannot delete account in use"""

    def test_module_access_control(self):
        """Test FIN module check"""
```

### API Tests

**Location**: `backend/tests/api/test_chart_of_accounts_api.py`

**Test Cases**:

```python
class TestChartOfAccountsAPI:
    def test_list_accounts_endpoint(self):
        """Test GET /api/tenant-admin/chart-of-accounts"""

    def test_create_account_endpoint(self):
        """Test POST /api/tenant-admin/chart-of-accounts"""

    def test_update_account_endpoint(self):
        """Test PUT /api/tenant-admin/chart-of-accounts/<account>"""

    def test_delete_account_endpoint(self):
        """Test DELETE /api/tenant-admin/chart-of-accounts/<account>"""

    def test_export_excel_endpoint(self):
        """Test GET /api/tenant-admin/chart-of-accounts/export"""

    def test_import_excel_endpoint(self):
        """Test POST /api/tenant-admin/chart-of-accounts/import"""

    def test_unauthorized_access(self):
        """Test access without tenant_admin role"""

    def test_fin_module_disabled(self):
        """Test access when FIN module disabled"""
```

### Integration Tests

**Location**: `backend/tests/integration/test_chart_of_accounts_integration.py`

**Test Scenarios**:

1. Create account → List accounts → Verify in list
2. Create account → Update account → Verify changes
3. Create account → Delete account → Verify removed
4. Create account → Use in transaction → Cannot delete
5. Import Excel → Verify all accounts created
6. Export Excel → Verify file format and content

### Test Data

**Fixtures** (`backend/tests/conftest.py`):

```python
@pytest.fixture
def sample_accounts():
    return [
        {
            'account': '1000',
            'accountName': 'Kas',
            'accountLookup': 'CASH',
            'belastingaangifte': 'Activa'
        },
        {
            'account': '1100',
            'accountName': 'Bank',
            'accountLookup': 'BANK',
            'belastingaangifte': 'Activa'
        }
    ]

@pytest.fixture
def sample_excel_file():
    """Create sample Excel file for import testing"""
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Account', 'AccountName', 'AccountLookup', 'Belastingaangifte'])
    ws.append(['2000', 'Crediteuren', 'PAYABLE', 'Passiva'])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
```

---

## Performance Considerations

### Database Indexes

**Existing Indexes**:

- Primary key: `(Account, administration)` - Fast lookups
- Index on `administration` - Fast tenant filtering
- Index on `AccountLookup` - Fast category queries

**Query Performance**:

- List accounts: Uses index on `administration`
- Search: Uses index + LIKE (acceptable for small datasets)
- Pagination: LIMIT/OFFSET (acceptable for < 10,000 records)

### Optimization Strategies

**For Large Account Lists** (> 1,000 accounts):

- Consider full-text search index for better search performance
- Implement cursor-based pagination instead of OFFSET
- Add caching layer for frequently accessed data

**Excel Export/Import**:

- Stream large files instead of loading into memory
- Process in batches for very large imports
- Add progress tracking for imports > 1,000 rows

---

## Audit Logging

### Logged Actions

All actions are logged to `audit_log` table:

- `CREATE_ACCOUNT` - New account created
- `UPDATE_ACCOUNT` - Account modified (includes old/new values)
- `DELETE_ACCOUNT` - Account deleted
- `EXPORT_ACCOUNTS` - Accounts exported to Excel
- `IMPORT_ACCOUNTS` - Accounts imported from Excel

### Audit Log Format

```python
audit_logger.log_action(
    user_email='user@example.com',
    action='CREATE_ACCOUNT',
    resource_type='chart_of_accounts',
    resource_id='1000',
    tenant='GoodwinSolutions',
    details={'account': '1000', 'name': 'Kas'}
)
```

---

## Dependencies

### Python Packages

- `flask` - Web framework
- `mysql-connector-python` - Database driver
- `openpyxl` - Excel file handling
- `python-jose` - JWT token validation
- `pytest` - Testing framework

### Internal Modules

- `database.py` - DatabaseManager
- `auth/cognito_utils.py` - Authentication decorators
- `auth/tenant_context.py` - Tenant isolation
- `audit_logger.py` - Audit trail logging

---

## Deployment Notes

### Environment Variables

No new environment variables required. Uses existing:

- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `TEST_MODE` - Switches between test/production database

### Database Migrations

**None required** - Uses existing `rekeningschema` table.

### Railway Deployment

1. Merge feature branch to `main`
2. Railway auto-deploys from GitHub
3. No manual steps required
4. Verify deployment in Railway logs

---

## API Summary

| Method | Endpoint                                        | Description        |
| ------ | ----------------------------------------------- | ------------------ |
| GET    | `/api/tenant-admin/chart-of-accounts`           | List all accounts  |
| GET    | `/api/tenant-admin/chart-of-accounts/<account>` | Get single account |
| POST   | `/api/tenant-admin/chart-of-accounts`           | Create account     |
| PUT    | `/api/tenant-admin/chart-of-accounts/<account>` | Update account     |
| DELETE | `/api/tenant-admin/chart-of-accounts/<account>` | Delete account     |
| GET    | `/api/tenant-admin/chart-of-accounts/export`    | Export to Excel    |
| POST   | `/api/tenant-admin/chart-of-accounts/import`    | Import from Excel  |

**All endpoints require**:

- Valid JWT token (Cognito authentication)
- `tenant_admin` role
- FIN module enabled for tenant
- `X-Tenant` header with tenant name
