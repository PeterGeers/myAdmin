# Year End Closure - Requirements

**Status**: Draft  
**Feature**: Year End Closure for Financial Administration  
**Module**: FIN (Financial)  
**Priority**: Medium

## Overview

Year-end closure creates opening balance transactions for the new year, eliminating the need to query from the beginning of time for balance sheet reports. This improves performance and formalizes the year-end process.

## Current Situation

**How it works now**:

- P&L accounts (VW='Y'): Reports filter by year - works fine
- Balance sheet accounts (VW='N'): Reports query ALL transactions from beginning of time to calculate balances
- XLSX export: Calculates opening balances on-the-fly

**Problems**:

- Performance degrades as historical data grows
- No formal year-end closure process
- No audit trail of year-end activities

## Proposed Solution

Create opening balance transactions at year-end that capture:

1. Net P&L result for the year
2. Ending balances of all balance sheet accounts (where balance ≠ 0)

**Benefits**:

- Reports only need to query current year data
- Formal audit trail of year-end closure
- Can be done retrospectively (typically months after year-end when all transactions are finalized)
- Formal audit trail of year-end closure
- Consistent with accounting best practices
- Improves performance over time

## Three Core Tasks

### 1. Fix Historical Data

**Problem**: Existing years don't have opening balance transactions

**Solution**: One-time migration script to generate opening balances for all historical years

**Process**:

- Identify first year with transactions (Year 0)
- For each subsequent year:
  - Calculate ending balance from vw_mutaties as of December 31st previous year
  - Create opening balance transaction dated January 1st
  - Include only balance sheet accounts (VW='N') with non-zero balances

**Transaction Format** (in `mutaties` table, double-entry format):

```
TransactionNumber: "OpeningBalance YYYY"
TransactionDate: YYYY-01-01
TransactionDescription: "Opening balance for year YYYY of Administration [Name]"

For each account with non-zero balance, create ONE record:
  If balance is positive (debit balance):
    - Debet: [balance sheet account]
    - Credit: [interim account, e.g., 2001]
    - TransactionAmount: balance (positive value)

  If balance is negative (credit balance):
    - Debet: [interim account, e.g., 2001]
    - Credit: [balance sheet account]
    - TransactionAmount: abs(balance) (positive value)

Note: Interim account (e.g., 2001) is used as the balancing account.
All TransactionAmount values are positive (no sign).
```

### 2. Calculate Net P&L Result

**Problem**: Need to record the year's profit/loss in equity

**Solution**: Calculate sum of all P&L accounts (VW='Y') for the year

**Process**:

```sql
SELECT SUM(Amount) as net_result
FROM vw_mutaties
WHERE VW='Y'
AND jaar = [YEAR]
AND administration = [TENANT]
```

**Result Handling**:

- If net_result > 0: Profit - Credit to equity result account
- If net_result < 0: Loss - Debit to equity result account
- Equity result account is tenant-configurable (e.g., 3080 for GoodwinSolutions)

**Transaction Format** (in `mutaties` table, double-entry format):

```
TransactionNumber: "YearClose YYYY"
TransactionDate: YYYY-12-31
TransactionDescription: "Year-end closure YYYY - [Administration]"

If profit (net_result > 0):
  - Debet: [P&L closing account, e.g., 8099]
  - Credit: [equity result account, e.g., 3080]
  - TransactionAmount: net_result (positive value)

If loss (net_result < 0):
  - Debet: [equity result account, e.g., 3080]
  - Credit: [P&L closing account, e.g., 8099]
  - TransactionAmount: abs(net_result) (positive value)

Note: P&L closing account (e.g., 8099) is used to close P&L accounts to equity.
This transaction transfers the net result from P&L to equity.
All TransactionAmount values are positive (no sign).
```

### 3. Calculate Opening Balances

**Problem**: Need to create opening balance transactions for next year

**Solution**: Extract ending balances from vw_mutaties and create opening balance transactions

**Process**:

```sql
SELECT
  Reknum,
  AccountName,
  SUM(Amount) as balance
FROM vw_mutaties
WHERE VW='N'
AND TransactionDate <= 'YYYY-12-31'
AND administration = [TENANT]
GROUP BY Reknum, AccountName
HAVING SUM(Amount) <> 0
```

