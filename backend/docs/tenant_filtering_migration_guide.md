# Tenant Filtering Migration Guide

This guide explains how to update existing API routes to support multi-tenant filtering.

## Overview

All routes that access tenant-specific data must:
1. Use the `@tenant_required()` decorator
2. Filter queries by the `administration` field
3. Validate tenant access before returning data

## Step-by-Step Migration

### 1. Import Required Functions

```python
from auth.tenant_context import tenant_required, add_tenant_filter
```

### 2. Add Tenant Decorator

Add `@tenant_required()` decorator after `@cognito_required()`:

```python
# BEFORE
@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def get_invoices(user_email, user_roles):
    # ...

# AFTER
@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
@tenant_required()
def get_invoices(user_email, user_roles, tenant, user_tenants):
    # tenant and user_tenants are now injected
    # ...
```

### 3. Update SQL Queries

#### Option A: Use `add_tenant_filter()` Helper

```python
# BEFORE
query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
params = ['2024-01-01']
results = db.execute_query(query, params, fetch=True)

# AFTER
query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
params = ['2024-01-01']
query, params = add_tenant_filter(query, params, tenant)
results = db.execute_query(query, params, fetch=True)
```

#### Option B: Manual Filtering

```python
# BEFORE
query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
params = ['2024-01-01']

# AFTER
query = "SELECT * FROM mutaties WHERE TransactionDate > %s AND administration = %s"
params = ['2024-01-01', tenant]
```

### 4. Handle Views

Views that already include `administration` field work automatically:

```python
# vw_mutaties already has administration field
query = "SELECT * FROM vw_mutaties WHERE jaar = %s AND administration = %s"
params = [2024, tenant]
```

### 5. SysAdmin Bypass (Optional)

For system administration routes that need to access all tenants:

```python
@app.route('/api/admin/all-transactions', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
@tenant_required(allow_sysadmin=True)
def get_all_transactions(user_email, user_roles, tenant, user_tenants):
    # SysAdmin can access without tenant filtering
    if 'SysAdmin' in user_roles:
        query = "SELECT * FROM mutaties"  # No tenant filter
    else:
        query = "SELECT * FROM mutaties WHERE administration = %s"
        params = [tenant]
```

## Examples

### Example 1: Simple Query

```python
@reporting_bp.route('/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
@tenant_required()
def get_invoices(user_email, user_roles, tenant, user_tenants):
    """Get invoices for current tenant"""
    
    # Build query with tenant filter
    query = """
        SELECT ID, TransactionDate, TransactionAmount, TransactionDescription
        FROM mutaties
        WHERE TransactionDate > %s
        AND administration = %s
        ORDER BY TransactionDate DESC
    """
    
    params = ['2024-01-01', tenant]
    results = db.execute_query(query, params, fetch=True)
    
    return jsonify({
        'success': True,
        'tenant': tenant,
        'data': results
    })
```

### Example 2: Using Helper Function

```python
@reporting_bp.route('/transactions', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def get_transactions(user_email, user_roles, tenant, user_tenants):
    """Get transactions for current tenant"""
    
    date_from = request.args.get('dateFrom', '2024-01-01')
    
    # Build base query
    query = "SELECT * FROM mutaties WHERE TransactionDate >= %s"
    params = [date_from]
    
    # Add tenant filter using helper
    query, params = add_tenant_filter(query, params, tenant)
    
    results = db.execute_query(query, params, fetch=True)
    
    return jsonify({
        'success': True,
        'tenant': tenant,
        'count': len(results),
        'data': results
    })
```

### Example 3: Complex Query with Joins

```python
@reporting_bp.route('/financial-summary', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_financial_summary(user_email, user_roles, tenant, user_tenants):
    """Get financial summary for current tenant"""
    
    query = """
        SELECT 
            m.TransactionDate,
            m.TransactionAmount,
            r.AccountName
        FROM mutaties m
        LEFT JOIN rekeningschema r ON m.Debet = r.AccountNumber
        WHERE m.TransactionDate >= %s
        AND m.administration = %s
        AND r.administration = %s
        ORDER BY m.TransactionDate DESC
    """
    
    params = ['2024-01-01', tenant, tenant]
    results = db.execute_query(query, params, fetch=True)
    
    return jsonify({
        'success': True,
        'tenant': tenant,
        'data': results
    })
```

### Example 4: Aggregation Query

