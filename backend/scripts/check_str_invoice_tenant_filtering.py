#!/usr/bin/env python3
"""
Check tenant filtering in STR Invoice Generator module
Tests all input/output points for proper tenant isolation
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("="*80)
print("STR INVOICE GENERATOR - TENANT FILTERING CHECK")
print("="*80)

# 1. Check vw_bnb_total view structure
print("\n1. Checking vw_bnb_total view structure:")
result = db.execute_query("""
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'finance' 
      AND TABLE_NAME = 'vw_bnb_total'
    ORDER BY ORDINAL_POSITION
""")
columns = [row['COLUMN_NAME'] for row in result]
print(f"   Columns: {', '.join(columns)}")
has_admin = 'administration' in columns
print(f"   ✅ Has 'administration' column: {has_admin}" if has_admin else "   ❌ Missing 'administration' column")

# 2. Check data distribution by tenant
print("\n2. Checking booking distribution by tenant:")
result = db.execute_query("""
    SELECT administration, COUNT(*) as count
    FROM vw_bnb_total
    GROUP BY administration
    ORDER BY administration
""")
total = 0
for row in result:
    print(f"   {row['administration']:30} : {row['count']:>6} bookings")
    total += row['count']
print(f"   {'TOTAL':30} : {total:>6} bookings")

# 3. Check recent bookings (last 90 days) by tenant
print("\n3. Checking recent bookings (last 90 days) by tenant:")
result = db.execute_query("""
    SELECT administration, COUNT(*) as count
    FROM vw_bnb_total
    WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
      AND checkinDate <= CURDATE()
    GROUP BY administration
    ORDER BY administration
""")
total = 0
for row in result:
    print(f"   {row['administration']:30} : {row['count']:>6} bookings")
    total += row['count']
print(f"   {'TOTAL':30} : {total:>6} bookings")

# 4. Check for bookings without administration
print("\n4. Checking for bookings without administration:")
result = db.execute_query("""
    SELECT COUNT(*) as count
    FROM vw_bnb_total
    WHERE administration IS NULL OR administration = ''
""")
orphan_count = result[0]['count']
if orphan_count > 0:
    print(f"   ❌ Found {orphan_count} bookings without administration")
else:
    print(f"   ✅ All bookings have administration assigned")

# 5. Sample bookings for GoodwinSolutions
print("\n5. Sample bookings for GoodwinSolutions (last 5):")
result = db.execute_query("""
    SELECT reservationCode, guestName, checkinDate, channel, administration
    FROM vw_bnb_total
    WHERE administration = 'GoodwinSolutions'
    ORDER BY checkinDate DESC
    LIMIT 5
""")
for row in result:
    print(f"   {row['reservationCode']:20} | {row['guestName']:30} | {row['checkinDate']} | {row['channel']:15} | {row['administration']}")

# 6. Sample bookings for PeterPrive
print("\n6. Sample bookings for PeterPrive (last 5):")
result = db.execute_query("""
    SELECT reservationCode, guestName, checkinDate, channel, administration
    FROM vw_bnb_total
    WHERE administration = 'PeterPrive'
    ORDER BY checkinDate DESC
    LIMIT 5
""")
if result:
    for row in result:
        print(f"   {row['reservationCode']:20} | {row['guestName']:30} | {row['checkinDate']} | {row['channel']:15} | {row['administration']}")
else:
    print("   No bookings found for PeterPrive")

# 7. Check future bookings
print("\n7. Checking future bookings by tenant:")
result = db.execute_query("""
    SELECT administration, COUNT(*) as count
    FROM vw_bnb_total
    WHERE checkinDate > CURDATE()
    GROUP BY administration
    ORDER BY administration
""")
if result:
    for row in result:
        print(f"   {row['administration']:30} : {row['count']:>6} future bookings")
else:
    print("   No future bookings found")

# 8. Test search query simulation (what the API does)
print("\n8. Simulating API search query for GoodwinSolutions:")
result = db.execute_query("""
    SELECT COUNT(*) as count
    FROM vw_bnb_total 
    WHERE (guestName LIKE %s OR reservationCode LIKE %s)
    AND administration = %s
    AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
    AND checkinDate <= CURDATE()
""", ('%2%', '%2%', 'GoodwinSolutions'))
print(f"   Query with '2' pattern: {result[0]['count']} bookings")

print("\n9. Simulating API search query for PeterPrive:")
result = db.execute_query("""
    SELECT COUNT(*) as count
    FROM vw_bnb_total 
    WHERE (guestName LIKE %s OR reservationCode LIKE %s)
    AND administration = %s
    AND checkinDate >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
    AND checkinDate <= CURDATE()
""", ('%2%', '%2%', 'PeterPrive'))
print(f"   Query with '2' pattern: {result[0]['count']} bookings")

print("\n" + "="*80)
print("TENANT FILTERING CHECK COMPLETE")
print("="*80)
