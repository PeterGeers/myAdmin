"""
Country Lookup Test Script

This is a standalone test script, not a pytest test file.
Run it directly with: python scripts/test_country_lookup.py
"""

# Prevent pytest from collecting this file
__test__ = False

import sys
from pathlib import Path
import mysql.connector
import os

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

def run_tests():
    """Run the country lookup tests"""
    load_dotenv()

    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("Country Lookup Table Test")
    print("="*80 + "\n")

    # Test 1: Show all countries in lookup table
    print("1. Countries Lookup Table (first 20):")
    print("-" * 80)
    cursor.execute("SELECT code, name, name_nl, region FROM countries ORDER BY name LIMIT 20")
    print(f"{'Code':4s} | {'English Name':25s} | {'Dutch Name':25s} | {'Region':15s}")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"{row[0]:4s} | {row[1]:25s} | {row[2] or 'N/A':25s} | {row[3] or 'N/A':15s}")

    # Test 2: Query view with country names
    print("\n2. Sample Bookings with Country Names (from view):")
    print("-" * 80)
    cursor.execute("""
        SELECT id, channel, country, countryName, countryNameNL, guestName
        FROM vw_bnb_total
        WHERE country IS NOT NULL
        ORDER BY id DESC
        LIMIT 10
    """)
    print(f"{'ID':>6s} | {'Channel':12s} | {'Code':4s} | {'English':15s} | {'Dutch':15s} | {'Guest':20s}")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"{row[0]:6d} | {row[1]:12s} | {row[2]:4s} | {row[3] or 'N/A':15s} | {row[4] or 'N/A':15s} | {row[5][:20]:20s}")

    # Test 3: Bookings by country with names
    print("\n3. Top 15 Countries by Booking Count:")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            country, 
            countryName, 
            countryNameNL,
            countryRegion,
            COUNT(*) as bookings
        FROM vw_bnb_total
        WHERE country IS NOT NULL
        GROUP BY country, countryName, countryNameNL, countryRegion
        ORDER BY bookings DESC
        LIMIT 15
    """)
    print(f"{'Code':4s} | {'English Name':20s} | {'Dutch Name':20s} | {'Region':15s} | {'Count':>6s}")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"{row[0]:4s} | {row[1]:20s} | {row[2] or 'N/A':20s} | {row[3] or 'N/A':15s} | {row[4]:6d}")

    # Test 4: Bookings by region
    print("\n4. Bookings by Region:")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            countryRegion,
            COUNT(*) as bookings
        FROM vw_bnb_total
        WHERE countryRegion IS NOT NULL
        GROUP BY countryRegion
        ORDER BY bookings DESC
    """)
    print(f"{'Region':20s} | {'Bookings':>8s}")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"{row[0]:20s} | {row[1]:8d}")

    cursor.close()
    conn.close()

    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_tests()
