# Frontend Tenant Handling Utilities

This directory contains standardized utilities for implementing tenant-aware functionality across the frontend application.

## Overview

The tenant handling system provides:

- **Consistent tenant validation** across all components
- **Automatic tenant context** in API calls
- **Security-first approach** with built-in access controls
- **Comprehensive testing** for all tenant operations

## Quick Start

### 1. Basic Tenant Validation

```typescript
import { useTenantValidation } from "../hooks/useTenantValidation";

const MyComponent: React.FC = () => {
  const { validateTenantSelection, validateBankingDataOwnership } =
    useTenantValidation();

  const handleOperation = () => {
    try {
      const tenant = validateTenantSelection();
      // Proceed with tenant-aware operation
    } catch (error) {
      setError(error.message);
    }
  };
};
```

### 2. Tenant-Aware API Calls

```typescript
import { tenantAwareGet, tenantAwarePost } from "../services/tenantApiService";

// GET request with automatic tenant context
const response = await tenantAwareGet("/api/reports/data", { year: "2024" });

// POST request with tenant context in body
const result = await tenantAwarePost("/api/data/save", { name: "test" });
```

### 3. Data Ownership Validation

```typescript
import { useTenantValidation } from "../hooks/useTenantValidation";

const { validateBankingDataOwnership } = useTenantValidation();

const validation = validateBankingDataOwnership(
  "NL91ABNA0417164300",
  lookupData,
  "transactions.csv",
);

if (!validation.isValid) {
  setError(validation.reason);
  return;
}
```

## Available Utilities

### Hooks

#### `useTenantValidation`

Provides tenant validation utilities for components.

**Methods:**

- `validateTenantSelection()` - Ensures a tenant is selected
- `validateBankingDataOwnership(iban, lookupData, fileName?)` - Validates IBAN ownership
- `validateAdministrationAccess(administration)` - Validates admin access
- `getCurrentTenantFromStorage()` - Gets tenant from localStorage

### Services

#### `tenantApiService`

Extends base API service with automatic tenant context.

**Methods:**

- `tenantAwareGet(endpoint, params?, options?)` - GET with tenant context
- `tenantAwarePost(endpoint, data, options?)` - POST with tenant context
- `tenantAwarePut(endpoint, data, options?)` - PUT with tenant context
- `tenantAwareDelete(endpoint, params?, options?)` - DELETE with tenant context
- `getCurrentTenant()` - Get current tenant
- `requireTenant()` - Get tenant or throw error
- `createTenantParams(params?)` - Create tenant-aware URL params

### Types

#### `tenant.ts`

Provides TypeScript definitions for tenant operations.

**Key Types:**

- `TenantValidationResult` - Result of validation operations
- `DataOwnershipResult` - Result of ownership validation
- `TenantAwareFilters` - Standard filter interface
- `TenantError` - Standardized error class

## Implementation Patterns

### Pattern A: Data Import Components

For components that handle file uploads or data processing:

```typescript
const DataImportComponent: React.FC = () => {
  const { currentTenant } = useTenant();
  const { validateTenantSelection, validateBankingDataOwnership } =
    useTenantValidation();

  const handleFileUpload = async (files: File[]) => {
    try {
      // 1. Validate tenant selection
      validateTenantSelection();

      // 2. Validate data ownership
      for (const file of files) {
        const iban = extractIbanFromFile(file);
        const validation = validateBankingDataOwnership(
          iban,
          lookupData,
          file.name,
        );

        if (!validation.isValid) {
          setError(validation.reason);
          return;
        }
      }

      // 3. Process files
      await processFiles(files);
    } catch (error) {
      setError(error.message);
    }
  };

  // 4. Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      fetchData();
      fetchLookupData();
    }
  }, [currentTenant]);
};
```

### Pattern B: Report Components

For components that display tenant-scoped data:

```typescript
const ReportComponent: React.FC = () => {
  const { currentTenant } = useTenant();
  const [data, setData] = useState([]);

  const fetchReportData = useCallback(async () => {
    try {
      const response = await tenantAwareGet("/api/reports/data", {
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
      });
      setData(await response.json());
    } catch (error) {
      setError("Failed to load report data");
    }
  }, [filters]);

  // Auto-refresh on tenant change
  useEffect(() => {
    if (currentTenant) {
      fetchReportData();
    }
  }, [currentTenant, fetchReportData]);
};
```

### Pattern C: Configuration Components

For components that manage tenant-specific settings:

```typescript
const ConfigComponent: React.FC = () => {
  const { validateAdministrationAccess } = useTenantValidation();

  const handleSaveConfig = async (config: any) => {
    const validation = validateAdministrationAccess(config.administration);

    if (!validation.isValid) {
      setError(validation.reason);
      return;
    }

    await tenantAwarePost("/api/config/save", config);
  };
};
```

## Security Guidelines

### 1. Always Validate First

Never process data without validating tenant selection and ownership:

```typescript
// ❌ BAD - No validation
const processData = (data) => {
  // Process without checking tenant
};

// ✅ GOOD - Validate first
const processData = (data) => {
  validateTenantSelection();
  const validation = validateDataOwnership(data);
  if (!validation.isValid) {
    throw new Error(validation.reason);
  }
  // Now safe to process
};
```

### 2. Use Tenant-Aware APIs

Always use tenant-aware API methods for data operations:

```typescript
// ❌ BAD - Manual tenant handling
const response = await authenticatedGet(
  `/api/data?administration=${currentTenant}`,
);

// ✅ GOOD - Automatic tenant context
const response = await tenantAwareGet("/api/data");
```

### 3. Handle Tenant Changes

Components must respond to tenant changes:

```typescript
// ✅ Required pattern
useEffect(() => {
  if (currentTenant) {
    fetchData();
    clearPreviousData();
    updateFilters();
  }
}, [currentTenant]);
```

## Testing

All utilities include comprehensive tests. Run tests with:

```bash
# Test tenant validation hook
npm test -- --testPathPattern="useTenantValidation.test.ts" --watchAll=false

# Test tenant API service
npm test -- --testPathPattern="tenantApiService.test.ts" --watchAll=false
```

## Migration Guide

### Migrating Existing Components

1. **Replace manual tenant handling:**

   ```typescript
   // Before
   const currentTenant = localStorage.getItem("selectedTenant");

   // After
   const { currentTenant } = useTenant();
   ```

2. **Replace manual API calls:**

   ```typescript
   // Before
   const response = await authenticatedGet(
     `/api/data?administration=${tenant}`,
   );

   // After
   const response = await tenantAwareGet("/api/data");
   ```

3. **Add validation:**

   ```typescript
   // Add at the beginning of operations
   const { validateTenantSelection } = useTenantValidation();
   validateTenantSelection();
   ```

4. **Add auto-refresh:**
   ```typescript
   // Add effect for tenant changes
   useEffect(() => {
     if (currentTenant) {
       fetchData();
     }
   }, [currentTenant]);
   ```

## Best Practices

1. **Use TypeScript types** for better type safety
2. **Handle errors gracefully** with user-friendly messages
3. **Test tenant isolation** thoroughly
4. **Log security violations** for audit purposes
5. **Follow the established patterns** consistently

## Support

For questions or issues with tenant handling utilities:

1. Check the test files for usage examples
2. Review the implementation in `BankingProcessor.tsx`
3. Refer to the main documentation in the analysis document