```python
@reporting_bp.route('/revenue-by-month', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_revenue_by_month(user_email, user_roles, tenant, user_tenants):
    """Get monthly revenue for current tenant"""
    
    query = """
        SELECT 
            DATE_FORMAT(TransactionDate, '%Y-%m') as month,
            SUM(TransactionAmount) as total_revenue
        FROM mutaties
        WHERE Credit BETWEEN '4000' AND '4999'
        AND administration = %s
        GROUP BY month
        ORDER BY month DESC
    """
    
    params = [tenant]
    results = db.execute_query(query, params, fetch=True)
    
    return jsonify({
        'success': True,
        'tenant': tenant,
        'data': results
    })
```

## Testing

### Test with Multiple Tenants

```python
# Test user with GoodwinSolutions tenant
headers = {
    'Authorization': 'Bearer <jwt_token>',
    'X-Tenant': 'GoodwinSolutions'
}

response = requests.get('/api/invoices', headers=headers)
# Should only return GoodwinSolutions data

# Test user with PeterPrive tenant
headers = {
    'Authorization': 'Bearer <jwt_token>',
    'X-Tenant': 'PeterPrive'
}

response = requests.get('/api/invoices', headers=headers)
# Should only return PeterPrive data
```

### Test Tenant Isolation

```python
# User with only GoodwinSolutions access tries to access PeterPrive
headers = {
    'Authorization': 'Bearer <jwt_token_goodwin_only>',
    'X-Tenant': 'PeterPrive'
}

response = requests.get('/api/invoices', headers=headers)
# Should return 403 Forbidden
```

## Common Pitfalls

### 1. Forgetting to Add Tenant Filter

```python
# ❌ WRONG - No tenant filter
query = "SELECT * FROM mutaties WHERE TransactionDate > %s"

# ✅ CORRECT - With tenant filter
query = "SELECT * FROM mutaties WHERE TransactionDate > %s AND administration = %s"
params = [date, tenant]
```

### 2. Using Wrong Column Name

```python
# ❌ WRONG - Using uppercase (old schema)
query = "SELECT * FROM mutaties WHERE Administration = %s"

# ✅ CORRECT - Using lowercase (new schema)
query = "SELECT * FROM mutaties WHERE administration = %s"
```

### 3. Forgetting Tenant Filter in Joins

```python
# ❌ WRONG - Only filtering main table
query = """
    SELECT * FROM mutaties m
    LEFT JOIN rekeningschema r ON m.Debet = r.AccountNumber
    WHERE m.administration = %s
"""

# ✅ CORRECT - Filtering both tables
query = """
    SELECT * FROM mutaties m
    LEFT JOIN rekeningschema r ON m.Debet = r.AccountNumber
    WHERE m.administration = %s AND r.administration = %s
"""
params = [tenant, tenant]
```

### 4. Not Using Decorator

```python
# ❌ WRONG - No tenant validation
@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def get_invoices(user_email, user_roles):
    tenant = request.headers.get('X-Tenant')  # Not validated!
    query = f"SELECT * FROM mutaties WHERE administration = '{tenant}'"  # SQL injection risk!

# ✅ CORRECT - Using decorator
@app.route('/api/invoices', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
@tenant_required()
def get_invoices(user_email, user_roles, tenant, user_tenants):
    query = "SELECT * FROM mutaties WHERE administration = %s"
    params = [tenant]  # Safe parameterized query
```

## Migration Checklist

For each route that accesses tenant data:

- [ ] Import `tenant_required` and `add_tenant_filter`
- [ ] Add `@tenant_required()` decorator
- [ ] Update function signature to include `tenant` and `user_tenants`
- [ ] Add `administration = %s` filter to all queries
- [ ] Use parameterized queries (never string interpolation)
- [ ] Test with multiple tenants
- [ ] Test tenant isolation (unauthorized access)
- [ ] Update API documentation

## Routes to Migrate

Priority order:

1. **High Priority** (Financial data):
   - `/api/reports/*` - All reporting routes
   - `/api/invoices/*` - Invoice management
   - `/api/transactions/*` - Transaction routes
   - `/api/banking/*` - Banking routes

2. **Medium Priority** (STR data):
   - `/api/bnb/*` - BNB routes
   - `/api/str-channel/*` - STR channel routes
   - `/api/str-invoice/*` - STR invoice routes

3. **Low Priority** (System routes):
   - `/api/admin/*` - Admin routes (may need SysAdmin bypass)
   - `/api/audit/*` - Audit routes
   - `/api/cache/*` - Cache management

## Next Steps

1. Start with high-priority routes
2. Test each route after migration
3. Update frontend to send X-Tenant header
4. Add tenant selector to UI
5. Test end-to-end with multiple tenants
