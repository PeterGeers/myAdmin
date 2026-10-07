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
3. Fill in the form. Which fields you see is determined by your tenant's **field configuration** — the form is not fixed, but built from the fields your Tenant Admin set up. The fields are grouped into sections (for example *Personal details*, *Membership*).
4. Click **Save**

Common fields are name, email, the membership type, and the region/subgroup. The required fields and the exact set depend on your tenant.

!!! info
The form is parameter-driven. Some fields only appear once you make a certain choice (conditional fields), and **calculated fields** are filled in automatically and cannot be edited. The system checks required fields and the member number format on save.

!!! info
The **Membership type** dropdown shows only the **active** types from [Membership types](membership-types.md). Deactivated types do not appear, so you cannot create members on an expired type.

## Editing a member

1. Go to **Member Administration** → **Overview**
2. Open the member and click **Edit**
3. Adjust the fields you want in the form (the same sections and fields as when adding)
4. Click **Save**

The changes are immediately visible in the table.

!!! tip
When editing, the **Membership type** dropdown also shows only active types, and calculated fields stay read-only.

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
| Desired membership type is missing | The type is not active             | Activate the type in [Membership types](membership-types.md) (or ask your Tenant Admin) |
| Member cannot be edited          | Read-only (`Members_Read`)           | Ask your Tenant Admin for `Members_CRUD`            |
