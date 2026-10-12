# Requirements Document

## Introduction

This feature delivers a two-part transactions CSV export fix for the multi-tenant Flask/MySQL + React (Chakra UI) finance admin application.

Part (a) adds a CSV export control to the Transactions table view (`BankingMutatiesTab`), exporting the current filtered and sorted set of transaction rows. Part (b) guarantees and verifies that the FIN Report transactions CSV export (`MutatiesReport`) maps the Debit column to the account code and the Credit column to the account name, end-to-end from the database view through the API to the generated CSV.

Both parts reuse the shared CSV utilities, preserve existing tenant isolation, use i18n translation keys for all user-facing strings, and produce RFC-4180-compliant CSV output suitable for re-import. The change is intended to be a small, low-risk, frontend-focused fix deployed to `main`.

## Glossary

- **Transactions_Export**: The combined capability covering the table-view export (Part a) and the report export (Part b).
- **Table_Export**: The CSV export control and behavior added to the Transactions table view component (`BankingMutatiesTab.tsx`).
- **Report_Export**: The CSV export behavior of the FIN Report transactions component (`MutatiesReport.tsx`).
- **Processed_Data**: The full filtered-and-sorted dataset produced by the Table Filter Framework v2 (`useFilterableTable` `processedData`), before any display-limit slice is applied.
- **Display_Data**: The locally display-limit-sliced subset of Processed_Data used only for on-screen rendering (`displayedData`).
- **CSV_Utility**: The shared CSV module at `frontend/src/utils/csvExport.ts` (`generateCsv`, `generateCsvFromObjects`, `downloadCsv`), which performs RFC-4180 escaping and adds a UTF-8 BOM via `downloadCsv`.
- **Transaction_Row**: A transaction record with fields ID, row_id, TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration.
- **Mutaties_View**: The MySQL view `vw_mutaties`, where `Reknum` is the account code (joined ON `Reknum = r.Account`) and `AccountName` is the account name.
- **Account_Code**: The account code value, equal to `vw_mutaties.Reknum`.
- **Account_Name**: The account name value, equal to `vw_mutaties.AccountName`.
- **Tenant_Scope**: The server-enforced tenant isolation (`@tenant_required`, administration filtering) that restricts loaded rows to the current tenant and filters.

## Requirements

### Requirement 1: Table export control

**User Story:** As a finance administrator, I want an export control on the Transactions table view, so that I can download the transactions I am currently viewing as a CSV file.

#### Acceptance Criteria

1. THE Table_Export SHALL present an export control on the Transactions table view.
2. THE Table_Export SHALL position and style the export control consistently with the existing "Add new record" control on the same table.
3. THE Table_Export SHALL label the export control using a react-i18next translation key in the `banking` namespace.
4. THE Table_Export SHALL render the export control without adding row-selection checkboxes to the table.

### Requirement 2: Export the filtered and sorted view

**User Story:** As a finance administrator, I want the table export to reflect exactly what my filters and sorting produced, so that the downloaded file matches the view I curated.

#### Acceptance Criteria

1. WHEN the export control is activated, THE Table_Export SHALL generate a CSV from Processed_Data.
2. THE Table_Export SHALL include every row of Processed_Data in the generated CSV without applying the display-limit slice used for Display_Data.
3. THE Table_Export SHALL order the CSV rows to match the current sort order of Processed_Data.
4. THE Table_Export SHALL export the raw underlying field values of each Transaction_Row rather than locale-formatted display strings.

### Requirement 3: Table export columns and labels

**User Story:** As a finance administrator, I want the table export columns to match the on-screen column labels, so that the CSV is easy to read and re-import.

#### Acceptance Criteria

1. THE Table_Export SHALL emit CSV header labels corresponding to the Transaction_Row columns using the UI labels Trx Number, Date, Description, Amount, Debit, Credit, Reference, and Administration.
2. THE Table_Export SHALL source the CSV header labels from react-i18next translation keys in the `banking` namespace.
3. THE Table_Export SHALL map each exported column to its corresponding Transaction_Row field (TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit, ReferenceNumber, and Administration).

### Requirement 4: Shared CSV utility and encoding

**User Story:** As a developer, I want both exports to use the shared CSV utility, so that escaping and encoding behavior stays correct and consistent.

#### Acceptance Criteria

1. THE Table_Export SHALL produce CSV output using the CSV_Utility rather than a hand-rolled CSV builder.
2. WHERE a field value contains a comma, a double quote, or a newline, THE CSV_Utility SHALL escape that value per RFC 4180.
3. WHEN a CSV file is downloaded, THE CSV_Utility SHALL prepend a UTF-8 byte-order mark and use the `text/csv` content type.

### Requirement 5: Report export Debit/Credit mapping

**User Story:** As a finance administrator, I want the report transactions export to show the account code in the Debit column and the account name in the Credit column, so that the exported ledger data is correct.

#### Acceptance Criteria

1. THE Report_Export SHALL set the Debit column of each exported row to the Account_Code value (`vw_mutaties.Reknum`).
2. THE Report_Export SHALL set the Credit column of each exported row to the Account_Name value (`vw_mutaties.AccountName`).
3. THE Report_Export SHALL emit the CSV header columns in the order Date, Reference, Description, Amount, Debit, Credit, Administration using react-i18next translation keys in the `reports` namespace.
4. WHEN the Report_Export CSV is generated, THE Report_Export SHALL export the raw underlying field values rather than locale-formatted display strings.

### Requirement 6: End-to-end mapping verification

**User Story:** As a developer, I want the Debit-to-code and Credit-to-name mapping verified end-to-end, so that the contract holds from the database through the API to the CSV.

#### Acceptance Criteria

1. THE Report_Export SHALL preserve the backend `/api/reports/mutaties-table` SELECT so that the response includes the `Reknum` and `AccountName` fields from Mutaties_View.
2. THE Report_Export SHALL include a unit test asserting that the row-to-CSV mapping sets the Debit column to Account_Code and the Credit column to Account_Name.
3. IF investigation reveals that the deployed Debit or Credit column does not equal Account_Code or Account_Name respectively, THEN THE Report_Export SHALL correct the mapping to satisfy that contract.

### Requirement 7: Tenant-scope preservation

**User Story:** As a finance administrator, I want exports to respect tenant boundaries, so that I never export data from another tenant.

#### Acceptance Criteria

1. THE Transactions_Export SHALL export only the rows already loaded under the current Tenant_Scope and active filters.
2. THE Transactions_Export SHALL rely on the existing server-side tenant isolation without weakening the Tenant_Scope.

### Requirement 8: Preserve existing report output

**User Story:** As a finance administrator, I want report export changes to keep working as before, so that standardizing the implementation does not alter the output I rely on.

#### Acceptance Criteria

1. WHERE the Report_Export is standardized onto the CSV_Utility, THE Report_Export SHALL preserve the existing CSV header labels and column order.
2. WHERE the Report_Export is standardized onto the CSV_Utility, THE Report_Export SHALL preserve the UTF-8 byte-order mark that enables correct display in spreadsheet applications.
