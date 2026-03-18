# Tenant Management Quick Reference

## Overview

Quick reference for managing multi-tenant user assignments in Cognito.

## Common Tasks

### 1. Create New User with Tenant

```powershell
# Single tenant, single role
.\create-cognito-user.ps1 `
    -Email "user@test.com" `
    -Name "John Doe" `
    -Groups @("Finance_CRUD") `
    -Tenants @("GoodwinSolutions")

# Multiple tenants, multiple roles
.\create-cognito-user.ps1 `
    -Email "accountant@firm.com" `
    -Name "Jane Accountant" `
    -Groups @("Finance_CRUD", "Finance_Export") `
    -Tenants @("GoodwinSolutions", "PeterPrive")

# Tenant Admin
.\create-cognito-user.ps1 `
    -Email "admin@goodwin.com" `
    -Name "Goodwin Admin" `
    -Groups @("Tenant_Admin") `
    -Tenants @("GoodwinSolutions")
```

### 2. View User's Tenants

```powershell
.\assign-user-tenants.ps1 -Email "user@test.com"
```

### 3. Assign Tenant to Existing User

```powershell
# Set tenants (replace existing)
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "GoodwinSolutions" -Action set

# Add tenant to existing
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "PeterPrive" -Action add

# Assign multiple tenants
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "GoodwinSolutions,PeterPrive" -Action set
```

### 4. Remove Tenant from User

```powershell
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "InterimManagement" -Action remove
```

### 5. View User's Groups (Roles)

```powershell
.\assign-user-groups.ps1 -Email "user@test.com"
```

### 6. Assign Role to User

```powershell
# Add single role
.\assign-user-groups.ps1 -Email "user@test.com" -Groups "Finance_Export" -Action add

# Add multiple roles
.\assign-user-groups.ps1 -Email "user@test.com" -Groups "Finance_CRUD,Finance_Export" -Action add
```

### 7. Remove Role from User

```powershell
.\assign-user-groups.ps1 -Email "user@test.com" -Groups "Accountants" -Action remove
```

### 8. Migrate All Users to Default Tenant

**Note**: This is typically done manually per user using `assign-user-tenants.ps1` as shown in scenario 7 above.

For bulk operations, you can use AWS CLI:

```powershell
# Get all users and assign tenant to each
$users = aws cognito-idp list-users --user-pool-id <pool-id> --region eu-west-1 | ConvertFrom-Json
foreach ($user in $users.Users) {
    $email = ($user.Attributes | Where-Object { $_.Name -eq "email" }).Value
    .\assign-user-tenants.ps1 -Email $email -Tenants "GoodwinSolutions" -Action set
}
```

## Available Tenants

- `GoodwinSolutions` - Primary tenant
- `PeterPrive` - Secondary tenant
- `InterimManagement` - Third tenant

## Available Roles

### System Roles

- `Administrators` - Full system access (legacy)
- `Tenant_Admin` - Tenant administrator (manage config, users, secrets)
- `SysAdmin` - System administration (no tenant data access)
- `Viewers` - Read-only access (legacy)

### Finance Module

- `Finance_Read` - Read-only financial data
- `Finance_CRUD` - Full financial data access
- `Finance_Export` - Export financial reports

### STR Module

- `STR_Read` - Read-only STR data
- `STR_CRUD` - Full STR data access
- `STR_Export` - Export STR reports

### Legacy (Backward Compatibility)

- `Accountants` - Maps to Finance_CRUD + Finance_Export

## Common User Scenarios

### Scenario 1: Accountant for Single Tenant

```powershell
.\create-cognito-user.ps1 `
    -Email "accountant@goodwin.com" `
    -Name "Goodwin Accountant" `
    -Groups @("Finance_CRUD", "Finance_Export") `
    -Tenants @("GoodwinSolutions")
```

**Result**: User can access financial data for GoodwinSolutions only

### Scenario 2: Accountant for Multiple Tenants

```powershell
.\create-cognito-user.ps1 `
    -Email "accountant@firm.com" `
    -Name "Multi-Tenant Accountant" `
    -Groups @("Finance_CRUD", "Finance_Export") `
    -Tenants @("GoodwinSolutions", "PeterPrive")
```

**Result**: User can access financial data for both GoodwinSolutions and PeterPrive

### Scenario 3: Tenant Admin for Single Tenant

