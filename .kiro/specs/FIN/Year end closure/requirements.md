# Year End Closure - Requirements

**Status**: Draft  
**Feature**: Year End Closure for Financial Administration  
**Module**: FIN (Financial)  
**Priority**: High

## Overview

When a fiscal year is completed, the system must perform year-end closure to:

- Close all profit & loss (P&L) accounts to zero
- Transfer net profit/loss to equity
- Create opening balances for the next fiscal year
- Lock the closed year from further modifications
- Maintain audit trail of closure process

## User Stories

### US-1: Close Fiscal Year

**As a** financial administrator  
**I want to** close a completed fiscal year  
**So that** I can start the new year with correct opening balances and prevent modifications to closed periods

**Acceptance Criteria**:

- User can select a year to close from available years (not closed) and always N+1
- System validates that all required transactions are present
- System calculates net profit/loss from all P&L accounts (VW='Y')
- System creates closing entry to record net result in tenant's configured equity result account (see BR-6)
- System creates opening balance entries for next year from all balance sheet accounts (VW='N') where the value is not 0
- Closure process is atomic (all-or-nothing)
- Audit log records who closed the year and when

### US-2: Validate Year Readiness

**As a** financial administrator  
**I want to** validate if a year is ready to be closed  
**So that** I can ensure all required data is complete before closure

**Acceptance Criteria**:

- System checks if all quarters have BTW declarations
- System checks if all bank statements are imported
- System checks if all invoices are processed
- System reports any missing or incomplete data
- System shows summary of P&L and balance sheet before closure
- User can review validation report before proceeding

### US-3: View Closed Years

**As a** financial administrator  
**I want to** view which years are closed  
**So that** I know which periods are locked and which are still open

**Acceptance Criteria**:

- System displays list of all years with closure status
- Closed years show closure date and user who closed them
- System prevents editing transactions in closed years
- System allows viewing/reporting on closed years

### US-4: Reopen Closed Year (Finance CRUD Permission Required)

**As a** financial administrator with CRUD permissions  
**I want to** reopen a closed year in exceptional cases  
**So that** I can correct errors discovered after closure

**Acceptance Criteria**:

- Only users with FINANCE_CRUD permission can reopen years
- System requires reason for reopening
- System reverses closing and opening balance entries
- System logs reopening action with reason and user
- System warns about impact on subsequent years
- User must re-close year after corrections

## Functional Requirements

### FR-1: Year Closure Process

**VW Classification Explained**:

VW stands for "Verlies/Winst" (Dutch for Loss/Profit), equivalent to P&L (Profit & Loss) in English.

- **VW='Y' (Yes)**: P&L accounts (Verlies/Winst accounts) - Revenue and Expenses
- **VW='N' (No)**: Balance Sheet accounts (Balans accounts) - Assets, Liabilities, Equity

**How VW Logic Works**:

The system uses VW classification to automatically handle P&L vs Balance Sheet accounts:

- **VW='Y' (P&L accounts)**: Reports filter to show only transactions from the specific year - automatically starts at zero each year
- **VW='N' (Balance sheet accounts)**: Reports include all transactions up to the reporting date - balances carry forward

**What Year-End Closure Adds**:

While VW logic handles the filtering, year-end closure formalizes the process by:

1. **Capturing Net Result**: Creates a transaction to record the year's net profit/loss in the tenant's configured equity result account
2. **Audit Trail**: Provides a permanent record that the year was formally closed
3. **Year Lock**: Prevents modifications to closed periods
4. **Opening Balances**: Generates opening balance entries for the next year's balance sheet accounts

**Pre-Closure Validation**:

- Verify all transactions are categorized
- Check for unreconciled bank statements
- Validate BTW declarations are complete
- Ensure no pending invoices for the year
- Calculate preliminary P&L and balance sheet

**Year-End Closure Transaction**:

