# Tenant Filtering Patterns for Future Endpoints

## Overview

This document provides standardized patterns and best practices for implementing tenant filtering in new API endpoints. These patterns ensure consistent multi-tenant data isolation and security across the myAdmin application.

## Core Principles

1. **Default Deny**: All endpoints should deny access by default and explicitly grant access based on tenant permissions
2. **Explicit Filtering**: Every database query must include tenant filtering - no exceptions
3. **Consistent Error Handling**: Use standardized error responses for tenant access violations
4. **Performance Optimization**: Implement efficient tenant filtering with proper database indexing

## Implementation Patterns

### Pattern 1: Multi-Tenant Data Retrieval (BNB Style)

Use this pattern for endpoints that return data from multiple tenants that the user has access to.

#### Decorator Usage

```python
from auth.tenant_context import tenant_required
from auth.cognito_auth import cognito_required

@bp.route('/endpoint', methods=['GET'])
@cognito_required(required_permissions=['permission_name'])
@tenant_required()
def endpoint_handler(user_email, user_roles, tenant, user_tenants):
    # Implementation here
```

#### SQL Query Pattern

```python
def build_tenant_filtered_query(base_query, user_tenants, additional_conditions=None):
    """
    Build a tenant-filtered SQL query with proper parameterization

    Args:
        base_query (str): Base SQL query without WHERE clause
        user_tenants (list): List of tenant names user has access to
        additional_conditions (list): Additional WHERE conditions

    Returns:
        tuple: (query_string, parameters)
    """
    where_conditions = []
    params = []

    # Always add tenant filtering
    if user_tenants:
        placeholders = ', '.join(['%s'] * len(user_tenants))
        where_conditions.append(f"administration IN ({placeholders})")
        params.extend(user_tenants)
    else:
        # No tenants = no access
        where_conditions.append("1 = 0")

    # Add additional conditions
    if additional_conditions:
        for condition, condition_params in additional_conditions:
            where_conditions.append(condition)
            if condition_params:
                params.extend(condition_params)

    # Build final query
    where_clause = " AND ".join(where_conditions)
    final_query = f"{base_query} WHERE {where_clause}"

    return final_query, params

# Usage example
def get_bnb_data(user_tenants, year=None, listing=None):
    base_query = """
        SELECT listing, channel, year, revenue, administration
        FROM bnb
    """

    additional_conditions = []

    if year:
        additional_conditions.append(("year = %s", [year]))

    if listing:
        additional_conditions.append(("listing = %s", [listing]))

    query, params = build_tenant_filtered_query(
        base_query,
        user_tenants,
        additional_conditions
    )

    cursor.execute(query, params)
    return cursor.fetchall()
```

#### Complete Implementation Example

```python
@bnb_bp.route('/bnb-example', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
@tenant_required()
def get_bnb_example(user_email, user_roles, tenant, user_tenants):
    try:
        # Get query parameters
        year = request.args.get('year')
        listing = request.args.get('listing')

        # Build tenant-filtered query
        base_query = """
            SELECT listing, channel, year, revenue, bookings, administration
            FROM bnb
        """

        additional_conditions = []

        if year:
            additional_conditions.append(("year = %s", [year]))

        if listing:
            additional_conditions.append(("listing = %s", [listing]))

        query, params = build_tenant_filtered_query(
            base_query,
            user_tenants,
            additional_conditions
        )

        # Execute query
        cursor = get_db_cursor()
        cursor.execute(query, params)
        results = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': results,
            'tenant_filter_applied': True,
            'accessible_tenants': user_tenants
        })

    except Exception as e:
        logger.error(f"Error in get_bnb_example: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
```

### Pattern 2: Single Tenant Validation (STR Style)

Use this pattern for endpoints that operate on data from a single tenant, typically for write operations.

#### Implementation Example

```python
@str_bp.route('/str-example', methods=['POST'])
@cognito_required(required_permissions=['str_create'])
@tenant_required()
def create_str_example(user_email, user_roles, tenant, user_tenants):
    try:
        data = request.get_json()
        administration = data.get('administration', tenant)

        # Validate tenant access
        if administration not in user_tenants:
            return jsonify({
                'success': False,
                'error': f'Access denied to administration: {administration}'
            }), 403

        # Proceed with operation
        # ... implementation logic here

        return jsonify({
            'success': True,
            'message': f'Operation completed for administration: {administration}'
        })

    except Exception as e:
        logger.error(f"Error in create_str_example: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
```

