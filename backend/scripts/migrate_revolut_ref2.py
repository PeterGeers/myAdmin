#!/usr/bin/env python3
"""
Revolut Ref2 Migration Script

Migrates existing Revolut transaction Ref2 values in the `mutaties` table from
the old format [beschrijving]_[saldo]_[startdatum] to the new format
[beschrijving]_[saldo]_[datum voltooid].

This is needed because the frontend now uses the completion date (Datum voltooid)
instead of the start date (Startdatum) in Ref2 for more accurate duplicate detection.

Usage:
    python backend/scripts/migrate_revolut_ref2.py --dry-run   (default, reports changes)
    python backend/scripts/migrate_revolut_ref2.py --apply     (executes UPDATE statements)
"""

import csv
import os
import sys
import argparse
import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

# Add src to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / 'src'))

from database import DatabaseManager
from db_exceptions import DatabaseError

# Default Railway production connection (overridden by env vars when using railway-run.ps1)
DEFAULT_HOST = 'shinkansen.proxy.rlwy.net'
DEFAULT_PORT = 42375
DEFAULT_USER = 'root'
DEFAULT_DB = 'railway'  # Railway MySQL default database; 'finance' DB lives inside it

REVOLUT_IBAN = 'NL08REVO7549383472'
CSV_DIR = Path(__file__).parent.parent.parent / '.kiro' / 'specs' / 'FIN' / 'BankingProcessor' / 'Revolut'

# Column indices for Dutch Revolut CSV
COL_STARTDATUM = 2
COL_DATUM_VOLTOOID = 3
COL_BESCHRIJVING = 4
COL_BEDRAG = 5
COL_KOSTEN = 6
COL_STATUS = 8
COL_SALDO = 9


def format_saldo(raw_saldo: str) -> str:
    """Format saldo to 2 decimals, matching frontend's parseFloat(...).toFixed(2)."""
    try:
        return f"{float(raw_saldo.replace(',', '.')):.2f}"
    except (ValueError, AttributeError):
        return "0.00"


def parse_csv_file(filepath: Path) -> list[dict]:
    """Parse a single Revolut CSV file and extract completed transactions."""
    transactions = []

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return transactions

        for row in reader:
            if len(row) < 10:
                continue

            status = row[COL_STATUS].strip()
            datum_voltooid = row[COL_DATUM_VOLTOOID].strip()
            saldo_raw = row[COL_SALDO].strip()
            startdatum = row[COL_STARTDATUM].strip()
            beschrijving = row[COL_BESCHRIJVING].strip()

            # Only process completed transactions with filled fields
            if status != 'VOLTOOID':
                continue
            if not datum_voltooid or not saldo_raw:
                continue

            saldo_formatted = format_saldo(saldo_raw)
            bedrag = row[COL_BEDRAG].strip()
            kosten = row[COL_KOSTEN].strip()

            # Build old Ref2: [beschrijving]_[saldo]_[startdatum]
            old_ref2 = f"{beschrijving}_{saldo_formatted}_{startdatum}"
            # Build new Ref2: [beschrijving]_[saldo]_[datum voltooid]
            new_ref2 = f"{beschrijving}_{saldo_formatted}_{datum_voltooid}"

            transactions.append({
                'old_ref2': old_ref2,
                'new_ref2': new_ref2,
                'beschrijving': beschrijving,
                'startdatum': startdatum,
                'datum_voltooid': datum_voltooid,
                'saldo': saldo_formatted,
                'source_file': filepath.name
            })

            # Fee transaction: if kosten > 0, frontend also generates a fee Ref2
            try:
                fee_val = float(kosten.replace(',', '.'))
            except (ValueError, AttributeError):
                fee_val = 0.0

            if fee_val > 0:
                old_fee_ref2 = f"Revo Charges_{saldo_formatted}_{startdatum}"
                new_fee_ref2 = f"Revo Charges_{saldo_formatted}_{datum_voltooid}"
                transactions.append({
                    'old_ref2': old_fee_ref2,
                    'new_ref2': new_fee_ref2,
                    'beschrijving': 'Revo Charges',
                    'startdatum': startdatum,
                    'datum_voltooid': datum_voltooid,
                    'saldo': saldo_formatted,
                    'source_file': filepath.name
                })

    return transactions


def build_lookup_map() -> dict[str, dict]:
    """
    Parse all Revolut CSV files and build a deduplicated lookup map.
    Key: old_ref2, Value: dict with new_ref2 and metadata.
    """
    lookup = {}
    total_parsed = 0
    duplicates_skipped = 0

    csv_files = sorted(CSV_DIR.glob('*.csv'))
    print(f"Found {len(csv_files)} CSV files in {CSV_DIR}\n")

    for csv_file in csv_files:
        transactions = parse_csv_file(csv_file)
        print(f"  {csv_file.name}: {len(transactions)} completed transactions")
        total_parsed += len(transactions)

        for txn in transactions:
            old_ref2 = txn['old_ref2']
            if old_ref2 in lookup:
                # Deduplicate: same transaction in overlapping exports
                duplicates_skipped += 1
                continue
            lookup[old_ref2] = txn

    print(f"\nTotal transactions parsed: {total_parsed}")
    print(f"Duplicates skipped: {duplicates_skipped}")
    print(f"Unique lookup entries: {len(lookup)}")

    return lookup