- Calculate net result: SUM(Revenue accounts 8000-8999) - SUM(Expense accounts 4000-7999)
- Create ONE journal entry to record net result in the tenant's configured equity result account (see BR-6)
- Date entry as last day of fiscal year (YYYY-12-31)
- Use transaction number format: "YearClose [YEAR]"
- Reference: "Year-end closure [YEAR] - [Administration]"

**Opening Balances Creation**:

- Extract all balance sheet accounts (VW='N') as of year-end (YYYY-12-31)
- Create opening balance transaction entries for each account with a non-zero balance
- Date opening entries as first day of new year (YYYY+1-01-01)
- Use transaction number format: "OpeningBalance [YEAR]"
- Reference: "Opening balance for year [YEAR] of Administration [Administration]"
- Include the tenant's configured equity result account with the net result from previous year
- This creates a clean starting point for the new year, similar to XLSX export logic

**Year Lock**:

- Mark year as closed in database
- Record closure timestamp and user
- Prevent new transactions in closed year
- Prevent editing existing transactions in closed year

### FR-2: Account Classification

**Balance Sheet Accounts (VW='N')** - Carry forward to next year via opening balances

**P&L Accounts (VW='Y')** - Automatically filtered by year (no closing entries needed)

**Special Accounts**:

- Tenant-configurable equity result account (see BR-6 for configuration details)
  - Example: 3080 for GoodwinSolutions
- 0998: Result previous year (optional, for multi-year tracking)

### FR-3: Validation Rules

Year cannot be closed if:

- Previous year is not closed (except for first year)
- There are unprocessed bank statements
- BTW declarations are incomplete
- There are draft invoices
- Balance sheet doesn't balance (Debit ≠ Credit)

Year can be reopened only if:

- User has FINANCE_CRUD permission
- Subsequent years are not closed
- Reason is provided

### FR-4: Reporting Requirements

**Pre-closure report**:

- P&L summary by account group
- Balance sheet summary
- Net profit/loss
- Validation status
- Missing data warnings

**Post-closure report**:

- Closing entries created
- Opening balances for next year
- Closure confirmation
- Audit trail

## Non-Functional Requirements

### NFR-1: Performance

- Year closure process completes within 30 seconds for typical year (10,000 transactions)
- Validation checks complete within 5 seconds
- Reports generate within 10 seconds

### NFR-2: Data Integrity

- Closure process is transactional (ACID compliant)
- If any step fails, entire closure is rolled back
- Closing entries maintain double-entry bookkeeping rules
- Opening balances exactly match closing balances

### NFR-3: Audit Trail

- All closure actions logged with timestamp, user, administration, year, and reason
- Logs are immutable and retained indefinitely

### NFR-4: Security

- Year closure requires 'year_close' permission
- Year reopening requires 'FINANCE_CRUD' permission
- Closed year modifications blocked at API level
- Tenant isolation maintained throughout process

### NFR-5: Usability

- Clear step-by-step wizard for closure process
- Visual validation checklist
- Confirmation dialog before final closure
- Progress indicator during closure
- Success/error messages in user's language

## Business Rules

### BR-1: Fiscal Year Definition

- Fiscal year = Calendar year (January 1 - December 31)
- Closing date = Last day of fiscal year (YYYY-12-31)
- Opening date = First day of next fiscal year (YYYY+1-01-01)

### BR-2: Closing Entry Rules

- Net result calculated as: SUM(Revenue 8000-8999) - SUM(Expenses 4000-7999)
- Net result recorded in tenant's configured equity result account (see BR-6) with single journal entry
- P&L accounts (VW='Y') do NOT need individual closing entries - VW logic handles year filtering
- Closing entry dated last day of fiscal year (YYYY-12-31)
- Closing entry uses special transaction number and cannot be edited or deleted

### BR-2A: Ledger Codes for Year-End Closure

**Result Account**:

- **Tenant-Configurable Result Account** (see BR-6): Primary account to receive net P&L transfer during year-end closure
  - Example: 3080 for GoodwinSolutions (each tenant configures their own)
  - Debit: If net loss (expenses > revenue)
  - Credit: If net profit (revenue > expenses)
  - This account accumulates the current year's result

