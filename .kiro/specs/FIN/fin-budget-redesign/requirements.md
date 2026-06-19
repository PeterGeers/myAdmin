# Requirements: Budget Module Redesign

## Introduction

Simplification of the Budget module. The current implementation is over-engineered with 4 tables, 4 pages, and complex template machinery. The redesign reduces this to 2 tables, 2 concerns (preparation + dashboard), and a straightforward single-page workflow.

## Glossary

- **Budget_Version**: A named budget for a specific fiscal year with status (Draft, Approved, Revised) and an active flag
- **Budget_Line**: A budget entry for a Ledger Account with 12 monthly amounts and optional dimension breakdown
- **Active_Version**: Any Approved or Revised version marked as active — multiple can coexist
- **Actuals**: Realized amounts from `vw_mutaties`
- **Variance**: actual minus budget

## Requirements

### Requirement 1: Budget Preparation (Single Page)

**User Story:** As a financial administrator, I want a single page where I can create budget versions and manage their lines, so that budget preparation is straightforward without navigating multiple tabs.

#### Acceptance Criteria

1. WHEN the user opens Budget Preparation, THE system SHALL show a dropdown of all budget versions (all years, all statuses) and a "New Version" button
2. WHEN the user selects a version, THE system SHALL display its budget lines in a table showing: account code, account name, dimension, period mode, monthly totals, and line total
3. WHEN the user clicks a budget line row, THE system SHALL open an edit modal with 12 monthly amount fields (or 1 annual field when period mode is Annual)
4. WHEN the user clicks "Add Line", THE system SHALL open a modal to select an account code, period mode, optional dimension, and enter amounts
5. WHEN the user clicks "New Version", THE system SHALL open a modal with: name, fiscal year, and creation method (Empty / Copy from existing / AI draft)
6. WHEN "Copy from existing" is selected, THE system SHALL show a version selector and copy all lines from that version into the new Draft version
7. WHEN "AI draft" is selected, THE system SHALL allow the user to provide context notes, call AI to generate proposed lines, and show them for review before saving
8. THE system SHALL allow editing budget lines only on Draft versions; Approved and Revised versions are read-only
9. THE system SHALL allow deleting budget lines and deleting Draft versions
10. THE system SHALL allow status transitions: Draft → Approved, Approved → Revised (creates editable copy)

#### Permissions

- **Finance_CRUD**: full access (create, edit, delete versions and lines, status transitions)
- **Finance_Read**: view versions and lines (read-only)

### Requirement 2: Budget Dashboard (FIN Reports Tab)

**User Story:** As a financial administrator, I want to compare any active budget against actuals in the FIN Reports section, so that I can monitor financial performance without a separate budget module.

#### Acceptance Criteria

1. THE system SHALL add a "Budget vs Actuals" tab to the existing FIN Reports group (FinancialReportsGroup)
2. THE system SHALL show a dropdown of all active budget versions (any year); the selected version determines the fiscal year for actuals
3. WHEN the user selects an active version, THE system SHALL fetch actuals for that version's fiscal year and display budget vs actuals with variance
4. THE system SHALL support drill-down: Parent → SubParent → Account level with breadcrumb navigation
5. THE system SHALL support period selection: individual month, quarter, YTD, or full year
6. THE system SHALL NOT show a separate year selector — the year is implied by the selected budget version
7. IF no active versions exist, THE system SHALL show a notification explaining no budget is available for comparison
8. THE system SHALL display variance with color coding: green (under-budget), red (over-budget)

#### Permissions

- **Finance_Read** or **Finance_CRUD**: can view the dashboard
- **Finance_Export**: can export dashboard data

### Requirement 3: Multiple Active Budgets

**User Story:** As a financial administrator, I want multiple budget versions to be active simultaneously, so that I can compare different scenarios or years in the dashboard.

#### Acceptance Criteria

1. WHEN the user activates a version, THE system SHALL set `is_active = TRUE` without deactivating other versions
2. WHEN the user deactivates a version, THE system SHALL set `is_active = FALSE`
3. THE system SHALL only allow activating versions with status Approved or Revised
4. THE dashboard version dropdown SHALL show all versions where `is_active = TRUE`

### Requirement 4: Database Simplification

**User Story:** As a developer, I want the budget module to use only the tables it needs, so that the codebase is maintainable.

#### Acceptance Criteria

1. THE system SHALL use only `budget_versions` and `budget_lines` tables
2. THE system SHALL drop the `budget_templates` and `budget_template_lines` tables
3. THE system SHALL remove all template-related backend routes and service methods
4. THE system SHALL remove the `generate-draft` endpoint (replaced by AI draft in version creation)

### Requirement 5: AI Draft Generation (Simplified)

**User Story:** As a financial administrator, I want AI to propose budget lines when creating a new version, so that I have a data-driven starting point.

#### Acceptance Criteria

1. WHEN the user selects "AI draft" during version creation, THE system SHALL send the chart of accounts and prior-year actuals summary to AI
2. THE AI SHALL return proposed budget lines with: account code, period mode, 12 monthly amounts, and reasoning
3. THE system SHALL display proposed lines in a review table where the user can accept, modify, or remove individual lines before saving
4. THE system SHALL NOT auto-save AI proposals — the user must explicitly confirm
5. THE system SHALL retain the existing AI draft-suggestions feature for adjusting lines on an existing Draft version

### Requirement 6: Tenant Isolation (Unchanged)

All existing tenant isolation patterns remain: `administration` column on all tables, filtered on every query.

### Out of Scope

- Template recommendation AI (removed with templates)
- Budget template CRUD (removed)
- Single-active-per-year enforcement (replaced by multi-active)
- Year selector in dashboard (year implied by version)
