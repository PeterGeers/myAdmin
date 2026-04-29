#!/usr/bin/env python3
"""Quick script to check account 1022 registration in local database"""

import sys
sys.path.insert(0, 'src')

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("=" * 80)
print("Checking Account 1022 in Local Database (finance)")
print("=" * 80)

# Check rekeningschema columns
print("\n1. Checking rekeningschema columns:")
result = db.execute_query("SHOW COLUMNS FROM rekeningschema")
for col in result:
    print(f"   {col['Field']} ({col['Type']})")

# Check rekeningschema for account 1022
print("\n2. Checking rekeningschema for account 1022:")
result = db.execute_query("SELECT * FROM rekeningschema WHERE Account = '1022'")
if result:
    print(f"   ✓ Found: {result[0]}")
else:
    print("   ✗ Account 1022 NOT found")

# Check vw_rekeningnummers view definition
print("\n3. Checking vw_rekeningnummers view:")
try:
    result = db.execute_query("SHOW CREATE VIEW vw_rekeningnummers")
    if result:
        print(f"   View definition: {result[0].get('Create View', 'N/A')}")
except Exception as e:
    print(f"   Error: {e}")

# Check if account 1022 is in the view
print("\n4. Checking if account 1022 is in vw_rekeningnummers:")
try:
    result = db.execute_query("SELECT * FROM vw_rekeningnummers WHERE Account = '1022'")
    if result:
        print(f"   ✓ Found: {result}")
    else:
        print("   ✗ Account 1022 NOT found in view")
        # Show what IS in the view
        all_accounts = db.execute_query("SELECT DISTINCT Account FROM vw_rekeningnummers ORDER BY Account")
        accounts = [r['Account'] for r in all_accounts]
        print(f"   Accounts in view: {accounts}")
except Exception as e:
    print(f"   Error: {e}")

# Check mutaties for account 1022
print("\n5. Checking mutaties for account 1022 transactions:")
result = db.execute_query(
    "SELECT COUNT(*) as count FROM mutaties WHERE (Debet = '1022' OR Credit = '1022') AND administration = 'PeterPrive'"
)
if result:
    print(f"   Transaction count: {result[0]['count']}")

# Check pattern_verb_patterns
print("\n6. Checking pattern_verb_patterns for account 1022:")
result = db.execute_query(
    "SELECT COUNT(*) as count FROM pattern_verb_patterns WHERE bank_account = '1022'"
)
if result:
    print(f"   Pattern count: {result[0]['count']}")

# Show all bank_accounts in pattern table
print("\n7. All bank_accounts in pattern_verb_patterns:")
result = db.execute_query("SELECT DISTINCT bank_account FROM pattern_verb_patterns ORDER BY bank_account")
if result:
    accounts = [r['bank_account'] for r in result]
    print(f"   {accounts}")

print("\n" + "=" * 80)
