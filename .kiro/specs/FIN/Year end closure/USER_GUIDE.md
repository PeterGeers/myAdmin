# Year-End Closure User Guide

## Overview

The Year-End Closure feature allows you to formally close fiscal years, creating opening balance transactions for the next year and improving report performance. This guide explains how to use the feature and understand its behavior.

## Table of Contents

1. [Accessing Year-End Closure](#accessing-year-end-closure)
2. [Closing a Year](#closing-a-year)
3. [Reopening a Year](#reopening-a-year)
4. [Sequential Reopening Restriction](#sequential-reopening-restriction)
5. [Understanding the Process](#understanding-the-process)
6. [Troubleshooting](#troubleshooting)

---

## Accessing Year-End Closure

There are two ways to access the year-end closure functionality:

### Method 1: Through Aangifte IB Report (Recommended)

1. Navigate to **FIN Rapporten** → **Aangifte IB**
2. Select the year you want to close from the year filter
3. Scroll to the bottom of the report
4. You'll see the **Jaarafsluiting** (Year-End Closure) section

**Advantages:**

- See the exact financial data before closing
- Verify net result and balance sheet accounts
- Immediate context for the closure decision
- Auto-refreshes report after closing/reopening

## Closing a Year

### Prerequisites

Before you can close a year, the following conditions must be met:

1. **Previous Year Closed**: The previous year must already be closed (except for the first year you close)
2. **Account Configuration**: Required accounts must be configured in Tenant Admin:
   - Equity Result Account (e.g., 3080)
   - P&L Closing Account (e.g., 8099)
3. **Permissions**: You must have the `finance_write` permission (Finance_CRUD role)

### Step-by-Step Process

1. **Navigate to Aangifte IB**
   - Go to FIN Rapporten → Aangifte IB
   - Select the year you want to close

2. **Review the Report**
   - Verify all transactions are correct
   - Check the net result (profit/loss)
   - Review balance sheet accounts

3. **Check Validation Status**
   - Scroll to the **Jaarafsluiting** section at the bottom
   - Look for the validation summary:
     - ✅ Green badge: "Jaar kan worden afgesloten" (Year can be closed)
     - ❌ Red badge: "Jaar kan niet worden afgesloten" (Year cannot be closed)
   - Review any errors or warnings displayed

4. **Close the Year**
   - Click the **"Jaar [YYYY] afsluiten"** button
   - A confirmation dialog will appear
   - Optionally add notes (e.g., "Year-end closure 2025")
   - Click **"Bevestigen"** (Confirm)

5. **Verify Closure**
   - The report will automatically refresh
   - Status changes to **"Afgesloten"** (Closed)
   - Closure details are displayed (date, user, notes)

### What Happens When You Close a Year?

The system performs the following operations automatically:

1. **Creates Year-End Closure Transaction** (`YearClose YYYY`):
   - Closes all P&L accounts (VW='Y')
   - Records net result in equity account
   - Uses P&L closing account as offset
   - ReferenceNumber: "Year Closure"
   - Date: December 31st of the closed year

2. **Creates Opening Balance Transactions** (`OpeningBalance YYYY+1`):
   - Carries forward all balance sheet accounts (VW='N')
   - Uses equity account for balancing
   - ReferenceNumber: "Opening Balance"
   - Date: January 1st of the next year

3. **Records Closure Status**:
   - Saves closure date and user
   - Stores transaction numbers for audit trail
   - Saves optional notes

4. **Invalidates Cache**:
   - Clears report cache to reflect new transactions
   - Ensures reports show updated data immediately

---

## Reopening a Year

### When to Reopen a Year

You might need to reopen a year if:

- You discover an error in the closed year's transactions
- You need to add missing transactions
- You need to correct account assignments
- You need to adjust the year-end closure

### Step-by-Step Process

1. **Navigate to Aangifte IB**
   - Go to FIN Rapporten → Aangifte IB
   - Select the closed year you want to reopen

2. **Check Reopen Eligibility**
   - Scroll to the **Jaarafsluiting** section
   - Look for the **"Jaar [YYYY] heropenen"** button
   - If the button is disabled (gray), check the warning message

3. **Reopen the Year**
   - Click the **"Jaar [YYYY] heropenen"** button
   - A confirmation dialog will appear
   - Click **"Bevestigen"** (Confirm)

4. **Verify Reopening**
   - The report will automatically refresh
   - Status changes to **"Open"**
   - Validation summary is displayed again

### What Happens When You Reopen a Year?

The system performs the following operations automatically:

1. **Deletes Opening Balance Transactions**:
   - Removes all `OpeningBalance YYYY+1` transactions
   - Clears the opening balances for the next year

2. **Deletes Year-End Closure Transaction**:
   - Removes the `YearClose YYYY` transaction
   - Removes the P&L closure entry

3. **Removes Closure Status**:
   - Deletes the closure record from the database
   - Year becomes available for editing again

4. **Invalidates Cache**:
   - Clears report cache
   - Reports revert to showing cumulative data

---

## Sequential Reopening Restriction

### ⚠️ IMPORTANT: You Cannot Reopen Old Years When Subsequent Years Are Closed

This is a critical data integrity protection feature.

### The Rule

**You can only reopen a year if the NEXT year is NOT closed.**

### Examples

#### ✅ Allowed: Reopening the Most Recent Closed Year

```
2023: Closed
2024: Closed
2025: Closed
2026: Open
```

You CAN reopen 2025 because 2026 is open.

#### ❌ Not Allowed: Reopening an Old Year

```
2018: Closed ← You want to reopen this
2019: Closed ← This is still closed!
2020: Closed
...
2025: Closed
2026: Open
```

You CANNOT reopen 2018 because 2019 is still closed.

**Error Message:**

> "Kan jaar 2018 niet heropenen omdat jaar 2019 nog afgesloten is. Heropen eerst jaar 2019."
>
> (Cannot reopen year 2018 because year 2019 is still closed. Reopen year 2019 first.)

### Why This Restriction Exists

1. **Opening Balance Chain**: Each year's opening balance comes from the previous year's closing balance
2. **Data Integrity**: Reopening an old year would invalidate all subsequent years' opening balances
3. **Audit Trail**: Maintains a clear, sequential history of year closures
4. **Report Accuracy**: Prevents inconsistent data in reports

### How to Reopen Old Years

If you need to reopen an old year (e.g., 2018), you must reopen all subsequent years first, in reverse order:

**Step-by-Step:**

1. Reopen 2025 (most recent closed year)
2. Reopen 2024
3. Reopen 2023
4. Reopen 2022
5. Reopen 2021
6. Reopen 2020
7. Reopen 2019
8. Finally, reopen 2018

**After Making Changes:**

Once you've corrected the data in 2018, you must re-close all years in forward order:

1. Close 2018
2. Close 2019
3. Close 2020
4. Close 2021
5. Close 2022
6. Close 2023
7. Close 2024
8. Close 2025

### UI Indicators

When you select a closed year that cannot be reopened:

- The **"Jaar heropenen"** button is **disabled** (gray)
- A **warning message** is displayed in an orange alert box
- The message explains which year is blocking the reopen

---

## Understanding the Process

### The Two Models

The system uses two different calculation models:

#### Old Model (Before Closure)

- **Cumulative**: Sums all transactions from the beginning of time through the selected year
- **Query**: `WHERE TransactionDate <= 'YYYY-12-31'`
- **Performance**: Slower for old years (processes all historical data)

#### New Model (After Closure)

- **Current Year Only**: Sums only the current year's transactions plus opening balance
- **Query**: `WHERE YEAR(TransactionDate) = YYYY`
- **Performance**: Much faster (processes only one year of data)

### Why Both Models Produce Identical Results

After closing a year, the opening balance transaction brings forward all historical data. Therefore:

```
Old Model: SUM(all transactions from 1995 to 2025)
New Model: OpeningBalance 2025 + SUM(2025 transactions)

Result: IDENTICAL
```

The opening balance already contains the cumulative history, so we only need to add the current year's transactions.

### Transaction Types

#### YearClose Transaction

- **TransactionNumber**: `YearClose YYYY`
- **Date**: December 31st of the closed year
- **ReferenceNumber**: "Year Closure"
- **Purpose**: Closes P&L accounts to equity
- **Accounts**:
  - Debit: P&L Closing Account (8099) or Equity (3080)
  - Credit: Equity (3080) or P&L Closing Account (8099)
  - Depends on profit (negative) or loss (positive)

#### OpeningBalance Transactions

- **TransactionNumber**: `OpeningBalance YYYY`
- **Date**: January 1st of the new year
- **ReferenceNumber**: "Opening Balance"
- **Purpose**: Carries forward balance sheet accounts
- **Accounts**:
  - Multiple entries, one per balance sheet account
  - Equity account used for balancing
  - Preserves debit/credit nature of each account

### Account Configuration

Two accounts must be configured in **Tenant Beheer** → **Jaarafsluiting instellingen**:

1. **Eigen Vermogen Resultaat** (Equity Result Account)
   - Example: 3080 - Resultaatrekening
   - VW = N (Balance Sheet)
   - Purpose: Records net P&L result and balances opening entries

2. **W&V Afsluitrekening** (P&L Closing Account)
   - Example: 8099 - Afsluitrekening
   - VW = Y (P&L)
   - Purpose: Temporary account used in year-end closure transaction

**Note:** The interim account configuration has been removed. The equity account is now used for balancing all opening balance entries.

---

## Troubleshooting

### Error: "Previous year must be closed first"

**Problem**: You're trying to close year 2025, but year 2024 is not closed.

**Solution**: Close year 2024 first, then close 2025.

**Exception**: If 2025 is the first year you're closing, this error won't appear.

---

### Error: "Required accounts not configured"

**Problem**: The equity result or P&L closing accounts are not configured.

**Solution**:

1. Go to **Tenant Beheer** → **Jaarafsluiting instellingen**
2. Configure both required accounts:
   - Eigen Vermogen Resultaat (e.g., 3080)
   - W&V Afsluitrekening (e.g., 8099)
3. Click **"Configuratie Opslaan"**
4. Return to Aangifte IB and try again

---

### Error: "Cannot reopen year YYYY because year YYYY+1 is already closed"

**Problem**: You're trying to reopen an old year, but subsequent years are still closed.

**Solution**: See [Sequential Reopening Restriction](#sequential-reopening-restriction) section above.

---

### Warning: "Net P&L result is zero"

**Problem**: The year has no profit or loss (revenue equals expenses exactly).

**Impact**: This is just a warning. You can still close the year.

**Note**: No YearClose transaction will be created (not needed when result is zero).

---

### Warning: "No balance sheet accounts with balances"

**Problem**: All balance sheet accounts have zero balances.

**Impact**: This is just a warning. You can still close the year.

**Note**: No OpeningBalance transactions will be created (not needed when all balances are zero).

---

### Issue: Reports show old data after closing

**Problem**: Reports still show cumulative data instead of current year only.

**Solution**:

1. Refresh the page (F5)
2. If problem persists, the cache may not have been invalidated
3. Contact system administrator to manually clear cache

---

### Issue: Cannot find year-end closure section

**Problem**: The Jaarafsluiting section doesn't appear in Aangifte IB.

**Possible Causes**:

1. **No year selected**: Select a year from the year filter
2. **Wrong report**: Make sure you're in Aangifte IB, not another report
3. **Permissions**: You need `finance_write` permission
4. **Old version**: Update to the latest version

---

### Issue: Closed years table is empty

**Problem**: No closed years are shown in the table.

**Possible Causes**:

1. **No years closed yet**: Close your first year to see it in the table
2. **Wrong tenant**: Make sure you've selected the correct tenant
3. **Database issue**: Contact system administrator

---

## Best Practices

### When to Close Years

- **Timing**: Close years after completing the annual tax return
- **Verification**: Always review the Aangifte IB report before closing
- **Backup**: Ensure database backups are current before closing multiple years
- **Testing**: Test the closure process on a test tenant first

### Bulk Closing Historical Years

If you need to close many historical years:

1. **Use the bulk closure script**: `backend/scripts/database/bulk_close_years.py`
2. **Close in chronological order**: 2010 → 2011 → 2012 → ... → 2024
3. **Verify each closure**: Check a few sample years in Aangifte IB
4. **Document the process**: Add notes to each closure for audit trail

### Making Corrections

If you discover an error after closing:

1. **Minor corrections**: If only affecting one year, reopen that year only
2. **Major corrections**: If affecting multiple years, consider reopening all affected years
3. **Document changes**: Always add notes explaining why you reopened/reclosed
4. **Verify reports**: Check Aangifte IB reports after making corrections

### Performance Optimization

- **Close old years**: Improves report performance significantly
- **Don't reopen unnecessarily**: Each reopen/close cycle takes time
- **Bulk operations**: Use scripts for closing many years at once

---

## Permissions

### Required Roles

- **Finance_CRUD**: Required to close and reopen years
- **Tenant_Admin**: Required to configure year-end closure accounts

### Permission Checks

The system checks permissions at multiple levels:

1. **Frontend**: Buttons are disabled if you lack permissions
2. **Backend**: API endpoints verify permissions before executing
3. **Audit Log**: All operations are logged with user email

---

## Related Documentation

- **Admin Guide**: Configuration and troubleshooting for administrators
- **Technical Documentation**: Database schema and API specifications
- **Root Cause Analysis**: Understanding the old vs new model
- **Bulk Closure Script**: Documentation for `bulk_close_years.py`

---

## Support

If you encounter issues not covered in this guide:

1. Check the **OPEN_ISSUES.md** file for known problems
2. Review the **Root cause analysis.md** for technical details
3. Contact your system administrator
4. Check the audit log for error details

---

## Changelog

### Version 1.0 (March 2026)

- Initial release of year-end closure feature
- Integration with Aangifte IB report
- Sequential reopening restriction
- ReferenceNumber added to transactions
- Removed interim account configuration
- Comprehensive testing (43 backend tests, 15 frontend tests)
