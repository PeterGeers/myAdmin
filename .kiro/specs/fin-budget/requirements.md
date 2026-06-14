# Requirements Document

## Introduction

Budget Management for the FIN module of myAdmin. This feature provides a category-based budget vs actuals system with version-based budget cycles. Users define budgets at the Ledger Account level with optional detail dimensions, choose monthly or annual entry granularity, and compare budgeted amounts against actual transactions from the Banking Processor. Budgets roll up through the existing account hierarchy (Account → SubParent → Parent) for multi-level overview dashboards.

## Glossary

- **Budget_System**: The budget management subsystem within the FIN module responsible for creating, storing, and comparing budget data against actuals
- **Budget_Version**: A named budget instance for a specific fiscal year with a status (Draft, Approved, or Revised) and an active flag for dashboard comparisons
- **Budget_Template**: A configuration that defines which Ledger Accounts to include in a budget, their period mode, detail dimension settings, and default annualization method
- **Budget_Line**: A single budget entry representing a planned amount for a specific Ledger Account, period, and optional detail dimension
- **Ledger_Account**: The lowest level in the account hierarchy (the `Account` field in chart_of_accounts), where budgets are entered
- **SubParent**: The group level in the account hierarchy, used for mid-level budget rollup views
- **Parent**: The top level in the account hierarchy, used for high-level budget overview
- **Detail_Dimension**: An optional secondary axis on a Budget Line, either a platform identifier or a ReferenceNumber, used to break down a Ledger Account budget further
- **Period_Mode**: The granularity of budget entry for a Budget Line — either Monthly (12 individual amounts) or Annual (one amount auto-divided by 12)
- **Active_Version**: The single Budget Version per fiscal year marked as active, against which the Dashboard compares actuals
- **Actuals**: Realized financial transaction amounts sourced from the `vw_mutaties` view, filtered by Ledger Account and period
- **Variance**: The difference between budgeted and actual amounts, expressed as over-budget (positive) or under-budget (negative)
- **Draft_Generation**: The process of pre-filling budget amounts from prior-period actuals using annualization logic
- **Annualization**: The calculation method applied when prior-year data is partial: actual total multiplied by 12 divided by months_available

## Requirements

### Requirement 1: Budget Version Management

**User Story:** As a financial administrator, I want to create and manage named budget versions per fiscal year, so that I can track budget evolution through Draft, Approved, and Revised stages.

#### Acceptance Criteria

1. WHEN a user creates a new Budget Version, THE Budget_System SHALL store the version with a user-provided name (1 to 100 characters), a fiscal year (4-digit year), and an initial status of Draft
2. IF a user attempts to create a Budget Version with a name that already exists for the same fiscal year and tenant, THEN THE Budget_System SHALL reject the creation and return an error message indicating the name is already in use
3. WHEN a user transitions a Budget Version from Draft to Approved, THE Budget_System SHALL update the status to Approved and record the transition timestamp
4. WHEN a user transitions a Budget Version from Approved to Revised, THE Budget_System SHALL create a copy of the Approved version with status Revised, including all associated budget line items, and preserve the original Approved version unchanged
5. IF a user attempts a status transition that does not follow the sequence Draft → Approved → Revised, THEN THE Budget_System SHALL reject the transition and return an error message indicating the current status and the allowed next status
6. WHEN a user marks a Budget Version that has a status of Approved or Revised as active, THE Budget_System SHALL set that version as the Active Version and deactivate any previously active version for the same fiscal year
7. IF a user attempts to mark a Budget Version with status Draft as active, THEN THE Budget_System SHALL reject the activation and return an error message indicating that only Approved or Revised versions may be activated
8. THE Budget_System SHALL allow at most one Active Version per fiscal year per tenant

### Requirement 2: Budget Template Definition

**User Story:** As a financial administrator, I want to define budget templates that specify which Ledger Accounts to include and how they should be budgeted, so that budget creation is consistent and repeatable.

#### Acceptance Criteria

