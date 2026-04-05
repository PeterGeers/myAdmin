# Importing Statements

> Upload bank statements as CSV and process them in myAdmin.

## Overview

You can import bank statements by uploading CSV files downloaded from your online banking. myAdmin automatically recognizes the bank format and converts the data into transactions.

## What You'll Need

- A CSV file from your bank (Rabobank, Revolut, or credit card)
- Access to the Banking module (`banking_process` permissions)

## Step by Step

### 1. Download your bank statement

Log into your online banking and download the statement as a CSV file.

**Rabobank:**

- Go to Transactions → Download
- Choose format: CSV
- Files start with `CSV_O` or `CSV_A`

**Revolut:**

- Go to your transaction overview
- Click Export → CSV or TSV

### 2. Open the Banking module

In myAdmin, go to **Banking**. You'll see the import screen.

### 3. Select files

Click **Choose files** and select one or more CSV files. You can select multiple files at once.

!!! info
The system automatically checks whether the IBAN in the file belongs to your administration. If not, you'll get an error message.

### 4. Process the files

Click **Process**. myAdmin reads the files and displays the transactions in a review table.

For each transaction, the following fields are populated:

| Field            | Source                              |
| ---------------- | ----------------------------------- |
| Transaction date | From the CSV file                   |
| Description      | From the CSV file                   |
| Amount           | From the CSV file (always positive) |
| Ref1             | IBAN/account number                 |
| Ref2             | Sequence number                     |
| Ref3             | Balance after transaction           |
| Ref4             | File name                           |

The **Debit**, **Credit**, and **Reference number** fields are still empty — you'll fill those in the next step (manually or via patterns).

### 5. Next steps

After importing, you can:

- [Apply patterns](pattern-matching.md) to automatically fill in accounts
- [Review transactions](reviewing-transactions.md) and adjust manually
- [Check for duplicates](handling-duplicates.md) before saving

## Tips

!!! tip
Import statements in chronological order. This helps with correctly tracking balances and sequence numbers.

- You can import multiple CSV files at once
- The system automatically recognizes which bank format the file uses
- Files with an unrecognized format are skipped with an error message

## Troubleshooting

| Problem                                         | Cause                                      | Solution                                                                               |
| ----------------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------- |
| "No data found in files"                        | Empty file or wrong format                 | Check that the file contains transactions and uses the correct CSV format              |
| "Access denied: IBAN does not belong to tenant" | IBAN doesn't belong to your administration | Check that you selected the correct file and are working in the correct administration |
| File not recognized                             | Unknown bank format                        | Check that it's a supported format (Rabobank CSV, Revolut TSV/CSV)                     |
| Wrong characters in descriptions                | Encoding issue                             | Rabobank files use Latin-1 encoding — this is handled automatically                    |
