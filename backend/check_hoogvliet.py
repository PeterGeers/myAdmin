#!/usr/bin/env python3
"""Check Hoogvliet transactions for account 1022 vs 1003"""
import sys, json
sys.path.insert(0, 'src')
from database import DatabaseManager

db = DatabaseManager(test_mode=False)

print("=" * 80)
print("Checking HOOGVLIET transactions")
print("=" * 80)

# Check Hoogvliet transactions for account 1022
print("\n1. HOOGVLIET transactions involving account 1022:")
result = db.execute_query(
    "SELECT TransactionDescription, Debet, Credit, ReferenceNumber, Ref1 "
    "FROM mutaties WHERE (Debet = '1022' OR Credit = '1022') "
    "AND UPPER(TransactionDescription) LIKE '%HOOGVLIET%' LIMIT 5"
)
for r in result:
    print(f"   Desc: {r['TransactionDescription'][:60]}")
    print(f"   Debet: {r['Debet']}, Credit: {r['Credit']}, Ref: {r['ReferenceNumber']}, Ref1: {r['Ref1']}")
    print()
if not result:
    print("   NONE FOUND!")

# Check Hoogvliet transactions for account 1003
print("\n2. HOOGVLIET transactions involving account 1003:")
result = db.execute_query(
    "SELECT TransactionDescription, Debet, Credit, ReferenceNumber, Ref1 "
    "FROM mutaties WHERE (Debet = '1003' OR Credit = '1003') "
    "AND UPPER(TransactionDescription) LIKE '%HOOGVLIET%' LIMIT 5"
)
for r in result:
    print(f"   Desc: {r['TransactionDescription'][:60]}")
    print(f"   Debet: {r['Debet']}, Credit: {r['Credit']}, Ref: {r['ReferenceNumber']}, Ref1: {r['Ref1']}")
    print()
if not result:
    print("   NONE FOUND!")

# Check pattern_verb_patterns for HOOGVLIET
print("\n3. HOOGVLIET in pattern_verb_patterns:")
result = db.execute_query(
    "SELECT bank_account, verb, reference_number, debet_account, credit_account, occurrences "
    "FROM pattern_verb_patterns WHERE UPPER(verb) LIKE '%HOOGVLIET%'"
)
for r in result:
    print(f"   bank_account: {r['bank_account']}, verb: {r['verb']}, ref: {r['reference_number']}, "
          f"debet: {r['debet_account']}, credit: {r['credit_account']}, occ: {r['occurrences']}")
if not result:
    print("   NONE FOUND!")

# Check what patterns exist for account 1022 (sample)
print("\n4. Sample patterns for bank_account 1022 (first 10):")
result = db.execute_query(
    "SELECT verb, reference_number, debet_account, credit_account, occurrences "
    "FROM pattern_verb_patterns WHERE bank_account = '1022' LIMIT 10"
)
for r in result:
    print(f"   verb: {r['verb']}, ref: {r['reference_number']}, "
          f"debet: {r['debet_account']}, credit: {r['credit_account']}, occ: {r['occurrences']}")
if not result:
    print("   NONE FOUND!")

print("\n" + "=" * 80)
