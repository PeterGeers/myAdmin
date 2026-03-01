#!/usr/bin/env python3
"""
Test script for parameters JSON column in rekeningschema table.
Tests JSON_EXTRACT queries and helper functions.
"""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.database import get_db_connection
from src.config import Config


def test_json_column_exists():
    """Test that parameters column exists."""
    print("Testing parameters column existence...")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'rekeningschema'
            AND COLUMN_NAME = 'parameters'
        """, (Config.DB_NAME,))
        
        result = cursor.fetchone()
        
        if result:
            print("✓ Parameters column exists")
            print(f"  Type: {result['DATA_TYPE']}")
            print(f"  Nullable: {result['IS_NULLABLE']}")
            print(f"  Comment: {result['COLUMN_COMMENT']}")
            return True
        else:
            print("✗ Parameters column does not exist")
            return False
            
    finally:
        cursor.close()
        conn.close()


def test_json_operations():
    """Test JSON operations on parameters column."""
    print("\nTesting JSON operations...")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get first account for testing
        cursor.execute("""
            SELECT Account, AccountName, administration, parameters
            FROM rekeningschema
            LIMIT 1
        """)
        
        test_account = cursor.fetchone()
        
        if not test_account:
            print("✗ No accounts found for testing")
            return False
        
        account = test_account['Account']
        admin = test_account['administration']
        
        print(f"  Using test account: {account} ({test_account['AccountName']})")
        
        # Test 1: Set JSON value
        print("\n  Test 1: Setting JSON value...")
        cursor.execute("""
            UPDATE rekeningschema
            SET parameters = JSON_OBJECT('roles', JSON_ARRAY('test_role'))
            WHERE Account = %s AND administration = %s
        """, (account, admin))
        conn.commit()
        print("  ✓ JSON value set")
        
        # Test 2: Read JSON value
        print("\n  Test 2: Reading JSON value...")
        cursor.execute("""
            SELECT Account, parameters,
                   JSON_EXTRACT(parameters, '$.roles') as roles
            FROM rekeningschema
            WHERE Account = %s AND administration = %s
        """, (account, admin))
        
        result = cursor.fetchone()
        print(f"  ✓ Parameters: {result['parameters']}")
        print(f"  ✓ Roles: {result['roles']}")
        
        # Test 3: JSON_CONTAINS query
        print("\n  Test 3: JSON_CONTAINS query...")
        cursor.execute("""
            SELECT Account, AccountName, parameters
            FROM rekeningschema
            WHERE JSON_CONTAINS(parameters->'$.roles', '"test_role"')
            AND administration = %s
        """, (admin,))
        
        results = cursor.fetchall()
        print(f"  ✓ Found {len(results)} account(s) with 'test_role'")
        
        # Test 4: Multiple roles
        print("\n  Test 4: Setting multiple roles...")
        cursor.execute("""
            UPDATE rekeningschema
            SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result', 'test_role'))
            WHERE Account = %s AND administration = %s
        """, (account, admin))
        conn.commit()
        
        cursor.execute("""
            SELECT parameters
            FROM rekeningschema
            WHERE Account = %s AND administration = %s
        """, (account, admin))
        
        result = cursor.fetchone()
        print(f"  ✓ Multiple roles: {result['parameters']}")
        
        # Test 5: Clear parameters (set to NULL)
        print("\n  Test 5: Clearing parameters...")
        cursor.execute("""
            UPDATE rekeningschema
            SET parameters = NULL
            WHERE Account = %s AND administration = %s
        """, (account, admin))
        conn.commit()
        print("  ✓ Parameters cleared")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()


def test_helper_function():
    """Test get_account_by_role helper function."""
    print("\nTesting get_account_by_role helper function...")
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Setup: Create a test account with a role
        cursor.execute("""
            SELECT Account, administration
            FROM rekeningschema
            LIMIT 1
        """)
        
        test_account = cursor.fetchone()
        account = test_account['Account']
        admin = test_account['administration']
        
        # Set test role
        cursor.execute("""
            UPDATE rekeningschema
            SET parameters = JSON_OBJECT('roles', JSON_ARRAY('equity_result'))
            WHERE Account = %s AND administration = %s
        """, (account, admin))
        conn.commit()
        
        # Test the helper function query
        role = 'equity_result'
        cursor.execute("""
            SELECT Account, AccountName, VW, parameters
            FROM rekeningschema
            WHERE administration = %s
            AND JSON_CONTAINS(parameters->'$.roles', %s)
            LIMIT 1
        """, (admin, json.dumps(role)))
        
        result = cursor.fetchone()
        
        if result:
            print(f"  ✓ Found account for role '{role}': {result['Account']} ({result['AccountName']})")
            print(f"    VW: {result['VW']}")
            print(f"    Parameters: {result['parameters']}")
            
            # Cleanup
            cursor.execute("""
                UPDATE rekeningschema
                SET parameters = NULL
                WHERE Account = %s AND administration = %s
            """, (account, admin))
            conn.commit()
            
            return True
        else:
            print(f"  ✗ No account found for role '{role}'")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()


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
