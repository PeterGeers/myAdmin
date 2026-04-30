import csv
import sys
from pathlib import Path

# Add backend/src to path for imports
backend_src = Path(__file__).parent.parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from dotenv import load_dotenv
load_dotenv('backend/.env')

from database import DatabaseManager
from db_exceptions import DatabaseError

db = DatabaseManager()

# Read CSV
with open('gmail_urls_output.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    records = list(reader)

print(f"Processing {len(records)} records...")

updated = 0
skipped = 0
not_found = 0

for row in records:
    id_val = row['id']
    csv_ref3 = row['Ref3']

    # Get current Ref3 from database
    result = db.execute_query("SELECT Ref3 FROM mutaties WHERE ID = %s", (id_val,))

    if result:
        db_ref3 = result[0]['Ref3']

        # Compare and update if different
        if db_ref3 != csv_ref3:
            db.execute_query(
                "UPDATE mutaties SET Ref3 = %s WHERE ID = %s",
                (csv_ref3, id_val),
                fetch=False,
                commit=True
            )
            updated += 1
            print(f"Updated ID {id_val}")
        else:
            skipped += 1
    else:
        print(f"ID {id_val} not found in database")
        not_found += 1

print(f"\nDone!")
print(f"Updated: {updated}")
print(f"Skipped (already matching): {skipped}")
print(f"Not found: {not_found}")