**P&L Accounts** (VW='Y'):

- Revenue accounts (8000-8999): Automatically filtered by year via VW logic
- Expense accounts (4000-7999): Automatically filtered by year via VW logic
- No individual closing entries needed - VW logic handles year filtering

**Balance Sheet Accounts** (VW='N'):

- All balance sheet accounts carry forward via opening balances
- Opening balance amount = Closing balance of previous year
- Includes tenant's configured result account with net P&L result

**Special Handling**:

- **VAT Accounts** (see BR-7 for account configuration):
  - VAT collection accounts (e.g., 2020, 2021) should be zero at year start
  - VAT payable account (e.g., 2010) may have balance if payment pending
  - If VAT is paid before year-end, transfer 2010 to accounts payable (e.g., 1300)
  - Opening balances created only for accounts with non-zero balances

- **Suspense/Temporary Accounts**:
  - Any accounts with "temp" or "suspense" in name should be zero before closure
  - System validates double-entry bookkeeping: SUM(vw_mutaties.amount) must equal 0
  - Each transaction has both debit and credit entries (view makes one negative, one positive)
  - System should warn if this validation fails

**Closing Entry Examples**:

_Example 1: Net Profit Scenario_

```
Revenue accounts (8000-8999) total: €100,000
Expense accounts (4000-7999) total: €70,000
Net profit: €30,000

Year-end closing entry (dated 2024-12-31):
TransactionNumber: "YearClose 2024"
Description: "Year-end closure 2024 - GoodwinSolutions"
Debit: (none - net profit)
Credit: 3080 (Equity Result Account - tenant configured): €30,000

Note: Individual P&L accounts are NOT closed with entries.
VW logic automatically filters them by year in reports.
```

_Example 2: Net Loss Scenario_

```
Revenue accounts (8000-8999) total: €50,000
Expense accounts (4000-7999) total: €80,000
Net loss: €30,000

Year-end closing entry (dated 2024-12-31):
TransactionNumber: "YearClose 2024"
Description: "Year-end closure 2024 - GoodwinSolutions"
Debit: 3080 (Equity Result Account - tenant configured): €30,000
Credit: (none - net loss)

Note: Individual P&L accounts are NOT closed with entries.
VW logic automatically filters them by year in reports.
```

_Example 3: Opening Balances for New Year_

```
After closing 2024, create opening balances for 2025:

TransactionNumber: "OpeningBalance 2025"
TransactionDate: 2025-01-01
Description: "Opening balance for year 2025 of Administration GoodwinSolutions"

Balance sheet accounts as of 2024-12-31:
- 1000 (Bank Account): €50,000 (debit)
- 1100 (Accounts Receivable): €15,000 (debit)
- 1500 (Fixed Assets): €100,000 (debit)
- 2100 (Accounts Payable): €20,000 (credit)
- 2010 (VAT Payable): €5,000 (credit)
- 0900 (Capital): €110,000 (credit)
- 3080 (Equity Result Account - tenant configured): €30,000 (credit) ← from 2024 net profit

Each account gets a transaction line dated 2025-01-01 with its opening balance.
This creates a clean starting balance sheet for 2025, similar to XLSX export logic.
```

### BR-3: Opening Balance Rules

- Opening balances created for ALL balance sheet accounts (VW='N') with non-zero balances
- Opening balance amount = Closing balance of previous year (as of YYYY-12-31)
- Opening balances dated first day of new year (YYYY+1-01-01)
- Opening balances use special transaction number: "OpeningBalance [YEAR]"
- Each account gets its own line in the opening balance transaction
- Tenant's configured equity result account included with previous year's net result
- This mirrors the logic in `xlsx_export.py` and `financial_report_generator.py`
- Opening balances provide a clean starting point and improve year-over-year reporting

### BR-4: Sequential Closure

- Years must be closed in sequential order
- Cannot close year N+1 if year N is not closed
- Exception: First year of administration can be closed without previous year

### BR-5: Modification Restrictions

