# Tenant Context Quick Reference

Quick reference for using multi-tenant features in myAdmin backend.

## Import

```python
from auth import (
    tenant_required,
    get_current_tenant,
    add_tenant_filter,
    is_tenant_admin,
    get_tenant_config,
    set_tenant_config
)
```

## Basic Usage

### 1. Add Tenant Filtering to Route

```python
@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
@tenant_required()
def get_invoices(user_email, user_roles, tenant, user_tenants):
    """tenant and user_tenants are automatically injected"""
    
    query = "SELECT * FROM mutaties WHERE administration = %s"
    params = [tenant]
    results = db.execute_query(query, params, fetch=True)
    
    return jsonify({'data': results, 'tenant': tenant})
```

### 2. Use Helper Function

```python
@app.route('/api/transactions', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def get_transactions(user_email, user_roles, tenant, user_tenants):
    # Build base query
    query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
    params = ['2024-01-01']
    
    # Add tenant filter
    query, params = add_tenant_filter(query, params, tenant)
    
    results = db.execute_query(query, params, fetch=True)
    return jsonify({'data': results})
```

### 3. Check Tenant Admin

```python
@app.route('/api/tenant/settings', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def update_settings(user_email, user_roles, tenant, user_tenants):
    # Check if user is tenant admin
    if not is_tenant_admin(user_roles, tenant, user_tenants):
        return jsonify({'error': 'Tenant admin required'}), 403
    
    # Update settings...
    return jsonify({'success': True})
```

### 4. SysAdmin Bypass

```python
@app.route('/api/admin/all-data', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
@tenant_required(allow_sysadmin=True)
def get_all_data(user_email, user_roles, tenant, user_tenants):
    if 'SysAdmin' in user_roles:
        # Access all tenants
        query = "SELECT * FROM mutaties"
    else:
        # Regular users see only their tenant
        query = "SELECT * FROM mutaties WHERE administration = %s"
        params = [tenant]
```

## Tenant Configuration

### Get Configuration

```python
from auth import get_tenant_config

# Get config value
folder_id = get_tenant_config(db, tenant, 'google_drive_folder_id', is_secret=True)
```

### Set Configuration

```python
from auth import set_tenant_config

# Set config value
success = set_tenant_config(
    db, 
    tenant, 
    'google_drive_folder_id', 
    'abc123xyz',
    is_secret=True,
    created_by=user_email
)
```

## SQL Query Patterns

### Simple Filter

```python
query = "SELECT * FROM mutaties WHERE administration = %s"
params = [tenant]
```

### With WHERE Clause

```python
query = "SELECT * FROM mutaties WHERE TransactionDate > %s AND administration = %s"
params = ['2024-01-01', tenant]
```

### With Table Alias

```python
query = "SELECT * FROM mutaties m WHERE m.administration = %s"
params = [tenant]
```

### JOIN with Multiple Tables

```python
query = """
    SELECT m.*, r.AccountName
    FROM mutaties m
    LEFT JOIN rekeningschema r ON m.Debet = r.AccountNumber
    WHERE m.administration = %s AND r.administration = %s
"""
params = [tenant, tenant]
```

### Using Helper

```python
query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
params = ['2024-01-01']
query, params = add_tenant_filter(query, params, tenant)
# Result: "... WHERE TransactionDate > %s AND administration = %s"
# params: ['2024-01-01', 'GoodwinSolutions']
```

## Frontend Integration

### Send X-Tenant Header

```javascript
fetch('/api/invoices', {
  headers: {
    'Authorization': `Bearer ${token}`,
    'X-Tenant': 'GoodwinSolutions'
  }
})
```

### Extract Tenants from JWT

```javascript
const payload = JSON.parse(atob(token.split('.')[1]));
const tenants = payload['custom:tenants'] || [];
```

## Tenant Admin API

### Get Tenant Config

```http
GET /api/tenant/config
Headers:
  Authorization: Bearer <token>
  X-Tenant: GoodwinSolutions
```

### Set Tenant Config

```http
POST /api/tenant/config
Headers:
  Authorization: Bearer <token>
  X-Tenant: GoodwinSolutions
Body:
{
  "config_key": "google_drive_folder_id",
  "config_value": "abc123",
  "is_secret": true
}
```

### Get Tenant Users

```http
GET /api/tenant/users
Headers:
  Authorization: Bearer <token>
  X-Tenant: GoodwinSolutions
```

