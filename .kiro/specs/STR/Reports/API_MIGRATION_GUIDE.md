# STR/BNB API Migration Guide - Tenant Filtering Implementation

## Overview

This guide helps existing API consumers migrate to the new tenant-filtered STR/BNB endpoints. All BNB and STR endpoints now implement multi-tenant data isolation for enhanced security.

## What Changed

### Before (Pre-Tenant Filtering)

- Endpoints returned all data regardless of user's tenant access
- No tenant validation on write operations
- Single authentication requirement only

### After (With Tenant Filtering)

- Endpoints automatically filter data by user's accessible tenants
- Write operations validate tenant access before processing
- 403 errors returned for unauthorized tenant access
- Consistent tenant-aware error handling

## Breaking Changes

### 1. Data Filtering

**Impact**: API responses now contain only data from user's accessible tenants

**Before**:

```javascript
// Returned all BNB data regardless of user
const response = await fetch("/api/bnb/bnb-listing-data");
const data = await response.json();
// data.data contained all listings from all tenants
```

**After**:

```javascript
// Returns only data from user's accessible tenants
const response = await authenticatedGet("/api/bnb/bnb-listing-data");
const data = await response.json();
// data.data contains only listings from user's tenants
```

### 2. New Error Responses

**Impact**: Endpoints may return 403 errors for tenant access violations

**Before**:

```javascript
// Only handled 200/500 responses
if (response.ok) {
  const data = await response.json();
  // Process data
}
```

**After**:

```javascript
// Must handle 403 tenant access errors
if (response.status === 403) {
  const error = await response.json();
  console.error("Tenant access denied:", error.error);
  showUserMessage("You do not have permission to access this data");
  return;
}

if (response.ok) {
  const data = await response.json();
  // Process data
}
```

### 3. Write Operation Validation

**Impact**: STR write operations now validate tenant access

**Before**:

```javascript
// No tenant validation
const response = await fetch('/api/str-channel/save', {
  method: 'POST',
  body: JSON.stringify({
    transactions: [
      { Administration: 'AnyTenant', ... }
    ]
  })
});
```

**After**:

```javascript
// Validates all transactions belong to accessible tenants
const response = await authenticatedPost('/api/str-channel/save', {
  transactions: [
    { Administration: 'PeterPrive', ... }  // Must be accessible
  ]
});

if (response.status === 403) {
  // Handle tenant validation failure
  const error = await response.json();
  console.error('Unauthorized tenant:', error.error);
}
```

## Migration Steps

### Step 1: Update Error Handling

Add 403 error handling to all BNB and STR endpoint calls:

```javascript
// Before
async function loadBNBData() {
  const response = await fetch("/api/bnb/bnb-listing-data");
  if (response.ok) {
    return await response.json();
  }
  throw new Error("Failed to load data");
}

// After
async function loadBNBData() {
  const response = await authenticatedGet("/api/bnb/bnb-listing-data");

  if (response.status === 403) {
    throw new Error("You do not have permission to access this data");
  }

  if (response.ok) {
    return await response.json();
  }

  throw new Error("Failed to load data");
}
```

### Step 2: Update Data Processing Logic

Remove any client-side tenant filtering since it's now handled server-side:

```javascript
// Before - client-side filtering
async function getUserTenantData(userTenant) {
  const response = await fetch("/api/bnb/bnb-listing-data");
  const data = await response.json();

  // Client-side filtering - NO LONGER NEEDED
  return data.data.filter((item) => item.administration === userTenant);
}

// After - server-side filtering
async function getUserTenantData() {
  const response = await authenticatedGet("/api/bnb/bnb-listing-data");
  const data = await response.json();

  // Data is already filtered by server
  return data.data;
}
```

### Step 3: Update Write Operations

Add tenant validation error handling for STR write operations:

```javascript
// Before
async function saveTransactions(transactions) {
  const response = await fetch("/api/str-channel/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions }),
  });

  if (response.ok) {
    return await response.json();
  }

  throw new Error("Save failed");
}

// After
async function saveTransactions(transactions) {
  const response = await authenticatedPost("/api/str-channel/save", {
    transactions,
  });

  if (response.status === 403) {
    const error = await response.json();
    throw new Error(`Access denied: ${error.error}`);
  }

  if (response.ok) {
    return await response.json();
  }

  throw new Error("Save failed");
}
```

### Step 4: Update UI Components

Modify components to handle tenant access scenarios:

