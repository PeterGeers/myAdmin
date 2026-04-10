# Requirements Document

## Introduction

The current FIN Reports "Actuals" tab combines Balance (VW=N) and Profit & Loss (VW=Y) data in a single page, causing confusion for users. This feature splits the Actuals tab into two dedicated pages: Balance and P&L. Additionally, it addresses issues with multi-year balance summarization after year-end closing, improves the P&L table with reference number expansion and alternative column layouts, splits the P&L histogram into separate profit/loss graphs, improves responsive layout behavior, and clarifies cache refresh behavior.

## Glossary

- **Balance_Page**: The new dedicated page for displaying balance sheet data (accounts where VW=N in the vw_mutaties view)
- **PL_Page**: The new dedicated page for displaying Profit & Loss data (accounts where VW=Y in the vw_mutaties view)
- **Actuals_Tab**: The current single tab in FinancialReportsGroup that combines both Balance and P&L data (to be replaced)
- **VW_Flag**: The "VW" column in the vw_mutaties database view. "N" indicates balance accounts, "Y" indicates profit/loss accounts
- **Year_End_Closure**: The process of closing a fiscal year, which creates opening balance transactions for the next year. Tracked in the year_closure_status table
- **Opening_Balance**: The balance carried forward from a closed year into the next year as opening transactions
- **Parent_Account**: A grouping category for ledger accounts identified by number range (e.g., 1000 = Assets, 2000 = Liabilities, 4000 = Costs/Expenses, 8000 = Revenue/Income). Used for hierarchical display and for splitting P&L charts into profit (8000-range) and loss (4000-range)
- **Ledger_Account**: An individual account identified by Reknum and AccountName within a Parent_Account group
- **Drill_Down_Level**: The time granularity for P&L data display: year, quarter, or month
- **Display_Format**: The number formatting option for amounts: 2 decimals, whole numbers, thousands (K), or millions (M)
- **MutatiesCache**: The backend in-memory cache (mutaties_cache.py) that stores financial transaction data with a configurable TTL
- **FinancialReportsGroup**: The React component that renders the FIN Reports tab structure using Chakra UI Tabs

## Requirements

### Requirement 1: Split Actuals Tab into Balance and P&L Tabs

**User Story:** As a financial administrator, I want separate Balance and P&L pages in the FIN Reports section, so that I can focus on one type of financial data at a time without confusion.

#### Acceptance Criteria

1. WHEN the user navigates to FIN Reports, THE FinancialReportsGroup SHALL display a "Balance" tab and a "P&L" tab instead of the single "Actuals" tab
2. WHEN the user selects the Balance tab, THE Balance_Page SHALL display only balance account data (VW_Flag = N)
3. WHEN the user selects the P&L tab, THE PL_Page SHALL display only profit and loss account data (VW_Flag = Y)
4. THE Balance_Page SHALL include a year filter, display format selector, and an Update Data button
5. THE PL_Page SHALL include a year filter, display format selector, drill-down level selector (year/quarter/month), and an Update Data button
6. WHEN the user changes the year filter or display format on either tab, THE FinancialReportsGroup SHALL apply the same filter values to both the Balance and P&L tabs

### Requirement 2: Balance Page — Year-Column Table with Year-End Closure Awareness

**User Story:** As a financial administrator, I want the Balance page to show balance values per year in separate columns, so that I can compare balances across years without incorrect cross-year summarization.

#### Acceptance Criteria

1. WHEN multiple years are selected, THE Balance_Page SHALL display a table with one column per selected year and the balance value for each year in its respective column
2. WHEN a year has been closed (recorded in year_closure_status), THE Balance_Page SHALL display the balance for that year using only transactions within that year (excluding opening balances from prior years that are already reflected in the closing)
3. WHEN a year has not been closed, THE Balance_Page SHALL display the cumulative balance from the start of records up to and including that year
4. THE Balance_Page SHALL visually indicate which years are closed and which are open (e.g., with an icon or label in the column header)
5. THE Balance_Page SHALL support expanding Parent_Account rows to show individual Ledger_Account amounts per year
6. THE Balance_Page SHALL display a grand total row at the bottom with the sum per year column

