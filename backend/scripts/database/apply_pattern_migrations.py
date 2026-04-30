#!/usr/bin/env python3
"""
Apply Pattern Storage Database Migrations

This script applies the database migrations required for the persistent pattern cache:
- pattern_analysis_metadata table
- pattern_verb_patterns table
- compound verb pattern support

REQ-PAT-005: Store discovered patterns in optimized database structure
REQ-PAT-006: Implement pattern caching for performance
"""

import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database_migrations import DatabaseMigration
from database import DatabaseManager
from dialect_helpers import dialect


def apply_pattern_migrations(test_mode=False):
    """Apply all pattern-related database migrations"""
    print("🔧 Applying Pattern Storage Database Migrations")
    print("=" * 60)
    
    try:
        # Initialize migration manager
        migration_manager = DatabaseMigration(test_mode=test_mode)
        
        # Get migration status
        status = migration_manager.get_migration_status()
        print(f"📊 Migration Status:")
        print(f"   - Total migrations: {status['total_migrations']}")
        print(f"   - Applied migrations: {status['applied_migrations']}")
        print(f"   - Pending migrations: {status['pending_migrations']}")
        
        # Show pending migrations
        if status['pending_migrations'] > 0:
            print(f"\n📋 Pending Migrations:")
            for migration in status['migrations']:
                if not migration['applied']:
                    print(f"   - {migration['name']}: {migration['description']}")
        
        # Apply all pending migrations
        print(f"\n🚀 Applying Migrations...")
        applied_count = migration_manager.run_all_migrations()
        
        if applied_count > 0:
            print(f"\n✅ Successfully applied {applied_count} migrations")
            
            # Verify pattern tables exist
            print(f"\n🔍 Verifying Pattern Tables...")
            db = DatabaseManager(test_mode=test_mode)
            
            # Check pattern_analysis_metadata table
            try:
                result = db.execute_query(dialect.describe_table('pattern_analysis_metadata'))
                print(f"   ✅ pattern_analysis_metadata table exists ({len(result)} columns)")
            except Exception as e:
                print(f"   ❌ pattern_analysis_metadata table missing: {e}")
            
            # Check pattern_verb_patterns table
            try:
                result = db.execute_query(dialect.describe_table('pattern_verb_patterns'))
                print(f"   ✅ pattern_verb_patterns table exists ({len(result)} columns)")
                
                # Check for compound verb columns
                columns = [row['Field'] for row in result]
                compound_columns = ['verb_company', 'verb_reference', 'is_compound']
                for col in compound_columns:
                    if col in columns:
                        print(f"   ✅ Compound verb column '{col}' exists")
                    else:
                        print(f"   ⚠️ Compound verb column '{col}' missing")
                        
            except Exception as e:
                print(f"   ❌ pattern_verb_patterns table missing: {e}")
            
            print(f"\n🎉 Pattern storage database setup complete!")
            return True
            
        else:
            print(f"\n✅ All migrations already applied - database is up to date")
            return True
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pattern_tables(test_mode=False):
    """Test that pattern tables are working correctly"""
    print(f"\n🧪 Testing Pattern Tables")
    print("-" * 40)
    
    try:
        db = DatabaseManager(test_mode=test_mode)
        
        # Test pattern_analysis_metadata table
        print("Testing pattern_analysis_metadata table...")
        test_admin = "TestAdmin"
        
        # Insert test metadata
        db.execute_query("""
            INSERT INTO pattern_analysis_metadata 
            (administration, last_analysis_date, transactions_analyzed, patterns_discovered)
            VALUES (%s, NOW(), 100, 50)
            ON DUPLICATE KEY UPDATE
            last_analysis_date = NOW(),
            transactions_analyzed = 100,
            patterns_discovered = 50
        """, (test_admin,), fetch=False, commit=True)
        
        # Read back test metadata
        result = db.execute_query("""
            SELECT administration, transactions_analyzed, patterns_discovered
            FROM pattern_analysis_metadata 
            WHERE administration = %s
        """, (test_admin,))
        
        if result:
            print(f"   ✅ Metadata table working: {result[0]}")
        else:
            print(f"   ❌ Metadata table test failed")
            return False
        
        # Test pattern_verb_patterns table
        print("Testing pattern_verb_patterns table...")
        
        # Insert test pattern
        db.execute_query("""
            INSERT INTO pattern_verb_patterns 
            (administration, bank_account, verb, verb_company, verb_reference, is_compound,
             reference_number, debet_account, credit_account, occurrences, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            occurrences = VALUES(occurrences),
            confidence = VALUES(confidence)
        """, (test_admin, "1300", "TESTCOMPANY|12345", "TESTCOMPANY", "12345", True,
              "TestRef", "1003", "1300", 5, 0.95), fetch=False, commit=True)
        
        # Read back test pattern
        result = db.execute_query("""
            SELECT administration, bank_account, verb, verb_company, verb_reference, 
                   is_compound, reference_number, debet_account, credit_account
            FROM pattern_verb_patterns 
            WHERE administration = %s
        """, (test_admin,))
        
        if result:
            pattern = result[0]
            print(f"   ✅ Pattern table working:")
            print(f"      - Verb: {pattern['verb']}")
            print(f"      - Company: {pattern['verb_company']}")
            print(f"      - Reference: {pattern['verb_reference']}")
            print(f"      - Is Compound: {pattern['is_compound']}")
        else:
            print(f"   ❌ Pattern table test failed")
            return False
        
        # Clean up test data
        db.execute_query("DELETE FROM pattern_analysis_metadata WHERE administration = %s", 
                        (test_admin,), fetch=False, commit=True)
        db.execute_query("DELETE FROM pattern_verb_patterns WHERE administration = %s", 
                        (test_admin,), fetch=False, commit=True)
        
        print(f"   ✅ Test data cleaned up")
        print(f"\n🎉 All pattern tables are working correctly!")
        return True
        
    except Exception as e:
        print(f"   ❌ Pattern table test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🚀 Pattern Storage Database Migration Script")
    print("=" * 60)
    
    # Apply migrations for both production and test databases
    print("\n1. Applying migrations to PRODUCTION database...")
    prod_success = apply_pattern_migrations(test_mode=False)
    
    print("\n2. Applying migrations to TEST database...")
    test_success = apply_pattern_migrations(test_mode=True)
    
    if prod_success and test_success:
        print("\n3. Testing pattern tables...")
        test_table_success = test_pattern_tables(test_mode=True)
        
        if test_table_success:
            print(f"\n🎉 SUCCESS: Pattern storage database setup complete!")
            print(f"   ✅ Production database migrated")
            print(f"   ✅ Test database migrated")
            print(f"   ✅ Pattern tables tested and working")
            print(f"\n📋 Ready for REQ-PAT-006: Persistent Pattern Cache implementation")
        else:
            print(f"\n❌ PARTIAL SUCCESS: Migrations applied but table tests failed")
    else:
        print(f"\n❌ FAILED: Migration errors occurred")
        if not prod_success:
            print(f"   ❌ Production database migration failed")
        if not test_success:
            print(f"   ❌ Test database migration failed")