### Pattern 3: Bulk Operations with Mixed Tenants

Use this pattern for endpoints that process multiple records that may belong to different tenants.

#### Implementation Example

```python
@str_bp.route('/bulk-save', methods=['POST'])
@cognito_required(required_permissions=['str_create'])
@tenant_required()
def bulk_save_example(user_email, user_roles, tenant, user_tenants):
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])

        # Validate all transactions belong to accessible tenants
        unauthorized_tenants = set()

        for transaction in transactions:
            admin = transaction.get('Administration')
            if admin and admin not in user_tenants:
                unauthorized_tenants.add(admin)

        if unauthorized_tenants:
            return jsonify({
                'success': False,
                'error': f'Access denied to administrations: {", ".join(unauthorized_tenants)}'
            }), 403

        # Process transactions
        saved_count = 0
        for transaction in transactions:
            # Save transaction logic here
            saved_count += 1

        return jsonify({
            'success': True,
            'saved_transactions': saved_count,
            'message': f'Successfully saved {saved_count} transactions'
        })

    except Exception as e:
        logger.error(f"Error in bulk_save_example: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
```

## Error Handling Patterns

### Standard Error Responses

#### Tenant Access Denied (403)

```python
def tenant_access_denied_response(administration=None):
    """Standard response for tenant access violations"""
    if administration:
        error_message = f'Access denied to administration: {administration}'
    else:
        error_message = 'Access denied - insufficient tenant permissions'

    return jsonify({
        'success': False,
        'error': error_message,
        'status': 'error'
    }), 403
```

#### Internal Server Error (500)

```python
def internal_server_error_response(error_id=None):
    """Standard response for internal server errors"""
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'error_id': error_id,
        'status': 'error'
    }), 500
```

### Error Logging Pattern

```python
import logging
import uuid

logger = logging.getLogger(__name__)

def log_tenant_violation(user_email, requested_tenant, user_tenants, endpoint):
    """Log tenant access violations for security monitoring"""
    error_id = str(uuid.uuid4())
    logger.warning(
        f"Tenant access violation - Error ID: {error_id}, "
        f"User: {user_email}, "
        f"Requested: {requested_tenant}, "
        f"Allowed: {user_tenants}, "
        f"Endpoint: {endpoint}"
    )
    return error_id
```

## Database Patterns

### Required Database Schema

All tables that require tenant filtering must have:

```sql
-- Administration column for tenant identification
administration VARCHAR(100) NOT NULL,

-- Index for performance
INDEX idx_administration (administration),

-- Composite indexes for common query patterns
INDEX idx_admin_year (administration, year),
INDEX idx_admin_date (administration, transaction_date)
```

### Query Optimization

#### Use Proper Indexing

```sql
-- For BNB table
CREATE INDEX idx_bnb_admin_year_listing ON bnb (administration, year, listing);
CREATE INDEX idx_bnb_admin_channel ON bnb (administration, channel);

-- For mutaties table
CREATE INDEX idx_mutaties_admin_date ON mutaties (administration, TransactionDate);
CREATE INDEX idx_mutaties_admin_ref ON mutaties (administration, ReferenceNumber);
```

#### Query Performance Monitoring

```python
import time

def execute_tenant_filtered_query(query, params, user_tenants):
    """Execute query with performance monitoring"""
    start_time = time.time()

    cursor = get_db_cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()

    execution_time = time.time() - start_time

    # Log slow queries
    if execution_time > 1.0:  # 1 second threshold
        logger.warning(
            f"Slow tenant-filtered query: {execution_time:.2f}s, "
            f"Tenants: {user_tenants}, "
            f"Query: {query[:100]}..."
        )

    return results
```

## Testing Patterns

### Test Scenarios Template

