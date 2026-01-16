"""
Update mutaties table Ref3 field with new Google Drive URLs
Removes ?usp=drivesdk from URLs
"""

import csv
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

# Configuration
INPUT_CSV = 'uploaded_invoices_with_urls.csv'
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'finance')
}

def clean_url(url):
    """Remove ?usp=drivesdk from URL"""
    return url.replace('?usp=drivesdk', '')

def update_database(records):
    """Update Ref3 in mutaties table"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    updated = 0
    errors = 0
    
    for record in records:
        try:
            record_id = record['ID']
            clean_google_url = clean_url(record['GoogleDriveURL'])
            
            cursor.execute(
                "UPDATE mutaties SET Ref3 = %s WHERE ID = %s",
                (clean_google_url, record_id)
            )
            
            if cursor.rowcount > 0:
                updated += 1
            
        except Exception as e:
            print(f"Error updating ID {record_id}: {e}")
            errors += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return updated, errors

def main():
    print("Loading CSV file...")
    
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        records = list(reader)
    
    print(f"Total records to update: {len(records)}")
    print()
    
    print("Connecting to database...")
    print(f"Database: {DB_CONFIG['database']}")
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
