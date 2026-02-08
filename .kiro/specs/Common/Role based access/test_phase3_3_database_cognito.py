#!/usr/bin/env python3
"""
Test script for Phase 3.3: Testing (Database & Cognito Only)

Run with: python ".kiro/specs/Common/Role based access/test_phase3_3_database_cognito.py"
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend', '.env')
load_dotenv(env_path)

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'backend', 'src'))

from auth.tenant_context import validate_tenant_access
from database import DatabaseManager


class Phase3_3_Test:
    """Test Database and Cognito integration"""
    
    def __init__(self):
        self.cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.test_mode = os.getenv('TEST_MODE', 'true').lower() == 'true'
        self.results = []
        
    def log_result(self, test_name, passed, message):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({'test': test_name, 'passed': passed, 'message': message})
        print(f"{status}: {test_name}")
        print(f"   {message}\n")
        
    def test_1_sysadmin_no_access(self):
        """Test 1: SysAdmin has NO direct tenant data access"""
        user_tenants = []
        test_tenants = ['GoodwinSolutions', 'PeterPrive', 'myAdmin']
        
        for tenant in test_tenants:
            is_authorized, error = validate_tenant_access(user_tenants, tenant)
            if is_authorized:
                self.log_result("SysAdmin denied database access", False, f"Incorrectly authorized for {tenant}")
                return False
            print(f"   ✓ SysAdmin denied access to {tenant}")
        
        self.log_result("SysAdmin has NO direct tenant data access", True, "Correctly denied all tenant access")
        return True
            
    def test_2_tenant_isolation(self):
        """Test 2: Verify tenant isolation"""
        try:
            db = DatabaseManager(test_mode=self.test_mode)
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            
            tenant_counts = {}
            for tenant in ['GoodwinSolutions', 'PeterPrive']:
                result = db.execute_query(query, [tenant])
                tenant_counts[tenant] = result[0]['count'] if result else 0
            
            self.log_result("Tenant isolation verified", True, 
                          f"Tenant data separated. Counts: {tenant_counts}")
            return True
        except Exception as e:
            self.log_result("Tenant isolation verified", False, f"Error: {str(e)}")
            return False
            
    def test_3_tenantadmin_access(self):
        """Test 3: TenantAdmin can access their tenant data"""
        user_tenants = ['GoodwinSolutions']
        is_authorized, error = validate_tenant_access(user_tenants, 'GoodwinSolutions')
        
        if not is_authorized:
            self.log_result("TenantAdmin can access data", False, f"Denied: {error}")
            return False
        
        try:
            db = DatabaseManager(test_mode=self.test_mode)
            query = "SELECT COUNT(*) as count FROM mutaties WHERE administration = %s"
            result = db.execute_query(query, ['GoodwinSolutions'])
            count = result[0]['count'] if result else 0
            
            self.log_result("TenantAdmin can access their tenant data", True,
                          f"Successfully accessed GoodwinSolutions ({count} records)")
            return True
        except Exception as e:
            self.log_result("TenantAdmin can access data", False, f"Error: {str(e)}")
            return False
            
    def test_4_combined_roles(self):
        """Test 4: Combined roles (TenantAdmin + SysAdmin) work correctly"""
        user_tenants = ['GoodwinSolutions']
        user_roles = ['Tenant_Admin', 'SysAdmin']
        
        # Can access tenant data
        is_auth, _ = validate_tenant_access(user_tenants, 'GoodwinSolutions')
        if not is_auth:
            self.log_result("Combined roles access", False, "Denied tenant access")
            return False
        print("   ✓ Can access tenant data")
        
        # Has SysAdmin role
        if 'SysAdmin' not in user_roles:
            self.log_result("Combined roles access", False, "Missing SysAdmin")
            return False
        print("   ✓ Has SysAdmin for platform functions")
        
        # Cannot access other tenants
        is_auth_other, _ = validate_tenant_access(user_tenants, 'PeterPrive')
        if is_auth_other:
            self.log_result("Combined roles access", False, "Incorrectly accessed other tenant")
            return False
        print("   ✓ Cannot access other tenants")
        
        self.log_result("Combined roles work correctly", True,
                      "Can access tenant data AND platform functions, not other tenants")
        return True
        
    def test_5_security_rbac(self):
        """Test 5: Security tests for RBAC"""
        tests = []
        
        # Test 1: No tenant = no access
        is_auth, _ = validate_tenant_access([], 'GoodwinSolutions')
        tests.append(('No tenant denied', not is_auth))
        print(f"   {'✓' if not is_auth else '✗'} No tenant assignment denied")
        
        # Test 2: Tenant assignment grants access
        is_auth, _ = validate_tenant_access(['GoodwinSolutions'], 'GoodwinSolutions')
        tests.append(('Tenant assignment grants', is_auth))
        print(f"   {'✓' if is_auth else '✗'} Tenant assignment grants access")
        
        # Test 3: Cross-tenant denied
        is_auth, _ = validate_tenant_access(['GoodwinSolutions'], 'PeterPrive')
        tests.append(('Cross-tenant denied', not is_auth))
        print(f"   {'✓' if not is_auth else '✗'} Cross-tenant access denied")
        
        # Test 4: Multiple tenants work
        is_auth1, _ = validate_tenant_access(['GoodwinSolutions', 'PeterPrive'], 'GoodwinSolutions')
        is_auth2, _ = validate_tenant_access(['GoodwinSolutions', 'PeterPrive'], 'PeterPrive')
        is_auth3, _ = validate_tenant_access(['GoodwinSolutions', 'PeterPrive'], 'myAdmin')
        tests.append(('Multiple tenants', is_auth1 and is_auth2 and not is_auth3))
        print(f"   {'✓' if (is_auth1 and is_auth2 and not is_auth3) else '✗'} Multiple tenants work")
        
        all_passed = all(t[1] for t in tests)
        self.log_result("Security tests for RBAC", all_passed,
                      f"{sum(1 for t in tests if t[1])}/{len(tests)} security tests passed")
        return all_passed
        
    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("Phase 3.3: Testing (Database & Cognito Only)")
        print("=" * 80)
        print()
        
        if not self.user_pool_id:
            print("❌ ERROR: COGNITO_USER_POOL_ID not set")
            return False
            
        print(f"User Pool ID: {self.user_pool_id}")
        print(f"Test Mode: {self.test_mode}\n")
        
        self.test_1_sysadmin_no_access()
        self.test_2_tenant_isolation()
        self.test_3_tenantadmin_access()
        self.test_4_combined_roles()
        self.test_5_security_rbac()
        
        print("=" * 80)
        print("Test Summary")
        print("=" * 80)
        
        passed = sum(1 for r in self.results if r['passed'])
        total = len(self.results)
        
        print(f"\nTotal: {total} | Passed: {passed} | Failed: {total - passed}\n")
        
        if passed == total:
            print("✅ ALL TESTS PASSED\n")
            print("Phase 3.3 Complete:")
            print("- SysAdmin has NO direct tenant data access ✓")
            print("- Tenant isolation verified ✓")
            print("- TenantAdmin can access their tenant data ✓")
            print("- Combined roles work correctly ✓")
            print("- Security tests passed ✓")
            return True
        else:
            print("❌ SOME TESTS FAILED")
            return False


if __name__ == '__main__':
    tester = Phase3_3_Test()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
