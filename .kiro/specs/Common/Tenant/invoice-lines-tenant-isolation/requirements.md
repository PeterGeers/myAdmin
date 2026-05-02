# Requirements Document

## Introduction

The myAdmin multitenant architecture requires every tenant-scoped table to have a direct `administration` column for defense-in-depth tenant isolation (REQ13 from the Multitenant spec). Two child tables created during the ZZP invoicing spec — `invoice_lines` and `contact_emails` — were created without this column, relying on JOINs through their parent tables (`invoices` and `contacts` respectively) for tenant filtering. This creates a gap in the defense-in-depth strategy: queries against these child tables either require expensive JOINs for tenant filtering or risk cross-tenant data leakage if the JOIN is accidentally omitted.

This feature adds the `administration` column to both child tables, migrates existing data from parent tables, updates all backend queries to use direct tenant filtering, and updates the `vw_invoice_vat_summary` view to include tenant context.

## Glossary

- **Administration**: The tenant identifier column used across all myAdmin tables. VARCHAR(50), lowercase. Equivalent to "tenant" in generic multitenant terminology.
- **Invoice_Lines_Table**: The `invoice_lines` database table storing line items per invoice.
- **Contact_Emails_Table**: The `contact_emails` database table storing email addresses per contact.
- **Invoices_Table**: The `invoices` parent table that currently provides tenant context for invoice lines via JOIN.
- **Contacts_Table**: The `contacts` parent table that currently provides tenant context for contact emails via JOIN.
- **VAT_Summary_View**: The `vw_invoice_vat_summary` database view that aggregates VAT breakdown per rate per invoice from invoice lines.
- **Migration_Script**: A SQL script that adds the `administration` column and backfills existing rows from parent tables.
- **ZZPInvoiceService**: The backend service class handling invoice CRUD, line calculations, and send flow.
- **ContactService**: The backend service class handling contact CRUD and email management.
- **ProductService**: The backend service class handling product CRUD, which queries invoice_lines for in-use checks.
- **Direct_Tenant_Filter**: A WHERE clause filtering by `administration = %s` directly on the table being queried, without requiring a JOIN to a parent table.

## Requirements

### Requirement 1: Add administration column to invoice_lines

**User Story:** As a system administrator, I want the `invoice_lines` table to have its own `administration` column, so that tenant isolation can be enforced directly without JOINs to the parent invoices table.

#### Acceptance Criteria

1. THE Migration_Script SHALL add a `administration` column of type VARCHAR(50) to the Invoice_Lines_Table
2. THE Migration_Script SHALL populate the `administration` column for all existing rows by reading the value from the corresponding row in the Invoices_Table via the `invoice_id` foreign key
3. WHEN the migration completes, THE Invoice_Lines_Table SHALL have zero rows where `administration` is NULL
4. THE Migration_Script SHALL add an index `idx_administration` on the `administration` column of the Invoice_Lines_Table
5. THE Migration_Script SHALL add a composite index `idx_admin_invoice` on `(administration, invoice_id)` on the Invoice_Lines_Table

### Requirement 2: Add administration column to contact_emails

**User Story:** As a system administrator, I want the `contact_emails` table to have its own `administration` column, so that tenant isolation can be enforced directly without JOINs to the parent contacts table.

#### Acceptance Criteria

1. THE Migration_Script SHALL add a `administration` column of type VARCHAR(50) to the Contact_Emails_Table
2. THE Migration_Script SHALL populate the `administration` column for all existing rows by reading the value from the corresponding row in the Contacts_Table via the `contact_id` foreign key
3. WHEN the migration completes, THE Contact_Emails_Table SHALL have zero rows where `administration` is NULL
4. THE Migration_Script SHALL add an index `idx_administration` on the `administration` column of the Contact_Emails_Table

### Requirement 3: Update invoice_lines queries to use direct tenant filtering

**User Story:** As a developer, I want all queries against `invoice_lines` to filter by `administration` directly, so that tenant isolation does not depend on JOINs to the invoices table.

#### Acceptance Criteria

1. WHEN the ZZPInvoiceService inserts a new invoice line, THE ZZPInvoiceService SHALL include the `administration` value in the INSERT statement
2. WHEN the ZZPInvoiceService selects invoice lines for a given invoice, THE ZZPInvoiceService SHALL include `administration = %s` in the WHERE clause
3. WHEN the ZZPInvoiceService deletes invoice lines during an update, THE ZZPInvoiceService SHALL include `administration = %s` in the DELETE WHERE clause
4. WHEN the ProductService checks whether a product is in use, THE ProductService SHALL filter `invoice_lines` by `administration = %s` directly instead of JOINing through the Invoices_Table
5. WHEN the ZZPInvoiceService reads invoice lines for copy-last functionality, THE ZZPInvoiceService SHALL include `administration = %s` in the WHERE clause

### Requirement 4: Update contact_emails queries to use direct tenant filtering

**User Story:** As a developer, I want all queries against `contact_emails` to filter by `administration` directly, so that tenant isolation does not depend on JOINs to the contacts table.

#### Acceptance Criteria

1. WHEN the ContactService inserts a new contact email, THE ContactService SHALL include the `administration` value in the INSERT statement
2. WHEN the ContactService selects emails for a contact, THE ContactService SHALL include `administration = %s` in the WHERE clause
3. WHEN the ContactService deletes emails during a replace operation, THE ContactService SHALL include `administration = %s` in the DELETE WHERE clause
4. WHEN the ContactService retrieves the invoice email for a contact, THE ContactService SHALL include `administration = %s` in the WHERE clause

### Requirement 5: Update vw_invoice_vat_summary view

**User Story:** As a developer, I want the VAT summary view to include the `administration` column, so that tenant-scoped queries against the view can filter directly without JOINing to invoices.

#### Acceptance Criteria

1. THE Migration_Script SHALL recreate the VAT_Summary_View to include the `administration` column from the Invoice_Lines_Table in the SELECT and GROUP BY clauses
2. WHEN a service queries the VAT_Summary_View, THE service SHALL be able to filter by `administration = %s` directly on the view

### Requirement 6: Migration safety and backward compatibility

**User Story:** As a system administrator, I want the migration to be safe and non-destructive, so that existing data and application functionality are preserved.

#### Acceptance Criteria

1. THE Migration_Script SHALL be idempotent — running the script multiple times SHALL produce the same result without errors
2. THE Migration_Script SHALL check whether the `administration` column already exists before attempting to add the column
3. THE Migration_Script SHALL execute the backfill UPDATE within a transaction to ensure atomicity
4. WHEN the migration completes, THE Migration_Script SHALL set the `administration` column to NOT NULL to prevent future rows from being inserted without a tenant
5. IF the backfill UPDATE encounters a row where the parent table row is missing, THEN THE Migration_Script SHALL log a warning and skip the orphaned row
6. THE Migration_Script SHALL record the migration in the `database_migrations` table with a description and timestamp

### Requirement 7: Data consistency enforcement

**User Story:** As a developer, I want the system to ensure that the `administration` value on child rows always matches the parent row, so that data integrity is maintained.

#### Acceptance Criteria

1. WHEN the ZZPInvoiceService creates invoice lines, THE ZZPInvoiceService SHALL use the same `administration` value as the parent invoice
2. WHEN the ContactService creates contact emails, THE ContactService SHALL use the same `administration` value as the parent contact
3. THE Invoice_Lines_Table SHALL have a NOT NULL constraint on the `administration` column after migration
4. THE Contact_Emails_Table SHALL have a NOT NULL constraint on the `administration` column after migration
