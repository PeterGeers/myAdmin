# Phase 2: Cognito Setup - Multi-Tenant Support

## Overview

This document describes the Cognito configuration for multi-tenant support in myAdmin. Phase 2 implements the tenant assignment system using Cognito custom attributes and groups.

## Implementation Status

✅ **COMPLETED** - Phase 2 Cognito Setup

## What Was Implemented

### 1. Custom Attribute: `custom:tenants`

**Purpose**: Store a JSON array of tenant names that a user can access

**Configuration**:

- Attribute Name: `custom:tenants`
- Type: String
- Max Length: 2048 characters (supports up to 100 tenants)
- Mutable: Yes
- Format: JSON array, e.g., `["GoodwinSolutions", "PeterPrive"]`

**Already exists in Cognito schema** (defined as "tenants" in terraform)

### 2. Cognito Groups

The following groups have been added to the Terraform configuration:

#### Tenant Management

- **Tenant_Admin** (Precedence: 4)
  - Can manage tenant configuration, users, and secrets for assigned tenants
  - Tenant access controlled by `custom:tenants` attribute
  - Cannot access tenants not in their assignment list

#### Module-Based Access Control

- **Finance_Read** (Precedence: 10) - Read-only financial data
- **Finance_CRUD** (Precedence: 9) - Full financial data access
- **Finance_Export** (Precedence: 11) - Export financial reports

- **STR_Read** (Precedence: 20) - Read-only STR data
- **STR_CRUD** (Precedence: 19) - Full STR data access
- **STR_Export** (Precedence: 21) - Export STR reports

#### System Administration

- **SysAdmin** (Precedence: 5)
  - System administration only (logs, config, templates)
  - **No tenant data access** unless explicitly assigned tenants + module role
  - Separation of duties: system admin vs. data access

#### Legacy Groups (Backward Compatibility)

- **Administrators** (Precedence: 1) - Full system access
- **Accountants** (Precedence: 2) - Financial data management
- **Viewers** (Precedence: 3) - Read-only access

### 3. User Pool Client Updates

Updated read/write attributes to include:

- `custom:tenants` - JSON array of accessible tenants

### 4. PowerShell Scripts

#### New Scripts

**`assign-user-tenants.ps1`** - Manage tenant assignments

```powershell
# List user's tenants
.\assign-user-tenants.ps1 -Email "user@test.com"

# Set tenants (replace existing)
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "GoodwinSolutions" -Action set

# Add tenant to existing
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "PeterPrive" -Action add

# Remove tenant
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "InterimManagement" -Action remove

# Assign multiple tenants
.\assign-user-tenants.ps1 -Email "admin@test.com" -Tenants "GoodwinSolutions,PeterPrive" -Action set
```

#### Updated Scripts

**`create-cognito-user.ps1`** - Now supports:

- Multiple groups assignment
- Tenant assignment via `-Tenants` parameter
- Backward compatible with old single-group syntax

```powershell
# Create user with tenant and role
.\create-cognito-user.ps1 `
    -Email "accountant@test.com" `
    -Name "John Accountant" `
    -Groups @("Finance_CRUD", "Finance_Export") `
    -Tenants @("GoodwinSolutions")

# Create tenant admin for multiple tenants
.\create-cognito-user.ps1 `
    -Email "admin@test.com" `
    -Name "Tenant Admin" `
    -Groups @("Tenant_Admin") `
    -Tenants @("GoodwinSolutions", "PeterPrive")

# Create SysAdmin (no tenant access)
.\create-cognito-user.ps1 `
    -Email "sysadmin@test.com" `
    -Name "System Admin" `
    -Groups @("SysAdmin")
```

## Deployment Steps

### Step 1: Apply Terraform Changes

```powershell
cd infrastructure
terraform plan
terraform apply
```

This will:

- Create the Tenant_Admin group
- Create module-based groups (Finance*\*, STR*\*)
- Create SysAdmin group
- Update User Pool Client to include custom:tenants attribute

### Step 2: Assign Tenants to Users

For each user, assign their tenant access:

```powershell
# Assign single tenant
.\assign-user-tenants.ps1 -Email "user@test.com" -Tenants "GoodwinSolutions" -Action set

# Assign multiple tenants
.\assign-user-tenants.ps1 -Email "admin@test.com" -Tenants "GoodwinSolutions,PeterPrive" -Action set
```

### Step 3: Verify User Assignments

```powershell
# Check a user's tenant assignments
.\assign-user-tenants.ps1 -Email "user@test.com"

# Check a user's group memberships
.\assign-user-groups.ps1 -Email "user@test.com"
```

### Step 4: Test JWT Token

After deployment, verify that JWT tokens contain the `custom:tenants` attribute:

1. Log in as a user
2. Decode the JWT token (use jwt.io or similar)
3. Verify the token contains: `"custom:tenants": ["GoodwinSolutions"]`

## User Role Examples

### Example 1: Tenant Admin for Single Tenant

```powershell
.\create-cognito-user.ps1 `
    -Email "admin@goodwin.com" `
    -Name "Goodwin Admin" `
    -Groups @("Tenant_Admin") `
    -Tenants @("GoodwinSolutions")
