#!/usr/bin/env python3
"""
Phase 1 Query Testing Script

This script tests that all existing queries still work after the Phase 1 migration.
It verifies that adding the 'administration' field didn't break any functionality.

Usage:
    python backend/scripts/test_phase1_queries.py
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path to import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import DatabaseManager

class Phase1QueryTester:
    def __init__(self):
        self.db = DatabaseManager()
        self.passed = 0
        self.failed = 0
        self.errors = []
        
    def test_query(self, test_name, query, params=None, expected_columns=None):
        """Test a single query"""
        try:
            print(f"  Testing: {test_name}...", end=" ")
            
            results = self.db.execute_query(query, params)
            
            # Check if results were returned
            if results is None:
                raise Exception("Query returned None")
            
            # Check expected columns if provided
            if expected_columns and len(results) > 0:
                result_columns = set(results[0].keys())
                missing_columns = set(expected_columns) - result_columns
                if missing_columns:
                    raise Exception(f"Missing columns: {missing_columns}")
            
            print(f"✅ PASS ({len(results)} rows)")
            self.passed += 1
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.failed += 1
            self.errors.append({
                'test': test_name,
                'query': query[:100] + '...' if len(query) > 100 else query,
                'error': str(e)
            })
            return False
    
    def test_basic_selects(self):
        """Test basic SELECT queries on all tables"""
        print("\n📋 Testing Basic SELECT Queries...")
        
        tables = [
            ('bnb', ['id', 'sourceFile', 'administration']),
            ('bnbfuture', ['id', 'administration']),
            ('bnblookup', ['lookUp', 'id', 'administration']),
            ('bnbplanned', ['id', 'sourceFile', 'administration']),
            ('listings', ['id', 'administration']),
            ('pricing_events', ['id', 'administration']),
            ('pricing_recommendations', ['id', 'administration']),
            ('mutaties', ['ID', 'TransactionNumber', 'administration']),
            ('rekeningschema', ['Account', 'administration']),
        ]
        
        for table, expected_cols in tables:
            self.test_query(
                f"SELECT from {table}",
                f"SELECT * FROM {table} LIMIT 1",
                expected_columns=expected_cols
            )
    
    def test_administration_filters(self):
        """Test filtering by administration field"""
        print("\n🔍 Testing Administration Field Filters...")
        
        # Test filtering on each table
        tables = ['bnb', 'bnbfuture', 'bnblookup', 'bnbplanned', 'listings', 
                  'pricing_events', 'pricing_recommendations', 'mutaties', 'rekeningschema']
        
        for table in tables:
            self.test_query(
                f"Filter {table} by administration",
                f"SELECT COUNT(*) as count FROM {table} WHERE administration = %s",
                ('GoodwinSolutions',)
            )
    
    def test_views(self):
        """Test that views still work"""
        print("\n👁️  Testing Views...")
        
        views = [
            ('vw_bnb_total', ['id', 'sourceFile', 'administration']),
            ('vw_readreferences', ['debet', 'credit', 'administration']),
            ('vw_mutaties', ['ID', 'administration']),
            ('vw_rekeningschema', ['Account', 'administration']),
        ]
        
        for view, expected_cols in views:
            self.test_query(
                f"SELECT from {view}",
                f"SELECT * FROM {view} LIMIT 1",
                expected_columns=expected_cols
            )
    
    def test_existing_application_queries(self):
        """Test queries used by the application"""
        print("\n🔧 Testing Application Queries...")
        
        # Test get_bnb_lookup (from database.py)
        self.test_query(
            "get_bnb_lookup",
            "SELECT * FROM bnblookup WHERE bnblookup.lookUp LIKE %s",
            ('bdc',)
        )
        
        # Test get_patterns (from database.py)
        self.test_query(
            "get_patterns",
            """SELECT debet, credit, administration, referenceNumber, Date
               FROM vw_readreferences 
               WHERE administration = %s 
               AND (debet < '1300' OR credit < '1300')
               AND Date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
               ORDER BY Date DESC
               LIMIT 10""",
            ('GoodwinSolutions',)
        )
        
        # Test get_bank_account_lookups (from database.py)
        self.test_query(
            "get_bank_account_lookups",
            "SELECT rekeningNummer, Account, Administration FROM lookupbankaccounts_R LIMIT 10"
        )
        
        # Test get_recent_transactions (from database.py)
        self.test_query(
            "get_recent_transactions",
            """SELECT TransactionDescription, Debet, Credit FROM mutaties 
               ORDER BY ID DESC LIMIT 10"""
        )
        
        # Test check_duplicate_transactions (from database.py)
        test_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        self.test_query(
            "check_duplicate_transactions",
            """SELECT ID, TransactionNumber, TransactionDate, TransactionDescription, 
                      TransactionAmount, Debet, Credit, ReferenceNumber, 
                      Ref1, Ref2, Ref3, Ref4, Administration
               FROM mutaties
               WHERE ReferenceNumber = %s
               AND TransactionDate = %s
               AND ABS(TransactionAmount - %s) < 0.01
               AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
               ORDER BY ID DESC""",
            ('TEST123', test_date, 100.00)
        )
    
    def test_joins(self):
        """Test queries with JOINs"""
        print("\n🔗 Testing JOIN Queries...")
        
        # Test join between mutaties and rekeningschema
        self.test_query(
            "JOIN mutaties with rekeningschema",
            """SELECT m.ID, m.TransactionNumber, m.administration, 
                      r.Account, r.AccountName
               FROM mutaties m
               LEFT JOIN rekeningschema r ON m.Debet = r.Account 
                   AND m.administration = r.administration
               WHERE m.administration = %s
               LIMIT 10""",
            ('GoodwinSolutions',)
        )
    
    def test_aggregations(self):
        """Test aggregation queries"""
        print("\n📊 Testing Aggregation Queries...")
        
        # Count by administration
        self.test_query(
            "COUNT by administration",
            "SELECT administration, COUNT(*) as count FROM mutaties GROUP BY administration"
        )
        
        # Sum amounts by administration
        self.test_query(
            "SUM amounts by administration",
            """SELECT administration, SUM(TransactionAmount) as total 
               FROM mutaties 
               WHERE administration = %s
               GROUP BY administration""",
            ('GoodwinSolutions',)
        )
        
        # Count BnB reservations by administration
        self.test_query(
            "COUNT BnB by administration",
            "SELECT administration, COUNT(*) as count FROM bnb GROUP BY administration"
        )
    
    def test_inserts_and_updates(self):
        """Test INSERT and UPDATE operations"""
        print("\n✏️  Testing INSERT/UPDATE Operations...")
        
        # Test insert into tenant_config
        try:
            print("  Testing: INSERT into tenant_config...", end=" ")
            
            # Insert test config
            self.db.execute_query(
                """INSERT INTO tenant_config 
                   (administration, config_key, config_value, is_secret, created_by)
                   VALUES (%s, %s, %s, %s, %s)""",
                ('TestTenant', 'test_key', 'test_value', False, 'test_script'),
                fetch=False,
                commit=True
            )
            
            # Verify insert
            result = self.db.execute_query(
                "SELECT * FROM tenant_config WHERE administration = %s AND config_key = %s",
                ('TestTenant', 'test_key')
            )
            
            if not result or len(result) == 0:
                raise Exception("Insert verification failed")
            
            # Clean up
            self.db.execute_query(
                "DELETE FROM tenant_config WHERE administration = %s AND config_key = %s",
                ('TestTenant', 'test_key'),
                fetch=False,
                commit=True
            )
            
            print("✅ PASS")
            self.passed += 1
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.failed += 1
            self.errors.append({
                'test': 'INSERT into tenant_config',
                'error': str(e)
            })
    
    def test_indexes(self):
        """Test that indexes exist and are being used"""
        print("\n📇 Testing Indexes...")
        
        tables = ['bnb', 'bnbfuture', 'bnblookup', 'bnbplanned', 'listings',
                  'pricing_events', 'pricing_recommendations', 'mutaties', 'rekeningschema']
        
        for table in tables:
            self.test_query(
                f"Index on {table}.administration",
                """SELECT INDEX_NAME 
                   FROM INFORMATION_SCHEMA.STATISTICS 
                   WHERE TABLE_SCHEMA = DATABASE() 
                   AND TABLE_NAME = %s 
                   AND INDEX_NAME = 'idx_administration'""",
                (table,)
            )
    
    def test_performance(self):
        """Test query performance with administration filter"""
        print("\n⚡ Testing Query Performance...")
        
        import time
        
        # Test query with administration filter
        try:
            print("  Testing: Query performance with administration filter...", end=" ")
            
            start = time.time()
            results = self.db.execute_query(
                """SELECT COUNT(*) as count 
                   FROM mutaties 
                   WHERE administration = %s 
                   AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 1 YEAR)""",
                ('GoodwinSolutions',)
            )
            elapsed = time.time() - start
            
            if elapsed > 5.0:  # Should complete in under 5 seconds
                print(f"⚠️  SLOW ({elapsed:.2f}s) - Consider optimizing")
            else:
                print(f"✅ PASS ({elapsed:.3f}s)")
            
            self.passed += 1
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.failed += 1
            self.errors.append({
                'test': 'Query performance',
                'error': str(e)
            })
    
    def run_all_tests(self):
        """Run all test suites"""
        print("=" * 60)
        print("Phase 1: Query Testing")
        print("=" * 60)
        
        # Run test suites
        self.test_basic_selects()
        self.test_administration_filters()
        self.test_views()
        self.test_existing_application_queries()
        self.test_joins()
        self.test_aggregations()
        self.test_inserts_and_updates()
        self.test_indexes()
        self.test_performance()
        
        # Print summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"📊 Total:  {self.passed + self.failed}")
        
        if self.failed > 0:
            print("\n❌ Failed Tests:")
            for error in self.errors:
                print(f"\n  Test: {error['test']}")
                if 'query' in error:
                    print(f"  Query: {error['query']}")
                print(f"  Error: {error['error']}")
        
        print("\n" + "=" * 60)
        
        if self.failed == 0:
            print("✅ All tests passed! Phase 1 migration is successful.")
            print("   Your application queries are working correctly.")
            return True
        else:
            print("⚠️  Some tests failed. Please review the errors above.")
            print("   You may need to update queries or fix the migration.")
            return False


def main():
    tester = Phase1QueryTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
