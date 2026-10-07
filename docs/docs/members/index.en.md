# Member Administration

> View, filter, manage, and export the members of your organization.

## Overview

The Member Administration module lets you manage your organization's members in one clear table — the **Members Overview**. You see the key details per member, search and filter the list, choose which columns to show, add or edit members, change the membership status, and export the members to CSV.

What you see in the table depends on the **region scope** assigned to your account. A user scoped to a single region (for example Noord) sees only the members of that region; a user with full access sees all members. This filtering is applied by the system based on your assigned role — not by a setting on this page.

!!! info
The Member Administration module must be enabled for your tenant by your SysAdmin. Creating users and assigning roles (including the region scope) happens in [Tenant Admin](../tenant-admin/index.md) — see [User management](../tenant-admin/user-management.md).

## What can you do here?

| Task                                          | Description                                                   |
| --------------------------------------------- | ------------------------------------------------------------- |
| [Filters & views](filters-and-views.md)       | Search, filter, sort, and choose your own columns             |
| [Managing members](managing-members.md)       | View, add, edit, and delete a member                          |
| [Status & transitions](transitions.md)        | Move one member or several members at once to another status  |
| [Membership types](membership-types.md)       | Manage your tenant's membership types (Lidmaatschap Beheer)   |
| [Export](export.md)                           | Export the members to CSV                                     |

## The members table

The Members Overview shows your members in a table. By default (for anyone who has not yet chosen their own columns) these core columns appear:

| Column            | Description                                                |
| ----------------- | ---------------------------------------------------------- |
| Member number     | The readable member number (e.g. M00001) — always first and cannot be hidden |
| Name              | Full name of the member                                    |
| Email             | Email address of the member                                |
| Status            | Current membership status (e.g. Active, Applied)           |
| Membership type   | The member's membership type                               |

You can add extra columns yourself (such as **Region** and other fields from your tenant's field configuration) through the **Columns** chooser. See [Filters & views](filters-and-views.md).

!!! tip
Click a row to view a member's details in a read-only dialog. See [Managing members](managing-members.md).

## The toolbar above the table

Above the table you find the tools to tailor the list:

| Element           | Behavior                                                                |
| ----------------- | ----------------------------------------------------------------------- |
| **Search**        | A single search box that searches across *all* member fields — including fields that are not shown as columns |
| **Columns**       | Choose which fields appear as columns; your choice is remembered per user |
| **View**          | A dropdown with preset views (column set + sorting), if your tenant configured them |
| **Export**        | Export the members to CSV (only visible to Tenant Admin / SysAdmin)     |
| **New member**    | Add a new member                                                        |

### Statistics strip

Directly above the table is a strip of four live counters that move with your search and filters:

| Counter   | Meaning                                                          |
| --------- | ---------------------------------------------------------------- |
| Total     | All members within your region scope                             |
| Filtered  | The number of rows currently shown (after search/filter)         |
| Active    | Number of members with status *Active*                           |
| Regions   | Number of distinct regions in the shown rows                     |

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
| `Members_Read`   | View members (table, search, filters, read-only dialog) |
| `Members_CRUD`   | Create, edit, delete, change status, and manage membership types |
| `Members_Export` | Export members to CSV                            |

!!! info
The export button in the Members Overview is additionally only visible to **Tenant Admin** and **SysAdmin**. Ordinary users produce richer, filtered exports through the reporting/pivot views. See [Export](export.md).

!!! warning
Which permissions are available depends on the modules the SysAdmin enabled for your tenant and the roles your Tenant Admin assigns. Without a Members role, Member Administration is not visible.