```

**Permissions**:

- Can manage GoodwinSolutions configuration
- Can manage users within GoodwinSolutions
- Can manage secrets for GoodwinSolutions
- Cannot access PeterPrive or InterimManagement

### Example 2: Accountant for Multiple Tenants

```powershell
.\create-cognito-user.ps1 `
    -Email "accountant@firm.com" `
    -Name "Multi-Tenant Accountant" `
    -Groups @("Finance_CRUD", "Finance_Export") `
    -Tenants @("GoodwinSolutions", "PeterPrive")
```

**Permissions**:

- Can access financial data for GoodwinSolutions and PeterPrive
- Can create, read, update, delete invoices/transactions
- Can export financial reports
- Cannot access InterimManagement

### Example 3: Tenant Admin for Multiple Tenants

```powershell
.\create-cognito-user.ps1 `
    -Email "superadmin@firm.com" `
    -Name "Multi-Tenant Admin" `
    -Groups @("Tenant_Admin") `
    -Tenants @("GoodwinSolutions", "PeterPrive", "InterimManagement")
```

**Permissions**:

- Can manage configuration for all three tenants
- Can manage users for all three tenants
- Can manage secrets for all three tenants

### Example 4: SysAdmin (No Tenant Access)

```powershell
.\create-cognito-user.ps1 `
    -Email "sysadmin@firm.com" `
    -Name "System Administrator" `
    -Groups @("SysAdmin")
```

**Permissions**:

- Can access system logs, configuration, templates
- **Cannot access any tenant data** (no tenants assigned)
- Separation of duties: system management vs. data access

### Example 5: SysAdmin with Development Access

```powershell
.\create-cognito-user.ps1 `
    -Email "dev@firm.com" `
    -Name "Developer" `
    -Groups @("SysAdmin", "Finance_CRUD") `
    -Tenants @("GoodwinSolutions")

# Note: This is for development/testing only
# Production best practice: separate SysAdmin and data access users
```

## Available Tenants

- **GoodwinSolutions** - Primary tenant
- **PeterPrive** - Secondary tenant
- **InterimManagement** - Third tenant

## Security Considerations

### Tenant Isolation

- Users can only access tenants in their `custom:tenants` attribute
- Backend validates tenant access on every request
- JWT token contains tenant list for client-side validation

### SysAdmin Separation

- SysAdmin role does NOT grant tenant data access
- SysAdmin needs explicit tenant assignment + module role to access data
- Production best practice: separate SysAdmin users from data access users

### Tenant_Admin Permissions

- Can only manage tenants in their assignment list
- Cannot assign SysAdmin or other Tenant_Admin roles
- Can only assign module roles (Finance*\*, STR*\*)
- All actions are audit logged

## Verification Checklist

- [ ] Terraform applied successfully
- [ ] Tenant_Admin group created
- [ ] Module groups created (Finance*\*, STR*\*)
- [ ] SysAdmin group created
- [ ] Existing users migrated to default tenant
- [ ] JWT tokens contain `custom:tenants` attribute
- [ ] User can be assigned multiple tenants
- [ ] Tenant assignment scripts work correctly
- [ ] User creation script supports new parameters

## Next Steps

After completing Phase 2, proceed to:

**Phase 3: Backend Implementation**

- Create tenant context middleware
- Implement Tenant_Admin validation
- Update all queries to filter by `administration` field
- Add tenant validation to all endpoints
- Create Tenant_Admin API endpoints
- Implement tenant secret encryption

See `.kiro/specs/Common/Multitennant/architecture.md` for details.

## Troubleshooting

### Issue: User Pool ID not found

```powershell
# Manually specify User Pool ID
.\assign-user-tenants.ps1 -UserPoolId "eu-west-1_XXXXXXX" -Email "user@test.com"
```

### Issue: JWT token doesn't contain custom:tenants

1. Verify attribute is in User Pool schema
2. Verify attribute is in User Pool Client read_attributes
3. User must log out and log back in to get new token
4. Check token at jwt.io

### Issue: Cannot update user attributes

- Verify AWS CLI is configured correctly
- Verify you have admin permissions on the User Pool
- Check AWS region is correct

## References

- Architecture Document: `.kiro/specs/Common/Multitennant/architecture.md`
- Quick Reference: `.kiro/specs/Common/Multitennant/TENANT_MANAGEMENT_QUICK_REFERENCE.md`
- Phase 1 (Database): `.kiro/specs/Common/Multitennant/phase1_migration_complete.md`
- Cognito Terraform: `infrastructure/cognito.tf`
