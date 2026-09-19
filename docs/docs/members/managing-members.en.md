# Managing members

> View, add, edit, and delete a member.

## Overview

From the Members Overview you manage individual members: you view a member's details, add a new member, edit existing details, or delete a member.

## What you need

- `Members_Read` to view members
- `Members_CRUD` to add, edit, or delete members

## Viewing a member

1. Go to **Member Administration** → **Overview**
2. Click the row of the member you want to view
3. A read-only dialog opens with the member's full details
4. Close the dialog to return to the table

!!! info
The view dialog is read-only. To change something, use **Edit** (see below).

## Adding a member

1. Go to **Member Administration** → **Overview**
2. Click **New member** in the top right
3. Fill in the application/add form:

| Field           | Required | Description                                        |
| --------------- | -------- | -------------------------------------------------- |
| Name            | Yes      | Full name of the member                            |
| Email           | Yes      | Email address of the member                        |
| Membership type | Yes      | Choose a type from the dropdown                    |
| Region          | Yes      | The region/subgroup the member belongs to          |

4. Click **Save**

!!! info
The **Membership type** dropdown shows only the **active** types. Deactivated types do not appear, so you cannot create members on an expired type.

## Editing a member

1. Go to **Member Administration** → **Overview**
2. Open the member and click **Edit** (or use the edit action)
3. Adjust the fields you want in the form
4. Click **Save**

The changes are immediately visible in the table.

!!! tip
When editing, the **Membership type** dropdown also shows only active types.

## Deleting a member

1. Go to **Member Administration** → **Overview**
2. Open the member and choose **Delete**
3. Confirm the action in the confirmation dialog

!!! warning
Deletion cannot be undone. Make sure you selected the right member before you confirm.

## Changing status

Viewing and editing details does not change the membership status. To move a member to another status (for example from *Applied* to *Active*), use the status transitions — see [Status & transitions](transitions.md).

## Onboarding and roles

Creating *users* (accounts that log in) and assigning roles and region scope is handled in [Tenant Admin](../tenant-admin/index.md). See [User management](../tenant-admin/user-management.md) — this is not duplicated here. On this page you manage *members* as administrative records, not login accounts.

## Troubleshooting

| Problem                          | Cause                                | Solution                                            |
| -------------------------------- | ------------------------------------ | --------------------------------------------------- |
| **New member** button is missing | You do not have the `Members_CRUD` permission | Ask your Tenant Admin for the right permission |
| Desired membership type is missing | The type is not active             | Ask your Tenant Admin to activate the type          |
| Member cannot be edited          | Read-only (`Members_Read`)           | Ask your Tenant Admin for `Members_CRUD`            |
