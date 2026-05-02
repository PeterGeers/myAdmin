# Design Document: Invoice Lines & Contact Emails Tenant Isolation

## Architecture Overview

This feature adds defense-in-depth tenant isolation to two child tables (`invoice_lines`, `contact_emails`) and one view (`vw_invoice_vat_summary`) that were created without a direct `administration` column. The change is purely backend — no frontend or API contract changes are needed since the tenant is already resolved server-side via the `@tenant_required()` decorator.

### Data Flow (Before → After)

**Before:** Service → query child table → JOIN parent for tenant filter
**After:** Service → query child table → direct `WHERE administration = %s`

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Route       │────▶│  Service      │────▶│  Database         │
│ @tenant_req  │     │ (tenant arg)  │     │  invoice_lines    │
│              │     │               │     │  + administration │
└─────────────┘     └──────────────┘     └──────────────────┘
                                           Direct WHERE clause
                                           No JOIN required
```

### Affected Components

| Component         | File                                                                 | Change Type    |
| ----------------- | -------------------------------------------------------------------- | -------------- |
| Migration script  | `backend/src/migrations/2026XXXX_tenant_isolation_child_tables.json` | New file       |
| ZZPInvoiceService | `backend/src/services/zzp_invoice_service.py`                        | Modify queries |
| ContactService    | `backend/src/services/contact_service.py`                            | Modify queries |
| ProductService    | `backend/src/services/product_service.py`                            | Modify query   |
| DDL reference     | `backend/sql/phase_zzp_tables.sql`                                   | Update DDL     |

No new API endpoints. No frontend changes. No new dependencies.

---

## Database Schema Changes

### 1. invoice_lines — Add administration column

**Current schema:**

```sql
CREATE TABLE invoice_lines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoice_id INT NOT NULL,
    product_id INT DEFAULT NULL,
    description VARCHAR(512) NOT NULL,
    quantity DECIMAL(10, 4) DEFAULT 1.0000,
    unit_price DECIMAL(12, 2) NOT NULL,
    vat_code VARCHAR(20) NOT NULL,
    vat_rate DECIMAL(5, 2) NOT NULL,
    vat_amount DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(12, 2) NOT NULL,
    sort_order INT DEFAULT 0,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id),
    INDEX idx_invoice_id (invoice_id)
);
```

**New column and indexes:**

```sql
ALTER TABLE invoice_lines ADD COLUMN administration VARCHAR(50) DEFAULT NULL;

-- Backfill from parent
UPDATE invoice_lines il
  JOIN invoices i ON il.invoice_id = i.id
  SET il.administration = i.administration;

-- Enforce NOT NULL after backfill
ALTER TABLE invoice_lines MODIFY COLUMN administration VARCHAR(50) NOT NULL;

-- Indexes for tenant-scoped queries
CREATE INDEX idx_administration ON invoice_lines (administration);
CREATE INDEX idx_admin_invoice ON invoice_lines (administration, invoice_id);
```

### 2. contact_emails — Add administration column

**Current schema:**

```sql
CREATE TABLE contact_emails (
    id INT AUTO_INCREMENT PRIMARY KEY,
    contact_id INT NOT NULL,
    email VARCHAR(255) NOT NULL,
    email_type ENUM('general', 'invoice', 'other') DEFAULT 'general',
    is_primary BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    INDEX idx_contact_id (contact_id)
);
```

**New column and index:**

```sql
ALTER TABLE contact_emails ADD COLUMN administration VARCHAR(50) DEFAULT NULL;

-- Backfill from parent
UPDATE contact_emails ce
  JOIN contacts c ON ce.contact_id = c.id
  SET ce.administration = c.administration;

-- Enforce NOT NULL after backfill
ALTER TABLE contact_emails MODIFY COLUMN administration VARCHAR(50) NOT NULL;

-- Index for tenant-scoped queries
CREATE INDEX idx_administration ON contact_emails (administration);
```

### 3. vw_invoice_vat_summary — Include administration

**Current view:**

```sql
CREATE OR REPLACE VIEW vw_invoice_vat_summary AS
SELECT invoice_id,
    vat_code,
    vat_rate,
    ROUND(SUM(line_total), 2) AS base_amount,
    ROUND(SUM(vat_amount), 2) AS vat_amount
