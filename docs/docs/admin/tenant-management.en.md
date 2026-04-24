# Tenant Management

> Create, configure tenants, assign modules, and invite the first administrator.

## Overview

As SysAdmin, you manage all tenants (organizations) on the platform. You create new tenants, assign modules, and invite the first Tenant Admin who then takes over organization management.

## What You'll Need

- `SysAdmin` role in AWS Cognito
- Access to the SysAdmin panel

## Step by Step

### Create a new tenant

1. Go to the **SysAdmin** panel
2. Click **Create new tenant**
3. Fill in the basic details:

| Field               | Description                                    | Required |
| ------------------- | ---------------------------------------------- | -------- |
| Administration name | Unique name for the tenant (e.g., "MyCompany") | ✅       |
| Display name        | Name as shown in the interface                 | ✅       |
| Status              | Active or inactive                             | ✅       |

4. Click **Create**

### Assign modules

After creating a tenant, assign modules:

1. Open the tenant in the SysAdmin panel
2. Go to the **Modules** tab
3. Enable the desired modules:

| Module        | What it provides                     |
| ------------- | ------------------------------------ |
| **Financial** | Banking, invoices, reports, tax      |
| **STR**       | Short-term rental, bookings, pricing |

4. Click **Save**

!!! info
Modules determine which functionality is available for the tenant. Users only see the modules that are enabled.

### Invite the first administrator

After creating and configuring the tenant, invite the first Tenant Admin:

1. The tenant is provisioned in AWS Cognito
2. The first user receives a welcome email with login credentials
3. This user is assigned the `Tenant_Admin` role
4. The Tenant Admin can then add users themselves

### Edit a tenant

1. Open the tenant in the SysAdmin panel
2. Adjust the desired fields
3. Click **Save**

### Delete a tenant

1. Open the tenant in the SysAdmin panel
2. Click **Delete**
3. Confirm the action

!!! danger
Deletion is a soft delete — the tenant is marked as "deleted" but the data remains in the database. This cannot be undone via the interface.

## Provisioning

When creating or reprovisioning a tenant:

- Cognito user groups are created
- The first administrator is invited by email
- A welcome email is sent with login credentials
- The administration name is added to the user's Cognito profile

### Reprovisioning

If something went wrong during initial setup, you can reprovision a tenant:

1. Open the tenant
2. Click **Reprovision**
3. The system re-executes the provisioning steps

## Role management

As SysAdmin, you can also manage roles (Cognito groups):

- **View roles** — All available roles with user counts
- **Create role** — Add a new role
- **Delete role** — Remove a role (only if no users are assigned)

## Advanced Parameters (Advanced Tab)

As SysAdmin, you have access to the **Advanced tab** (🔧) in the Tenant Admin dashboard. This tab shows a raw parameter table with all configuration values for the tenant.

### How the parameter system works

Parameters control how myAdmin behaves for each tenant. They follow a **scope inheritance chain**:

```
user → role → tenant → system
```

When a parameter is requested, the system walks this chain and returns the first value found. This means:

- **System-scope** parameters are defaults that apply to all tenants. They are defined in the codebase and only change when the software is updated.
- **Tenant-scope** parameters are overrides set by the Tenant Admin (through the structured tabs like Storage and Financial) or by the SysAdmin (through the Advanced tab).
- **Role-scope** and **User-scope** parameters allow fine-grained overrides for specific roles or users.

### What you see in the Advanced tab

The raw parameter table shows all parameters across all namespaces. Each row displays:

| Column        | Description                                                          |
| ------------- | -------------------------------------------------------------------- |
| **Namespace** | Parameter group (e.g., `storage`, `fin`, `str`, `zzp_branding`)      |
| **Key**       | Parameter name within the namespace                                  |
| **Value**     | Current value (secrets are masked for non-SysAdmin users)            |
| **Type**      | Data type (`string`, `number`, `boolean`, `json`)                    |
| **Scope**     | Where the value comes from (`system` = default, `tenant` = override) |

### When to use the Advanced tab

- **Troubleshooting** — Check what values a tenant is actually using
- **Override defaults** — Set a tenant-specific value that isn't available through the structured UI
- **Manage secrets** — View or update encrypted parameters (e.g., API keys)

!!! warning
Changes in the Advanced tab take effect immediately. Be careful when editing system-scope parameters — they affect all tenants.

### Key parameter namespaces

| Namespace      | Description                                  | Managed via                   |
| -------------- | -------------------------------------------- | ----------------------------- |
| `storage`      | Storage provider, folder IDs, bucket names   | Storage tab (structured UI)   |
| `fin`          | Currency, fiscal year, locale                | Financial tab (structured UI) |
| `str`          | Room count, platforms                        | Module configuration          |
| `str_branding` | Company details for STR documents            | Advanced tab                  |
| `zzp_branding` | Company details for ZZP invoices             | Advanced tab                  |
| `zzp`          | Invoice prefix, payment terms, field configs | Module configuration          |

## Troubleshooting

| Problem               | Cause                      | Solution                              |
| --------------------- | -------------------------- | ------------------------------------- |
| Tenant creation fails | Name already in use        | Choose a unique administration name   |
| Modules not visible   | Modules not assigned       | Assign modules via the SysAdmin panel |
| User can't log in     | Provisioning not completed | Reprovision the tenant                |
| Role deletion fails   | Users assigned to the role | Remove all users from the role first  |
