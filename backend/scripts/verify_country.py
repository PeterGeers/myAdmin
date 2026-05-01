"""Verify country backfill results"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from dotenv import load_dotenv
from database import DatabaseManager

load_dotenv()

db = DatabaseManager()

print("\n" + "="*60)
print("Country Detection Verification")
print("="*60 + "\n")

# Overall statistics
print("1. Overall Statistics:")
print("-" * 60)
stats = db.execute_query("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN country IS NOT NULL THEN 1 ELSE 0 END) as with_country,
        SUM(CASE WHEN country IS NULL THEN 1 ELSE 0 END) as without_country
    FROM bnb
""")
row = stats[0]
total = row['total']
with_country = row['with_country']
without_country = row['without_country']
print(f"Total records:        {total}")
print(f"With country:         {with_country} ({with_country/total*100:.1f}%)")
print(f"Without country:      {without_country} ({without_country/total*100:.1f}%)")

# Top countries by channel
print("\n2. Top Countries by Channel (bnb table):")
print("-" * 60)
channel_data = db.execute_query("""
    SELECT channel, country, COUNT(*) as count 
    FROM bnb 
    WHERE country IS NOT NULL 
    GROUP BY channel, country 
    ORDER BY channel, count DESC 
    LIMIT 30
""")
current_channel = None
for row in channel_data:
    if current_channel != row['channel']:
        current_channel = row['channel']
        print(f"\n{current_channel}:")
    print(f"  {row['country']:2s} - {row['count']:4d} bookings")

# Sample records
print("\n3. Sample Records with Country:")
print("-" * 60)
samples = db.execute_query("""
    SELECT id, channel, country, guestName, LEFT(phone, 15) as phone_sample
    FROM bnb 
    WHERE country IS NOT NULL 
    ORDER BY id DESC 
    LIMIT 10
""")
print(f"{'ID':>6s} | {'Channel':15s} | {'Country':7s} | {'Guest':20s} | {'Phone':15s}")
print("-" * 60)
for row in samples:
    phone = row['phone_sample'] if row['phone_sample'] else 'N/A'
    print(f"{row['id']:6d} | {row['channel']:15s} | {row['country']:7s} | {row['guestName'][:20]:20s} | {phone:15s}")

print("\n" + "="*60)
print("Verification Complete!")
print("="*60 + "\n")