1. WHEN a user creates a Budget Template, THE Budget_System SHALL store the template with a name (maximum 100 characters) and a list of at least one Ledger Account configuration
2. THE Budget_System SHALL store for each Ledger Account configuration: the account code, the Period Mode (Monthly or Annual), whether a Detail Dimension applies, and the default annualization method (equal-spread, being actual total multiplied by 12 divided by months with data)
3. WHEN a user selects Annual as Period Mode for a template line, THE Budget_System SHALL divide the entered annual amount equally across 12 months during budget generation, applying banker's rounding to each monthly amount
4. WHEN a user adds a Ledger Account with Detail Dimension enabled, THE Budget_System SHALL require specification of the dimension type (platform or ReferenceNumber)
5. IF a user references a Ledger Account code that does not exist in the tenant chart of accounts, THEN THE Budget_System SHALL reject the template entry and return a validation error
6. IF a user adds a Ledger Account code that already exists in the same Budget Template, THEN THE Budget_System SHALL reject the duplicate entry and return a validation error indicating the account is already configured
7. IF a user attempts to create a Budget Template with a name that already exists within the same tenant, THEN THE Budget_System SHALL reject the creation and return a validation error indicating the name is taken

### Requirement 3: Budget Line Entry

**User Story:** As a financial administrator, I want to enter budget amounts at the Ledger Account level with optional detail breakdowns, so that I have granular control over planned spending and revenue.

#### Acceptance Criteria

1. WHEN a user enters a Monthly budget line, THE Budget_System SHALL accept 12 individual monthly amounts for the specified Ledger Account and fiscal year
2. WHEN a user enters an Annual budget line, THE Budget_System SHALL accept one annual amount and store 12 equal monthly amounts (annual amount divided by 12), applying banker's rounding to each monthly amount
3. WHERE a Budget Line has a Detail Dimension configured, THE Budget_System SHALL associate the budget amounts with the specified platform or ReferenceNumber value
4. THE Budget_System SHALL validate that each Budget Line belongs to exactly one Budget Version
5. IF a user enters a budget amount with more than 2 decimal places, THEN THE Budget_System SHALL round the amount to 2 decimal places using banker's rounding
6. IF a user attempts to create a Budget Line for a Ledger Account and Detail Dimension combination that already exists within the same Budget Version, THEN THE Budget_System SHALL reject the entry and return a validation error indicating a duplicate exists

### Requirement 4: Draft Generation from Prior-Period Actuals

**User Story:** As a financial administrator, I want to generate a draft budget pre-filled from prior-year actuals, so that I have a realistic starting point without manual data entry.

#### Acceptance Criteria

1. WHEN a user triggers draft generation for a fiscal year with 12 months of prior-year actuals available, THE Budget_System SHALL pre-fill each template Ledger Account with the corresponding prior-year actual monthly amounts
2. WHEN a user triggers draft generation for a fiscal year with fewer than 12 months of prior-year actuals available, THE Budget_System SHALL annualize by multiplying the total actual amount by 12 divided by the number of months with data, then distribute equally across 12 months applying banker's rounding
3. WHEN a user triggers draft generation, THE Budget_System SHALL use the specified Budget Template to determine which accounts to include and their configurations
4. THE Budget_System SHALL create the generated budget lines within a new Budget Version with status Draft and a user-provided name
5. IF no prior-year actuals exist for a template Ledger Account, THEN THE Budget_System SHALL create the budget line with zero amounts for all 12 months
6. WHEN a template Ledger Account has a Detail Dimension configured and prior-year actuals contain multiple dimension values (e.g., multiple platforms), THE Budget_System SHALL create separate budget lines for each dimension value found in the actuals

### Requirement 5: Copy Budget from Previous Year

**User Story:** As a financial administrator, I want to copy an existing budget version from a previous year as a starting point for the new year, so that I can reuse past budget structures without regenerating from actuals.

#### Acceptance Criteria

1. WHEN a user copies a Budget Version from a prior fiscal year, THE Budget_System SHALL create a new Budget Version with the user-provided name, status Draft, and all budget lines from the source version including their Detail Dimension associations (platform or ReferenceNumber)
2. WHEN copying, THE Budget_System SHALL update the fiscal year on the new version to the target year while preserving all 12 monthly amounts and Period Mode settings from the source budget lines
3. IF the source Budget Version contains Ledger Accounts that no longer exist in the tenant chart of accounts, THEN THE Budget_System SHALL exclude those lines from the new version and return a warning listing each excluded Ledger Account code
4. IF the user specifies a target fiscal year that is the same as or earlier than the source version fiscal year, THEN THE Budget_System SHALL reject the copy operation and return a validation error indicating the target year must be later than the source year