- Closed years are read-only
- No new transactions can be added to closed years
- Existing transactions cannot be modified
- Exception: Users with FINANCE_CRUD permission can reopen year for corrections

### BR-6: Tenant-Specific Result Account Configuration

- Each tenant configures their preferred equity result account for year-end closure
- Configuration stored in tenant settings/configuration table
- Account must be a balance sheet account (VW='N') in the equity range (typically 0900-0999 or 3000-3999)
- Example configurations:
  - GoodwinSolutions: 3080 (Equity)
  - Default if not configured: Standard result account
- Configuration validated during tenant setup
- Used for:
  - Recording net P&L result during year-end closure
  - Creating opening balance entries for new year
  - Displaying year-end closure reports

### BR-7: VAT Account Configuration

**Applicability**:

- VAT configuration applies only to business/commercial administrations
- Private accounts (personal finances) do not use VAT tracking
- System should allow null/empty VAT configuration for private accounts

**Date-Effective Configuration**:

- VAT account assignments are date-effective (can change over time)
- Each configuration has a `valid_from` date (required)
- Each configuration has a `valid_to` date (optional - null means currently active)
- Historical configurations must be maintained for audit and reporting purposes
- When closing a year, use the VAT configuration that was active during that year

**Typical VAT Accounts** (tenant-configurable, date-effective):

- VAT Payable account (e.g., 2010): VAT amounts paid to vendors and the VAT amount owed/paid to tax authority
- VAT Collected - High Rate (e.g., 2020): VAT collected at 21%
- VAT Collected - Low Rate (e.g., 2021): VAT collected at 9%
- Accounts Payable for VAT (e.g., 1300): When VAT payment is pending

**Year-End Closure Expectations**:

- VAT collection accounts (2020, 2021) should be zero after BTW declaration
- VAT payable account (2010) may have balance if payment is pending
- If pending, can be transferred to accounts payable before year-end
- Opening balances created only for accounts with non-zero balances

**Configuration Usage**:

- BTW declaration validation
- Year-end closure validation
- Opening balance generation
- Historical reporting (use configuration active during reporting period)

### BR-8: Tenant Configuration Storage Requirements

**Configuration Table Structure**:

A `tenant_year_end_config` table must store tenant-specific business rules with date-effective tracking:

| Field Name                 | Data Type    | Required | Description                                                           | Example Value                                  |
| -------------------------- | ------------ | -------- | --------------------------------------------------------------------- | ---------------------------------------------- |
| id                         | Integer/UUID | Yes      | Unique configuration record identifier                                | 1                                              |
| administration             | String       | Yes      | Tenant/administration identifier (used in all tenant-specific tables) | "goodwinsolutions"                             |
| valid_from                 | Date         | Yes      | Configuration effective start date                                    | 2024-01-01                                     |
| valid_to                   | Date         | No       | Configuration effective end date (null = currently active)            | null or 2024-12-31                             |
| result_account             | String       | Yes      | Equity result account for year-end closure                            | "3080"                                         |
| is_vat_applicable          | Boolean      | Yes      | Whether VAT tracking applies (false for private accounts)             | true                                           |
| vat_payable_account        | String       | No       | VAT amounts paid to vendors and owed to tax authority                 | "2010"                                         |
| vat_collected_high_account | String       | No       | VAT collected at high rate (21%)                                      | "2020"                                         |
| vat_collected_low_account  | String       | No       | VAT collected at low rate (9%)                                        | "2021"                                         |
| vat_accounts_payable       | String       | No       | Accounts payable for pending VAT payments                             | "1300"                                         |
| fiscal_year_start_month    | Integer      | Yes      | Fiscal year start month (1-12)                                        | 1 (January)                                    |
| fiscal_year_start_day      | Integer      | Yes      | Fiscal year start day (1-31)                                          | 1                                              |
| created_at                 | Timestamp    | Yes      | Configuration creation timestamp                                      |                                                |
| created_by                 | String       | Yes      | User who created configuration                                        |                                                |
| notes                      | Text         | No       | Reason for configuration change                                       | "Changed result account per accountant advice" |

