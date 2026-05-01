"""Fix records with country='12' by re-detecting from addInfo"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from dotenv import load_dotenv
from country_detector import extract_country_from_booking_addinfo
from database import DatabaseManager
from db_exceptions import DatabaseError

load_dotenv()

db = DatabaseManager()

print("\nFixing records with country='12'...\n")
print("="*60)

try:
    with db.get_cursor(dictionary=False) as (cursor, conn):
        # Get records with country='12'
        for table in ['bnb', 'bnbplanned']:
            print(f"\nProcessing table: {table}")
            print("-"*60)
            
            cursor.execute(f"""
                SELECT id, addInfo
                FROM {table}
                WHERE country = '12'
            """)
            
            records = cursor.fetchall()
            print(f"Found {len(records)} records to fix")
            
            updates = []
            for record_id, addinfo in records:
                country = extract_country_from_booking_addinfo(addinfo)
                if country and country != '12':
                    updates.append((country, record_id))
                    print(f"  ID {record_id:6d}: 12 -> {country}")
            
            if updates:
                update_query = f"UPDATE {table} SET country = %s WHERE id = %s"
                cursor.executemany(update_query, updates)
                print(f"\nUpdated {len(updates)} records in {table}")
            else:
                print(f"No updates needed for {table}")
        
        conn.commit()

except DatabaseError as e:
    print(f"\n✗ Database error: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("Fix completed!")
print("="*60 + "\n")
