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

## Troubleshooting

| Problem               | Cause                      | Solution                              |
| --------------------- | -------------------------- | ------------------------------------- |
| Tenant creation fails | Name already in use        | Choose a unique administration name   |
| Modules not visible   | Modules not assigned       | Assign modules via the SysAdmin panel |
| User can't log in     | Provisioning not completed | Reprovision the tenant                |
| Role deletion fails   | Users assigned to the role | Remove all users from the role first  |