```javascript
// Before
function BNBReport() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      {data.map((item) => (
        <div key={item.id}>{item.name}</div>
      ))}
    </div>
  );
}

// After
function BNBReport() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData()
      .then(setData)
      .catch((err) => {
        if (err.message.includes("permission")) {
          setError("You do not have access to this data");
        } else {
          setError("Failed to load data");
        }
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div>
      {data.map((item) => (
        <div key={item.id}>{item.name}</div>
      ))}
    </div>
  );
}
```

## Affected Endpoints

### BNB Endpoints (Data Filtering Applied)

All endpoints now filter results by user's accessible tenants:

- ✅ `/api/bnb/bnb-listing-data`
- ✅ `/api/bnb/bnb-channel-data`
- ✅ `/api/bnb/bnb-table`
- ✅ `/api/bnb/bnb-guest-bookings`
- ✅ `/api/bnb/bnb-actuals`
- ✅ `/api/bnb/bnb-filter-options`
- ✅ `/api/bnb/bnb-violin-data`
- ✅ `/api/bnb/bnb-returning-guests`

### STR Endpoints (Tenant Validation Applied)

Write operations now validate tenant access:

- ✅ `/api/str-channel/save` - Validates transaction tenants
- ✅ `/api/str-invoice/generate-invoice` - Validates booking tenant
- ✅ `/api/str-invoice/upload-template` - Tenant-specific templates

## Testing Your Migration

### Test Scenarios

1. **Single Tenant User**
   - Verify data contains only user's tenant
   - Confirm write operations work for user's tenant
   - Test 403 error when accessing unauthorized tenant

2. **Multi-Tenant User**
   - Verify data contains all accessible tenants
   - Confirm write operations work for all accessible tenants
   - Test mixed tenant scenarios

3. **No Tenant Access**
   - Verify empty data sets are returned gracefully
   - Confirm appropriate error messages

### Test Code Example

```javascript
// Test tenant filtering
describe("BNB API Migration", () => {
  test("handles tenant access denial", async () => {
    // Mock 403 response
    global.fetch = jest.fn().mockResolvedValue({
      status: 403,
      ok: false,
      json: () =>
        Promise.resolve({
          success: false,
          error: "Access denied to administration: UnauthorizedTenant",
        }),
    });

    try {
      await loadBNBData();
      fail("Should have thrown error");
    } catch (error) {
      expect(error.message).toContain("permission");
    }
  });

  test("processes filtered data correctly", async () => {
    // Mock successful response with filtered data
    global.fetch = jest.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: () =>
        Promise.resolve({
          success: true,
          data: [{ administration: "PeterPrive", listing: "Test" }],
        }),
    });

    const data = await loadBNBData();
    expect(data.data).toHaveLength(1);
    expect(data.data[0].administration).toBe("PeterPrive");
  });
});
```

## Common Migration Issues

### Issue 1: Unexpected Empty Data

**Problem**: API returns empty data sets where data was previously available

**Cause**: User doesn't have access to the tenant that owns the data

**Solution**:

- Check user's tenant assignments
- Verify tenant names match exactly (case-sensitive)
- Review tenant access permissions

```javascript
// Debug tenant access
const response = await authenticatedGet("/api/bnb/bnb-listing-data");
const data = await response.json();

if (data.data.length === 0) {
  console.log("No data returned - check tenant access");
  console.log("User tenants:", data.accessible_tenants); // If provided
}
```

### Issue 2: 403 Errors on Previously Working Endpoints

**Problem**: Endpoints that worked before now return 403 errors

**Cause**: Tenant filtering is now enforced

**Solution**:

- Add 403 error handling to all affected endpoints
- Show user-friendly messages instead of technical errors
- Implement proper error boundaries

```javascript
// Handle 403 errors gracefully
async function apiCall(endpoint) {
  try {
    const response = await authenticatedGet(endpoint);

    if (response.status === 403) {
      // Don't expose technical details to users
      throw new Error("You do not have permission to access this data");
    }

    return await response.json();
  } catch (error) {
    // Log technical details for debugging
    console.error(`API call failed for ${endpoint}:`, error);
    throw error;
  }
}
```

### Issue 3: Write Operations Failing

**Problem**: STR save operations return 403 errors

**Cause**: Transactions contain data for tenants user doesn't have access to

**Solution**:

- Validate tenant access before sending requests
- Filter transactions to only include accessible tenants
- Provide clear error messages

