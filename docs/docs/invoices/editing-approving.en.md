# Editing & Approving

> Review extracted invoice data, adjust, and save as transactions.

## Overview

After uploading and AI extraction, prepared transaction records appear. These are based on templates from previous invoices from the same vendor. You review the data, adjust where needed, and approve to save.

## What You'll Need

- An uploaded invoice with extracted data
- Access to the Invoices module

## Step by Step

### 1. View the prepared transactions

After upload, one or more transaction records appear under "New Transaction Records (Ready for Approval)". Usually there are two records:

| Record   | Content                           |
| -------- | --------------------------------- |
| Record 1 | Main amount (total including VAT) |
| Record 2 | VAT amount (posted separately)    |

!!! info
The number of records depends on the template for the vendor. Some vendors have more than two posting lines.

### 2. Review and edit the fields

Each record contains the following editable fields:

| Field              | Description                           | Auto-filled?       |
| ------------------ | ------------------------------------- | ------------------ |
| Transaction number | Vendor name                           | ✅                 |
| Reference number   | Vendor name                           | ✅                 |
| Date               | Invoice date from AI extraction       | ✅                 |
| Description        | Invoice number and identifiers        | ✅                 |
| Amount             | Total amount or VAT amount            | ✅                 |
| Debit              | Debit account (ledger number)         | ✅ (from template) |
| Credit             | Credit account (ledger number)        | ✅ (from template) |
| Ref1               | Accommodation name or extra reference | Sometimes          |
| Ref2               | Invoice number (for Booking.com etc.) | Sometimes          |
| Ref3               | Google Drive link to the file         | ✅                 |
| Ref4               | Filename                              | ✅                 |
| Administration     | Your current tenant                   | ✅                 |

Click on a field to edit it. All fields are adjustable.

### 3. Approve and save

When all data is correct, click **Approve & Save to Database**.

The system:

- Saves the transactions to the database
- Transactions with an amount of €0.00 are automatically skipped
- Confirms the number of saved records

!!! warning
Always check the amount and debit/credit accounts. Incorrect assignments affect your reports and tax declarations.

### 4. Duplicate check on approval

If the system detects that similar transactions already exist, a warning dialog appears. You can:

- **Save anyway** — The transaction is saved despite the potential duplicate
- **Cancel** — The approval is stopped

## Templates

The system uses templates to automatically fill in debit and credit accounts. Templates are based on previous transactions from the same vendor:

- **First time**: Debit and credit are empty — fill them in manually
- **Next times**: The system uses the previous assignment as a template

!!! tip
Make sure the first invoice from a new vendor is entered correctly. All subsequent invoices from the same vendor will use this as a template.

## Tips

- Pay special attention to the **amount** and **date** — these are the most critical fields
- The **description** often contains the invoice number — useful for your records
- Click the **URL** to open the original file in Google Drive
- Transactions with €0.00 are automatically skipped when saving

## Troubleshooting

| Problem                 | Cause                                            | Solution                                                           |
| ----------------------- | ------------------------------------------------ | ------------------------------------------------------------------ |
| No transactions visible | No template found for this vendor                | Create a transaction manually via the Banking module               |
| Wrong accounts          | Template based on incorrect previous transaction | Adjust the accounts manually — the new template will be remembered |
| Amount is 0.00          | AI couldn't extract the amount                   | Fill in the amount manually                                        |
