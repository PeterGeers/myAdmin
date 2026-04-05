# Handling Duplicates

> Detect duplicate transactions and prevent them from being saved twice.

## Overview

When importing and saving bank statements, myAdmin automatically checks for duplicates. This prevents the same transaction from ending up in your administration twice.

## What You'll Need

- Imported transactions ready to save
- Access to the Banking module

## How does duplicate detection work?

The system uses two methods to detect duplicates:

### Method 1: Sequence number check (on save)

When saving, the system checks whether the **sequence number** (Ref2) already exists for the same **IBAN** (Ref1). Transactions with an existing sequence number are automatically skipped.

### Method 2: Transaction check (manual)

You can also manually check for duplicates. The system then searches for transactions with the same:

- **Reference number** (exact match)
- **Transaction date** (exact match)
- **Transaction amount** (exact match)

All three must match to be flagged as a duplicate. The check searches transactions from the past 2 years.

## Step by Step

### 1. Automatic check on save

When you click **Save**:

1. The system checks each sequence number against the database
2. Transactions with existing sequence numbers are skipped
3. You'll see a summary:
   - Number of saved transactions
   - Total number of transactions
   - Number of skipped duplicates

### 2. Manual duplicate check

If the system finds a potential duplicate, a warning dialog appears showing:

- Number of matches found
- Details of the existing transaction(s): ID, date, description, amount, debit, credit, and references

You have two options:

| Action       | What it does                                        |
| ------------ | --------------------------------------------------- |
| **Continue** | Import the transaction anyway (creates a duplicate) |
| **Cancel**   | Skip this transaction (prevents duplicate)          |

!!! warning
If you choose **Continue**, the transaction is saved despite the duplicate warning. Only do this if you're sure it's not a real duplicate.

## When are duplicates not real duplicates?

Sometimes the system flags transactions as duplicates when they're not:

- **Recurring payments** with the same amount on the same day (e.g., two separate card transactions)
- **Correction postings** that occur on the same day
- **Split payments** with identical amounts

In these cases, you can safely click **Continue**.

## Tips

!!! tip
Always import bank statements in chronological order and avoid re-importing the same period. This minimizes the number of duplicate warnings.

- All duplicate decisions are recorded in the audit log
- If a database error occurs during the duplicate check, the import continues with a warning
- The Ref3 field in the duplicate view is clickable — if it contains a Google Drive URL, you can open the associated PDF

## Troubleshooting

| Problem                                | Cause                                              | Solution                                                                             |
| -------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------ |
| All transactions flagged as duplicates | You're importing a file that was already processed | Check that you selected the correct (new) file                                       |
| No duplicate check                     | Sequence numbers missing from the file             | The automatic check relies on sequence numbers — without Ref2, no check is performed |
| Duplicate missed                       | Transaction has a different reference number       | The check is exact — small differences in reference numbers are not detected         |
