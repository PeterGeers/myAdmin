"""Debug country detection issues"""
import mysql.connector
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from dotenv import load_dotenv
from country_detector import extract_country_from_booking_addinfo

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

print("\nDebugging booking.com records with country='12':\n")
print("="*80)

cursor.execute("""
    SELECT id, channel, country, addInfo
    FROM bnb 
    WHERE channel LIKE '%booking%' AND country = '12'
    LIMIT 3
""")

for row in cursor.fetchall():
    record_id, channel, country, addinfo = row
    print(f"\nID: {record_id}")
    print(f"Channel: {channel}")
    print(f"Current country: {country}")
    print(f"AddInfo length: {len(addinfo) if addinfo else 0}")
    
    if addinfo:
        fields = addinfo.split('|')
        print(f"Number of fields: {len(fields)}")
        print(f"\nFirst 20 fields:")
        for i, field in enumerate(fields[:20]):
            print(f"  [{i:2d}]: {field[:50]}")
        
        # Test extraction
        detected = extract_country_from_booking_addinfo(addinfo)
        print(f"\nDetected country: {detected}")

cursor.close()
conn.close()
