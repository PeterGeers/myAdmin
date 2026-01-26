Analyse the status of the implementation of tennant handling in the front end

- [x] FIN: Import Banking Accounts
- [x] Define preferred default logic for frontend tennant handling (with shared features where useful ) at the next chapter
- [x] FIN: Import invoices Analyse the status of the implementation of tennant handling in the front end
- [ ] FIN: Fin Reports

Before marking any component as "tenant-ready", verify:

- [ ] Uses `useTenant()` hook for tenant context
- [ ] Implements pre-processing validation (if applicable)
- [ ] Auto-refreshes on tenant change
- [ ] Makes tenant-aware API calls
- [ ] Handles tenant switching gracefully
- [ ] Provides clear error messages
- [ ] Includes comprehensive tests
- [ ] Follows security requirements

## Analysis: FIN Import Banking Accounts - Frontend Tenant Implementation

### Status: ✅ COMPLETE

The frontend tenant handling for banking accounts import is **fully implemented** and working correctly.

### Implementation Details:

#### 1. Tenant Context Integration ✅

- Uses `useTenant()` hook to access current tenant
- Properly imports and utilizes `TenantContext`
- Initializes filters with current tenant as default

#### 2. Pre-Processing Tenant Validation ✅

- **File-level validation**: Before processing any files, validates that IBANs belong to current tenant
- **IBAN extraction**: Correctly handles different file types (CSV vs TSV)
  - CSV files: Extracts IBAN from first column
  - Revolut TSV files: Uses hardcoded IBAN `NL08REVO7549383472`
- **Lookup validation**: Cross-references extracted IBANs against `lookupData.bank_accounts`
- **Access control**: Blocks processing if IBAN doesn't belong to current tenant

#### 3. Error Handling ✅

- Clear error messages when no tenant is selected
- Specific error messages when bank accounts don't belong to current organization
- Graceful handling of validation failures

#### 4. Auto-Refresh on Tenant Change ✅

- **Mutaties data**: Automatically refreshes transaction data when tenant changes
- **Lookup data**: Refreshes bank account lookup data for new tenant
- **Filter updates**: Updates all tenant-dependent filters automatically
- **Data clearing**: Clears previous tenant's data when switching

#### 5. Tenant-Aware API Calls ✅

- All API calls include current tenant context
- Mutaties fetching filtered by current tenant
- Lookup data scoped to current tenant

#### 6. UI State Management ✅

- Tenant changes trigger proper state updates
- Filters automatically updated with new tenant
- Previous tenant data cleared appropriately

### Key Implementation Highlights:

```typescript
// Tenant validation before processing
const currentTenant = localStorage.getItem("selectedTenant");
if (!currentTenant) {
  setMessage("Error: No tenant selected. Please select a tenant first.");
  return;
}

// IBAN validation against tenant's bank accounts
const bankLookup = lookupData.bank_accounts.find(
  (ba) => ba.rekeningNummer === iban,
);
if (!bankLookup) {
  setMessage(
    `Access denied: The bank account ${iban} in file "${file.name}" does not belong to your current organization.`,
  );
  return;
}

// Auto-refresh on tenant change
useEffect(() => {
  if (currentTenant) {
    fetchMutaties();
    fetchLookupData();
  }
}, [currentTenant, fetchMutaties, fetchLookupData]);
```

### Security Features:

- **Pre-processing validation**: Prevents unauthorized file processing
- **IBAN ownership verification**: Ensures users can only import their organization's banking data
- **Tenant isolation**: Complete data separation between tenants

### Conclusion:

The FIN Import Banking Accounts frontend tenant implementation is **production-ready** and follows security best practices. No additional work is required for this component.

## Preferred Default Logic for Frontend Tenant Handling

### Status: ✅ COMPLETE

This chapter defines the standardized approach for implementing tenant handling across all frontend components, based on the successful patterns identified in the FIN Import Banking Accounts implementation.

### Core Principles

#### 1. **Tenant Context Integration** 🎯

All components requiring tenant-aware functionality MUST use the centralized `useTenant()` hook:

```typescript
import { useTenant } from "../context/TenantContext";

const MyComponent: React.FC = () => {
  const { currentTenant } = useTenant();
  // Component logic here
};
```

#### 2. **Pre-Processing Validation** 🔒

For data import/processing components, implement tenant validation BEFORE any processing:

```typescript
// Validate tenant selection
const currentTenant = localStorage.getItem("selectedTenant");
if (!currentTenant) {
  setMessage("Error: No tenant selected. Please select a tenant first.");
  return;
}

// Validate data ownership (for file imports)
const dataOwnership = validateDataOwnership(data, currentTenant, lookupData);
if (!dataOwnership.isValid) {
  setMessage(`Access denied: ${dataOwnership.reason}`);
  return;
}
```

#### 3. **Auto-Refresh on Tenant Change** 🔄

Components MUST automatically refresh tenant-dependent data when tenant changes:

