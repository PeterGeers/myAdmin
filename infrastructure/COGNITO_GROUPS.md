# Cognito Groups Structure

## Overview

**User Pool ID**: `eu-west-1_Hdp40eWmu`  
**Region**: `eu-west-1`

## Current Groups

### System Roles

| Group              | Precedence | Description           | Access                                 |
| ------------------ | ---------- | --------------------- | -------------------------------------- |
| **Administrators** | 1          | Full system access    | Everything                             |
| **SysAdmin**       | 5          | System administration | Logs, config, templates (no user data) |
| **Viewers**        | 3          | Read-only access      | Reports only                           |

### Finance Module

| Group              | Precedence | Description              | Permissions                                 |
| ------------------ | ---------- | ------------------------ | ------------------------------------------- |
| **Finance_Read**   | 10         | Read-only financial data | View invoices, transactions, reports        |
| **Finance_CRUD**   | 9          | Full financial access    | Create, read, update, delete financial data |
| **Finance_Export** | 11         | Export financial data    | Export reports and data                     |

### STR Module (Short-Term Rental)

| Group          | Precedence | Description        | Permissions                           |
| -------------- | ---------- | ------------------ | ------------------------------------- |
| **STR_Read**   | 20         | Read-only STR data | View bookings, pricing, reports       |
| **STR_CRUD**   | 19         | Full STR access    | Create, read, update, delete STR data |
| **STR_Export** | 21         | Export STR data    | Export STR reports and data           |

### Legacy Groups

| Group           | Precedence | Description          | Maps To                       |
| --------------- | ---------- | -------------------- | ----------------------------- |
| **Accountants** | 2          | Financial operations | Finance_CRUD + Finance_Export |

## Group Precedence

Lower number = higher priority. When a user has multiple groups, the lowest precedence number takes effect for conflicting permissions.

```
1  - Administrators (highest priority)
2  - Accountants (legacy)
3  - Viewers
5  - SysAdmin
9  - Finance_CRUD
10 - Finance_Read
11 - Finance_Export
19 - STR_CRUD
20 - STR_Read
21 - STR_Export
```

## Common User Configurations

### Administrator

```powershell
Groups: Administrators
Access: Everything
```

### Accountant (New Style)

```powershell
Groups: Finance_CRUD, Finance_Export
Access: Full financial operations + export
```

### Accountant (Legacy Style)

```powershell
Groups: Accountants
Access: Full financial operations (backward compatible)
```

### Financial Analyst

```powershell
Groups: Finance_Read, Finance_Export
Access: View and export financial data (no editing)
```

### STR Manager

```powershell
Groups: STR_CRUD, STR_Export
Access: Full STR operations + export
```

### STR Viewer

```powershell
Groups: STR_Read
Access: View STR data only
```

### Multi-Module User

```powershell
Groups: Finance_CRUD, STR_Read, Finance_Export
Access: Full finance access + view STR data + export finance reports
```

### System Administrator

```powershell
Groups: SysAdmin
Access: System logs, config, templates (no user data)
```

### Report Viewer

```powershell
Groups: Viewers
Access: Read-only reports
```

## Management Scripts

### Create Groups

```powershell
.\infrastructure\create-module-groups.ps1
```

### List User's Groups

```powershell
.\infrastructure\assign-user-groups.ps1 -Email "user@example.com"
```

### Add User to Groups

```powershell
.\infrastructure\assign-user-groups.ps1 -Email "user@example.com" -Groups "Finance_CRUD,Finance_Export" -Action add
```

### Remove User from Group

```powershell
.\infrastructure\assign-user-groups.ps1 -Email "user@example.com" -Groups "Accountants" -Action remove
```

### Direct AWS CLI Commands

```powershell
# Add user to group
aws cognito-idp admin-add-user-to-group `
    --user-pool-id eu-west-1_Hdp40eWmu `
    --username user@example.com `
    --group-name Finance_CRUD `
    --region eu-west-1

# Remove user from group
aws cognito-idp admin-remove-user-from-group `
    --user-pool-id eu-west-1_Hdp40eWmu `
    --username user@example.com `
    --group-name Accountants `
    --region eu-west-1

# List user's groups
aws cognito-idp admin-list-groups-for-user `
    --user-pool-id eu-west-1_Hdp40eWmu `
    --username user@example.com `
    --region eu-west-1

