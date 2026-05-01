#!/usr/bin/env python3
"""
Test script for parameters JSON column in rekeningschema table.
Tests JSON_EXTRACT queries and helper functions.
"""

import sys
import os
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database import DatabaseManager
from dialect_helpers import dialect


def test_json_column_exists():
    """Test that parameters column exists."""
    print("Testing parameters column existence...")

    db_manager = DatabaseManager()

    result = db_manager.execute_query("""
        SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'rekeningschema'
        AND COLUMN_NAME = 'parameters'
    """)

    if result:
        row = result[0]
        print("✓ Parameters column exists")
        print(f"  Type: {row['DATA_TYPE']}")
        print(f"  Nullable: {row['IS_NULLABLE']}")
        print(f"  Comment: {row['COLUMN_COMMENT']}")
        return True
    else:
        print("✗ Parameters column does not exist")
        return False


def test_json_operations():
    """Test JSON operations on parameters column."""
    print("\nTesting JSON operations...")

    db_manager = DatabaseManager()

    # Get first account for testing
    test_accounts = db_manager.execute_query("""
        SELECT Account, AccountName, administration, parameters
        FROM rekeningschema
        LIMIT 1
    """)

    if not test_accounts:
        print("✗ No accounts found for testing")
        return False

    test_account = test_accounts[0]
    account = test_account['Account']
    admin = test_account['administration']

    print(f"  Using test account: {account} ({test_account['AccountName']})")

    try:
        # Test 1: Set JSON value
        print("\n  Test 1: Setting JSON value...")
        db_manager.execute_query("""
            UPDATE rekeningschema
            SET parameters = JSON_OBJECT('roles', JSON_ARRAY('test_role'))
            WHERE Account = %s AND administration = %s
        """, (account, admin), fetch=False, commit=True)
        print("  ✓ JSON value set")

        # Test 2: Read JSON value using dialect helper
        print("\n  Test 2: Reading JSON value...")
        je_roles = dialect.json_extract('parameters', '$.roles')
        result = db_manager.execute_query(f"""
            SELECT Account, parameters,
                   {je_roles} as roles
            FROM rekeningschema
            WHERE Account = %s AND administration = %s
        """, (account, admin))

        row = result[0]
        print(f"  ✓ Parameters: {row['parameters']}")
        print(f"  ✓ Roles: {row['roles']}")

        # Test 3: JSON_CONTAINS query using dialect helper
        print("\n  Test 3: JSON_CONTAINS query...")
        jc_roles = dialect.json_contains("parameters->'$.roles'", '"test_role"')
        results = db_manager.execute_query(f"""
            SELECT Account, AccountName, parameters
            FROM rekeningschema
            WHERE {jc_roles}
            AND administration = %s
        """, (admin,))

        print(f"  ✓ Found {len(results)} account(s) with 'test_role'")

        # Test 4: Multiple roles
        print("\n  Test 4: Setting multiple roles...")
        db_manager.execute_query("""
            UPDATE rekeningschema
            SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result', 'test_role'))
            WHERE Account = %s AND administration = %s
        """, (account, admin), fetch=False, commit=True)

        result = db_manager.execute_query("""
            SELECT parameters
            FROM rekeningschema
            WHERE Account = %s AND administration = %s
        """, (account, admin))

        print(f"  ✓ Multiple roles: {result[0]['parameters']}")

        # Test 5: Clear parameters (set to NULL)
        print("\n  Test 5: Clearing parameters...")
        db_manager.execute_query("""
            UPDATE rekeningschema
            SET parameters = NULL
            WHERE Account = %s AND administration = %s
        """, (account, admin), fetch=False, commit=True)
        print("  ✓ Parameters cleared")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        # Attempt cleanup
        try:
            db_manager.execute_query("""
                UPDATE rekeningschema
                SET parameters = NULL
                WHERE Account = %s AND administration = %s
            """, (account, admin), fetch=False, commit=True)
        except Exception:
            pass
        return False


def test_helper_function():
    """Test get_account_by_role helper function."""
    print("\nTesting get_account_by_role helper function...")

    db_manager = DatabaseManager()

    # Setup: Get a test account
    test_accounts = db_manager.execute_query("""
        SELECT Account, administration
        FROM rekeningschema
        LIMIT 1
    """)

    if not test_accounts:
        print("✗ No accounts found for testing")
        return False

    test_account = test_accounts[0]
    account = test_account['Account']
    admin = test_account['administration']

    try:
        # Set test role
        db_manager.execute_query("""
            UPDATE rekeningschema
            SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result'))
            WHERE Account = %s AND administration = %s
        """, (account, admin), fetch=False, commit=True)

        # Test the helper function query using dialect helpers
        role = 'equity_result'
        jc_roles = dialect.json_contains("parameters->'$.roles'", '%s')
        result = db_manager.execute_query(f"""
            SELECT Account, AccountName, VW, parameters
            FROM rekeningschema
            WHERE administration = %s
            AND {jc_roles}
            LIMIT 1
        """, (admin, json.dumps(role)))

        if result:
            row = result[0]
            print(f"  ✓ Found account for role '{role}': {row['Account']} ({row['AccountName']})")
            print(f"    VW: {row['VW']}")
            print(f"    Parameters: {row['parameters']}")

            # Cleanup
            db_manager.execute_query("""
                UPDATE rekeningschema
                SET parameters = NULL
                WHERE Account = %s AND administration = %s
            """, (account, admin), fetch=False, commit=True)

            return True
        else:
            print(f"  ✗ No account found for role '{role}'")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        # Attempt cleanup
        try:
            db_manager.execute_query("""
                UPDATE rekeningschema
                SET parameters = NULL
                WHERE Account = %s AND administration = %s
            """, (account, admin), fetch=False, commit=True)
        except Exception:
            pass
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing parameters JSON column in rekeningschema")
    print("=" * 60)

    results = []

    # Test 1: Column exists
    results.append(("Column exists", test_json_column_exists()))

    # Test 2: JSON operations
    results.append(("JSON operations", test_json_operations()))

    # Test 3: Helper function
    results.append(("Helper function", test_helper_function()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
