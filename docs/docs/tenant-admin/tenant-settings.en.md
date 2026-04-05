# Settings

> Manage tenant configuration, templates, and chart of accounts.

## Overview

As Tenant Admin, you can manage your organization's settings. This includes configuration keys, report templates, and the chart of accounts (general ledger accounts).

## Configuration

### View configuration

1. Go to **Tenant Admin** → **Settings**
2. You'll see two sections:
   - **Configuration** — Non-secret settings with their values
   - **Secrets** — Secret keys (only the key name is visible, not the value)

### Add or change configuration

1. Click **Add setting**
2. Fill in:

| Field  | Description                                          |
| ------ | ---------------------------------------------------- |
| Key    | Name of the setting (e.g., `google_drive_folder_id`) |
| Value  | The value of the setting                             |
| Secret | Check if the value should remain hidden              |

3. Click **Save**

### Delete configuration

1. Click the delete icon next to the setting
2. Confirm the action

!!! warning
Secret configurations (like API keys and passwords) only show the key name. The value is stored encrypted and not visible in the interface.

## Templates

Templates determine how invoice processing and reports work for your organization. You can view, edit, and approve templates.

### View a template

1. Go to **Tenant Admin** → **Templates**
2. Select the template type (e.g., `financial_report_xlsx`)
3. You'll see the current template with field mappings

### Edit a template

1. Adjust the fields in the editing form
2. Click **Preview** to see the result
3. Click **Validate** to check for errors
4. Click **Approve** to activate the template

If there are validation errors, you can use **AI Help** to get suggestions for fixing them.

### Reject a template

If a template change is not correct, click **Reject** to revert to the previous version.

## Chart of accounts

The chart of accounts contains all general ledger accounts available for your administration. These are used when posting transactions.

!!! info
Accounts that are already used in transactions cannot be deleted. The system checks this automatically.

## Troubleshooting

| Problem                        | Cause                                | Solution                                    |
| ------------------------------ | ------------------------------------ | ------------------------------------------- |
| "Tenant admin access required" | You don't have the Tenant_Admin role | Contact your SysAdmin                       |
| Configuration not saved        | Required fields missing              | Check that key and value are filled in      |
| Template validation failed     | Missing required fields              | Use AI Help for suggestions                 |
| Account can't be deleted       | Account is used in transactions      | The account is in use and cannot be deleted |