```powershell
.\create-cognito-user.ps1 `
    -Email "admin@goodwin.com" `
    -Name "Goodwin Admin" `
    -Groups @("Tenant_Admin") `
    -Tenants @("GoodwinSolutions")
```

**Result**: User can manage GoodwinSolutions configuration, users, and secrets

### Scenario 4: Tenant Admin for Multiple Tenants

```powershell
.\create-cognito-user.ps1 `
    -Email "superadmin@firm.com" `
    -Name "Multi-Tenant Admin" `
    -Groups @("Tenant_Admin") `
    -Tenants @("GoodwinSolutions", "PeterPrive", "InterimManagement")
```

**Result**: User can manage all three tenants

### Scenario 5: Read-Only User for STR Module

```powershell
.\create-cognito-user.ps1 `
    -Email "viewer@goodwin.com" `
    -Name "STR Viewer" `
    -Groups @("STR_Read") `
    -Tenants @("GoodwinSolutions")
```

**Result**: User can view STR data for GoodwinSolutions (read-only)

### Scenario 6: System Administrator (No Tenant Access)

```powershell
.\create-cognito-user.ps1 `
    -Email "sysadmin@firm.com" `
    -Name "System Admin" `
    -Groups @("SysAdmin")
```

**Result**: User can access system logs, config, templates but NO tenant data

### Scenario 7: Add Tenant to Existing User

```powershell
# User currently has access to GoodwinSolutions
# Add PeterPrive access
.\assign-user-tenants.ps1 -Email "accountant@firm.com" -Tenants "PeterPrive" -Action add
```

**Result**: User now has access to both GoodwinSolutions and PeterPrive

### Scenario 8: Change User's Tenants

```powershell
# Replace all tenants with new list
.\assign-user-tenants.ps1 -Email "accountant@firm.com" -Tenants "InterimManagement" -Action set
```

**Result**: User now only has access to InterimManagement

## Verification

### Check JWT Token Contains Tenants

1. Log in as the user
2. Copy the JWT token from browser (localStorage or cookies)
3. Decode at https://jwt.io
4. Verify token contains:
   ```json
   {
     "custom:tenants": ["GoodwinSolutions", "PeterPrive"]
   }
   ```

### Check User Attributes in Cognito

```powershell
# Using AWS CLI
aws cognito-idp admin-get-user `
    --user-pool-id <pool-id> `
    --username user@test.com `
    --region eu-west-1
```

Look for:

```json
{
  "Name": "custom:tenants",
  "Value": "[\"GoodwinSolutions\",\"PeterPrive\"]"
}
```

## Troubleshooting

### Issue: Script can't find User Pool ID

**Solution**: Manually specify User Pool ID

```powershell
.\assign-user-tenants.ps1 -UserPoolId "eu-west-1_XXXXXXX" -Email "user@test.com"
```

### Issue: User doesn't see tenants in JWT

**Solution**: User must log out and log back in to get new token with updated attributes

### Issue: Cannot update user attributes

**Possible causes**:

1. AWS CLI not configured correctly
2. Insufficient permissions on User Pool
3. Wrong AWS region

**Solution**: Verify AWS CLI configuration

```powershell
aws configure list
aws cognito-idp list-user-pools --max-results 10 --region eu-west-1
```

### Issue: User has tenants but can't access data

**Possible causes**:

1. User doesn't have appropriate role (Finance_CRUD, STR_CRUD, etc.)
2. Backend not filtering by tenant correctly
3. Frontend not sending X-Tenant header

**Solution**: Verify user has both tenant assignment AND appropriate role

```powershell
.\assign-user-tenants.ps1 -Email "user@test.com"
.\assign-user-groups.ps1 -Email "user@test.com"
```

## Best Practices

1. **Principle of Least Privilege**: Only assign tenants and roles that users need
2. **Separate SysAdmin**: Don't give SysAdmin role tenant data access in production
3. **Tenant Admin Scope**: Tenant_Admin should only manage their assigned tenants
4. **Regular Audits**: Periodically review user tenant assignments
5. **Document Changes**: Keep track of who has access to which tenants

## Related Documentation

- Full Architecture: `.kiro/specs/Common/Multitennant/architecture.md`
- Phase 2 Details: `.kiro/specs/Common/Multitennant/PHASE2_COGNITO_SETUP.md`
- Cognito Configuration: `infrastructure/cognito.tf`