```python
import pytest
from unittest.mock import patch

class TestTenantFilteringEndpoint:
    """Template for testing tenant filtering endpoints"""

    def test_single_tenant_user_access(self, client, auth_headers):
        """Test user with single tenant access"""
        with patch('auth.tenant_context.get_user_tenants') as mock_tenants:
            mock_tenants.return_value = ['PeterPrive']

            response = client.get('/api/endpoint', headers=auth_headers)

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

            # Verify all returned data belongs to accessible tenant
            for item in data['data']:
                assert item['administration'] == 'PeterPrive'

    def test_multi_tenant_user_access(self, client, auth_headers):
        """Test user with multiple tenant access"""
        with patch('auth.tenant_context.get_user_tenants') as mock_tenants:
            mock_tenants.return_value = ['PeterPrive', 'GoodwinSolutions']

            response = client.get('/api/endpoint', headers=auth_headers)

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True

            # Verify all returned data belongs to accessible tenants
            allowed_tenants = {'PeterPrive', 'GoodwinSolutions'}
            for item in data['data']:
                assert item['administration'] in allowed_tenants

    def test_unauthorized_tenant_access(self, client, auth_headers):
        """Test access to unauthorized tenant data"""
        with patch('auth.tenant_context.get_user_tenants') as mock_tenants:
            mock_tenants.return_value = ['PeterPrive']

            # Try to access data for unauthorized tenant
            response = client.post('/api/endpoint',
                                 json={'administration': 'UnauthorizedTenant'},
                                 headers=auth_headers)

            assert response.status_code == 403
            data = response.get_json()
            assert data['success'] is False
            assert 'Access denied' in data['error']

    def test_no_tenant_access(self, client, auth_headers):
        """Test user with no tenant access"""
        with patch('auth.tenant_context.get_user_tenants') as mock_tenants:
            mock_tenants.return_value = []

            response = client.get('/api/endpoint', headers=auth_headers)

            assert response.status_code == 200
            data = response.get_json()
            assert data['success'] is True
            assert len(data['data']) == 0  # No data returned

    def test_sysadmin_access(self, client, auth_headers):
        """Test SysAdmin bypass (if applicable)"""
        with patch('auth.tenant_context.get_user_tenants') as mock_tenants:
            with patch('auth.tenant_context.is_sysadmin') as mock_sysadmin:
                mock_tenants.return_value = []
                mock_sysadmin.return_value = True

                response = client.get('/api/endpoint', headers=auth_headers)

                # SysAdmin should see all data regardless of tenant restrictions
                assert response.status_code == 200
                data = response.get_json()
                assert data['success'] is True
```

## Security Considerations

### SQL Injection Prevention

```python
# ❌ NEVER do this - vulnerable to SQL injection
def bad_query_example(user_tenants):
    tenants_str = "', '".join(user_tenants)
    query = f"SELECT * FROM bnb WHERE administration IN ('{tenants_str}')"
    return query

# ✅ ALWAYS do this - safe parameterized query
def good_query_example(user_tenants):
    placeholders = ', '.join(['%s'] * len(user_tenants))
    query = f"SELECT * FROM bnb WHERE administration IN ({placeholders})"
    return query, user_tenants
```

### Information Disclosure Prevention

```python
def safe_error_response(error_details, user_email):
    """Prevent information disclosure in error messages"""

    # Log detailed error for debugging
    logger.error(f"Detailed error for {user_email}: {error_details}")

    # Return generic error to client
    return jsonify({
        'success': False,
        'error': 'Access denied',
        'status': 'error'
    }), 403
```

### Audit Logging

```python
def log_tenant_access(user_email, endpoint, tenants_accessed, action):
    """Log tenant access for audit purposes"""
    logger.info(
        f"Tenant access - User: {user_email}, "
        f"Endpoint: {endpoint}, "
        f"Tenants: {tenants_accessed}, "
        f"Action: {action}, "
        f"Timestamp: {datetime.utcnow().isoformat()}"
    )
```

## Performance Optimization

### Query Optimization Checklist

- [ ] Administration column is indexed
- [ ] Composite indexes exist for common query patterns
- [ ] Query uses parameterized placeholders for tenant lists
- [ ] LIMIT clauses are used for large result sets
- [ ] Query execution time is monitored

