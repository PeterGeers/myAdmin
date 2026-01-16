import csv
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv('backend/.env')

# Connect to database
db = mysql.connector.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME', 'finance')
)

cursor = db.cursor()

# Read CSV
with open('gmail_urls_output.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    records = list(reader)

print(f"Processing {len(records)} records...")

updated = 0
skipped = 0

for row in records:
    id_val = row['id']
    csv_ref3 = row['Ref3']
    
    # Get current Ref3 from database
    cursor.execute("SELECT Ref3 FROM mutaties WHERE ID = %s", (id_val,))
    result = cursor.fetchone()
    
    if result:
        db_ref3 = result[0]
        
        # Compare and update if different
        if db_ref3 != csv_ref3:
            cursor.execute("UPDATE mutaties SET Ref3 = %s WHERE ID = %s", (csv_ref3, id_val))
            updated += 1
            print(f"Updated ID {id_val}")
        else:
            skipped += 1
    else:
        print(f"ID {id_val} not found in database")

# Commit changes
db.commit()

print(f"\nDone!")
print(f"Updated: {updated}")
print(f"Skipped (already matching): {skipped}")
print(f"Not found: {len(records) - updated - skipped}")

cursor.close()
db.close()
