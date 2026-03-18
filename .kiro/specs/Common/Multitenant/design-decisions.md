# Multi-Tenant Design Decisions

## Decision: No `custom:default_tenant` Attribute

**Question**: Why don't we need a `custom:default_tenant` attribute in Cognito?

**Answer**: Default tenant selection is a **UI preference**, not an **identity attribute**.

### Rationale

1. **Frontend Responsibility**
   - Default tenant is about user experience, not authentication
   - Frontend can handle this with localStorage + first tenant fallback
   - No need to store in Cognito and sync across systems

2. **Simpler Architecture**
   - One less attribute to maintain in Cognito
   - No sync issues between Cognito and frontend preference
   - User can change default without Cognito API calls

3. **Better User Experience**
   - Frontend can remember last selected tenant (localStorage)
   - Fallback to first tenant in `custom:tenants` array
   - No server round-trip needed for preference

### Implementation

```typescript
// Frontend handles default tenant selection
useEffect(() => {
  if (tenants.length > 0 && !currentTenant) {
    // Try localStorage first (user preference)
    const savedTenant = localStorage.getItem("selectedTenant");
    if (savedTenant && tenants.includes(savedTenant)) {
      setCurrentTenant(savedTenant);
    } else {
      // Fallback to first tenant
      setCurrentTenant(tenants[0]);
    }
  }
}, [tenants]);
```

### What We DO Need in Cognito

**`custom:tenants` (JSON array)**

- Contains list of tenants user can access
- Example: `["GoodwinSolutions", "PeterPrive"]`
- This IS an identity attribute (authorization)
- Must be in JWT token for backend validation

### Summary

| Attribute               | Needed? | Reason                                                  |
| ----------------------- | ------- | ------------------------------------------------------- |
| `custom:tenants`        | ✅ Yes  | Authorization - backend needs to validate tenant access |
| `custom:default_tenant` | ❌ No   | UI preference - frontend can handle with localStorage   |

**Cognito Attributes**: Only store what's needed for authentication/authorization
**Frontend State**: Handle UI preferences and user experience
