# Role & Permission Quick Reference

**Last Updated**: January 23, 2026

## Quick Role Lookup

| Role             | Finance Access | STR Access   | System Admin |
| ---------------- | -------------- | ------------ | ------------ |
| `Finance_CRUD`   | ✅ Full        | ❌ None      | ❌ No        |
| `Finance_Read`   | ✅ Read-only   | ❌ None      | ❌ No        |
| `Finance_Export` | ✅ Export      | ❌ None      | ❌ No        |
| `STR_CRUD`       | ❌ None        | ✅ Full      | ❌ No        |
| `STR_Read`       | ❌ None        | ✅ Read-only | ❌ No        |
| `STR_Export`     | ❌ None        | ✅ Export    | ❌ No        |
| `SysAdmin`       | ✅ Full        | ✅ Full      | ✅ Yes       |

## Feature Access Matrix

| Feature                  | Required Roles                                               |
| ------------------------ | ------------------------------------------------------------ |
| 📄 Import Invoices       | `Finance_CRUD`, `Finance_Read`, `Finance_Export`, `SysAdmin` |
| 🏦 Import Banking        | `Finance_CRUD`, `SysAdmin`                                   |
| 🏠 Import STR Bookings   | `STR_CRUD`, `STR_Read`, `SysAdmin`                           |
| 🧾 STR Invoice Generator | `STR_CRUD`, `STR_Read`, `SysAdmin`                           |
| 💰 STR Pricing Model     | `STR_CRUD`, `SysAdmin`                                       |
| 📈 Financial Reports     | `Finance_CRUD`, `Finance_Read`, `Finance_Export`, `SysAdmin` |
| 📈 BNB Reports           | `STR_CRUD`, `STR_Read`, `STR_Export`, `SysAdmin`             |

## Code Examples

### Check if user has Finance access

```typescript
const { user } = useAuth();

// Check for any Finance access
const hasFinanceAccess = user?.roles?.some((role) =>
  ["Finance_CRUD", "Finance_Read", "Finance_Export", "SysAdmin"].includes(role),
);

// Check for Finance write access
const hasFinanceWrite = user?.roles?.some((role) =>
  ["Finance_CRUD", "SysAdmin"].includes(role),
);
```

### Check if user has STR access

```typescript
const { user } = useAuth();

// Check for any STR access
const hasStrAccess = user?.roles?.some((role) =>
  ["STR_CRUD", "STR_Read", "STR_Export", "SysAdmin"].includes(role),
);

// Check for STR write access
const hasStrWrite = user?.roles?.some((role) =>
  ["STR_CRUD", "SysAdmin"].includes(role),
);
```

### Protect a route

```typescript
<ProtectedRoute
  requiredRoles={['Finance_CRUD', 'SysAdmin']}
  onLoginSuccess={() => setCurrentPage('menu')}
>
  <YourComponent />
</ProtectedRoute>
```

### Conditionally render UI elements

```typescript
{/* Show button only for users with Finance CRUD access */}
{user?.roles?.some(role => ['Finance_CRUD', 'SysAdmin'].includes(role)) && (
  <Button onClick={handleImport}>Import Data</Button>
)}

{/* Show read-only view for Finance Read users */}
{user?.roles?.some(role => ['Finance_Read'].includes(role)) && (
  <Text>Read-only mode</Text>
)}
```

## Common Role Combinations

### Accountant (Finance + STR Read)

```typescript
roles: ["Finance_CRUD", "STR_Read"];
```

- Full access to financial data
- Read-only access to STR data
- Can view both Financial and BNB reports

### Property Manager (STR Only)

```typescript
roles: ["STR_CRUD"];
```

- Full access to STR features
- No access to financial data
- Can view BNB reports only

### Finance Viewer

```typescript
roles: ["Finance_Read"];
```

- Read-only access to invoices
- Can view Financial reports
- Cannot import or modify data

### Multi-Module Manager

```typescript
roles: ["Finance_CRUD", "STR_CRUD"];
```

- Full access to both Finance and STR modules
- Can view all reports
- Can perform all operations

## Permission Hierarchy

### Finance Module

```
Finance_CRUD (highest)
  ├── Can import invoices
  ├── Can import banking data
  ├── Can modify financial data
  └── Can view financial reports

Finance_Read
  ├── Can view invoices (read-only)
  └── Can view financial reports

Finance_Export
  ├── Can view invoices (read-only)
  └── Can export financial reports
```

### STR Module

```
STR_CRUD (highest)
  ├── Can import STR bookings
  ├── Can generate STR invoices
  ├── Can manage STR pricing
  └── Can view BNB reports

STR_Read
  ├── Can view STR bookings (read-only)
  ├── Can view STR invoices (read-only)
  └── Can view BNB reports

STR_Export
  ├── Can view STR data (read-only)
  └── Can export BNB reports
```

### System Administration

```
SysAdmin (highest)
  ├── Full access to all Finance features
  ├── Full access to all STR features
  ├── System configuration access
  └── User management access
```

## Migration from Legacy Roles

| Legacy Role    | New Role(s)                                 | Notes                         |
| -------------- | ------------------------------------------- | ----------------------------- |
| Administrators | `SysAdmin`                                  | Full system access            |
| Accountants    | `Finance_CRUD` or `Finance_CRUD + STR_Read` | Depends on STR access needs   |
| Viewers        | `Finance_Read` or `STR_Read`                | Choose based on module access |

## Best Practices

1. **Principle of Least Privilege**: Assign only the permissions users need
2. **Module Separation**: Keep Finance and STR permissions separate unless needed
3. **Use Read Roles**: For users who only need to view data, use `_Read` roles
4. **Combine Roles**: Users can have multiple roles for cross-module access
5. **SysAdmin Sparingly**: Only assign `SysAdmin` to actual system administrators

## Testing Checklist

When adding new features, verify:

- [ ] Feature is protected with appropriate role check
- [ ] UI elements are hidden for unauthorized users
- [ ] Backend API enforces the same permissions
- [ ] Error messages are user-friendly
- [ ] Audit logs capture access attempts

## Troubleshooting

### User can't see expected features

1. Check user's assigned roles in Cognito
2. Verify JWT token contains correct `cognito:groups`
3. Check browser console for authentication errors
4. Verify backend API permissions match frontend

### User sees features they shouldn't

1. Check role assignment logic in code
2. Verify ProtectedRoute is properly configured
3. Check for typos in role names
4. Ensure backend also blocks unauthorized access

## Related Documentation

- `RBAC_MENU_IMPLEMENTATION.md` - Complete RBAC implementation details
- `MODULE_PERMISSIONS_MIGRATION.md` - Migration guide from legacy roles
- `backend/docs/RBAC_IMPLEMENTATION_SUMMARY.md` - Backend RBAC documentation