**Transaction Creation**:

- Create multiple records in `mutaties` table (one per account with non-zero balance)
- Each record has both Debet and Credit (double-entry)
- Date: January 1st of new year
- Include equity result account with previous year's net result
- Only include accounts with non-zero balances

**Transaction Format** (in `mutaties` table, double-entry format):

```
TransactionNumber: "OpeningBalance YYYY+1"
TransactionDate: YYYY+1-01-01
TransactionDescription: "Opening balance for year YYYY+1 of Administration [Name]"

For each account with non-zero balance, create ONE record:
  If balance is positive (debit balance):
    - Debet: [balance sheet account]
    - Credit: [interim account, e.g., 2001]
    - TransactionAmount: balance (positive value)

  If balance is negative (credit balance):
    - Debet: [interim account, e.g., 2001]
    - Credit: [balance sheet account]
    - TransactionAmount: abs(balance) (positive value)

Note: Interim account (e.g., 2001) is used as the balancing account.
All TransactionAmount values are positive (no sign).
```

## User Stories

### US-1: Close Fiscal Year

**As a** financial administrator  
**I want to** close a completed fiscal year  
**So that** reports run faster and I have a formal year-end record

**Acceptance Criteria**:

- User can select a year to close
- System calculates net P&L result
- System creates year-end closure transaction
- System creates opening balance transactions for next year
- Process is atomic (all-or-nothing)
- Audit log records who closed the year and when

### US-2: View Closed Years

**As a** financial administrator  
**I want to** view which years are closed  
**So that** I know which periods are finalized

**Acceptance Criteria**:

- System displays list of all years with closure status
- Closed years show closure date and user
- System allows viewing/reporting on closed years

### US-3: Migrate Historical Data

**As a** tenant administrator  
**I want to** generate opening balances for historical years  
**So that** all years use the same calculation method

**Acceptance Criteria**:

- Migration script generates opening balances for all past years
- Script validates that new calculations match old calculations
- Script can run in dry-run mode
- Script is idempotent (can be re-run safely)

## Functional Requirements

### FR-1: Year Closure Process

**Pre-closure validation**:

- Verify year is not already closed
- Verify previous year is closed (except for first year)
- Optional: Check for unprocessed transactions

**Year-end closure transaction**:

- Calculate net result: `SUM(Amount) FROM vw_mutaties WHERE VW='Y' AND jaar=[YEAR]`
- Create transaction dated December 31st
- Record in tenant's configured equity result account
- Use TransactionNumber format: "YearClose [YEAR]"

**Opening balance transaction**:

- Extract all balance sheet accounts with non-zero balances
- Create transaction dated January 1st of next year
- Include equity result account with previous year's net result
- Use TransactionNumber format: "OpeningBalance [YEAR]"

**Year lock**:

- Mark year as closed in database
- Record closure timestamp and user
- Prevent new transactions in closed year (optional - can be phase 2)

### FR-2: Historical Data Migration

**Migration script requirements**:

- Process years sequentially from oldest to newest
- For each year:
  - Calculate ending balance from vw_mutaties
  - Create opening balance transaction for next year
  - Validate calculations
- Transactional: rollback if any year fails
- Logging: detailed log of all transactions created
- Dry-run mode: preview changes without applying

**Validation**:

- Compare balance calculations before and after migration
- Verify all accounts balance (sum of amounts = 0 for each transaction)
- Alert if any discrepancies found

### FR-3: Tenant Configuration

**Required configuration per tenant**:

- Equity result account code (e.g., 3080)
- Fiscal year definition (currently: calendar year only)
- Language preference (for transaction descriptions)

**Configuration storage**:

- Store in tenants table or separate configuration table
- Validate account exists and is VW='N' (balance sheet)

## Non-Functional Requirements

### NFR-1: Performance

- Year closure process completes within 30 seconds for typical year
- Migration script processes 1 year per second
- Reports using opening balances are 10x faster than querying from beginning

### NFR-2: Data Integrity

