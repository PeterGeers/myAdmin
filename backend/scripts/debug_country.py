"""Debug country detection issues"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from dotenv import load_dotenv
from country_detector import extract_country_from_booking_addinfo
from database import DatabaseManager

load_dotenv()

db = DatabaseManager()

print("\nDebugging booking.com records with country='12':\n")
print("="*80)

results = db.execute_query("""
    SELECT id, channel, country, addInfo
    FROM bnb 
    WHERE channel LIKE %s AND country = %s
    LIMIT 3
""", ('%booking%', '12'))

for row in results:
    record_id = row['id']
    channel = row['channel']
    country = row['country']
    addinfo = row['addInfo']
    
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