FROM invoice_lines
GROUP BY invoice_id, vat_code, vat_rate;
```

**Updated view:**

```sql
CREATE OR REPLACE VIEW vw_invoice_vat_summary AS
SELECT administration,
    invoice_id,
    vat_code,
    vat_rate,
    ROUND(SUM(line_total), 2) AS base_amount,
    ROUND(SUM(vat_amount), 2) AS vat_amount
FROM invoice_lines
GROUP BY administration, invoice_id, vat_code, vat_rate;
```

---

## Migration Script Design

The migration follows the existing JSON migration pattern in `backend/src/migrations/`.

**File:** `backend/src/migrations/20260502120000_tenant_isolation_child_tables.json`

### Idempotency Strategy

Each DDL statement is guarded by a conditional check:

- `ALTER TABLE ... ADD COLUMN` uses an `IF NOT EXISTS`-style check via a stored procedure or by catching the "duplicate column" error
- Since MySQL JSON migrations execute raw SQL, we use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (MySQL 8.0 does not support this natively), so we wrap in a procedure pattern

**Practical approach:** Use a series of SQL statements that check `INFORMATION_SCHEMA.COLUMNS` before altering. The migration framework already tracks applied migrations by name, so re-running a previously applied migration is a no-op at the framework level.

### Migration SQL Statements (up)

```json
{
  "name": "tenant_isolation_child_tables",
  "description": "Add administration column to invoice_lines and contact_emails for defense-in-depth tenant isolation",
  "timestamp": "20260502120000",
  "up": [
    "SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'invoice_lines' AND COLUMN_NAME = 'administration'); SET @sql = IF(@col_exists = 0, 'ALTER TABLE invoice_lines ADD COLUMN administration VARCHAR(50) DEFAULT NULL', 'SELECT 1'); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt",
    "UPDATE invoice_lines il JOIN invoices i ON il.invoice_id = i.id SET il.administration = i.administration WHERE il.administration IS NULL",
    "ALTER TABLE invoice_lines MODIFY COLUMN administration VARCHAR(50) NOT NULL",
    "CREATE INDEX idx_administration ON invoice_lines (administration)",
    "CREATE INDEX idx_admin_invoice ON invoice_lines (administration, invoice_id)",
    "SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'contact_emails' AND COLUMN_NAME = 'administration'); SET @sql = IF(@col_exists = 0, 'ALTER TABLE contact_emails ADD COLUMN administration VARCHAR(50) DEFAULT NULL', 'SELECT 1'); PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt",
    "UPDATE contact_emails ce JOIN contacts c ON ce.contact_id = c.id SET ce.administration = c.administration WHERE ce.administration IS NULL",
    "ALTER TABLE contact_emails MODIFY COLUMN administration VARCHAR(50) NOT NULL",
    "CREATE INDEX idx_administration ON contact_emails (administration)",
    "CREATE OR REPLACE VIEW vw_invoice_vat_summary AS SELECT administration, invoice_id, vat_code, vat_rate, ROUND(SUM(line_total), 2) AS base_amount, ROUND(SUM(vat_amount), 2) AS vat_amount FROM invoice_lines GROUP BY administration, invoice_id, vat_code, vat_rate"
  ],
  "down": [
    "CREATE OR REPLACE VIEW vw_invoice_vat_summary AS SELECT invoice_id, vat_code, vat_rate, ROUND(SUM(line_total), 2) AS base_amount, ROUND(SUM(vat_amount), 2) AS vat_amount FROM invoice_lines GROUP BY invoice_id, vat_code, vat_rate",
    "DROP INDEX idx_administration ON contact_emails",
    "ALTER TABLE contact_emails DROP COLUMN administration",
    "DROP INDEX idx_admin_invoice ON invoice_lines",
    "DROP INDEX idx_administration ON invoice_lines",
    "ALTER TABLE invoice_lines DROP COLUMN administration"
  ],
  "version": "1.0"
}
```

### Orphan Row Handling

The `UPDATE ... WHERE il.administration IS NULL` clause ensures only unset rows are backfilled. Orphaned rows (where the parent invoice/contact was deleted but CASCADE didn't fire) will remain with `administration IS NULL`. The subsequent `MODIFY COLUMN ... NOT NULL` will fail if orphans exist, which is the desired behavior — orphans must be investigated and resolved before the migration can complete. If orphans are found, they should be logged and deleted manually before re-running.

**Decision:** Fail-fast on orphans rather than silently skipping them. This is safer for a tenant isolation feature where silent data gaps could mask security issues.

---

## Service Layer Changes

### ZZPInvoiceService (`zzp_invoice_service.py`)

#### \_save_lines — Add administration to INSERT

**Current:**

```python
self.db.execute_query(
    """INSERT INTO invoice_lines
       (invoice_id, product_id, description, quantity, unit_price,
        vat_code, vat_rate, vat_amount, line_total, sort_order)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
    (invoice_id, calc.get('product_id'), calc['description'],
     calc['quantity'], calc['unit_price'], calc['vat_code'],
     calc['vat_rate'], calc['vat_amount'], calc['line_total'],
     calc.get('sort_order', idx)),
    fetch=False, commit=True,
)
```

**Updated:**

```python
self.db.execute_query(
    """INSERT INTO invoice_lines
       (invoice_id, administration, product_id, description, quantity,
        unit_price, vat_code, vat_rate, vat_amount, line_total, sort_order)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
    (invoice_id, tenant, calc.get('product_id'), calc['description'],
     calc['quantity'], calc['unit_price'], calc['vat_code'],
     calc['vat_rate'], calc['vat_amount'], calc['line_total'],
     calc.get('sort_order', idx)),
    fetch=False, commit=True,
)
```

#### update_invoice — Add administration to DELETE

**Current:**

```python
self.db.execute_query(
    "DELETE FROM invoice_lines WHERE invoice_id = %s",
    (invoice_id,), fetch=False, commit=True,
)
```

**Updated:**

```python
self.db.execute_query(
    "DELETE FROM invoice_lines WHERE invoice_id = %s AND administration = %s",
    (invoice_id, tenant), fetch=False, commit=True,
)
```

#### get_invoice — Add administration to SELECT (lines + VAT summary)

**Current (lines):**

```python
inv['lines'] = self.db.execute_query(
    """SELECT id, product_id, description, quantity, unit_price,
              vat_code, vat_rate, vat_amount, line_total, sort_order
       FROM invoice_lines WHERE invoice_id = %s ORDER BY sort_order""",
    (invoice_id,),
) or []
```

**Updated (lines):**

```python
inv['lines'] = self.db.execute_query(
    """SELECT id, product_id, description, quantity, unit_price,
              vat_code, vat_rate, vat_amount, line_total, sort_order
       FROM invoice_lines
       WHERE invoice_id = %s AND administration = %s
       ORDER BY sort_order""",
    (invoice_id, tenant),
) or []
```

**Current (VAT summary in get_invoice):**

```python
inv['vat_summary'] = self.db.execute_query(
    """SELECT vat_code, vat_rate, base_amount, vat_amount
       FROM vw_invoice_vat_summary WHERE invoice_id = %s""",
    (invoice_id,),
) or []
```

**Updated (VAT summary in get_invoice):**

```python
inv['vat_summary'] = self.db.execute_query(
    """SELECT vat_code, vat_rate, base_amount, vat_amount
       FROM vw_invoice_vat_summary
       WHERE invoice_id = %s AND administration = %s""",
    (invoice_id, tenant),
) or []
```

#### \_update_totals — Add administration to VAT summary SELECT

**Current:**

```python
vat_summary = self.db.execute_query(
    """SELECT vat_code, vat_rate, base_amount, vat_amount
       FROM vw_invoice_vat_summary WHERE invoice_id = %s""",
    (invoice_id,),
) or []
```

**Updated:** The `_update_totals` method currently does not receive `tenant` as a parameter. The method signature must be updated:

```python
def _update_totals(self, invoice_id: int, lines: list, tenant: str) -> dict:
```

Then the query becomes:

```python
vat_summary = self.db.execute_query(
    """SELECT vat_code, vat_rate, base_amount, vat_amount
       FROM vw_invoice_vat_summary
       WHERE invoice_id = %s AND administration = %s""",
    (invoice_id, tenant),
) or []
```

**Callers to update:**

- `create_invoice` (line ~237): `self._update_totals(invoice_id, calculated, tenant)`
- `update_invoice` (line ~288): `self._update_totals(invoice_id, calculated, tenant)`
- `create_credit_note` (line ~470): `self._update_totals(cn_id, calculated, tenant)`

#### copy_last_invoice — Add administration to SELECT

**Current:**

```python
last_lines = self.db.execute_query(
    "SELECT * FROM invoice_lines WHERE invoice_id = %s ORDER BY sort_order",
    (last_invoice['id'],),
) or []
```

**Updated:**

```python
last_lines = self.db.execute_query(
    "SELECT * FROM invoice_lines WHERE invoice_id = %s AND administration = %s ORDER BY sort_order",
    (last_invoice['id'], tenant),
) or []
```

---

### ContactService (`contact_service.py`)

All email helper methods currently take only `contact_id`. They need `tenant` added to their signatures.

#### \_save_emails — Add administration to INSERT

**Current signature:** `def _save_emails(self, contact_id: int, emails: List[dict]) -> None`
**Updated signature:** `def _save_emails(self, contact_id: int, emails: List[dict], tenant: str) -> None`

**Current:**

```python
self.db.execute_query(
    """INSERT INTO contact_emails (contact_id, email, email_type, is_primary)
       VALUES (%s, %s, %s, %s)""",
    (contact_id, em['email'], em.get('email_type', 'general'),
     em.get('is_primary', False)),
    fetch=False, commit=True,
)
```

**Updated:**

```python
self.db.execute_query(
    """INSERT INTO contact_emails (contact_id, administration, email, email_type, is_primary)
       VALUES (%s, %s, %s, %s, %s)""",
    (contact_id, tenant, em['email'], em.get('email_type', 'general'),
     em.get('is_primary', False)),
    fetch=False, commit=True,
)
```

#### \_get_emails — Add administration to SELECT

**Current signature:** `def _get_emails(self, contact_id: int) -> List[dict]`
**Updated signature:** `def _get_emails(self, contact_id: int, tenant: str) -> List[dict]`

**Current:**

```python
rows = self.db.execute_query(
    "SELECT id, email, email_type, is_primary FROM contact_emails WHERE contact_id = %s",
    (contact_id,),
)
```

**Updated:**

```python
rows = self.db.execute_query(
    "SELECT id, email, email_type, is_primary FROM contact_emails WHERE contact_id = %s AND administration = %s",
    (contact_id, tenant),
)
```

#### \_replace_emails — Add administration to DELETE

**Current signature:** `def _replace_emails(self, contact_id: int, emails: List[dict]) -> None`
**Updated signature:** `def _replace_emails(self, contact_id: int, emails: List[dict], tenant: str) -> None`

**Current:**

```python
self.db.execute_query(
    "DELETE FROM contact_emails WHERE contact_id = %s",
    (contact_id,), fetch=False, commit=True,
)
self._save_emails(contact_id, emails)
```

**Updated:**

```python
self.db.execute_query(
    "DELETE FROM contact_emails WHERE contact_id = %s AND administration = %s",
    (contact_id, tenant), fetch=False, commit=True,
)
self._save_emails(contact_id, emails, tenant)
```

#### get_invoice_email — Add administration to SELECT

**Current:**

```python
rows = self.db.execute_query(
    """SELECT email, email_type, is_primary FROM contact_emails
       WHERE contact_id = %s ORDER BY FIELD(email_type,'invoice','general','other')""",
    (contact_id,),
)
```

**Updated:**

```python
rows = self.db.execute_query(
    """SELECT email, email_type, is_primary FROM contact_emails
       WHERE contact_id = %s AND administration = %s
       ORDER BY FIELD(email_type,'invoice','general','other')""",
    (contact_id, tenant),
)
```

#### Callers to update

All callers of `_get_emails`, `_save_emails`, and `_replace_emails` must pass `tenant`:

- `create_contact`: calls `_save_emails(contact_id, emails)` → `_save_emails(contact_id, emails, tenant)`
- `update_contact`: calls `_replace_emails(contact_id, emails)` → `_replace_emails(contact_id, emails, tenant)`
- `get_contact`: calls `_get_emails(contact_id)` → `_get_emails(contact_id, tenant)`
- `get_contact_by_client_id`: calls `_get_emails(contact_id)` → `_get_emails(contact_id, tenant)`

---

### ProductService (`product_service.py`)

#### \_check_product_in_use — Replace JOIN with direct filter

**Current:**

```python
rows = self.db.execute_query(
    "SELECT 1 FROM invoice_lines il JOIN invoices i ON il.invoice_id = i.id "
    "WHERE il.product_id = %s AND i.administration = %s LIMIT 1",
    (product_id, tenant),
)
```

**Updated:**

```python
rows = self.db.execute_query(
    "SELECT 1 FROM invoice_lines WHERE product_id = %s AND administration = %s LIMIT 1",
    (product_id, tenant),
)
```

This eliminates the JOIN, improving query performance and aligning with the direct tenant filter pattern.

---

## DDL Reference Update

Update `backend/sql/phase_zzp_tables.sql` to reflect the new schema for fresh installations:

### invoice_lines table

Add `administration VARCHAR(50) NOT NULL` after `invoice_id`, plus the two new indexes.

### contact_emails table

Add `administration VARCHAR(50) NOT NULL` after `contact_id`, plus the new index.

### vw_invoice_vat_summary view

Add `administration` to SELECT and GROUP BY.

---

## Performance Considerations

- **Index on `administration`**: Single-column index supports standalone tenant queries
- **Composite index `(administration, invoice_id)`**: Covers the most common query pattern (get lines for a specific invoice within a tenant) without needing to hit the clustered index
- **JOIN elimination in ProductService**: Removes one table scan from the product-in-use check
- **View performance**: Adding `administration` to GROUP BY has negligible impact since it's functionally dependent on `invoice_id` (all lines for an invoice share the same tenant)
- **Migration backfill**: The UPDATE JOIN is a one-time operation. For large tables, it will lock rows briefly. Acceptable for a maintenance window deployment.

---

## Security Considerations

- **Defense-in-depth**: Every query against `invoice_lines` and `contact_emails` will include `AND administration = %s`, preventing cross-tenant data access even if a bug passes the wrong `invoice_id` or `contact_id`
- **NOT NULL constraint**: Prevents future inserts without a tenant value, catching bugs at the database level
- **No FK to administrations table**: Consistent with existing pattern — tenant validation happens at the application layer via `@tenant_required()`
- **Parameterized queries**: All tenant values are passed as `%s` parameters, maintaining SQL injection protection

---

## Testing Strategy

### Unit Tests

- Verify all modified queries include `administration = %s` parameter
- Verify `_update_totals` receives and passes `tenant` correctly
- Verify ContactService helper methods accept and use `tenant` parameter
- Mock database to confirm parameter tuples include tenant value

### Integration Tests

- Run migration on test database, verify columns exist with NOT NULL constraint
- Verify indexes are created
- Insert invoice lines with administration, query back with tenant filter
- Insert contact emails with administration, query back with tenant filter
- Verify vw_invoice_vat_summary returns administration column

### Migration Tests

- Run migration twice — second run should be a no-op (idempotency)
- Verify backfill populates all existing rows
- Verify NOT NULL constraint is enforced after migration

---

## Key Technical Decisions

| Decision                              | Rationale                                                        |
| ------------------------------------- | ---------------------------------------------------------------- |
| Fail-fast on orphan rows              | Silent skipping could mask tenant isolation gaps                 |
| No FK constraint on administration    | Matches existing pattern; tenant validation is application-level |
| Composite index `(admin, invoice_id)` | Covers the primary query pattern for invoice_lines               |
| Single index on contact_emails        | Lower query volume doesn't justify a composite index             |
| Update `_update_totals` signature     | Cleanest way to pass tenant to VAT summary query                 |
| JSON migration format                 | Matches existing migration framework in `database_migrations.py` |
