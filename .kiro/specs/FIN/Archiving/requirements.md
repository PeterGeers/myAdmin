# Requirements Document

## Introduction

The Archiving feature enables long-term storage of financial transaction records in a read-only archive. After a fiscal year is closed, the previous year's transactions are moved to an archive table, removing them from the active `mutaties` table used by the Banking module's Transactions tab. Archived data remains fully accessible through `vw_mutaties` and all reporting views (P&L, balance sheets, tax declarations), preserving a seamless reporting experience. Tenants can restore archived years and request permanent deletion of records older than a configurable threshold.

## Glossary

- **Archive_Table**: A MySQL table (`mutaties_archive`) with the same schema as `mutaties`, storing archived transaction records in a read-only capacity
- **Active_Table**: The existing `mutaties` table containing current (non-archived) transaction records
- **Archive_Service**: The backend Python service responsible for executing archive, restore, and purge operations
- **Archive_API**: The set of Flask REST endpoints exposing archive operations to the frontend
- **Year_Closure_Status**: The existing `year_closure_status` table that tracks which fiscal years have been closed per tenant
- **Reporting_Views**: The set of database views (`vw_debetmutaties`, `vw_creditmutaties`, `vw_mutaties`) used by all financial reports
- **Banking_Transactions_Tab**: The React frontend tab in the Banking module that displays transactions from the Active_Table via `/api/banking/mutaties`
- **Archiving_Trigger_Year**: The most recent closed fiscal year minus one year (e.g., if 2025 is the most recently closed year, 2024 and earlier are eligible for archiving)
- **Tenant**: An administration (identified by the `administration` column) representing an isolated set of financial data
- **Purge**: Permanent, irreversible deletion of archived records for a specified year

## Requirements

### Requirement 1: Archive Table Structure

**User Story:** As a system administrator, I want archived transactions stored in a dedicated archive table with the same schema as the active transactions table, so that data integrity and query compatibility are preserved.

#### Acceptance Criteria

1. THE Archive_Table SHALL have the same column definitions, data types, and character sets as the Active_Table
2. THE Archive_Table SHALL include an `archived_at` DATETIME column recording when each record was archived
3. THE Archive_Table SHALL include an `archived_by` VARCHAR(255) column recording which user initiated the archive operation
4. THE Archive_Table SHALL preserve the original `ID` values from the Active_Table to enable traceability
5. THE Archive_Table SHALL enforce the same foreign key constraints on `Debet` and `Credit` columns referencing `rekeningschema` as the Active_Table

### Requirement 2: Archive Eligibility

**User Story:** As a tenant administrator, I want only transactions from fully closed fiscal years (excluding the most recent closed year) to be eligible for archiving, so that recent data remains readily available for year-end comparisons.

#### Acceptance Criteria

1. WHEN a tenant requests archiving, THE Archive_Service SHALL determine the Archiving_Trigger_Year by subtracting one year from the most recent closed year recorded in Year_Closure_Status for that Tenant
2. THE Archive_Service SHALL only archive transactions where the fiscal year of `TransactionDate` is less than or equal to the Archiving_Trigger_Year
3. IF no closed years exist in Year_Closure_Status for the Tenant, THEN THE Archive_Service SHALL reject the archive request and return a descriptive error message
4. IF only one closed year exists for the Tenant, THEN THE Archive_Service SHALL reject the archive request because no year qualifies as the Archiving_Trigger_Year

### Requirement 3: Archive Execution

**User Story:** As a tenant administrator, I want to archive eligible transactions for my tenant, so that the active transactions table stays lean and performant.

#### Acceptance Criteria

1. WHEN an archive operation is initiated, THE Archive_Service SHALL copy all eligible transactions from the Active_Table to the Archive_Table within a single database transaction
2. WHEN the copy to the Archive_Table succeeds, THE Archive_Service SHALL delete the copied records from the Active_Table within the same database transaction
3. IF any step of the archive operation fails, THEN THE Archive_Service SHALL roll back the entire database transaction and return a descriptive error message
4. THE Archive_Service SHALL record the archive operation in the audit log, including the Tenant, the archived year range, the number of records archived, and the user who initiated the operation
5. THE Archive_Service SHALL scope all archive operations to a single Tenant using the `administration` column
6. WHEN an archive operation completes, THE Archive_Service SHALL invalidate the mutaties cache for the affected Tenant

### Requirement 4: Post-Year-Closure Archiving

**User Story:** As a tenant administrator, I want the previous year's transactions to become archive-eligible after I close a fiscal year, so that archiving follows the natural year-end workflow.

#### Acceptance Criteria

1. WHEN a fiscal year is closed via the year-end closure process, THE Archive_API SHALL provide an endpoint to archive newly eligible years for the Tenant
2. THE Archive_Service SHALL NOT automatically archive transactions upon year closure; archiving SHALL require an explicit user action
3. WHEN a user requests archiving after year closure, THE Archive_Service SHALL recalculate the Archiving_Trigger_Year based on the updated Year_Closure_Status

