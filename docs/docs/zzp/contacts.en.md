# Managing Contacts

> Register, edit, and manage clients and suppliers.

## Overview

The contact registry is where you manage all business contacts you invoice or purchase from. Each contact has a unique Client ID used for payment matching and invoicing. Contacts are shared with future modules, so you only need to create them once.

## What You'll Need

- Access to the ZZP module (`zzp_crud` permissions)
- The company name and a unique Client ID for each contact

## Step by Step

### 1. Create a contact

1. Go to **ZZP** → **Contacts**
2. Click **New contact**
3. Fill in the required fields:

| Field          | Required | Description                                                         |
| -------------- | -------- | ------------------------------------------------------------------- |
| Client ID      | Yes      | Short unique code (e.g., "ACME", "KPN") — used for payment matching |
| Company name   | Yes      | Official company name                                               |
| Contact person | No       | Name of the contact person                                          |
| Address        | No       | Street, postal code, city, country                                  |
| VAT number     | No       | VAT identification number                                           |
| CoC number     | No       | Chamber of Commerce registration number                             |
| Phone          | No       | Phone number                                                        |
| IBAN           | No       | Bank account number                                                 |

4. Click **Save**

!!! tip
Choose a short, recognizable Client ID. This ID appears on invoices and is used to automatically match bank payments with outstanding invoices.

### 2. Add email addresses

Each contact can have multiple email addresses with a type indicator:

| Type    | Usage                                   |
| ------- | --------------------------------------- |
| General | Default email address                   |
| Invoice | Used as recipient when sending invoices |
| Other   | Additional email addresses              |

1. Open the contact
2. Click **Add email**
3. Enter the email address and choose the type
4. Click **Save**

!!! info
If no invoice email address is set, the general email address is used when sending invoices.

### 3. Edit a contact

1. Go to **ZZP** → **Contacts**
2. Click the contact you want to edit
3. Adjust the desired fields
4. Click **Save**

### 4. Delete a contact

1. Go to **ZZP** → **Contacts**
2. Click the contact you want to delete
3. Click **Delete**

!!! warning
Contacts linked to existing invoices cannot be deleted. The contact is deactivated instead (soft delete) so your invoice history remains intact.

## Contact types

Each contact has a type indicating the relationship:

| Type     | Description                 |
| -------- | --------------------------- |
| Client   | You invoice this contact    |
| Supplier | This contact invoices you   |
| Both     | Both client and supplier    |
| Other    | Other business relationship |

## Tips

!!! tip
Use the Client ID consistently on all your invoices. When your client includes this ID in their bank payment, the system can automatically match the payment with the outstanding invoice.

- Fill in the VAT number for business clients — this is needed for correct VAT invoicing
- The CoC number is useful for your own records but not required
- You can customize available fields via tenant settings (hide or make fields required)

## Troubleshooting

| Problem                      | Cause                                      | Solution                                                |
| ---------------------------- | ------------------------------------------ | ------------------------------------------------------- |
| "Client ID already exists"   | Client ID is not unique within your tenant | Choose a different Client ID                            |
| Contact cannot be deleted    | Contact is linked to invoices              | The contact is deactivated instead of deleted           |
| Fields missing from the form | Fields are hidden via tenant settings      | Ask your Tenant Admin to adjust the field configuration |