**Note**: Language preference for transaction descriptions is retrieved from the existing `tenants` table, not duplicated here.

**Date-Effective Configuration Rules**:

1. **No Overlapping Periods**: For a given administration, configuration periods cannot overlap
2. **Continuous Coverage**: When creating a new configuration, the previous configuration's `valid_to` should be set to the day before the new `valid_from`
3. **Historical Immutability**: Configurations for past periods cannot be deleted, only marked as ended
4. **Active Configuration**: Only one configuration per administration can have `valid_to = null` (the current active configuration)
5. **Year Closure Lookup**: When closing a year, query for the configuration where `valid_from <= year_end_date AND (valid_to IS NULL OR valid_to >= year_end_date)`

**Configuration Validation Rules**:

1. **Result Account**:
   - Must exist in chart of accounts for tenant
   - Must be a balance sheet account (VW='N')
   - Must be in equity range (typically 0900-0999 or 3000-3999)
   - Cannot be changed if any years are already closed using this account

2. **VAT Accounts**:
   - Must exist in chart of accounts for tenant
   - Must be balance sheet accounts (VW='N')
   - Should be in liability range (typically 2000-2999)
   - Can be null if `is_vat_applicable = false` (private accounts)
   - Required if `is_vat_applicable = true` (business accounts)

3. **Language**:
   - Retrieved from `tenants` table (not stored in year-end config)
   - Determines transaction number formats and descriptions
   - Can be changed at any time (affects future transactions only)

4. **Fiscal Year**:
   - Currently only calendar year supported (January 1 - December 31)
   - Future enhancement: Support custom fiscal years

**Configuration Management**:

- **Initial Setup**: Configuration created during tenant onboarding
- **Updates**: Only users with TENANT_ADMIN or FINANCE_ADMIN permission can modify
- **Audit Trail**: All configuration changes logged with timestamp, user, old value, new value
- **Validation**: System validates configuration before saving
- **Migration**: Existing tenants need configuration populated during migration

**Default Values**:

If tenant configuration is missing, system uses these defaults:

- `result_account`: "0999" (standard result account)
- `vat_payable_account`: "2010"
- `vat_collected_high_account`: "2020"
- `vat_collected_low_account`: "2021"
- `vat_accounts_payable`: "1300"
- `fiscal_year_start_month`: 1 (January)
- `fiscal_year_start_day`: 1

**API Endpoints Required**:

- `GET /api/tenants/{administration}/year-end-config` - Retrieve configuration
- `PUT /api/tenants/{administration}/year-end-config` - Update configuration
- `POST /api/tenants/{administration}/year-end-config/validate` - Validate configuration without saving

**Usage in Year-End Closure**:

1. **Retrieve Configuration**: Load tenant's year-end config at start of closure process
2. **Retrieve Language**: Load tenant's preferred language from `tenants` table
3. **Validate Accounts**: Verify all configured accounts exist and are correct type
4. **Generate Transactions**: Use configured accounts and language for transaction creation
5. **Localize Descriptions**: Format transaction numbers and descriptions based on preferred language

## Out of Scope

- Multi-year financial consolidation
- Automated year-end adjustments (depreciation, accruals)
- Tax return generation (handled separately)
- Interim period closures (monthly/quarterly)
- Budget vs actual analysis
- Foreign currency translation adjustments

## Success Criteria

**Functional Success**:

- User can successfully close a fiscal year
- Opening balances correctly carry forward
- Closed years are locked from modifications
- Validation prevents premature closure

**Data Quality**:

- Balance sheet balances after closure
- P&L accounts are zeroed
- No orphaned transactions
- Audit trail is complete

**User Experience**:

- Process is intuitive and guided
- Validation errors are clear
- Closure completes in reasonable time
- Reports are accurate and helpful

**System Reliability**:

- No data loss during closure
- Rollback works correctly on errors
- Multi-tenant isolation maintained
- Performance meets requirements