### Requirement 6: Budget vs Actuals Dashboard

**User Story:** As a financial administrator, I want to view a dashboard comparing budgeted amounts against actual transactions, so that I can monitor spending and revenue performance in real time.

#### Acceptance Criteria

1. THE Budget_System SHALL compare actuals against the Active Version for the selected fiscal year
2. WHEN displaying the dashboard at Parent level, THE Budget_System SHALL show aggregated budget and actual totals for each Parent account with the calculated Variance
3. WHEN a user selects a Parent account, THE Budget_System SHALL drill down to SubParent level showing aggregated budget and actual totals for each SubParent within that Parent
4. WHEN a user selects a SubParent account, THE Budget_System SHALL drill down to Ledger Account level showing individual budget and actual amounts for each Account within that SubParent
5. THE Budget_System SHALL calculate Variance as actual amount minus budgeted amount, where positive values indicate over-budget (spending exceeded plan) and negative values indicate under-budget (spending below plan)
6. WHEN a user applies a ReferenceNumber filter, THE Budget_System SHALL filter both budget and actual amounts by the specified ReferenceNumber, showing zero for budget or actuals where no matching data exists
7. THE Budget_System SHALL support period selection for dashboard comparison: individual month (1–12), individual quarter (Q1–Q4), year-to-date (month 1 through the current calendar month), or full year (all 12 months)
8. IF no Active Version exists for the selected fiscal year, THEN THE Budget_System SHALL display the dashboard with zero budget amounts and a notification indicating no active budget version is available
9. THE Budget_System SHALL display all monetary amounts rounded to 2 decimal places

### Requirement 7: Multi-Level Hierarchy Rollup

**User Story:** As a financial administrator, I want budget amounts to automatically roll up through the account hierarchy, so that I can see budget summaries at any level without manual aggregation.

#### Acceptance Criteria

1. THE Budget_System SHALL compute SubParent budget totals by summing all Budget Line amounts for Ledger Accounts that share the same SubParent code, grouped by fiscal year, Budget Version, and month
2. THE Budget_System SHALL compute Parent budget totals by summing all SubParent budget totals that share the same Parent code, grouped by fiscal year, Budget Version, and month
3. WHEN a Budget Line amount is modified, THE Budget_System SHALL reflect the change in the corresponding SubParent and Parent rollup totals on the next query without manual recalculation
4. THE Budget_System SHALL compute rollup totals at query time using the current account hierarchy from the chart of accounts, so that hierarchy reassignments are immediately reflected in rollup results
5. IF a Ledger Account referenced by a Budget Line has no SubParent assigned in the chart of accounts, THEN THE Budget_System SHALL exclude that Budget Line from hierarchy rollup totals and include it in an "Unassigned" category visible at the Parent level
6. THE Budget_System SHALL compute rollup totals with 2 decimal places precision, applying banker's rounding to the final summed result

### Requirement 9: AI-Powered Budget Narrative

**User Story:** As a financial administrator, I want the system to generate a concise executive summary of my budget vs actuals dashboard, so that I can quickly communicate financial performance to stakeholders without writing reports manually.

#### Acceptance Criteria

1. WHEN a user requests a budget narrative from the dashboard view, THE Budget_System SHALL send the current dashboard data (budget totals, actual totals, variances, period, and hierarchy level) to the OpenRouter AI service and return a generated summary text
2. THE Budget_System SHALL limit the AI prompt payload to the aggregated dashboard rows (maximum 50 rows of code, name, budget, actual, variance) and period context, never sending raw transaction data
3. THE Budget_System SHALL use the project's model fallback chain (free models first, then cheap, then paid) to minimize cost per narrative generation
4. IF the OpenRouter API is unavailable or all models fail, THEN THE Budget_System SHALL return a structured error response indicating AI service unavailability without disrupting dashboard functionality
5. THE Budget_System SHALL generate narratives in Dutch by default, matching the tenant's financial reporting language
6. THE Budget_System SHALL complete narrative generation within 15 seconds; if the AI service exceeds this timeout, the system SHALL return a timeout error