### Requirement 5: Reporting View Compatibility

**User Story:** As a financial analyst, I want all reports (P&L, balance sheets, tax declarations) to include archived data seamlessly, so that historical reporting accuracy is maintained.

#### Acceptance Criteria

1. THE Reporting_Views SHALL query both the Active_Table and the Archive_Table using a UNION ALL approach
2. WHEN `vw_mutaties` is queried for reporting, THE Reporting_Views SHALL return archived records with the same column structure and data types as active records
3. THE Reporting_Views SHALL apply the same sign conventions (debet negative, credit positive) to archived records as to active records
4. WHEN a report filters by year, Tenant, or account, THE Reporting_Views SHALL apply the same filter to both active and archived data

### Requirement 6: Banking Transactions Tab Exclusion

**User Story:** As a bookkeeper, I want the Banking module's Transactions tab to show only active (non-archived) transactions, so that the working view remains focused on current data.

#### Acceptance Criteria

1. THE Banking_Transactions_Tab SHALL query only the Active_Table via the `/api/banking/mutaties` endpoint
2. THE Banking_Transactions_Tab SHALL NOT display any records from the Archive_Table
3. WHEN a year's transactions have been archived, THE Banking_Transactions_Tab SHALL no longer list those transactions in its results

### Requirement 7: Restore (Un-Archive) by Fiscal Year

**User Story:** As a tenant administrator, I want to restore archived transactions for a specific fiscal year back to the active table, so that I can make corrections or re-process data when needed.

#### Acceptance Criteria

1. WHEN a restore operation is requested for a specific fiscal year, THE Archive_Service SHALL copy all archived transactions for that year and Tenant from the Archive_Table back to the Active_Table within a single database transaction
2. WHEN the copy to the Active_Table succeeds, THE Archive_Service SHALL delete the restored records from the Archive_Table within the same database transaction
3. IF any step of the restore operation fails, THEN THE Archive_Service SHALL roll back the entire database transaction and return a descriptive error message
4. THE Archive_Service SHALL record the restore operation in the audit log, including the Tenant, the restored year, the number of records restored, and the user who initiated the operation
5. WHEN a restore operation completes, THE Archive_Service SHALL invalidate the mutaties cache for the affected Tenant

### Requirement 8: Purge Archived Records

**User Story:** As a tenant administrator, I want to permanently delete archived records older than a specified year, so that I can comply with data retention policies and reduce storage.

#### Acceptance Criteria

1. WHEN a purge request is submitted for a cutoff year, THE Archive_Service SHALL permanently delete all archived records for the Tenant where the fiscal year of `TransactionDate` is less than the specified cutoff year
2. THE Archive_Service SHALL require explicit confirmation from the user before executing a purge operation
3. IF the purge request targets records that are not in the Archive_Table, THEN THE Archive_Service SHALL reject the request and return a descriptive error message
4. THE Archive_Service SHALL record the purge operation in the audit log, including the Tenant, the cutoff year, the number of records purged, and the user who initiated the operation
5. THE Archive_Service SHALL NOT allow purging of records from the Active_Table; only archived records are eligible for purging

### Requirement 9: Archive Status and Visibility

**User Story:** As a tenant administrator, I want to see which fiscal years are archived, active, or purged for my tenant, so that I have a clear overview of my data lifecycle.

#### Acceptance Criteria

1. THE Archive_API SHALL provide an endpoint that returns the archive status per fiscal year for a given Tenant
2. WHEN the archive status is requested, THE Archive_API SHALL return each fiscal year with its status: `active`, `archived`, or `closed` (closed but not yet archived)
3. THE Archive_API SHALL include the record count per fiscal year in the status response
4. THE Archive_API SHALL include the `archived_at` timestamp and `archived_by` user for archived years

### Requirement 10: Multi-Tenant Data Isolation

**User Story:** As a system administrator, I want all archive operations to be strictly scoped to the requesting tenant, so that no tenant can access or modify another tenant's archived data.

#### Acceptance Criteria

1. THE Archive_Service SHALL filter all archive, restore, and purge operations by the `administration` column matching the authenticated Tenant
2. THE Archive_API SHALL validate that the authenticated user has access to the requested Tenant before executing any archive operation
3. IF a user attempts an archive operation on a Tenant they do not have access to, THEN THE Archive_API SHALL return an access denied error
4. THE Archive_Table SHALL use a single shared table with the `administration` column for tenant isolation, consistent with the Active_Table pattern

### Requirement 11: Archive API Authorization

**User Story:** As a system administrator, I want archive operations restricted to users with appropriate permissions, so that only authorized personnel can archive, restore, or purge data.

#### Acceptance Criteria

1. THE Archive_API SHALL require `finance_read` permission for viewing archive status
2. THE Archive_API SHALL require `finance_write` permission for executing archive, restore, and purge operations
3. IF a user lacks the required permission, THEN THE Archive_API SHALL return a 403 Forbidden response
