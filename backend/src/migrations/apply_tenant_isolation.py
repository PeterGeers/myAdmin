"""One-time script to apply tenant isolation migration to invoice_lines and contact_emails."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import DatabaseManager


def _column_exists(db, table_name, column_name):
    """Return True if the given column exists on the table in the current database."""
    result = db.execute_query(
        "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND COLUMN_NAME = %s",
        (table_name, column_name),
        fetch=True,
    )
    return result[0]["cnt"] > 0


def run(db=None):
    if db is None:
        db = DatabaseManager()

    # 1. invoice_lines: add administration column
    if not _column_exists(db, "invoice_lines", "administration"):
        db.execute_ddl(
            "ALTER TABLE invoice_lines ADD COLUMN administration "
            "VARCHAR(50) DEFAULT NULL AFTER invoice_id"
        )
        print("Added administration to invoice_lines")
    else:
        print("invoice_lines already has administration")

    # 2. Backfill invoice_lines
    rowcount = db.execute_query(
        "UPDATE invoice_lines il JOIN invoices i ON il.invoice_id = i.id "
        "SET il.administration = i.administration WHERE il.administration IS NULL",
        fetch=False,
        commit=True,
    )
    print(f"Backfilled {rowcount} invoice_lines rows")

    # 3. Set NOT NULL
    db.execute_ddl(
        "ALTER TABLE invoice_lines MODIFY COLUMN administration VARCHAR(50) NOT NULL"
    )
    print("Set NOT NULL on invoice_lines.administration")

    # 4. Add indexes
    for idx_name, idx_sql in [
        (
            "idx_administration",
            "CREATE INDEX idx_administration ON invoice_lines (administration)",
        ),
        (
            "idx_admin_invoice",
            "CREATE INDEX idx_admin_invoice ON invoice_lines (administration, invoice_id)",
        ),
    ]:
        try:
            db.execute_ddl(idx_sql)
            print(f"Created {idx_name} on invoice_lines")
        except Exception as e:
            print(f"Index {idx_name} on invoice_lines: {e}")

    # 5. contact_emails: add administration column
    if not _column_exists(db, "contact_emails", "administration"):
        db.execute_ddl(
            "ALTER TABLE contact_emails ADD COLUMN administration "
            "VARCHAR(50) DEFAULT NULL AFTER contact_id"
        )
        print("Added administration to contact_emails")
    else:
        print("contact_emails already has administration")

    # 6. Backfill contact_emails
    rowcount = db.execute_query(
        "UPDATE contact_emails ce JOIN contacts c ON ce.contact_id = c.id "
        "SET ce.administration = c.administration WHERE ce.administration IS NULL",
        fetch=False,
        commit=True,
    )
    print(f"Backfilled {rowcount} contact_emails rows")

    # 7. Set NOT NULL
    db.execute_ddl(
        "ALTER TABLE contact_emails MODIFY COLUMN administration VARCHAR(50) NOT NULL"
    )
    print("Set NOT NULL on contact_emails.administration")

    # 8. Add index
    try:
        db.execute_ddl(
            "CREATE INDEX idx_administration ON contact_emails (administration)"
        )
        print("Created idx_administration on contact_emails")
    except Exception as e:
        print(f"Index idx_administration on contact_emails: {e}")

    # 9. Recreate view
    db.execute_ddl(
        "CREATE OR REPLACE VIEW vw_invoice_vat_summary AS "
        "SELECT administration, invoice_id, vat_code, vat_rate, "
        "ROUND(SUM(line_total), 2) AS base_amount, "
        "ROUND(SUM(vat_amount), 2) AS vat_amount "
        "FROM invoice_lines "
        "GROUP BY administration, invoice_id, vat_code, vat_rate"
    )
    print("Recreated vw_invoice_vat_summary with administration")

    # 10. Record migration
    db.execute_query(
        "INSERT INTO database_migrations (migration_name, status, notes) "
        "VALUES (%s, %s, %s)",
        (
            "tenant_isolation_child_tables",
            "success",
            "Add administration to invoice_lines and contact_emails for REQ13",
        ),
        fetch=False,
        commit=True,
    )
    print("Recorded migration")

    print("Migration complete!")


if __name__ == "__main__":
    run()