### Caching Considerations

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_tenant_filter_options(user_tenants_tuple):
    """Cache filter options per tenant combination"""
    user_tenants = list(user_tenants_tuple)

    # Build and execute query
    query, params = build_tenant_filtered_query(
        "SELECT DISTINCT year, listing, channel FROM bnb",
        user_tenants
    )

    cursor = get_db_cursor()
    cursor.execute(query, params)
    return cursor.fetchall()

# Usage - convert list to tuple for caching
def get_filter_options_cached(user_tenants):
    return get_tenant_filter_options(tuple(sorted(user_tenants)))
```

## Migration Checklist

When adding tenant filtering to existing endpoints:

### Pre-Implementation

- [ ] Identify all database tables/views used by the endpoint
- [ ] Verify administration column exists in all tables
- [ ] Check existing indexes on administration column
- [ ] Review current query patterns

### Implementation

- [ ] Add `@tenant_required()` decorator
- [ ] Update function signature to include tenant parameters
- [ ] Implement tenant filtering in all SQL queries
- [ ] Add tenant validation for write operations
- [ ] Update error handling to use standard patterns

### Testing

- [ ] Write tests for single tenant access
- [ ] Write tests for multi-tenant access
- [ ] Write tests for unauthorized access attempts
- [ ] Test with empty tenant list
- [ ] Test SysAdmin bypass (if applicable)
- [ ] Performance test with large datasets

### Documentation

- [ ] Update API documentation
- [ ] Add endpoint to OpenAPI spec
- [ ] Document any special tenant filtering logic
- [ ] Update frontend integration guides

## Common Pitfalls

### 1. Forgetting Tenant Filtering in Subqueries

```python
# ❌ Bad - subquery not filtered
query = """
    SELECT * FROM bnb b
    WHERE administration IN (%s, %s)
    AND listing IN (
        SELECT DISTINCT listing FROM bnb  -- Missing tenant filter!
    )
"""

# ✅ Good - all queries filtered
query = """
    SELECT * FROM bnb b
    WHERE administration IN (%s, %s)
    AND listing IN (
        SELECT DISTINCT listing FROM bnb
        WHERE administration IN (%s, %s)  -- Tenant filter applied
    )
"""
```

### 2. Inconsistent Error Messages

```python
# ❌ Bad - inconsistent error messages
return jsonify({'error': 'No access'}), 403
return jsonify({'message': 'Forbidden'}), 403
return jsonify({'status': 'denied'}), 403

# ✅ Good - consistent error format
return jsonify({
    'success': False,
    'error': 'Access denied to administration: {tenant}',
    'status': 'error'
}), 403
```

### 3. Missing Parameter Validation

```python
# ❌ Bad - no validation
administration = data.get('administration')
if administration not in user_tenants:
    return error_response()

# ✅ Good - proper validation
administration = data.get('administration', tenant)
if not administration:
    return jsonify({
        'success': False,
        'error': 'Administration parameter is required'
    }), 400

if administration not in user_tenants:
    return tenant_access_denied_response(administration)
```

## Future Considerations

### Hierarchical Tenants

If implementing hierarchical tenant structures:

```python
def get_accessible_tenants_hierarchical(user_tenants, include_children=True):
    """Get tenants including hierarchical relationships"""
    accessible = set(user_tenants)

    if include_children:
        for tenant in user_tenants:
            children = get_child_tenants(tenant)
            accessible.update(children)

    return list(accessible)
```

### Tenant-Specific Features

```python
def get_tenant_features(tenant):
    """Get enabled features for specific tenant"""
    tenant_config = get_tenant_configuration(tenant)
    return tenant_config.get('enabled_features', [])

def feature_required(feature_name):
    """Decorator to check if tenant has specific feature enabled"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            tenant = kwargs.get('tenant')
            if feature_name not in get_tenant_features(tenant):
                return jsonify({
                    'success': False,
                    'error': f'Feature {feature_name} not enabled for tenant'
                }), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

## Conclusion

These patterns provide a solid foundation for implementing consistent, secure, and performant tenant filtering across all API endpoints. Always prioritize security and data isolation, and ensure comprehensive testing of tenant access controls.

For questions or clarifications on these patterns, refer to the existing implementations in:

- `backend/src/auth/tenant_context.py`
- `backend/src/bnb_routes.py`
- `backend/src/str_channel_routes.py`
- `backend/src/str_invoice_routes.py`