- Closure process is transactional (ACID compliant)
- Opening balances maintain double-entry rules (debits = credits)
- Migration validation ensures accuracy

### NFR-3: Audit Trail

- All closure actions logged with timestamp, user, administration, year
- Logs are immutable and retained indefinitely

## Out of Scope

- Automated year-end adjustments (depreciation, accruals)
- Reopening closed years (can be added later if needed)
- Multi-year consolidation
- Non-calendar fiscal years (can be added later)
- Preventing edits to closed years (can be added as phase 2)

## Success Criteria

**Functional Success**:

- User can successfully close a fiscal year
- Opening balances correctly carry forward
- Historical migration completes without errors
- Reports use opening balances correctly

**Performance Success**:

- Balance sheet reports run in < 2 seconds (vs 10+ seconds before)
- Migration completes for 10 years of data in < 10 seconds

**Data Quality**:

- All opening balance transactions balance (sum = 0)
- Balance calculations match before and after migration
- No orphaned or incorrect transactions

## Implementation Phases

### Phase 1: Core Functionality

- Implement year closure logic (tasks 2 & 3)
- Create API endpoint for closing a year
- Add year closure status tracking
- Basic validation

### Phase 2: Historical Migration

- Create migration script (task 1)
- Add dry-run mode
- Add validation checks
- Run migration on test data

### Phase 3: UI & Polish

- Add year closure UI
- Add closed year indicators in reports
- Update report queries to use opening balances
- Documentation

### Phase 4: Optional Enhancements

- Prevent edits to closed years
- Reopen year functionality
- Automated validation checks
- Year-end checklist

## Technical Notes

### Database Changes

**New table: year_closure_status**

```sql
CREATE TABLE year_closure_status (
  id INT AUTO_INCREMENT PRIMARY KEY,
  administration VARCHAR(50) NOT NULL,
  year INT NOT NULL,
  closed_date DATETIME NOT NULL,
  closed_by VARCHAR(255) NOT NULL,
  closure_transaction_id INT,
  opening_balance_transaction_id INT,
  UNIQUE KEY (administration, year)
);
```

### Key Files to Modify

**Backend**:

- Create: `year_end_closure.py` - Main closure logic
- Create: `scripts/database/migrate_opening_balances.py` - Migration script
- Update: `mutaties_cache.py` - Use opening balances in calculations
- Update: `financial_report_generator.py` - Use opening balances
- Update: `xlsx_export.py` - Use opening balances
- Create: `routes/year_end_routes.py` - API endpoints

**Frontend**:

- Create: Year closure UI component
- Update: Reports to show closed year indicators

### SQL Queries

**Calculate net P&L result**:

```sql
SELECT SUM(Amount) as net_result
FROM vw_mutaties
WHERE VW='Y'
AND jaar = ?
AND administration = ?
```

**Get ending balances for opening balance**:

```sql
SELECT
  Reknum,
  AccountName,
  SUM(Amount) as balance
FROM vw_mutaties
WHERE VW='N'
AND TransactionDate <= ?
AND administration = ?
GROUP BY Reknum, AccountName
HAVING SUM(Amount) <> 0
```

**Check if year is closed**:

```sql
SELECT * FROM year_closure_status
WHERE administration = ?
AND year = ?
```

## Related Specifications

- `.kiro/specs/FIN/README.md` - FIN Module overview
- `.kiro/specs/FIN/Reports/` - Report specifications
- `.kiro/specs/Common/templates/` - Template system

## Questions to Resolve

1. Should we prevent edits to closed years immediately, or make that phase 2?
2. What permissions are required to close a year?
3. Should we send notifications when a year is closed?
4. Do we need a year-end checklist (BTW complete, invoices processed, etc.)?
5. Should the migration script run automatically on deployment, or manually?

## Summary

Year-end closure is a straightforward feature with three concrete tasks:

1. **Fix history**: Generate opening balances for past years (one-time migration)
2. **Calculate result**: Sum P&L accounts and record in equity
3. **Create opening balances**: Extract non-zero balance sheet accounts for next year

This approach:

- Improves performance (no more querying from beginning of time)
- Provides formal year-end audit trail
- Follows accounting best practices
- Is simple to implement and test
