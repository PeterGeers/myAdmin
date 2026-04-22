#!/usr/bin/env python3
"""
Composite Index Migration Script

Creates idx_mutaties_admin_txdate on mutaties(administration, TransactionDate)
to support the most common query pattern: filter by administration then range
scan on TransactionDate.

This index benefits:
- Sargable date range queries (YEAR() rewrites from task 4)
- Filter dropdown queries on base mutaties table (task 7)
- Tenant-scoped year filtering across all endpoints

Requirements: 2.1, 2.2
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import DatabaseManager

INDEX_NAME = "idx_mutaties_admin_txdate"
TABLE_NAME = "mutaties"


def check_index_exists(db):
    """Check if the composite index already exists."""
    indexes = db.execute_query(f"SHOW INDEX FROM {TABLE_NAME} WHERE Key_name = %s", (INDEX_NAME,))
    return len(indexes) > 0


def show_existing_indexes(db):
    """Display all current indexes on the mutaties table."""
    print("\n📋 Current indexes on mutaties:")
    indexes = db.execute_query(f"SHOW INDEX FROM {TABLE_NAME}")
    seen = set()
    for idx in indexes:
        key_name = idx['Key_name']
        if key_name not in seen:
            seen.add(key_name)
            # Collect all columns for this index
            cols = [
                row['Column_name']
                for row in indexes
                if row['Key_name'] == key_name
            ]
            unique = "UNIQUE " if idx['Non_unique'] == 0 else ""
            print(f"   {unique}{key_name}: ({', '.join(cols)})")


def create_index(db):
    """Create the composite index."""
    print(f"\n🔧 Creating index {INDEX_NAME} ON {TABLE_NAME}(administration, TransactionDate)...")
    db.execute_query(
        f"CREATE INDEX {INDEX_NAME} ON {TABLE_NAME}(administration, TransactionDate)",
        fetch=False,
        commit=True,
    )
    print(f"   ✅ Index {INDEX_NAME} created successfully")


def verify_index(db):
    """Verify the index exists and has the correct columns."""
    print(f"\n🔍 Verifying index {INDEX_NAME}...")
    indexes = db.execute_query(
        f"SHOW INDEX FROM {TABLE_NAME} WHERE Key_name = %s", (INDEX_NAME,)
    )
    if not indexes:
        print(f"   ❌ Index {INDEX_NAME} not found!")
        return False

    columns = [(row['Seq_in_index'], row['Column_name']) for row in indexes]
    columns.sort()
    col_names = [c[1] for c in columns]
    print(f"   Columns: ({', '.join(col_names)})")

    expected = ['administration', 'TransactionDate']
    if col_names == expected:
        print(f"   ✅ Index columns match expected: ({', '.join(expected)})")
        return True
    else:
        print(f"   ❌ Expected ({', '.join(expected)}), got ({', '.join(col_names)})")
        return False


def run_explain_check(db):
    """Run EXPLAIN on a representative query to confirm index usage."""
    print("\n🔍 Running EXPLAIN on representative query...")

    # Representative query: tenant-scoped date range filter
    explain = db.execute_query("""
        EXPLAIN SELECT * FROM mutaties
        WHERE administration = 'GoodwinSolutions'
          AND TransactionDate >= '2025-01-01'
          AND TransactionDate < '2026-01-01'
    """)

    uses_index = False
    for row in explain:
        table = row.get('table', '?')
        join_type = row.get('type', '?')
        possible_keys = row.get('possible_keys', '') or ''
        key = row.get('key', '') or ''
        rows_est = row.get('rows', '?')
        extra = row.get('Extra', '') or ''

        print(f"   table={table}, type={join_type}, possible_keys={possible_keys}, "
              f"key={key}, rows={rows_est}, Extra={extra}")

        if INDEX_NAME in key or INDEX_NAME in possible_keys:
            uses_index = True

    if uses_index:
        print(f"   ✅ Query plan uses {INDEX_NAME}")
    else:
        print(f"   ⚠️  Query plan does not reference {INDEX_NAME} directly")
        print(f"       (MySQL may choose a different index if it estimates fewer rows)")

    return uses_index


def main():
    print("=" * 70)
    print("COMPOSITE INDEX MIGRATION")
    print(f"Creates {INDEX_NAME} ON {TABLE_NAME}(administration, TransactionDate)")
    print("Requirements: 2.1, 2.2")
    print("=" * 70)

    db = DatabaseManager(test_mode=False)

    # Show current indexes
    show_existing_indexes(db)

    # Check if index already exists
    if check_index_exists(db):
        print(f"\n✅ Index {INDEX_NAME} already exists — skipping creation")
    else:
        create_index(db)

    # Verify index
    if not verify_index(db):
        print("\n❌ Index verification failed!")
        sys.exit(1)

    # Run EXPLAIN check
    run_explain_check(db)

    # Show updated indexes
    show_existing_indexes(db)

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print(f"   Index {INDEX_NAME} is active on {TABLE_NAME}(administration, TransactionDate)")
    print("   This supports tenant-scoped date range queries across all endpoints.")
    print("=" * 70)


if __name__ == '__main__':
    main()