```javascript
// Validate before sending
async function saveTransactions(transactions, userTenants) {
  // Client-side validation
  const invalidTenants = transactions
    .map((t) => t.Administration)
    .filter((admin) => !userTenants.includes(admin));

  if (invalidTenants.length > 0) {
    throw new Error(
      `Cannot save transactions for: ${invalidTenants.join(", ")}`,
    );
  }

  // Proceed with API call
  const response = await authenticatedPost("/api/str-channel/save", {
    transactions,
  });

  // Server-side validation backup
  if (response.status === 403) {
    const error = await response.json();
    throw new Error(`Server validation failed: ${error.error}`);
  }

  return await response.json();
}
```

## Performance Considerations

### Data Volume Changes

With tenant filtering, API responses may be significantly smaller:

```javascript
// Before: Might return 10,000 records from all tenants
// After: Might return 100 records from user's tenants

// Adjust pagination and caching accordingly
const pageSize = 50; // Reduced from 500
const cacheTimeout = 300000; // 5 minutes instead of 1 hour
```

### Caching Strategy

Update caching to account for tenant-specific data:

```javascript
// Before: Global cache key
const cacheKey = "bnb-listing-data";

// After: Tenant-specific cache key
const cacheKey = `bnb-listing-data-${userTenants.sort().join("-")}`;
```

## Rollback Plan

If issues arise during migration:

### Immediate Actions

1. **Monitor Error Rates**: Watch for increased 403 errors
2. **Check User Reports**: Look for "no data" complaints
3. **Verify Tenant Assignments**: Ensure users have correct tenant access

### Rollback Procedure

If rollback is necessary:

1. **Backend**: Temporarily disable `@tenant_required()` decorators
2. **Frontend**: Remove 403 error handling (optional)
3. **Database**: No changes needed (tenant filtering is query-level)

```python
# Temporary rollback - comment out tenant filtering
@bnb_bp.route('/bnb-listing-data', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
# @tenant_required()  # Temporarily disabled
def get_bnb_listing_data(user_email, user_roles):  # Remove tenant params
    # Remove tenant filtering from queries
    query = "SELECT * FROM bnb"  # No WHERE clause
    # ... rest of implementation
```

## Support and Troubleshooting

### Common Error Messages

| Error Message                                    | Cause                                             | Solution                           |
| ------------------------------------------------ | ------------------------------------------------- | ---------------------------------- |
| "Access denied to administration: X"             | User trying to access tenant X without permission | Check user's tenant assignments    |
| "You do not have permission to access this data" | User has no tenant access                         | Assign user to appropriate tenants |
| "Authentication required"                        | JWT token issues                                  | Check authentication flow          |

### Debug Information

Add debug logging to track tenant access:

```javascript
// Debug tenant filtering
function debugTenantAccess(endpoint, response) {
  if (response.status === 403) {
    console.group(`Tenant Access Debug: ${endpoint}`);
    console.log("Status:", response.status);
    console.log("User:", getCurrentUser());
    console.log("Timestamp:", new Date().toISOString());
    console.groupEnd();
  }
}
```

### Contact Information

For migration support:

- **Technical Issues**: Check existing implementations in `backend/src/bnb_routes.py`
- **Tenant Access Issues**: Review tenant assignments in AWS Cognito
- **Performance Issues**: Monitor database query performance

## Migration Checklist

### Pre-Migration

- [ ] Review all BNB/STR API calls in your application
- [ ] Identify components that process BNB/STR data
- [ ] Plan error handling strategy
- [ ] Prepare test scenarios

### During Migration

- [ ] Update error handling for all affected endpoints
- [ ] Remove client-side tenant filtering logic
- [ ] Add tenant validation for write operations
- [ ] Update UI components for error scenarios
- [ ] Test with different tenant access scenarios

### Post-Migration

- [ ] Monitor error rates and user feedback
- [ ] Verify data integrity and access patterns
- [ ] Update documentation and training materials
- [ ] Plan for ongoing tenant management

### Testing Checklist

- [ ] Single tenant user can access their data
- [ ] Multi-tenant user sees combined data
- [ ] Unauthorized access returns 403 with user-friendly message
- [ ] Write operations validate tenant access
- [ ] Empty tenant access returns empty data gracefully
- [ ] Performance is acceptable with tenant filtering

## Conclusion

The tenant filtering implementation enhances security by ensuring users can only access data from their authorized tenants. While this requires some migration effort, the patterns are consistent and the security benefits are significant.

Follow this guide step-by-step, test thoroughly, and monitor the migration closely. The new tenant-aware API provides a solid foundation for secure multi-tenant operations.