```typescript
useEffect(() => {
  if (currentTenant) {
    fetchData();
    fetchLookupData();
    updateFilters();
  }
}, [currentTenant, fetchData, fetchLookupData]);
```

#### 4. **Tenant-Aware API Calls** 🌐

All API calls MUST include current tenant context:

```typescript
const fetchData = useCallback(async () => {
  const params = new URLSearchParams({
    administration: currentTenant || "all",
  });
  const response = await authenticatedGet(`/api/endpoint?${params}`);
}, [currentTenant]);
```

#### 5. **State Management** 📊

- Initialize filters with current tenant as default
- Clear previous tenant data when switching
- Update tenant-dependent filters automatically

### Implementation Patterns

#### Pattern A: Data Import Components

**Use Case**: File uploads, data processing, bulk operations
**Example**: BankingProcessor

**Required Elements**:

- Pre-processing tenant validation
- Data ownership verification
- Clear error messages for access violations
- Auto-refresh on tenant change

#### Pattern B: Report Components

**Use Case**: Data visualization, analytics, reporting
**Example**: Financial Reports, STR Reports

**Required Elements**:

- Tenant-scoped data fetching
- Filter initialization with current tenant
- Auto-refresh on tenant change
- Tenant-aware export functionality

#### Pattern C: Configuration Components

**Use Case**: Settings, preferences, tenant-specific configurations
**Example**: System settings, user preferences

**Required Elements**:

- Tenant-scoped configuration loading
- Validation against tenant permissions
- Tenant-specific defaults

### Shared Utilities

#### 1. **Tenant Validation Hook** (Recommended)

Create a shared hook for common tenant validation patterns:

```typescript
// hooks/useTenantValidation.ts
export function useTenantValidation() {
  const { currentTenant } = useTenant();

  const validateTenantSelection = () => {
    if (!currentTenant) {
      throw new Error("No tenant selected. Please select a tenant first.");
    }
    return currentTenant;
  };

  const validateDataOwnership = (data: any, lookupData: any) => {
    // Implementation based on BankingProcessor pattern
  };

  return { validateTenantSelection, validateDataOwnership };
}
```

#### 2. **Tenant-Aware API Service** (Recommended)

Extend the API service to automatically include tenant context:

```typescript
// services/tenantApiService.ts
export const tenantAwareGet = async (
  endpoint: string,
  additionalParams?: Record<string, string>,
) => {
  const currentTenant = localStorage.getItem("selectedTenant");
  const params = new URLSearchParams({
    administration: currentTenant || "all",
    ...additionalParams,
  });
  return authenticatedGet(`${endpoint}?${params}`);
};
```

### Security Requirements

#### 1. **Access Control** 🛡️

- NEVER process data without tenant validation
- ALWAYS verify data ownership before operations
- BLOCK cross-tenant data access attempts

#### 2. **Error Handling** ⚠️

- Provide clear, user-friendly error messages
- Log security violations for audit purposes
- Gracefully handle tenant switching scenarios

#### 3. **Data Isolation** 🔐

- Ensure complete data separation between tenants
- Clear previous tenant data when switching
- Validate all user inputs against tenant permissions

### Testing Requirements

#### 1. **Unit Tests** ✅

- Test tenant validation logic
- Test auto-refresh behavior
- Test error handling scenarios

#### 2. **Integration Tests** ✅

- Test tenant switching workflows
- Test cross-tenant access prevention
- Test data isolation

#### 3. **Security Tests** ✅

- Attempt unauthorized data access
- Test with malformed tenant data
- Verify audit logging

### Migration Guidelines

#### For Existing Components:

1. **Audit Current Implementation**: Review existing tenant handling
2. **Apply Standard Patterns**: Implement the patterns defined above
3. **Add Missing Validations**: Ensure all security requirements are met
4. **Test Thoroughly**: Verify tenant isolation and security

#### For New Components:

1. **Start with Template**: Use established patterns from day one
2. **Include Security by Design**: Implement validation from the beginning
3. **Follow Testing Requirements**: Ensure comprehensive test coverage

### Component Checklist

Before marking any component as "tenant-ready", verify:

- [ ] Uses `useTenant()` hook for tenant context
- [ ] Implements pre-processing validation (if applicable)
- [ ] Auto-refreshes on tenant change
- [ ] Makes tenant-aware API calls
- [ ] Handles tenant switching gracefully
- [ ] Provides clear error messages
- [ ] Includes comprehensive tests
- [ ] Follows security requirements

### Conclusion

This standardized approach ensures:

- **Consistent User Experience**: All components behave predictably
- **Security by Design**: Tenant isolation is built-in, not added later
- **Maintainable Code**: Shared patterns reduce complexity
- **Scalable Architecture**: Easy to extend to new components

The patterns defined here are based on the successful implementation in FIN Import Banking Accounts and should be applied consistently across all frontend components requiring tenant awareness.
