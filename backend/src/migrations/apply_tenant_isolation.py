"""One-time script to apply tenant isolation migration to invoice_lines and contact_emails."""

import mysql.connector
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run():
    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST", "db"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "finance"),
    )
    cursor = conn.cursor()

    # 1. invoice_lines: add administration column
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'invoice_lines' "
        "AND COLUMN_NAME = 'administration'"
    )
    exists = cursor.fetchone()[0]
    if not exists:
        cursor.execute(
            "ALTER TABLE invoice_lines ADD COLUMN administration "
            "VARCHAR(50) DEFAULT NULL AFTER invoice_id"
        )
        print("Added administration to invoice_lines")
    else:
        print("invoice_lines already has administration")

    # 2. Backfill invoice_lines
    cursor.execute(
        "UPDATE invoice_lines il JOIN invoices i ON il.invoice_id = i.id "
        "SET il.administration = i.administration WHERE il.administration IS NULL"
    )
    print(f"Backfilled {cursor.rowcount} invoice_lines rows")

    # 3. Set NOT NULL
    cursor.execute(
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
            cursor.execute(idx_sql)
            print(f"Created {idx_name} on invoice_lines")
        except Exception as e:
            print(f"Index {idx_name} on invoice_lines: {e}")

    # 5. contact_emails: add administration column
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'contact_emails' "
        "AND COLUMN_NAME = 'administration'"
    )
    exists = cursor.fetchone()[0]
    if not exists:
        cursor.execute(
            "ALTER TABLE contact_emails ADD COLUMN administration "
            "VARCHAR(50) DEFAULT NULL AFTER contact_id"
        )
        print("Added administration to contact_emails")
    else:
        print("contact_emails already has administration")

    # 6. Backfill contact_emails
    cursor.execute(
        "UPDATE contact_emails ce JOIN contacts c ON ce.contact_id = c.id "
        "SET ce.administration = c.administration WHERE ce.administration IS NULL"
    )
    print(f"Backfilled {cursor.rowcount} contact_emails rows")

    # 7. Set NOT NULL
    cursor.execute(
        "ALTER TABLE contact_emails MODIFY COLUMN administration VARCHAR(50) NOT NULL"
    )
    print("Set NOT NULL on contact_emails.administration")

    # 8. Add index
    try:
        cursor.execute(
            "CREATE INDEX idx_administration ON contact_emails (administration)"
        )
        print("Created idx_administration on contact_emails")
    except Exception as e:
        print(f"Index idx_administration on contact_emails: {e}")

    # 9. Recreate view
    cursor.execute(
        "CREATE OR REPLACE VIEW vw_invoice_vat_summary AS "
        "SELECT administration, invoice_id, vat_code, vat_rate, "
        "ROUND(SUM(line_total), 2) AS base_amount, "
        "ROUND(SUM(vat_amount), 2) AS vat_amount "
        "FROM invoice_lines "
        "GROUP BY administration, invoice_id, vat_code, vat_rate"
    )
    print("Recreated vw_invoice_vat_summary with administration")

    # 10. Record migration
    cursor.execute(
        "INSERT INTO database_migrations (migration_name, status, notes) "
        "VALUES (%s, %s, %s)",
        (
            "tenant_isolation_child_tables",
            "success",
            "Add administration to invoice_lines and contact_emails for REQ13",
        ),
    )
    print("Recorded migration")

    conn.commit()
    cursor.close()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    run()
