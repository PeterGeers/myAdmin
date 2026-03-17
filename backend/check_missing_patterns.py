#!/usr/bin/env python3
"""Check which patterns are missing for account 1022"""
import sys
sys.path.insert(0, 'src')
from database import DatabaseManager

db = DatabaseManager(test_mode=False)

vendors = ['HOOGVLIET', 'TMC', 'VOSSENBERG', 'FUNMANIA']

print("=" * 80)
print("Checking patterns for account 1022 vs 1003")
print("=" * 80)

for vendor in vendors:
    print(f"\n{'=' * 80}")
    print(f"Vendor: {vendor}")
    print('=' * 80)
    
    # Check transactions for 1022
    print(f"\n1. {vendor} transactions for account 1022:")
    result = db.execute_query(
        f"SELECT COUNT(*) as count FROM mutaties "
        f"WHERE (Debet = '1022' OR Credit = '1022') "
        f"AND UPPER(TransactionDescription) LIKE '%{vendor}%'"
    )
    count_1022 = result[0]['count'] if result else 0
    print(f"   Transaction count: {count_1022}")
    
    if count_1022 > 0:
        # Show sample
        sample = db.execute_query(
            f"SELECT TransactionDescription, Debet, Credit, ReferenceNumber "
            f"FROM mutaties WHERE (Debet = '1022' OR Credit = '1022') "
            f"AND UPPER(TransactionDescription) LIKE '%{vendor}%' LIMIT 1"
        )
        if sample:
            print(f"   Sample: {sample[0]['TransactionDescription'][:50]}")
            print(f"   Debet: {sample[0]['Debet']}, Credit: {sample[0]['Credit']}, Ref: {sample[0]['ReferenceNumber']}")
    
    # Check patterns for 1022
    print(f"\n2. {vendor} patterns for bank_account 1022:")
    result = db.execute_query(
        f"SELECT verb, reference_number, debet_account, credit_account, occurrences "
        f"FROM pattern_verb_patterns WHERE bank_account = '1022' "
        f"AND UPPER(verb) LIKE '%{vendor}%'"
    )
    if result:
        for r in result:
            print(f"   ✓ FOUND: verb={r['verb']}, ref={r['reference_number']}, occ={r['occurrences']}")
    else:
        print(f"   ✗ NO PATTERN FOUND")
    
    # Check transactions for 1003
    print(f"\n3. {vendor} transactions for account 1003:")
    result = db.execute_query(
        f"SELECT COUNT(*) as count FROM mutaties "
        f"WHERE (Debet = '1003' OR Credit = '1003') "
        f"AND UPPER(TransactionDescription) LIKE '%{vendor}%'"
    )
    count_1003 = result[0]['count'] if result else 0
    print(f"   Transaction count: {count_1003}")
    
    # Check patterns for 1003
    print(f"\n4. {vendor} patterns for bank_account 1003:")
    result = db.execute_query(
        f"SELECT COUNT(*) as count FROM pattern_verb_patterns "
        f"WHERE bank_account = '1003' AND UPPER(verb) LIKE '%{vendor}%'"
    )
    count_patterns_1003 = result[0]['count'] if result else 0
    print(f"   Pattern count: {count_patterns_1003}")
    
    # Summary
    print(f"\n5. Summary for {vendor}:")
    if count_1022 > 0:
        print(f"   Account 1022: {count_1022} transactions, patterns: {'YES' if result else 'NO'}")
    if count_1003 > 0:
        print(f"   Account 1003: {count_1003} transactions, {count_patterns_1003} patterns")

print("\n" + "=" * 80)
