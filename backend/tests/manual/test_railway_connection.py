#!/usr/bin/env python3
"""
Test script to verify backend can connect to Railway MySQL database.
This script tests the database connection and runs basic queries.
"""

import os
import sys
from dotenv import load_dotenv

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
load_dotenv()

def test_database_connection():
    """Test database connection and basic operations"""
    print("=" * 80)
    print("Railway Database Connection Test")
    print("=" * 80)
    print()
    
    # Import database manager
    try:
        from database import DatabaseManager
        print("✅ Successfully imported DatabaseManager")
    except Exception as e:
        print(f"❌ Failed to import DatabaseManager: {e}")
        return False
    
    # Check environment variables
    print("\n" + "-" * 80)
    print("Environment Configuration:")
    print("-" * 80)
    db_host = os.getenv('DB_HOST', 'not set')
    db_user = os.getenv('DB_USER', 'not set')
    db_name = os.getenv('DB_NAME', 'not set')
    db_port = os.getenv('DB_PORT', 'not set')
    test_mode = os.getenv('TEST_MODE', 'false')
    
    print(f"DB_HOST: {db_host}")
    print(f"DB_USER: {db_user}")
    print(f"DB_NAME: {db_name}")
    print(f"DB_PORT: {db_port}")
    print(f"TEST_MODE: {test_mode}")
    
    # Initialize database manager
    print("\n" + "-" * 80)
    print("Initializing Database Manager:")
    print("-" * 80)
    try:
        db = DatabaseManager(test_mode=False)
        print("✅ DatabaseManager initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize DatabaseManager: {e}")
        return False
    
    # Test connection
    print("\n" + "-" * 80)
    print("Testing Database Connection:")
    print("-" * 80)
    try:
        conn = db.get_connection()
        print("✅ Successfully obtained database connection")
        
        # Test cursor
        cursor = conn.cursor(dictionary=True)
        print("✅ Successfully created cursor")
        
        # Test simple query
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        if result and result['test'] == 1:
            print("✅ Successfully executed test query")
        else:
            print("❌ Test query returned unexpected result")
            return False
        
        cursor.close()
        conn.close()
        print("✅ Successfully closed connection")
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False
    
    # Test database queries
    print("\n" + "-" * 80)
    print("Testing Database Queries:")
    print("-" * 80)
    
    # Test 1: Show tables
    try:
        tables = db.execute_query("SHOW TABLES")
        print(f"✅ Found {len(tables)} tables in database")
        if tables:
            print(f"   Sample tables: {', '.join([list(t.values())[0] for t in tables[:5]])}")
    except Exception as e:
        print(f"❌ Failed to list tables: {e}")
        return False
    
    # Test 2: Check mutaties table
    try:
        count_result = db.execute_query("SELECT COUNT(*) as count FROM mutaties")
        if count_result:
            count = count_result[0]['count']
            print(f"✅ mutaties table has {count} rows")
        else:
            print("⚠️  mutaties table exists but count query returned no results")
    except Exception as e:
        print(f"❌ Failed to query mutaties table: {e}")
        return False
    
    # Test 3: Check bnb table
    try:
        count_result = db.execute_query("SELECT COUNT(*) as count FROM bnb")
        if count_result:
            count = count_result[0]['count']
            print(f"✅ bnb table has {count} rows")
        else:
            print("⚠️  bnb table exists but count query returned no results")
    except Exception as e:
        print(f"❌ Failed to query bnb table: {e}")
        return False
    
    # Test 4: Check tenants table
    try:
        count_result = db.execute_query("SELECT COUNT(*) as count FROM tenants")
        if count_result:
            count = count_result[0]['count']
            print(f"✅ tenants table has {count} rows")
        else:
            print("⚠️  tenants table exists but count query returned no results")
    except Exception as e:
        print(f"❌ Failed to query tenants table: {e}")
        return False
    
    # Test 5: Check users table
    try:
        count_result = db.execute_query("SELECT COUNT(*) as count FROM users")
        if count_result:
            count = count_result[0]['count']
            print(f"✅ users table has {count} rows")
        else:
            print("⚠️  users table exists but count query returned no results")
    except Exception as e:
        print(f"❌ Failed to query users table: {e}")
        return False
    
    # Test 6: Sample data query
    try:
        sample = db.execute_query("SELECT * FROM mutaties LIMIT 1")
        if sample:
            print(f"✅ Successfully retrieved sample data from mutaties")
            print(f"   Sample columns: {', '.join(sample[0].keys())}")
        else:
            print("⚠️  mutaties table is empty")
    except Exception as e:
        print(f"❌ Failed to retrieve sample data: {e}")
        return False
    
    # Test 7: Check views
    try:
        views = db.execute_query("SHOW FULL TABLES WHERE Table_type = 'VIEW'")
        if views:
            print(f"✅ Found {len(views)} views in database")
            view_names = [list(v.values())[0] for v in views]
            print(f"   Views: {', '.join(view_names)}")
        else:
            print("⚠️  No views found in database")
    except Exception as e:
        print(f"❌ Failed to list views: {e}")
        return False
    
    # Test 8: Test vw_mutaties view (if exists)
    try:
        count_result = db.execute_query("SELECT COUNT(*) as count FROM vw_mutaties")
        if count_result:
            count = count_result[0]['count']
            print(f"✅ vw_mutaties view has {count} rows")
        else:
            print("⚠️  vw_mutaties view exists but count query returned no results")
    except Exception as e:
        print(f"⚠️  vw_mutaties view may not exist or has issues: {e}")
    
    # Success summary
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED - Backend can connect to Railway database!")
    print("=" * 80)
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = test_database_connection()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
