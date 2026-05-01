"""
Update mutaties table Ref3 field with new Google Drive URLs
Removes ?usp=drivesdk from URLs
"""

import csv
import sys
from pathlib import Path

# Add backend/src to path for imports
backend_src = Path(__file__).parent.parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv()

from database import DatabaseManager
from db_exceptions import DatabaseError

# Configuration
INPUT_CSV = 'uploaded_invoices_with_urls.csv'


def clean_url(url):
    """Remove ?usp=drivesdk from URL"""
    return url.replace('?usp=drivesdk', '')


def update_database(records):
    """Update Ref3 in mutaties table"""
    db = DatabaseManager()

    updated = 0
    errors = 0

    for record in records:
        try:
            record_id = record['ID']
            clean_google_url = clean_url(record['GoogleDriveURL'])

            result = db.execute_query(
                "UPDATE mutaties SET Ref3 = %s WHERE ID = %s",
                (clean_google_url, record_id),
                fetch=False,
                commit=True
            )

            if result and result > 0:
                updated += 1

        except DatabaseError as e:
            print(f"Error updating ID {record_id}: {e}")
            errors += 1
        except Exception as e:
            print(f"Error updating ID {record_id}: {e}")
            errors += 1

    return updated, errors


def main():
    print("Loading CSV file...")

    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        records = list(reader)

    print(f"Total records to update: {len(records)}")
    print()

    print("Connecting to database...")
    print()

    print("Updating records...")
    updated, errors = update_database(records)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Successfully updated: {updated} records")
    print(f"Errors: {errors} records")
    print("=" * 60)


if __name__ == '__main__':
    main()
