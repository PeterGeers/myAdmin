# User Management

> Add users to your organization and assign roles.

## Overview

As Tenant Admin, you manage the users of your organization. You can create new users, assign and remove roles, and deactivate users.

## What You'll Need

- `Tenant_Admin` role
- A selected tenant/administration

## Step by Step

### View users

1. Go to **Tenant Admin** → **Users**
2. You'll see a list of all users with access to your tenant

Per user you'll see:

| Column   | Description                                   |
| -------- | --------------------------------------------- |
| Username | Unique name in the system                     |
| Email    | User's email address                          |
| Roles    | Assigned roles (e.g., Finance_CRUD, STR_Read) |
| Status   | Active, inactive, or awaiting confirmation    |

### Create a new user

1. Click **Add user**
2. Fill in the details:

| Field         | Description           | Required |
| ------------- | --------------------- | -------- |
| Email address | Email of the new user | ✅       |
| First name    | First name            | ✅       |
| Last name     | Last name             | ✅       |

3. Assign roles (see below)
4. Click **Create**

The user receives an email with login credentials and must set a password on first login.

### Assign roles

1. Click on a user in the list
2. Click **Assign role**
3. Select the desired role from the available roles
4. Click **Assign**

Available roles depend on the enabled modules:

| Module enabled | Available roles                                  |
| -------------- | ------------------------------------------------ |
| Financial      | `Finance_Read`, `Finance_CRUD`, `Finance_Export` |
| STR            | `STR_Read`, `STR_CRUD`, `STR_Export`             |
| Always         | `Tenant_Admin`                                   |

### Remove roles

1. Click on a user in the list
2. Click the delete icon next to the role you want to remove
3. Confirm the action

### Delete a user

1. Click on a user in the list
2. Click **Delete**
3. Confirm the action

!!! danger
Deleting a user is permanent. The user loses all access to the platform.

## Tips

!!! tip
Only assign users the roles they need. A staff member who only views reports only needs `Finance_Read` — no need for `Finance_CRUD`.

- Each user can have multiple roles
- A user can have access to multiple tenants (if the SysAdmin configured this)
- All user changes are recorded in the audit log

## Troubleshooting

| Problem                        | Cause                                | Solution                                   |
| ------------------------------ | ------------------------------------ | ------------------------------------------ |
| "Tenant admin access required" | You don't have the Tenant_Admin role | Contact your SysAdmin                      |
| User sees no modules           | No roles assigned                    | Assign the correct roles                   |
| Role not available             | Module not enabled for your tenant   | Contact your SysAdmin to enable the module |
| User can't log in              | Account not activated                | Check the user status                      |