## Acceptance Testing Scenarios

### Scenario 1: Happy Path - Close Year 2024

**Given** all 2024 transactions are complete and validated  
**When** user initiates year closure for 2024  
**Then** system creates closing entries, opening balances, and locks the year

### Scenario 2: Validation Failure - Missing BTW

**Given** Q4 2024 BTW declaration is missing  
**When** user attempts to close year 2024  
**Then** system shows validation error and prevents closure

### Scenario 3: Sequential Closure - Skip Year

**Given** year 2023 is not closed  
**When** user attempts to close year 2024  
**Then** system prevents closure and shows error message

### Scenario 4: Reopen Year - Finance CRUD Correction

**Given** year 2024 is closed and user has FINANCE_CRUD permission  
**When** user reopens 2024 with reason "Correct invoice classification"  
**Then** system reverses closing and opening balance entries and allows modifications

## Dependencies

- Database schema must support year closure status tracking
- Transaction table must have immutability flags
- Audit log system must be in place
- User permission system must support year_close permission
- Reporting system must handle closed year indicators

## Migration Considerations

### Current System Behavior

The existing system does NOT have explicit opening balances for each year:

1. **Balance Calculation**: Balance sheet values are calculated from the beginning of all time to the reporting date
2. **Year-End Closure Entries**: Result amounts are already booked for all years (closing entries exist)
3. **No Opening Balance Transactions**: There are no "OpeningBalance" or "Beginbalans" transactions in historical data

### Migration Strategy

**One-Time Historical Data Migration**

Generate opening balance transactions for all historical years following the N+1 principle:

1. **Identify First Year**: Determine the earliest year with transactions (Year 0)
2. **Generate Opening Balances Sequentially**:
   - Year 1: Calculate opening balance from all Year 0 transactions
   - Year 2: Calculate opening balance from Year 0 + Year 1 transactions
   - Year 3: Calculate opening balance from Year 0 + Year 1 + Year 2 transactions
   - Continue for all years up to current year
3. **Transaction Format**:
   - TransactionNumber: "OpeningBalance [YEAR]" (or "Beginbalans [YEAR]" for Dutch)
   - TransactionDate: [YEAR]-01-01
   - Description: "Opening balance for year [YEAR] of Administration [Name]"
   - Include all balance sheet accounts (VW='N') with non-zero balances
4. **Mark as System-Generated**: Flag these transactions as migration-generated for audit trail

**Benefits of This Approach**:

- Single calculation method across all years (no dual-mode complexity)
- Consistent behavior for historical and future data
- Improved performance (no need to query all historical data)
- Clearer audit trail
- Simpler code maintenance

**Report Adjustments**

After migration, ALL balance sheet reports use the same logic:

1. **For any year**: Start with opening balance transaction for that year
2. **Calculate**: `Balance = OpeningBalance + SUM(transactions in year)`
3. **No special cases**: Same logic for historical and current years

**Migration Script Requirements**:

- Run as one-time migration before deploying year-end closure feature
- Transactional: All-or-nothing (rollback if any year fails)
- Validation: Verify that new calculation matches old calculation for all years
- Idempotent: Can be re-run safely (check if opening balances already exist)
- Logging: Detailed log of all opening balances created
- Dry-run mode: Preview changes before applying

**Validation Steps**:

1. **Pre-Migration**: Calculate all balance sheet values using legacy method (from beginning of time)
2. **Post-Migration**: Calculate all balance sheet values using new method (from opening balances)
3. **Compare**: Verify that results are identical for all accounts, all years
4. **Alert**: If any discrepancies found, rollback and investigate

### Implementation Notes

**Affected Reports**:

- Balance sheet reports
- Trial balance reports
- Account detail reports
- XLSX exports
- P&L reports (should not be affected - VW logic already filters by year)

**Database Changes**:

- Add `year_closure_status` table to track which years are closed
- Opening balance transactions added to `mutaties` table with special flag
- Existing closing entries (result bookings) remain unchanged

**Code Changes**:

