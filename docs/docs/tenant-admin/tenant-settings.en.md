# Settings

> Manage your organization through 6 clear tabs.

## Overview

The Tenant Admin dashboard has 6 tabs. Which tabs you see depends on your modules and role.

| Tab         | Contents                                                    | Visible to         |
| ----------- | ----------------------------------------------------------- | ------------------ |
| Users       | Add users, assign roles                                     | Tenant Admin       |
| Financial   | Chart of Accounts + Tax Rates                               | Tenant Admin (FIN) |
| Storage     | Choose storage provider, Google Drive credentials & folders | Tenant Admin       |
| Templates   | Upload, edit, and approve report templates                  | Tenant Admin       |
| Tenant Info | Company details, contact info, bank details + Email log     | Tenant Admin       |
| Advanced    | Raw parameters table                                        | SysAdmin only      |

## Financial tab

The Financial tab (only visible when the FIN module is active) contains two sections:

### Chart of Accounts

All general ledger accounts for your administration. Click a row to edit.

- **Export** — Download as Excel
- **Import** — Upload an Excel file
- **Add** — Create a new account
- **Parameters** — Set per-account parameters (e.g., VAT netting, year-end closure purpose)

!!! info
Accounts that are already used in transactions cannot be deleted.

### Tax Rates

Manage VAT rates and other tax rates. Click a row to edit. System rates (source: system) can only be changed by the SysAdmin.

## Storage tab

Configure where your files are stored.

### Step 1: Choose provider

Select your storage provider:

- **Google Drive** — OAuth authentication + folder structure
- **S3 Shared Bucket** — Shared AWS S3 bucket (platform level)
- **S3 Tenant Bucket** — Dedicated AWS S3 bucket per tenant

### Step 2: Configure provider

**Google Drive:**

1. Upload your credentials JSON file, or start the OAuth flow
2. Test the connection with **Test Connection**
3. Enter the Root Folder ID
4. Review configured folders (invoices, templates, reports)

## Templates tab

Templates determine how invoice processing and reports work.

1. Select the template type
2. Adjust fields in the editing form
3. Click **Preview** to see the result
4. Click **Validate** to check for errors
5. Click **Approve** to activate the template

If there are validation errors, use **AI Help** for suggestions.

## Tenant Info tab

Manage your company details in the following sections:

- **Company Info** — Administration code, display name, status
- **Contact** — Email and phone number
- **Address** — Street, city, zipcode, country
- **Bank Details** — Account number and bank name
- **Email Log** — Overview of sent emails (invitations, password resets)

## Troubleshooting

| Problem                        | Cause                                | Solution                                   |
| ------------------------------ | ------------------------------------ | ------------------------------------------ |
| "Tenant admin access required" | You don't have the Tenant_Admin role | Contact your SysAdmin                      |
| Financial tab not visible      | FIN module not enabled               | Ask the SysAdmin to enable FIN             |
| Advanced tab not visible       | You're not a SysAdmin                | Only SysAdmin sees this tab                |
| Google Drive connection failed | Credentials expired or invalid       | Upload new credentials or start OAuth flow |
| Account can't be deleted       | Account is used in transactions      | The account is in use                      |