### Assign Role

```http
POST /api/tenant/users/user123/roles
Headers:
  Authorization: Bearer <token>
  X-Tenant: GoodwinSolutions
Body:
{
  "role": "Finance_CRUD"
}
```

## Common Patterns

### Pattern 1: Simple Data Retrieval

```python
@bp.route('/data', methods=['GET'])
@cognito_required(required_permissions=['data_read'])
@tenant_required()
def get_data(user_email, user_roles, tenant, user_tenants):
    query = "SELECT * FROM table WHERE administration = %s"
    results = db.execute_query(query, [tenant], fetch=True)
    return jsonify({'data': results})
```

### Pattern 2: Filtered Data Retrieval

```python
@bp.route('/data', methods=['GET'])
@cognito_required(required_permissions=['data_read'])
@tenant_required()
def get_filtered_data(user_email, user_roles, tenant, user_tenants):
    date_from = request.args.get('dateFrom')
    
    query = "SELECT * FROM table WHERE date >= %s"
    params = [date_from]
    query, params = add_tenant_filter(query, params, tenant)
    
    results = db.execute_query(query, params, fetch=True)
    return jsonify({'data': results})
```

### Pattern 3: Tenant Admin Operation

```python
@bp.route('/admin-action', methods=['POST'])
@cognito_required(required_permissions=[])
@tenant_required()
def admin_action(user_email, user_roles, tenant, user_tenants):
    if not is_tenant_admin(user_roles, tenant, user_tenants):
        return jsonify({'error': 'Tenant admin required'}), 403
    
    # Perform admin action
    return jsonify({'success': True})
```

### Pattern 4: Aggregation Query

```python
@bp.route('/summary', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_summary(user_email, user_roles, tenant, user_tenants):
    query = """
        SELECT 
            category,
            SUM(amount) as total
        FROM table
        WHERE administration = %s
        GROUP BY category
    """
    results = db.execute_query(query, [tenant], fetch=True)
    return jsonify({'data': results})
```

## Testing

### Test with cURL

```bash
# Get data for GoodwinSolutions
curl -H "Authorization: Bearer <token>" \
     -H "X-Tenant: GoodwinSolutions" \
     http://localhost:5000/api/invoices

# Try unauthorized tenant (should fail)
curl -H "Authorization: Bearer <token_goodwin_only>" \
     -H "X-Tenant: PeterPrive" \
     http://localhost:5000/api/invoices
```

### Test with Python

```python
import requests

headers = {
    'Authorization': f'Bearer {token}',
    'X-Tenant': 'GoodwinSolutions'
}

response = requests.get('http://localhost:5000/api/invoices', headers=headers)
print(response.json())
```

## Troubleshooting

### Error: "No tenant specified"

- Missing X-Tenant header
- JWT doesn't contain custom:tenants
- Solution: Add X-Tenant header or ensure JWT has custom:tenants

### Error: "Access denied to tenant"

- User doesn't have access to requested tenant
- Solution: Check user's custom:tenants attribute in Cognito

### Error: "Tenant admin access required"

- User doesn't have Tenant_Admin role
- User doesn't have access to the tenant
- Solution: Assign Tenant_Admin role and tenant access

### No Data Returned

- Tenant filter might be too restrictive
- Check if data exists for that tenant
- Verify administration field in database

## Best Practices

1. **Always use parameterized queries** - Never string interpolation
2. **Filter all tenant-specific tables** - Don't forget JOINs
3. **Use lowercase `administration`** - New schema standard
4. **Test with multiple tenants** - Ensure isolation
5. **Log tenant access** - For audit trail
6. **Validate tenant admin** - Before sensitive operations
7. **Use decorators** - Don't manually validate tenants
8. **Handle missing tenants** - Graceful error messages

## Migration Checklist

For each route:

- [ ] Import tenant functions
- [ ] Add `@tenant_required()` decorator
- [ ] Update function signature (add `tenant`, `user_tenants`)
- [ ] Add `administration = %s` to queries
- [ ] Use parameterized queries
- [ ] Test with multiple tenants
- [ ] Test unauthorized access
- [ ] Update documentation

## See Also

- [Migration Guide](./tenant_filtering_migration_guide.md) - Detailed migration instructions
- [Phase 3 Summary](./phase3_backend_implementation_summary.md) - Implementation overview
- [Architecture](../../.kiro/specs/Common/Multitennant/architecture.md) - Multi-tenant architecture
