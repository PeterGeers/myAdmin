"""
Country Lookup Test Script

This is a standalone test script, not a pytest test file.
Run it directly with: python scripts/test_country_lookup.py
"""

# Prevent pytest from collecting this file
__test__ = False

import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from dotenv import load_dotenv
from database import DatabaseManager

def run_tests():
    """Run the country lookup tests"""
    load_dotenv()

    db = DatabaseManager()

    print("\n" + "="*80)
    print("Country Lookup Table Test")
    print("="*80 + "\n")

    # Test 1: Show all countries in lookup table
    print("1. Countries Lookup Table (first 20):")
    print("-" * 80)
    countries = db.execute_query(
        "SELECT code, name, name_nl, region FROM countries ORDER BY name LIMIT 20"
    )
    print(f"{'Code':4s} | {'English Name':25s} | {'Dutch Name':25s} | {'Region':15s}")
    print("-" * 80)
    for row in countries:
        print(f"{row['code']:4s} | {row['name']:25s} | {row['name_nl'] or 'N/A':25s} | {row['region'] or 'N/A':15s}")

    # Test 2: Query view with country names
    print("\n2. Sample Bookings with Country Names (from view):")
    print("-" * 80)
    bookings = db.execute_query("""
        SELECT id, channel, country, countryName, countryNameNL, guestName
        FROM vw_bnb_total
        WHERE country IS NOT NULL
        ORDER BY id DESC
        LIMIT 10
    """)
    print(f"{'ID':>6s} | {'Channel':12s} | {'Code':4s} | {'English':15s} | {'Dutch':15s} | {'Guest':20s}")
    print("-" * 80)
    for row in bookings:
        print(f"{row['id']:6d} | {row['channel']:12s} | {row['country']:4s} | {row['countryName'] or 'N/A':15s} | {row['countryNameNL'] or 'N/A':15s} | {row['guestName'][:20]:20s}")

    # Test 3: Bookings by country with names
    print("\n3. Top 15 Countries by Booking Count:")
    print("-" * 80)
    top_countries = db.execute_query("""
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
    for row in top_countries:
        print(f"{row['country']:4s} | {row['countryName']:20s} | {row['countryNameNL'] or 'N/A':20s} | {row['countryRegion'] or 'N/A':15s} | {row['bookings']:6d}")

    # Test 4: Bookings by region
    print("\n4. Bookings by Region:")
    print("-" * 80)
    regions = db.execute_query("""
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
    for row in regions:
        print(f"{row['countryRegion']:20s} | {row['bookings']:8d}")

    print("\n" + "="*80)
    print("Test Complete!")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_tests()
