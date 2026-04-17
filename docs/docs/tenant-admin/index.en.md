# Tenant Administration

> Settings, users, and audit logging for your organization.

## Overview

As Tenant Admin, you manage your own organization within myAdmin. You manage users, configure settings, and track activities via the audit log. You don't have access to other tenants or platform settings — that's reserved for the [SysAdmin](../admin/index.md).

!!! info
You became Tenant Admin because the SysAdmin invited you as the first administrator of your organization. From that point, you can add users and assign roles yourself.

## What can you do here?

| Task                                          | Description                                            |
| --------------------------------------------- | ------------------------------------------------------ |
| [Settings](tenant-settings.md)                | Tenant configuration, templates, and chart of accounts |
| [Template management](template-management.md) | Download, upload, edit, and delete templates           |
| [User management](user-management.md)         | Add users, assign and remove roles                     |
| [Audit logging](audit-logging.md)             | Track activities and compliance reports                |

## Your role vs SysAdmin

|              | Tenant Admin                    | SysAdmin                       |
| ------------ | ------------------------------- | ------------------------------ |
| **Scope**    | Your own organization           | The entire platform            |
| **Users**    | Add, assign/remove roles        | Invite first Tenant Admin      |
| **Settings** | Tenant configuration, templates | Assign modules, create tenants |
| **Data**     | Only your own tenant data       | All tenants                    |

## Available roles to assign

As Tenant Admin, you can assign the following roles to users in your organization:

| Role             | What the user can do                               |
| ---------------- | -------------------------------------------------- |
| `Tenant_Admin`   | Everything you can (manage users, change settings) |
| `Finance_Read`   | View financial reports                             |
| `Finance_CRUD`   | Edit financial data (import, adjust transactions)  |
| `Finance_Export` | Export financial data (Excel, CSV)                 |
| `STR_Read`       | View STR reports                                   |
| `STR_CRUD`       | Edit STR data (import bookings)                    |
| `STR_Export`     | Export STR data                                    |

!!! warning
Which roles are available depends on the modules the SysAdmin has enabled for your tenant. If the STR module is not enabled, STR roles are not available.

## Step by step: First time as Tenant Admin

1. **Log in** with the credentials you received by email
2. **Change your password** on first login
3. **Review the settings** via [Settings](tenant-settings.md)
4. **Add users** via [User management](user-management.md)
5. **Assign roles** so users can access the correct modules
