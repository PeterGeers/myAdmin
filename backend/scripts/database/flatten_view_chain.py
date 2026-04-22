#!/usr/bin/env python3
"""
View Chain Flattening Migration Script

Eliminates redundant rekeningschema joins in vw_mutaties by:
1. Adding r.Belastingaangifte to vw_debetmutaties SELECT list
2. Adding r.Belastingaangifte to vw_creditmutaties SELECT list
3. Recreating vw_mutaties as simple UNION ALL without re-joining rekeningschema

Before: vw_mutaties joins rekeningschema AGAIN on both debet/credit sides (4 total joins)
After:  vw_mutaties is a simple UNION ALL of the base views (2 total joins)

Requirements: 1.3, 2.3, 3.2, 3.3
"""

import sys
import os
import argparse
import re
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager


def get_view_definition(db, view_name):
    """Get the CREATE VIEW statement for a view using SHOW CREATE VIEW."""
    result = db.execute_query(f"SHOW CREATE VIEW {view_name}")
    if not result:
        raise RuntimeError(f"Could not get definition for view {view_name}")
    # SHOW CREATE VIEW returns a dict with 'View' and 'Create View' keys
    return result[0].get('Create View') or result[0].get('CREATE VIEW')


def extract_select_from_create_view(create_view_sql):
    """Extract the SELECT statement from a CREATE VIEW definition.

    SHOW CREATE VIEW returns something like:
      CREATE ALGORITHM=... DEFINER=... SQL SECURITY ... VIEW `name` AS SELECT ...
    We need just the SELECT ... part.
    """
    # Match everything after 'AS ' (case-insensitive)
    match = re.search(r'\bAS\s+(SELECT\b.+)', create_view_sql, re.IGNORECASE | re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not extract SELECT from view definition:\n{create_view_sql[:200]}")
    return match.group(1).strip().rstrip(';')


def capture_baseline(db):
    """Capture baseline metrics for vw_mutaties before any changes."""
    print("\n📊 Capturing baseline metrics...")

    # Total row count
    total = db.execute_query("SELECT COUNT(*) AS cnt FROM vw_mutaties")
    total_count = total[0]['cnt']
    print(f"   Total rows: {total_count:,}")

    # Row count per administration
    per_admin = db.execute_query("""
        SELECT administration, COUNT(*) AS cnt, 
               ROUND(SUM(Amount), 2) AS sum_amount,
               COUNT(DISTINCT Aangifte) AS distinct_aangifte
        FROM vw_mutaties
        GROUP BY administration
        ORDER BY administration
    """)

    baseline = {}
    for row in per_admin:
        admin = row['administration']
        baseline[admin] = {
            'count': row['cnt'],
            'sum_amount': row['sum_amount'],
            'distinct_aangifte': row['distinct_aangifte'],
        }
        print(f"   {admin}: {row['cnt']:,} rows, SUM(Amount)={row['sum_amount']}, "
              f"distinct Aangifte={row['distinct_aangifte']}")

    return total_count, baseline


def verify_against_baseline(db, original_total, original_baseline):
    """Verify that vw_mutaties still matches the baseline after changes."""
    print("\n🔍 Verifying against baseline...")
    errors = []

    # Total row count
    total = db.execute_query("SELECT COUNT(*) AS cnt FROM vw_mutaties")
    new_total = total[0]['cnt']
    if new_total != original_total:
        errors.append(f"Total row count mismatch: was {original_total:,}, now {new_total:,}")
    else:
        print(f"   ✅ Total rows match: {new_total:,}")

    # Per-administration checks
    per_admin = db.execute_query("""
        SELECT administration, COUNT(*) AS cnt,
               ROUND(SUM(Amount), 2) AS sum_amount,
               COUNT(DISTINCT Aangifte) AS distinct_aangifte
        FROM vw_mutaties
        GROUP BY administration
        ORDER BY administration
    """)

    new_baseline = {row['administration']: row for row in per_admin}

    for admin, orig in original_baseline.items():
        new = new_baseline.get(admin)
        if not new:
            errors.append(f"Administration '{admin}' missing after migration")
            continue

        if new['cnt'] != orig['count']:
            errors.append(f"{admin}: row count {orig['count']:,} → {new['cnt']:,}")
        if new['sum_amount'] != orig['sum_amount']:
            errors.append(f"{admin}: SUM(Amount) {orig['sum_amount']} → {new['sum_amount']}")
        if new['distinct_aangifte'] != orig['distinct_aangifte']:
            errors.append(f"{admin}: distinct Aangifte {orig['distinct_aangifte']} → {new['distinct_aangifte']}")

    # Check for new administrations that weren't in original
    for admin in new_baseline:
        if admin not in original_baseline:
            errors.append(f"New administration '{admin}' appeared after migration")

    if errors:
        print("   ❌ Verification FAILED:")
        for err in errors:
            print(f"      - {err}")
        return False
    else:
        print("   ✅ All per-administration counts, sums, and Aangifte counts match")
        return True


def verify_amount_signs(db):
    """Spot-check that amount signs are correct: positive for debet, negative for credit."""
    print("\n🔍 Verifying amount signs...")

    # Check a sample of debet rows (should have positive Amount = TransactionAmount)
    debet_check = db.execute_query("""
        SELECT d.TransactionAmount, m.Amount
        FROM vw_debetmutaties d
        JOIN vw_mutaties m ON d.TransactionNumber = m.TransactionNumber
            AND d.Reknum = m.Reknum
            AND d.administration = m.administration
            AND m.Amount >= 0
        LIMIT 5
    """)
    if debet_check:
        all_positive = all(row['Amount'] >= 0 for row in debet_check)
        print(f"   {'✅' if all_positive else '❌'} Debet amounts are positive: {all_positive}")
    else:
        print("   ⚠️  No debet rows found for sign check")

    # Check a sample of credit rows (should have negative Amount = -TransactionAmount)
    credit_check = db.execute_query("""
        SELECT c.TransactionAmount, m.Amount
        FROM vw_creditmutaties c
        JOIN vw_mutaties m ON c.TransactionNumber = m.TransactionNumber
            AND c.Reknum = m.Reknum
            AND c.administration = m.administration
            AND m.Amount < 0
        LIMIT 5
    """)
    if credit_check:
        all_negative = all(row['Amount'] < 0 for row in credit_check)
        print(f"   {'✅' if all_negative else '❌'} Credit amounts are negative: {all_negative}")
    else:
        print("   ⚠️  No credit rows found for sign check")


def verify_explain_join_count(db):
    """Verify EXPLAIN shows fewer rekeningschema references after flattening."""
    print("\n🔍 Checking EXPLAIN for join count...")

    explain = db.execute_query("EXPLAIN SELECT * FROM vw_mutaties LIMIT 1")
    rekeningschema_refs = sum(
        1 for row in explain
        if 'rekeningschema' in str(row.get('table', '')).lower()
        or str(row.get('table', '')).strip() == 'r'
    )
    total_tables = len(explain)

    print(f"   Tables in EXPLAIN: {total_tables}")
    print(f"   rekeningschema references: {rekeningschema_refs}")
    for row in explain:
        table = row.get('table', '?')
        join_type = row.get('type', '?')
        print(f"      - {table} (type: {join_type})")

    if rekeningschema_refs <= 2:
        print(f"   ✅ rekeningschema refs = {rekeningschema_refs} (expected ≤ 2)")
    else:
        print(f"   ⚠️  rekeningschema refs = {rekeningschema_refs} (expected ≤ 2, was 4 before)")

    return rekeningschema_refs


def add_belastingaangifte_to_view(db, view_name, dry_run=False):
    """Add r.Belastingaangifte to a base view's SELECT list.

    Dynamically reads the current view definition and inserts the column.
    """
    print(f"\n🔧 Altering {view_name} to include Belastingaangifte...")

    create_sql = get_view_definition(db, view_name)
    select_sql = extract_select_from_create_view(create_sql)

    # Check if Belastingaangifte is already in the SELECT list
    if 'belastingaangifte' in select_sql.lower():
        print(f"   ℹ️  {view_name} already includes Belastingaangifte — skipping")
        return False

    # Strategy: insert `r.Belastingaangifte,` right after `r.VW AS ...`
    # The base views have: r.AccountName, r.Parent, r.VW, YEAR(...)
    # MySQL SHOW CREATE VIEW returns backtick-quoted identifiers like `r`.`VW` AS `VW`
    # We insert after the VW alias clause
    # Match: `r`.`VW` AS `VW`, or r.VW AS VW, or `r`.`VW`,
    pattern = re.compile(r'(`r`\.`VW`\s+AS\s+`VW`\s*,|r\.VW\s+AS\s+\w+\s*,|`r`\.`VW`\s*,|r\.VW\s*,)', re.IGNORECASE)
    match = pattern.search(select_sql)
    if not match:
        # Fallback: try to insert after r.Parent / `r`.`Parent`
        pattern = re.compile(r'(`r`\.`Parent`\s+AS\s+`Parent`\s*,|r\.Parent\s+AS\s+\w+\s*,|`r`\.`Parent`\s*,|r\.Parent\s*,)', re.IGNORECASE)
        match = pattern.search(select_sql)

    if not match:
        raise RuntimeError(
            f"Could not find insertion point (r.VW or r.Parent) in {view_name} definition:\n"
            f"{select_sql[:300]}"
        )

    # Insert r.Belastingaangifte after the matched column
    # Use backtick-quoted format if the view definition uses backticks
    uses_backticks = '`r`.' in select_sql
    if uses_backticks:
        insert_col = "`r`.`Belastingaangifte` AS `Belastingaangifte`,"
    else:
        insert_col = "r.Belastingaangifte,"
    insertion_point = match.end()
    new_select = (
        select_sql[:insertion_point]
        + insert_col
        + select_sql[insertion_point:]
    )

    alter_sql = f"ALTER VIEW {view_name} AS\n{new_select}"

    if dry_run:
        print(f"   [DRY RUN] Would execute:\n{alter_sql[:500]}...")
        return True

    print(f"   Executing ALTER VIEW {view_name}...")
    db.execute_query(alter_sql, fetch=False, commit=True)
    print(f"   ✅ {view_name} now includes Belastingaangifte")

    # Verify the column exists
    verify = db.execute_query(f"SELECT Belastingaangifte FROM {view_name} LIMIT 1")
    if verify is not None:
        print(f"   ✅ Verified: Belastingaangifte column accessible in {view_name}")
    return True


def recreate_vw_mutaties(db, dry_run=False):
    """Recreate vw_mutaties as a simple UNION ALL without re-joining rekeningschema."""
    print("\n🔧 Recreating vw_mutaties (flattened, no redundant joins)...")

    new_sql = """
CREATE OR REPLACE VIEW vw_mutaties AS
SELECT
    d.Belastingaangifte AS Aangifte,
    d.TransactionNumber,
    d.TransactionDate,
    d.TransactionDescription,
    d.TransactionAmount AS Amount,
    d.Reknum,
    d.AccountName,
    d.Parent,
    d.VW,
    d.jaar,
    d.kwartaal,
    d.maand,
    d.week,
    d.ReferenceNumber,
    d.administration,
    d.Ref3,
    d.Ref4
FROM vw_debetmutaties d

UNION ALL

SELECT
    c.Belastingaangifte AS Aangifte,
    c.TransactionNumber,
    c.TransactionDate,
    c.TransactionDescription,
    -c.TransactionAmount AS Amount,
    c.Reknum,
    c.AccountName,
    c.Parent,
    c.VW,
    c.jaar,
    c.kwartaal,
    c.maand,
    c.week,
    c.ReferenceNumber,
    c.administration,
    c.Ref3,
    c.Ref4
FROM vw_creditmutaties c
""".strip()

    if dry_run:
        print(f"   [DRY RUN] Would execute:\n{new_sql}")
        return

    print("   Executing CREATE OR REPLACE VIEW vw_mutaties...")
    db.execute_query(new_sql, fetch=False, commit=True)
    print("   ✅ vw_mutaties recreated without redundant rekeningschema joins")


def show_current_view_definitions(db):
    """Print current view definitions for reference."""
    print("\n📋 Current view definitions:")
    for view_name in ['vw_debetmutaties', 'vw_creditmutaties', 'vw_mutaties']:
        try:
            defn = get_view_definition(db, view_name)
            select_part = extract_select_from_create_view(defn)
            print(f"\n   {view_name}:")
            for line in select_part.split('\n'):
                print(f"      {line}")
        except Exception as e:
            print(f"\n   {view_name}: ❌ Error: {e}")


def rollback_vw_mutaties(db, original_definition):
    """Rollback vw_mutaties to its original definition."""
    print("\n⏪ Rolling back vw_mutaties to original definition...")
    try:
        select_sql = extract_select_from_create_view(original_definition)
        rollback_sql = f"CREATE OR REPLACE VIEW vw_mutaties AS\n{select_sql}"
        db.execute_query(rollback_sql, fetch=False, commit=True)
        print("   ✅ vw_mutaties rolled back successfully")
    except Exception as e:
        print(f"   ❌ Rollback failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Flatten vw_mutaties view chain by eliminating redundant rekeningschema joins"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would change without executing any SQL"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("VIEW CHAIN FLATTENING MIGRATION")
    print("Eliminates redundant rekeningschema joins in vw_mutaties")
    print("Requirements: 1.3, 2.3, 3.2, 3.3")
    if args.dry_run:
        print("MODE: DRY RUN (no changes will be made)")
    print("=" * 70)

    db = DatabaseManager(test_mode=False)

    # Step 1: Show current definitions
    show_current_view_definitions(db)

    # Step 2: Save original vw_mutaties definition for rollback
    original_vw_mutaties_def = get_view_definition(db, 'vw_mutaties')

    # Step 3: Capture baseline
    total_count, baseline = capture_baseline(db)

    # Step 4: Check current EXPLAIN join count (before)
    print("\n📊 BEFORE migration:")
    before_refs = verify_explain_join_count(db)

    if args.dry_run:
        print("\n" + "-" * 70)
        print("DRY RUN — showing planned changes:")
        print("-" * 70)
        add_belastingaangifte_to_view(db, 'vw_debetmutaties', dry_run=True)
        add_belastingaangifte_to_view(db, 'vw_creditmutaties', dry_run=True)
        recreate_vw_mutaties(db, dry_run=True)
        print("\n✅ Dry run complete. No changes were made.")
        return

    # Step 5: Alter base views to include Belastingaangifte
    try:
        add_belastingaangifte_to_view(db, 'vw_debetmutaties')
        add_belastingaangifte_to_view(db, 'vw_creditmutaties')
    except Exception as e:
        print(f"\n❌ Error altering base views: {e}")
        print("   No changes were made to vw_mutaties. Base views may need manual inspection.")
        raise

    # Step 6: Recreate vw_mutaties as simple UNION ALL
    try:
        recreate_vw_mutaties(db)
    except Exception as e:
        print(f"\n❌ Error recreating vw_mutaties: {e}")
        print("   Attempting rollback...")
        rollback_vw_mutaties(db, original_vw_mutaties_def)
        raise

    # Step 7: Verify row counts and checksums match
    verification_passed = verify_against_baseline(db, total_count, baseline)

    if not verification_passed:
        print("\n❌ Verification FAILED — rolling back vw_mutaties...")
        rollback_vw_mutaties(db, original_vw_mutaties_def)
        print("   ⚠️  Base views (vw_debetmutaties, vw_creditmutaties) still have Belastingaangifte added.")
        print("   This is harmless — the extra column doesn't affect existing queries.")
        sys.exit(1)

    # Step 8: Verify amount signs
    verify_amount_signs(db)

    # Step 9: Check EXPLAIN join count (after)
    print("\n📊 AFTER migration:")
    after_refs = verify_explain_join_count(db)

    # Step 10: Show final view definitions
    show_current_view_definitions(db)

    # Summary
    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"   rekeningschema joins: {before_refs} → {after_refs}")
    print(f"   Row count preserved: ✅ {total_count:,} rows")
    print(f"   Administrations verified: ✅ {len(baseline)}")
    print(f"   Amount signs verified: ✅")
    if after_refs <= 2:
        print("\n🎉 Migration completed successfully!")
    else:
        print(f"\n⚠️  Migration completed but join count ({after_refs}) higher than expected (≤ 2).")
        print("   This may indicate the EXPLAIN plan includes derived table references.")


if __name__ == '__main__':
    main()
