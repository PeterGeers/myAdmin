# Reviewing Transactions

> View, edit, and save imported transactions to the database.

## Overview

After importing a bank statement, the transactions appear in an editable table. Here you check that everything is correct, fill in missing fields, and save the transactions.

## What You'll Need

- Imported transactions (via [Importing statements](importing-statements.md))
- Access to the Banking module

## Step by Step

### 1. View the transaction table

After importing, you'll see a table with all transactions. Each transaction shows:

| Column           | Editable | Description                                                         |
| ---------------- | -------- | ------------------------------------------------------------------- |
| Date             | ✅       | Transaction date (required)                                         |
| Description      | ✅       | Transaction description (required)                                  |
| Amount           | ✅       | Transaction amount, must be greater than 0 (required)               |
| Debit            | ✅       | Debit account with autocomplete dropdown (required\*)               |
| Credit           | ✅       | Credit account with autocomplete dropdown (required\*)              |
| Reference number | ✅       | Reference, often auto-filled by patterns                            |
| Ref1             | ❌       | IBAN/account number (read-only)                                     |
| Ref2             | ❌       | Sequence number (read-only)                                         |
| Ref3             | ❌       | Balance — clickable: opens Google Drive link or copies to clipboard |
| Ref4             | ❌       | Source file name (read-only)                                        |
| Administration   | ❌       | Automatically set to your current tenant                            |

_\* Debit or Credit must be filled in — both cannot be empty._

### 2. Edit transactions

Click on a field to edit it. Use **Tab** or **Enter** to move to the next field.

**Debit and Credit fields:**

- Type an account number to activate the autocomplete
- The system shows available general ledger accounts for your administration
- Select an account from the list or type the number manually

!!! tip
Use [Apply patterns](pattern-matching.md) first to auto-fill as many fields as possible. Then you only need to manually adjust the exceptions.

### 3. Add transactions manually

You can also add new transactions manually:

1. Click **Add new record**
2. Fill in all required fields
3. The transaction appears at the bottom of the table

### 4. Save

When all transactions are correct, click **Save**. The system:

- Checks that all required fields are filled in
- Checks for duplicates (based on sequence number and IBAN)
- Saves the transactions to the database
- Shows a summary: number saved, total, and any skipped duplicates

!!! warning
Always check the debit and credit accounts before saving. Incorrect assignments affect your reports and tax declarations.

## Tips

- Use the **Tab** key to quickly navigate through fields
- Click the **Ref3** field to open a Google Drive link (if it contains a URL)
- You can also update existing transactions through the same interface

## Troubleshooting

| Problem                 | Cause                     | Solution                                                                                |
| ----------------------- | ------------------------- | --------------------------------------------------------------------------------------- |
| Can't save              | Required fields are empty | Check that Date, Description, Amount, and Debit/Credit are filled in                    |
| No accounts in dropdown | Lookup data not loaded    | Refresh the page — accounts are loaded when opening the module                          |
| Transaction is skipped  | Duplicate sequence number | The system skips transactions that already exist with the same sequence number and IBAN |
