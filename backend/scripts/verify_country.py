"""Verify country backfill results"""
import mysql.connector
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

print("\n" + "="*60)
print("Country Detection Verification")
print("="*60 + "\n")

# Overall statistics
print("1. Overall Statistics:")
print("-" * 60)
cursor.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN country IS NOT NULL THEN 1 ELSE 0 END) as with_country,
        SUM(CASE WHEN country IS NULL THEN 1 ELSE 0 END) as without_country
    FROM bnb
""")
row = cursor.fetchone()
print(f"Total records:        {row[0]}")
print(f"With country:         {row[1]} ({row[1]/row[0]*100:.1f}%)")
print(f"Without country:      {row[2]} ({row[2]/row[0]*100:.1f}%)")

# Top countries by channel
print("\n2. Top Countries by Channel (bnb table):")
print("-" * 60)
cursor.execute("""
    SELECT channel, country, COUNT(*) as count 
    FROM bnb 
    WHERE country IS NOT NULL 
    GROUP BY channel, country 
    ORDER BY channel, count DESC 
    LIMIT 30
""")
current_channel = None
for row in cursor.fetchall():
    if current_channel != row[0]:
        current_channel = row[0]
        print(f"\n{current_channel}:")
    print(f"  {row[1]:2s} - {row[2]:4d} bookings")

# Sample records
print("\n3. Sample Records with Country:")
print("-" * 60)
cursor.execute("""
    SELECT id, channel, country, guestName, LEFT(phone, 15) as phone_sample
    FROM bnb 
    WHERE country IS NOT NULL 
    ORDER BY id DESC 
    LIMIT 10
""")
print(f"{'ID':>6s} | {'Channel':15s} | {'Country':7s} | {'Guest':20s} | {'Phone':15s}")
print("-" * 60)
for row in cursor.fetchall():
    print(f"{row[0]:6d} | {row[1]:15s} | {row[2]:7s} | {row[3][:20]:20s} | {row[4] if row[4] else 'N/A':15s}")

cursor.close()
conn.close()

print("\n" + "="*60)
print("Verification Complete!")
print("="*60 + "\n")
