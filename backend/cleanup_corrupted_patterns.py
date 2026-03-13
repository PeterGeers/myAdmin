#!/usr/bin/env python3
"""
Cleanup script to remove corrupted patterns and regenerate from real data

The test file created fake transactions that corrupted the pattern_verb_patterns table.
This script will:
1. Delete ALL patterns for PeterPrive administration
2. Re-run pattern analysis on real transaction data
3. Verify patterns are correct
"""

import sys
sys.path.insert(0, 'src')

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer

db = DatabaseManager(test_mode=False)
analyzer = PatternAnalyzer(test_mode=False)

print("=" * 80)
print("CLEANUP: Removing Corrupted Patterns and Regenerating from Real Data")
print("=" * 80)

# Step 1: Delete test transactions
print("\n1. Deleting test transactions...")
result = db.execute_query(
    "DELETE FROM mutaties WHERE TransactionDescription LIKE '%TEST_ACCOUNT_1022%'",
    (),
    fetch=False,
    commit=True
)
print("   ✓ Test transactions deleted")

# Step 2: Delete ALL patterns for PeterPrive
print("\n2. Deleting ALL patterns for PeterPrive administration...")
result = db.execute_query(
    "DELETE FROM pattern_verb_patterns WHERE administration = 'PeterPrive'",
    (),
    fetch=False,
    commit=True
)
print("   ✓ All patterns deleted")

# Step 3: Re-run pattern analysis on real data
print("\n3. Re-running pattern analysis on real transaction data...")
result = analyzer.analyze_historical_patterns('PeterPrive')
print(f"   ✓ Analysis complete:")
print(f"      - Total transactions analyzed: {result['total_transactions']}")
print(f"      - Patterns discovered: {result['patterns_discovered']}")

# Step 4: Verify HOOGVLIET patterns are correct
print("\n4. Verifying HOOGVLIET patterns...")
patterns = db.execute_query(
    "SELECT bank_account, verb, reference_number, debet_account, credit_account, occurrences "
    "FROM pattern_verb_patterns WHERE verb = 'HOOGVLIET' OR verb LIKE 'HOOGVLIET%'"
)

if patterns:
    for p in patterns:
        print(f"   Pattern found:")
        print(f"      bank_account: {p['bank_account']}")
        print(f"      verb: {p['verb']}")
        print(f"      reference_number: {p['reference_number']}")
        print(f"      debet_account: {p['debet_account']}")
        print(f"      credit_account: {p['credit_account']}")
        print(f"      occurrences: {p['occurrences']}")
        print()
        
        # Verify correctness
        if p['bank_account'] == '1003' and p['debet_account'] == '4001' and p['credit_account'] == '1003':
            print(f"   ✓ Pattern is CORRECT!")
        else:
            print(f"   ❌ Pattern is INCORRECT!")
else:
    print("   ❌ No HOOGVLIET patterns found!")

# Step 5: Check account 1022 patterns
print("\n5. Checking account 1022 patterns...")
patterns_1022 = db.execute_query(
    "SELECT COUNT(*) as count FROM pattern_verb_patterns WHERE bank_account = '1022'"
)
count = patterns_1022[0]['count'] if patterns_1022 else 0
print(f"   Patterns for account 1022: {count}")

if count > 0:
    # Show sample
    sample = db.execute_query(
        "SELECT verb, reference_number, debet_account, credit_account FROM pattern_verb_patterns "
        "WHERE bank_account = '1022' LIMIT 5"
    )
    for s in sample:
        print(f"      - {s['verb']}: debet={s['debet_account']}, credit={s['credit_account']}")

print("\n" + "=" * 80)
print("CLEANUP COMPLETE!")
print("=" * 80)