### Requirement 3: P&L Page — Enhanced Table with Reference Number Expansion

**User Story:** As a financial administrator, I want the P&L table to show reference numbers when expanding accounts and limit columns to years only, so that I can trace amounts back to specific transactions.

#### Acceptance Criteria

1. THE PL_Page SHALL display a hierarchical table with Parent_Account rows that expand to show Ledger_Account rows
2. WHEN a Ledger_Account row is expanded, THE PL_Page SHALL show individual transaction rows including the reference number (ReferenceNumber field)
3. THE PL_Page SHALL limit the default column headers to year values only (not quarter or month) in the primary table view
4. WHEN the drill-down level is changed to quarter or month, THE PL_Page SHALL update the column headers accordingly
5. THE PL_Page SHALL display a grand total row at the bottom with the sum per time-period column

### Requirement 4: P&L Page — Alternative Pivot Table View

**User Story:** As a financial administrator, I want an alternative table view with years/expansion in columns and accounts in the header, so that I can analyze P&L data from a different perspective.

#### Acceptance Criteria

1. THE PL_Page SHALL provide a toggle or tab to switch between the standard hierarchical view and the pivot table view
2. WHEN the pivot view is active, THE PL_Page SHALL display Parent_Account and Ledger_Account as row headers, with year and expansion period as column headers
3. WHEN the user switches between standard and pivot views, THE PL_Page SHALL preserve the selected filters and data
4. THE PL_Page pivot view SHALL support the same display format options as the standard view

### Requirement 5: P&L Histogram — Split Profit and Loss Graphs

**User Story:** As a financial administrator, I want the P&L distribution histogram split into separate profit and loss graphs, so that each graph uses its vertical space efficiently without large blank areas.

#### Acceptance Criteria

1. THE PL_Page SHALL display two separate bar charts: one for revenue accounts (8000-range Parent_Account) and one for cost accounts (4000-range Parent_Account)
2. WHEN profit data is available, THE PL_Page SHALL render the profit chart with its own Y-axis scale optimized for profit values
3. WHEN loss data is available, THE PL_Page SHALL render the loss chart with its own Y-axis scale optimized for loss values
4. THE PL_Page profit and loss charts SHALL each support year comparison with color-coded bars per selected year
5. THE PL_Page charts SHALL respond to the expand/collapse state of Parent_Account rows, showing ledger-level detail when a parent is expanded

### Requirement 6: Responsive Layout — Graphs Below Tables at All Window Sizes

**User Story:** As a user, I want graphs to reflow below their associated tables when the window width decreases, so that the layout remains usable at all screen sizes, not only on mobile.

#### Acceptance Criteria

1. WHEN the browser window width is reduced below the "lg" breakpoint, THE Balance_Page SHALL reflow the pie chart below the balance table instead of beside it
2. WHEN the browser window width is reduced below the "lg" breakpoint, THE PL_Page SHALL reflow the bar charts below the P&L table instead of beside it
3. THE Balance_Page and PL_Page SHALL use Chakra UI responsive breakpoints consistently so that the reflow behavior is identical across both pages

### Requirement 7: Cache Refresh Behavior

**User Story:** As a financial administrator, I want the Update Data button to clearly refresh the cached data, so that I see the latest transactions after imports or edits.

#### Acceptance Criteria

1. WHEN the user clicks the Update Data button on the Balance_Page, THE Balance_Page SHALL invalidate the MutatiesCache and fetch fresh data from the database
2. WHEN the user clicks the Update Data button on the PL_Page, THE PL_Page SHALL invalidate the MutatiesCache and fetch fresh data from the database
3. WHILE the cache is being refreshed, THE Balance_Page or PL_Page SHALL display a loading indicator on the Update Data button
4. WHEN the cache refresh completes, THE Balance_Page or PL_Page SHALL display the updated data and show a brief confirmation message indicating data was refreshed