### Requirement 10: AI-Powered Natural Language Budget Queries

**User Story:** As a financial administrator, I want to ask questions about my budget in natural language, so that I can quickly find specific budget insights without manually configuring filters.

#### Acceptance Criteria

1. WHEN a user submits a natural language query (e.g., "Which accounts are more than 20% over budget this quarter?"), THE Budget_System SHALL translate the query into dashboard API parameters (level, period, reference_number, parent_code, subparent_code) and return the filtered results
2. THE Budget_System SHALL validate that the AI-translated parameters are within the allowed set of dashboard query parameters before executing the query, rejecting any parameters that do not match the dashboard API schema
3. THE Budget_System SHALL include the tenant's account hierarchy names and the current fiscal year as context in the AI prompt so that account references in the natural language query can be resolved
4. IF the AI service cannot parse the query into valid parameters, THEN THE Budget_System SHALL return a user-friendly message suggesting how to rephrase the question
5. THE Budget_System SHALL enforce the same tenant isolation and authentication on the resulting dashboard query as on a manually constructed query

### Requirement 11: AI-Powered Smart Draft Adjustment Suggestions

**User Story:** As a financial administrator, I want the system to suggest adjustments to a draft budget based on contextual notes I provide, so that I can quickly incorporate known changes without recalculating every line manually.

#### Acceptance Criteria

1. WHEN a user requests adjustment suggestions for a Draft budget version, THE Budget_System SHALL send the current budget line amounts and any user-provided context notes (e.g., "rent increases 5% in June", "dropped platform X") to the AI service
2. THE Budget_System SHALL return suggestions as a list of proposed changes, each containing: the account code, the affected months, the suggested new amounts, and a brief explanation of the reasoning
3. THE Budget_System SHALL NOT automatically apply AI suggestions; each suggestion must be explicitly confirmed by the user before modifying budget lines
4. THE Budget_System SHALL limit the AI payload to a maximum of 100 budget lines per request; if the version contains more lines, the user must select a subset (by parent or subparent) for analysis
5. IF the AI service returns suggestions that reference account codes not present in the budget version, THEN THE Budget_System SHALL filter those suggestions out before presenting results to the user

### Requirement 12: AI-Powered Template Recommendations

**User Story:** As a financial administrator, I want the system to recommend which accounts to include in a new budget template, so that I can create comprehensive templates without manually reviewing the entire chart of accounts.

#### Acceptance Criteria

1. WHEN a user requests template recommendations, THE Budget_System SHALL analyze the tenant's chart of accounts and prior-year actuals to suggest a list of Ledger Accounts for inclusion in a new template
2. THE Budget_System SHALL rank recommendations based on: accounts with significant prior-year activity (non-zero actuals), accounts commonly grouped together at the SubParent level, and accounts that appeared in existing templates for the same tenant
3. THE Budget_System SHALL return each recommendation with: account code, account name, suggested period mode (Monthly or Annual), whether a detail dimension is recommended, and a confidence indicator (high, medium, low)
4. THE Budget_System SHALL NOT automatically create templates; recommendations are presented for the user to accept, modify, or reject before template creation
5. IF no prior-year actuals or existing templates are available, THEN THE Budget_System SHALL fall back to recommending all active accounts from the chart of accounts with a "low" confidence indicator

### Requirement 8: Tenant Isolation

**User Story:** As a system administrator, I want budget data to be isolated per tenant, so that each tenant sees only their own budget information.

#### Acceptance Criteria

1. THE Budget_System SHALL associate every Budget Version, Budget Template, and Budget Line with a specific tenant administration
2. THE Budget_System SHALL include a tenant administration filter on every read, update, and delete operation against Budget Versions, Budget Templates, and Budget Lines
3. WHEN a user creates or imports budget data (including draft generation and copy operations), THE Budget_System SHALL associate the resulting records with the authenticated user's current tenant administration
4. IF a user attempts to read, modify, or delete budget data belonging to a different tenant, THEN THE Budget_System SHALL deny the operation and return an HTTP 403 response with an error message indicating access is not permitted
5. IF a copy or draft generation operation references a source Budget Version, THEN THE Budget_System SHALL verify the source belongs to the authenticated tenant administration before proceeding