- Update `mutaties_cache.py` to calculate from opening balances
- Update `financial_report_generator.py` to use opening balance logic
- Update `xlsx_export.py` to use opening balance logic
- Create migration script: `scripts/database/generate_historical_opening_balances.py`

### Risk Mitigation

| Risk                                           | Impact | Mitigation                                               |
| ---------------------------------------------- | ------ | -------------------------------------------------------- |
| Incorrect balance calculations after migration | High   | Parallel validation: compare old vs new calculations     |
| Migration script fails mid-process             | High   | Use database transactions with rollback capability       |
| Reports showing different values               | High   | Extensive testing with historical data before deployment |
| Data inconsistency                             | Medium | Dry-run mode + validation before actual migration        |
| Performance during migration                   | Low    | Run during off-hours; add progress indicators            |

## Risks and Mitigations

| Risk                                   | Impact | Probability | Mitigation                                    |
| -------------------------------------- | ------ | ----------- | --------------------------------------------- |
| Data loss during closure               | High   | Low         | Implement transactional closure with rollback |
| Incorrect opening balances             | High   | Medium      | Extensive validation and testing              |
| Performance issues with large datasets | Medium | Medium      | Optimize queries, add progress indicators     |
| User closes year prematurely           | Medium | High        | Multi-step validation and confirmation        |
| Concurrent closure attempts            | Low    | Low         | Implement locking mechanism                   |

## Related Specifications

- `.kiro/specs/FIN/VAT Rules/` - BTW validation requirements
- `.kiro/specs/Common/templates/` - Report template system
- Multi-tenant architecture documentation

## Notes

- Current system generates opening balance entries in `xlsx_export.py` and `financial_report_generator.py`
- VW logic (N=Balance, Y=P&L) is implemented in `mutaties_cache.py`
- Need to formalize year closure as a first-class feature vs current ad-hoc approach
- Consider impact on existing XLSX export functionality

## Terminology Mapping

This document uses English terminology for clarity in a multi-language system. The following table maps English terms to their Dutch equivalents used in the database and codebase:

| English Term        | Dutch Term         | Database/Code Reference     | Notes                                      |
| ------------------- | ------------------ | --------------------------- | ------------------------------------------ |
| Opening Balance     | Beginbalans        | Transaction number format   | Used for first-day-of-year balance entries |
| Year-end Closure    | Jaarafsluiting     | Transaction description     | Used for last-day-of-year closing entry    |
| Year Close          | Afsluiting         | Transaction number format   | Abbreviated form for closing entry         |
| Transactions        | Mutaties           | `mutaties` table            | Core financial transactions table          |
| P&L / Profit & Loss | Verlies/Winst (VW) | `VW` column in database     | VW='Y' for P&L accounts                    |
| Balance Sheet       | Balans             | `VW` column in database     | VW='N' for balance sheet accounts          |
| Administration      | Administratie      | Tenant/administration field | Multi-tenant identifier                    |
| VAT Declaration     | BTW Aangifte       | BTW-related tables          | Dutch tax reporting                        |

**Implementation Note**: While this requirements document uses English terminology, the actual implementation should localize based on tenant preferences:

- Database table names (e.g., `mutaties`) - remain as-is for backward compatibility
- Transaction number formats and descriptions - localized based on tenant's preferred language:
  - English: "OpeningBalance 2025", "Opening balance for year 2025 of Administration GoodwinSolutions"
  - Dutch: "Beginbalans 2025", "Beginbalans van het jaar 2025 van Administratie GoodwinSolutions"
- User-facing UI text (localized per tenant language preference)
- Legacy code references

The design document will specify the localization strategy and which terms should be configurable per tenant language settings.

Now we have some migration issues

1. In the current dataset there is no startring balance for each year. The balance values are calculated as the result from beginning to reporting date.
   1.1. The closure (result amount) is booked for all years in each year. So this should rise no problems.
2. All reports that report on the balance values needs to be adjusted to calculate the balance values within the year starting with the starting balance of the bespoke year
