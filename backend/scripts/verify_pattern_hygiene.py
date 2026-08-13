#!/usr/bin/env python3
"""
Verify Pattern Data Hygiene (Task 1.4)

This script verifies that the pattern data hygiene fixes work correctly:
1. Connects to the database
2. Picks one administration that has existing patterns
3. Records existing pattern counts and occurrences before running
4. Runs a full pattern analysis via PatternAnalyzer.analyze_historical_patterns()
5. After analysis, checks:
   - No patterns with last_seen older than 1 year (stale cleanup works)
   - Occurrence counts match actual transaction counts (not doubled)
6. Reports results

Requirements validated: 0.1 (replace occurrences), 0.2 (stale pattern removal)
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer


def get_administration_with_patterns(db: DatabaseManager) -> str | None:
    """Find an administration that has existing patterns in the database."""
    result = db.execute_query(
        """
        SELECT administration, COUNT(*) as pattern_count
        FROM pattern_verb_patterns
        GROUP BY administration
        ORDER BY pattern_count DESC
        LIMIT 1
        """
    )
    if result:
        return result[0]["administration"]
    return None


def get_pattern_snapshot(db: DatabaseManager, administration: str) -> dict:
    """Capture current pattern state for comparison."""
    patterns = db.execute_query(
        """
        SELECT verb, reference_number, occurrences, confidence, last_seen,
               debet_account, credit_account, bank_account
        FROM pattern_verb_patterns
        WHERE administration = %s
        ORDER BY verb
        """,
        (administration,),
    )

    total_count = len(patterns)
    total_occurrences = sum(p["occurrences"] for p in patterns)

    # Find stale patterns (last_seen > 1 year ago)
    one_year_ago = datetime.now() - timedelta(days=365)
    stale_patterns = [
        p for p in patterns
        if p["last_seen"] and p["last_seen"] < one_year_ago.date()
    ]

    # Get occurrence distribution
    occurrence_values = sorted([p["occurrences"] for p in patterns], reverse=True)
    top_10 = occurrence_values[:10] if occurrence_values else []

    return {
        "total_count": total_count,
        "total_occurrences": total_occurrences,
        "stale_count": len(stale_patterns),
        "stale_patterns": stale_patterns[:5],  # Sample of stale ones
        "top_occurrences": top_10,
        "patterns": patterns,
    }


def get_actual_transaction_counts(db: DatabaseManager, administration: str) -> dict:
    """
    Get actual transaction counts per verb from mutaties for the last year.
    This allows us to compare pattern occurrences against real data.
    """
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    # Count transactions per description pattern (simplified — just total count)
    result = db.execute_query(
        """
        SELECT COUNT(*) as tx_count
        FROM mutaties
        WHERE administration = %s
          AND TransactionDate >= %s
          AND (Debet IS NOT NULL OR Credit IS NOT NULL)
        """,
        (administration, one_year_ago),
    )

    total_transactions = result[0]["tx_count"] if result else 0

    return {
        "total_transactions": total_transactions,
        "date_from": one_year_ago,
    }


def verify_occurrences_reasonable(
    before: dict, after: dict, tx_info: dict
) -> tuple[bool, list[str]]:
    """
    Check that occurrence counts are reasonable (not doubled).

    A pattern's occurrence count should never exceed the total number of
    transactions in the analysis window. If it does, accumulation is happening.
    """
    issues = []
    total_tx = tx_info["total_transactions"]

    for pattern in after["patterns"]:
        if pattern["occurrences"] > total_tx:
            issues.append(
                f"  Pattern '{pattern['verb']}' has {pattern['occurrences']} occurrences "
                f"but only {total_tx} total transactions exist — likely doubled!"
            )

    # Check that total occurrences didn't roughly double
    if before["total_occurrences"] > 0 and after["total_occurrences"] > 0:
        ratio = after["total_occurrences"] / before["total_occurrences"]
        if ratio > 1.8:
            issues.append(
                f"  Total occurrences grew by {ratio:.1f}x "
                f"({before['total_occurrences']} → {after['total_occurrences']}). "
                f"Possible accumulation bug!"
            )

    return len(issues) == 0, issues


def main():
    print("=" * 70)
    print("🔍 Pattern Data Hygiene Verification (Task 1.4)")
    print("=" * 70)
    print()

    # Step 1: Connect to database
    print("Step 1: Connecting to database...")
    try:
        db = DatabaseManager(test_mode=False)
        print("  ✅ Connected to database")
    except Exception as e:
        print(f"  ❌ Failed to connect: {e}")
        sys.exit(1)

    # Step 2: Find an administration with patterns
    print("\nStep 2: Finding administration with existing patterns...")
    administration = get_administration_with_patterns(db)
    if not administration:
        print("  ❌ No administrations found with patterns. Nothing to verify.")
        sys.exit(0)
    print(f"  ✅ Using administration: '{administration}'")

    # Step 3: Record state BEFORE analysis
    print("\nStep 3: Recording pattern state before analysis...")
    before = get_pattern_snapshot(db, administration)
    tx_info = get_actual_transaction_counts(db, administration)
    print(f"  Patterns: {before['total_count']}")
    print(f"  Total occurrences: {before['total_occurrences']}")
    print(f"  Stale patterns (last_seen > 1yr): {before['stale_count']}")
    print(f"  Transactions in last year: {tx_info['total_transactions']}")
    print(f"  Top 10 occurrence values: {before['top_occurrences']}")

    if before["stale_count"] > 0:
        print(f"\n  Sample stale patterns:")
        for p in before["stale_patterns"]:
            print(f"    - '{p['verb']}' last_seen={p['last_seen']}, occ={p['occurrences']}")

    # Step 4: Run full pattern analysis
    print("\nStep 4: Running full pattern analysis...")
    analyzer = PatternAnalyzer(test_mode=False)
    try:
        result = analyzer.analyze_historical_patterns(administration)
        print(f"  ✅ Analysis complete:")
        print(f"     Transactions processed: {result['total_transactions']}")
        print(f"     Patterns discovered: {result['patterns_discovered']}")
        print(f"     Date range: {result.get('date_range', {}).get('from')} to {result.get('date_range', {}).get('to')}")
    except Exception as e:
        print(f"  ❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 5: Check results
    print("\nStep 5: Verifying results...")
    after = get_pattern_snapshot(db, administration)

    print(f"\n  --- Before vs After ---")
    print(f"  Patterns:       {before['total_count']} → {after['total_count']}")
    print(f"  Occurrences:    {before['total_occurrences']} → {after['total_occurrences']}")
    print(f"  Stale patterns: {before['stale_count']} → {after['stale_count']}")

    # Check 5a: No stale patterns remain
    print(f"\n  Check 5a: Stale patterns (last_seen > 1 year) removed?")
    if after["stale_count"] == 0:
        print(f"    ✅ PASS — No stale patterns remain")
    else:
        print(f"    ❌ FAIL — {after['stale_count']} stale patterns still exist!")
        for p in after["stale_patterns"]:
            print(f"      - '{p['verb']}' last_seen={p['last_seen']}")

    # Check 5b: Occurrence counts are reasonable (not doubled)
    print(f"\n  Check 5b: Occurrence counts reasonable (not doubled)?")
    occ_ok, occ_issues = verify_occurrences_reasonable(before, after, tx_info)
    if occ_ok:
        print(f"    ✅ PASS — Occurrence counts look reasonable")
        print(f"    Max single pattern occurrence: {max(after['top_occurrences']) if after['top_occurrences'] else 0}")
        print(f"    Total transactions in window:  {tx_info['total_transactions']}")
    else:
        print(f"    ❌ FAIL — Occurrence count issues detected:")
        for issue in occ_issues:
            print(issue)

    # Step 6: Summary
    print("\n" + "=" * 70)
    all_pass = after["stale_count"] == 0 and occ_ok
    if all_pass:
        print("✅ ALL CHECKS PASSED — Pattern data hygiene is working correctly")
    else:
        print("❌ SOME CHECKS FAILED — Review issues above")
    print("=" * 70)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
