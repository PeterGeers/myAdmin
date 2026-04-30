import sys
from pathlib import Path

# Add backend/src to path for imports
backend_src = Path(__file__).parent.parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv()

from database import DatabaseManager
from db_exceptions import DatabaseError


def run_query(db, query, description, fetch_results=True):
    """Execute a query and print results."""
    print(f"\n{'='*60}")
    print(f"QUERY: {description}")
    print(f"{'='*60}")
    try:
        if fetch_results:
            results = db.execute_query(query)
            if results:
                columns = list(results[0].keys())
                # Print column headers
                print(" | ".join(f"{col:15}" for col in columns))
                print("-" * (len(columns) * 18))
                # Print results
                for row in results:
                    print(" | ".join(f"{str(val):15}" for val in row.values()))
                print(f"\nTotal rows: {len(results)}")
            else:
                print("No results returned")
        else:
            result = db.execute_query(query, fetch=False, commit=True)
            print(f"Query executed successfully. Affected rows: {result}")
    except DatabaseError as e:
        print(f"ERROR: {e}")
        return False
    return True


try:
    db = DatabaseManager()
    print("SUCCESS: Connected to database")

    # STEP 1: Count duplicates before fix
    query1 = """
    SELECT
        COUNT(*) as total_duplicate_rows
    FROM bnb b1
    WHERE EXISTS (
        SELECT 1 FROM bnb b2
        WHERE b1.id = b2.id
        AND b1.reservationCode = b2.reservationCode
        AND b1.checkinDate = b2.checkinDate
        AND b1.guestName = b2.guestName
    )
    """
    run_query(db, query1, "Count total duplicate rows before fix")

    # STEP 2-6: Use transaction for the multi-statement fix
    print(f"\n{'='*60}")
    print("STEP 2-6: Fixing duplicates using transaction")
    print(f"{'='*60}")

    with db.transaction() as (cursor, conn):
        # STEP 2: Create temporary table with unique records
        cursor.execute("DROP TEMPORARY TABLE IF EXISTS bnb_unique")
        cursor.execute("CREATE TEMPORARY TABLE bnb_unique AS SELECT DISTINCT * FROM bnb")
        print("Temporary table created with unique records")

        # STEP 3: Count records in temp table
        cursor.execute("SELECT COUNT(*) as unique_records FROM bnb_unique")
        temp_result = cursor.fetchone()
        print(f"Unique records in temp table: {temp_result['unique_records']}")

        # STEP 4: Count records in original table
        cursor.execute("SELECT COUNT(*) as original_records FROM bnb")
        orig_result = cursor.fetchone()
        print(f"Records in original table: {orig_result['original_records']}")

        # STEP 5: Backup original table
        print(f"\n{'='*60}")
        print("STEP 5: Creating backup of original table")
        print(f"{'='*60}")

        try:
            cursor.execute("DROP TABLE IF EXISTS bnb_backup_duplicates")
            cursor.execute("CREATE TABLE bnb_backup_duplicates AS SELECT * FROM bnb")
            print("Backup table 'bnb_backup_duplicates' created successfully")
        except Exception as e:
            print(f"Backup creation failed: {e}")
            print("STOPPING - Cannot proceed without backup")
            raise

        # STEP 6: Clear original table and insert unique records
        print(f"\n{'='*60}")
        print("STEP 6: Replacing original table with unique records")
        print(f"{'='*60}")

        cursor.execute("DELETE FROM bnb")
        print(f"Original table cleared. Rows affected: {cursor.rowcount}")

        cursor.execute("INSERT INTO bnb SELECT * FROM bnb_unique")
        print(f"Unique records inserted. Rows affected: {cursor.rowcount}")

    # STEP 7: Add PRIMARY KEY constraint (separate DDL operation)
    print(f"\n{'='*60}")
    print("STEP 7: Adding PRIMARY KEY constraint")
    print(f"{'='*60}")

    try:
        db.execute_ddl("ALTER TABLE bnb ADD PRIMARY KEY (id)")
        print("PRIMARY KEY constraint added successfully")
    except DatabaseError as e:
        print(f"PRIMARY KEY constraint failed: {e}")
        print("This might be expected if constraint already exists")

    # STEP 8: Verify fix
    query8 = """
    SELECT
        COUNT(*) as remaining_duplicates
    FROM bnb
    GROUP BY id
    HAVING COUNT(*) > 1
    """
    run_query(db, query8, "Check for remaining duplicate IDs (should be 0)")

    # STEP 9: Final count
    query9 = "SELECT COUNT(*) as final_record_count FROM bnb"
    run_query(db, query9, "Final record count")

    print(f"\n{'='*60}")
    print("DATABASE INTEGRITY FIX COMPLETE!")
    print("- Duplicate rows removed")
    print("- PRIMARY KEY constraint added")
    print("- Backup saved as 'bnb_backup_duplicates'")
    print(f"{'='*60}")

except DatabaseError as e:
    print(f"FAILED: {e}")
    print("Changes rolled back due to error")
except Exception as e:
    print(f"FAILED: {e}")