# List all groups
aws cognito-idp list-groups `
    --user-pool-id eu-west-1_Hdp40eWmu `
    --region eu-west-1
```

## Migration Guide

### Migrating from Legacy to Module-Based Groups

**Current**: User has `Accountants` group  
**New**: User should have `Finance_CRUD` + `Finance_Export`

```powershell
# Step 1: Add new groups
.\infrastructure\assign-user-groups.ps1 -Email "accountant@test.com" -Groups "Finance_CRUD,Finance_Export" -Action add

# Step 2: Test that user has correct access

# Step 3: Remove legacy group (optional, for cleanup)
.\infrastructure\assign-user-groups.ps1 -Email "accountant@test.com" -Groups "Accountants" -Action remove
```

**Note**: Keep legacy groups for backward compatibility during transition period.

## Permission Matrix

| Feature           | Administrators | Accountants | Finance_CRUD | Finance_Read | STR_CRUD | STR_Read | Viewers | SysAdmin |
| ----------------- | -------------- | ----------- | ------------ | ------------ | -------- | -------- | ------- | -------- |
| Import Invoices   | ✅             | ✅          | ✅           | ✅           | ❌       | ❌       | ✅ (RO) | ❌       |
| Import Banking    | ✅             | ✅          | ❌           | ❌           | ❌       | ❌       | ❌      | ❌       |
| Import STR        | ✅             | ❌          | ❌           | ❌           | ✅       | ✅ (RO)  | ❌      | ❌       |
| STR Invoice       | ✅             | ❌          | ❌           | ❌           | ✅       | ✅       | ❌      | ❌       |
| STR Pricing       | ✅             | ❌          | ❌           | ❌           | ✅       | ❌       | ❌      | ❌       |
| Financial Reports | ✅             | ✅          | ✅           | ✅           | ❌       | ❌       | ✅ (RO) | ❌       |
| BNB Reports       | ✅             | ❌          | ❌           | ❌           | ✅       | ✅ (RO)  | ❌      | ❌       |
| Export Data       | ✅             | ✅          | ❌           | ❌           | ❌       | ❌       | ❌      | ❌       |
| System Logs       | ✅             | ❌          | ❌           | ❌           | ❌       | ❌       | ❌      | ✅       |
| System Config     | ✅             | ❌          | ❌           | ❌           | ❌       | ❌       | ❌      | ✅       |

RO = Read-Only

## Best Practices

1. **Principle of Least Privilege**: Assign only the groups users need
2. **Use Module Groups**: Prefer `Finance_CRUD` over legacy `Accountants` for new users
3. **Multiple Groups**: Users can have multiple groups for cross-functional roles
4. **Regular Audits**: Review user group assignments quarterly
5. **Document Changes**: Log all group assignment changes for audit trail

## Troubleshooting

### User can't see expected features

```powershell
# Check user's groups
.\infrastructure\assign-user-groups.ps1 -Email "user@example.com"

# Verify groups match required permissions in RBAC_MENU_IMPLEMENTATION.md
```

### User has too much access

```powershell
# List current groups
.\infrastructure\assign-user-groups.ps1 -Email "user@example.com"

# Remove unnecessary groups
.\infrastructure\assign-user-groups.ps1 -Email "user@example.com" -Groups "GroupToRemove" -Action remove
```

### Need to create new group

```powershell
aws cognito-idp create-group `
    --user-pool-id eu-west-1_Hdp40eWmu `
    --group-name NewGroupName `
    --description "Description" `
    --precedence 15 `
    --region eu-west-1
```

## Related Documentation

- Frontend RBAC: `frontend/RBAC_MENU_IMPLEMENTATION.md`
- Backend RBAC: `backend/docs/RBAC_IMPLEMENTATION_SUMMARY.md`
- Cognito Setup: `infrastructure/COGNITO_QUICK_START.md`
