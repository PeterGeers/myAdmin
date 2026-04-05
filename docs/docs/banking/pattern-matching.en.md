# Pattern Matching

> Automatically fill in debit and credit accounts based on historical transactions.

## Overview

Pattern matching analyzes your transaction history from the past 2 years and uses it to automatically assign accounts to new transactions. The more transactions you process, the smarter the system becomes.

## What You'll Need

- Imported transactions in the editing table
- Historical transactions in the database (the more, the better)

## How does it work?

The system looks at previously processed transactions and finds similarities:

1. **Analysis** — The system searches the last 2 years of transactions for your administration
2. **Discover patterns** — Patterns are recognized based on descriptions and reference numbers
3. **Predict** — For new transactions with similar characteristics, accounts are automatically filled in

**What gets predicted?**

| Field            | When                                         |
| ---------------- | -------------------------------------------- |
| Debit account    | When the credit account is a bank account    |
| Credit account   | When the debit account is a bank account     |
| Reference number | When the description matches a known pattern |

!!! info
The system learns from the very first transaction. After one manual assignment, it can automatically suggest the same assignment on the next import.

## Step by Step

### 1. Import transactions

First import your bank statement via [Importing statements](importing-statements.md). The transactions appear in the table.

### 2. Click "Apply Patterns"

Click the **Apply Patterns** button above the transaction table.

### 3. Review the results

The system shows a summary:

- **Patterns found** — Number of recognized patterns in your history
- **Debit predictions** — Number of automatically filled debit accounts
- **Credit predictions** — Number of automatically filled credit accounts
- **Reference predictions** — Number of automatically filled reference numbers
- **Average confidence** — Percentage certainty of the predictions

### 4. Check the results

Auto-filled fields are visually highlighted in the table. Check whether the predictions are correct:

- **Correct?** — Leave it and move on
- **Incorrect?** — Adjust it manually

!!! tip
Confidence increases as you process more transactions. The first time there may be few patterns, but after a few months most transactions will be automatically recognized.

## How are patterns built?

The system analyzes:

- **Keywords** from the transaction description
- **Reference numbers** from previous transactions
- **Combinations** of description + reference

A pattern is created when:

- One side of the posting is a bank account (debit or credit)
- The other side is a general ledger account
- At least 1 previous transaction with the same characteristics exists

The confidence score grows with the number of matches (maximum 100% at 10+ matches).

## Tips

- Apply patterns **before** manual editing — this saves the most time
- Patterns are specific per administration — each tenant has its own patterns
- After saving new transactions, patterns are automatically updated
- You can apply patterns multiple times on the same set of transactions

## Troubleshooting

| Problem                 | Cause                                      | Solution                                                                |
| ----------------------- | ------------------------------------------ | ----------------------------------------------------------------------- |
| No patterns found       | No historical transactions                 | First process a few months of transactions manually                     |
| Wrong account suggested | Pattern based on incorrect historical data | Correct the assignment manually — the system learns from the correction |
| Few predictions         | Too little historical data                 | The system improves as you process more transactions                    |