def run_migration(apply: bool = False, csv_only: bool = False):
    """Run the Ref2 migration in dry-run or apply mode."""
    print("=" * 70)
    print("Revolut Ref2 Migration Script")
    if csv_only:
        print("Mode: CSV-ONLY (parse CSV files, no database connection)")
    else:
        print(f"Mode: {'APPLY (will modify database)' if apply else 'DRY-RUN (no changes)'}")
    print("=" * 70)
    print()

    # Step 1: Build lookup map from CSV files
    print("--- Step 1: Building lookup map from CSV files ---\n")
    lookup = build_lookup_map()

    if not lookup:
        print("\nNo transactions found. Nothing to migrate.")
        return

    # Filter out entries where old_ref2 == new_ref2 (no change needed)
    changes_needed = {k: v for k, v in lookup.items() if v['old_ref2'] != v['new_ref2']}
    print(f"\nEntries where Ref2 actually changes: {len(changes_needed)}")
    print(f"Entries where startdatum == datum voltooid (no change): {len(lookup) - len(changes_needed)}")

    if not changes_needed:
        print("\nAll Ref2 values already use the correct format. Nothing to migrate.")
        return

    # Show sample changes
    print("\n--- Sample changes (first 5) ---\n")
    for i, (old_ref2, txn) in enumerate(changes_needed.items()):
        if i >= 5:
            break
        print(f"  OLD: {old_ref2}")
        print(f"  NEW: {txn['new_ref2']}")
        print()

    if csv_only:
        print("\nCSV-ONLY mode: skipping database operations.")
        print(f"\nTotal unique Ref2 changes to apply: {len(changes_needed)}")
        return

    if not changes_needed:
        print("\nAll Ref2 values already use the correct format. Nothing to migrate.")
        return

    # Step 2: Connect to database and check/apply updates
    print(f"\n--- Step 2: {'Applying' if apply else 'Checking'} database updates ---\n")

    # Get connection details from env vars (set by railway-run.ps1) or use defaults
    db_host = os.environ.get('DB_HOST', DEFAULT_HOST)
    db_port = int(os.environ.get('DB_PORT', DEFAULT_PORT))
    db_user = os.environ.get('DB_USER', DEFAULT_USER)
    db_password = os.environ.get('DB_PASSWORD') or os.environ.get('RAILWAY_DB_PASSWORD')

    # Railway MySQL authenticates against 'railway' database, but data is in 'finance'
    # When railway-run.ps1 sets DB_NAME=finance, we still connect to 'railway' first
    db_name = DEFAULT_DB  # Always connect to 'railway' for auth
    target_db = 'finance'  # The actual database with mutaties table

    if not db_password:
        db_password = getpass.getpass(f"MySQL password for {db_user}@{db_host}:{db_port}: ")

    # Create DatabaseManager and override config for Railway connection
    db = DatabaseManager()
    db.config.update({
        'host': db_host,
        'port': db_port,
        'user': db_user,
        'password': db_password,
        'database': db_name,
    })

    total_matches = 0
    total_updated = 0
    no_match = 0

    try:
        with db.get_cursor() as (cursor, conn):
            # Switch to the finance database where mutaties lives
            cursor.execute(f"USE {target_db}")
            print(f"Connected to {db_host}:{db_port}/{target_db}")

            for old_ref2, txn in changes_needed.items():
                new_ref2 = txn['new_ref2']

                # Check if record exists
                cursor.execute(
                    "SELECT ID, Ref2 FROM mutaties WHERE Ref1 = %s AND Ref2 = %s",
                    (REVOLUT_IBAN, old_ref2)
                )
                matches = cursor.fetchall()

                if not matches:
                    no_match += 1
                    print(f"  NO MATCH: {old_ref2}")
                    continue

                total_matches += len(matches)

                if apply:
                    cursor.execute(
                        "UPDATE mutaties SET Ref2 = %s WHERE Ref1 = %s AND Ref2 = %s",
                        (new_ref2, REVOLUT_IBAN, old_ref2)
                    )
                    rows_affected = cursor.rowcount
                    total_updated += rows_affected
                    print(f"  UPDATED ({rows_affected} row{'s' if rows_affected != 1 else ''}): "
                          f"{old_ref2} → {new_ref2}")
                else:
                    print(f"  WOULD UPDATE ({len(matches)} row{'s' if len(matches) != 1 else ''}): "
                          f"{old_ref2} → {new_ref2}")
                    total_updated += len(matches)

            if apply:
                conn.commit()
                print("\nChanges committed to database.")
    except DatabaseError as e:
        print(f"Database connection failed: {e}")
        sys.exit(1)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Lookup entries built:        {len(lookup)}")
    print(f"  Entries requiring change:    {len(changes_needed)}")
    print(f"  Database matches found:      {total_matches}")
    print(f"  Records {'updated' if apply else 'that would update'}: {total_updated}")
    print(f"  No match in database:        {no_match}")
    print("=" * 70)

    if not apply:
        print("\nThis was a DRY-RUN. No changes were made.")
        print("Run with --apply to execute the migration.")


def main():
    parser = argparse.ArgumentParser(
        description='Migrate Revolut Ref2 values from startdatum to datum voltooid format'
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true', default=True,
                       help='Report what would change without modifying data (default)')
    group.add_argument('--apply', action='store_true',
                       help='Execute the actual UPDATE statements')
    group.add_argument('--csv-only', action='store_true',
                       help='Only parse CSV files and show lookup map (no database)')

    args = parser.parse_args()

    # Also support MIGRATE_MODE env var for use with railway-run.ps1
    # (which doesn't pass script arguments)
    env_mode = os.environ.get('MIGRATE_MODE', '').lower()
    if env_mode == 'apply':
        args.apply = True
    elif env_mode == 'csv-only':
        args.csv_only = True

    run_migration(apply=args.apply, csv_only=args.csv_only)


if __name__ == '__main__':
    main()
