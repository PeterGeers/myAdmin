"""
Migrate Revolut Ref2 values to use 3 fields with formatted saldo (2 decimals)
Old format: Beschrijving_Bedrag_Kosten_Valuta_Startdatum (5 fields)
New format: Beschrijving_Saldo_Startdatum (3 fields with 2 decimal saldo)
"""

from database import DatabaseManager


def migrate_revolut_ref2(test_mode=False):
    db = DatabaseManager(test_mode=test_mode)
    db_name = db.config["database"]

    with db.get_cursor() as (cursor, conn):
        # Get all Revolut transactions
        cursor.execute(
            """
            SELECT ID, Ref2
            FROM mutaties
            WHERE TransactionNumber LIKE %s
        """,
            ("Revolut 2025-%",),
        )

        records = cursor.fetchall()
        print(f"Found {len(records)} Revolut records to format in {db_name}")

        updated = 0
        for record in records:
            if not record["Ref2"]:
                continue
            parts = record["Ref2"].split("_")

            if len(parts) == 3:
                # Format: [Beschrijving, Saldo, Startdatum]
                beschrijving = parts[0]
                saldo_raw = parts[1]
                startdatum = parts[2]

                try:
                    # Format saldo to 2 decimals
                    saldo = f"{float(saldo_raw):.2f}"

                    # Only update if format changed
                    if saldo != saldo_raw:
                        new_ref2 = f"{beschrijving}_{saldo}_{startdatum}"

                        cursor.execute(
                            """
                            UPDATE mutaties 
                            SET Ref2 = %s 
                            WHERE ID = %s
                        """,
                            (new_ref2, record["ID"]),
                        )

                        updated += 1
                        print(f"ID {record['ID']}: {saldo_raw} -> {saldo}")
                except ValueError:
                    print(f"ID {record['ID']}: Skipping non-numeric saldo: {saldo_raw}")

        conn.commit()

    print(f"\nMigration complete: {updated} records updated in {db_name}")
    return updated


if __name__ == "__main__":
    import sys

    test_mode = "--test" in sys.argv

    print(f"Running in {'TEST' if test_mode else 'PRODUCTION'} mode")
    migrate_revolut_ref2(test_mode)
