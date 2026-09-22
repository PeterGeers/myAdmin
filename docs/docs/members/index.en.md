# Member Administration

> View, filter, manage, and export the members of your organization.

## Overview

The Member Administration module lets you manage your organization's members in one clear table — the **Members Overview**. You see the key details per member, filter and sort the list, add or edit members, change the membership status, and export the displayed rows to CSV.

What you see in the table depends on the **region scope** assigned to your account. A user scoped to a single region (for example Noord) sees only the members of that region; a user with full access sees all members. This filtering is applied by the system based on your assigned role — not by a setting on this page.

!!! info
The Member Administration module must be enabled for your tenant by your SysAdmin. Creating users and assigning roles (including the region scope) happens in [Tenant Admin](../tenant-admin/index.md) — see [User management](../tenant-admin/user-management.md).

## What can you do here?

| Task                                          | Description                                                    |
| --------------------------------------------- | ------------------------------------------------------------- |
| [Filters & views](filters-and-views.md)       | Filter and sort columns, switch between compact and full view |
| [Managing members](managing-members.md)       | View, add, edit, and delete a member                          |
| [Status & transitions](transitions.md)        | Move one member or several members at once to another status  |
| [Export](export.md)                           | Export the displayed members to CSV                           |

## The members table

The Members Overview shows your members in a table with the following default columns:

| Column          | Description                                          |
| --------------- | ---------------------------------------------------- |
| Name            | Full name of the member                              |
| Email           | Email address of the member                          |
| Status          | Current membership status (e.g. Active, Applied)     |
| Membership type | The member's membership type                         |
| Region          | The region/subgroup the member belongs to (as badge) |

Each row shows the region as a **badge**, so you can see at a glance which subgroup a member belongs to.

!!! tip
Click a row to view a member's details in a read-only dialog. See [Managing members](managing-members.md).

## Compact and full view

Above the table is a switch between **compact** and **full** view:

- **Compact** — shows only the core columns (Name, Email, Status, Membership type, Region).
- **Full** — additionally shows the extra columns configured through your tenant's field configuration.

Which extra fields appear in the full view is determined by your Tenant Admin through the field configuration. See [Filters & views](filters-and-views.md).

## Region scope: what you see

Your region scope determines which members you see in the table:

| Assigned scope           | What you see                    |
| ------------------------ | ------------------------------- |
| Single region (e.g. Noord) | Only the members of that region |
| Full access              | All members of all regions      |

!!! info
The region scope is enforced by the system, server-side. An export also contains only the rows within your scope — you cannot see or export members outside your scope. You do not change the scope here; it is determined by the role your Tenant Admin assigns in [User management](../tenant-admin/user-management.md).

## Permissions

| Permission       | What the user can do                             |
| ---------------- | ------------------------------------------------ |
| `Members_Read`   | View members (table, filters, read-only dialog)  |
| `Members_CRUD`   | Create, edit, delete, and change the status of members |
| `Members_Export` | Export members to CSV                            |

!!! warning
Which permissions are available depends on the modules the SysAdmin enabled for your tenant and the roles your Tenant Admin assigns. Without a Members role, Member Administration is not visible.
