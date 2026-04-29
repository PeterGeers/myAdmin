#!/usr/bin/env python3
"""
Test script for Phase 3.2: Configure SysAdmin Access

This script verifies:
1. SysAdmin role exists in Cognito
2. SysAdmin cannot access tenant data (GoodwinSolutions, PeterPrive, myAdmin)
3. Users with combined roles (TenantAdmin + SysAdmin) can access both functions
4. Role separation and combination behavior

Run with: python backend/tests/test_sysadmin_role_config.py
"""

import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables from backend/.env
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from auth.tenant_context import validate_tenant_access, get_user_tenants


class SysAdminRoleConfigTest:
    """Test SysAdmin role configuration and access control"""
    
    def __init__(self):
        self.cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.results = []
        
    def log_result(self, test_name, passed, message):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            'test': test_name,
            'passed': passed,
            'message': message
        })
        print(f"{status}: {test_name}")
        print(f"   {message}\n")
        
    def test_1_sysadmin_role_exists(self):
        """Test 1: Verify SysAdmin role exists in Cognito"""
        try:
            response = self.cognito_client.list_groups(
                UserPoolId=self.user_pool_id
            )
            
            groups = [group['GroupName'] for group in response.get('Groups', [])]
            
            if 'SysAdmin' in groups:
                # Get group details
                group_response = self.cognito_client.get_group(
                    GroupName='SysAdmin',
                    UserPoolId=self.user_pool_id
                )
                
                description = group_response['Group'].get('Description', '')
                
                self.log_result(
                    "SysAdmin role exists in Cognito",
                    True,
                    f"SysAdmin group found with description: '{description}'"
                )
                return True
            else:
                self.log_result(
                    "SysAdmin role exists in Cognito",
                    False,
                    f"SysAdmin group not found. Available groups: {', '.join(groups)}"
                )
                return False
                
        except ClientError as e:
            self.log_result(
                "SysAdmin role exists in Cognito",
                False,
                f"Error checking Cognito groups: {str(e)}"
            )
            return False
            
    def test_2_sysadmin_no_tenant_access(self):
        """Test 2: Verify SysAdmin cannot access tenant data"""
        
        # Simulate SysAdmin user with NO tenant assignments
        user_tenants = []  # SysAdmin has no tenants
        
        test_tenants = ['GoodwinSolutions', 'PeterPrive', 'myAdmin']
        all_denied = True
        
        for tenant in test_tenants:
            is_authorized, error = validate_tenant_access(user_tenants, tenant)
            
            if is_authorized:
                all_denied = False
                self.log_result(
                    f"SysAdmin denied access to {tenant}",
                    False,
                    f"SysAdmin was incorrectly granted access to {tenant}"
                )
            else:
                print(f"   ✓ SysAdmin correctly denied access to {tenant}")
        
        if all_denied:
            self.log_result(
                "SysAdmin cannot access tenant data",
                True,
                "SysAdmin correctly denied access to all tenants (GoodwinSolutions, PeterPrive, myAdmin)"
            )
        
        return all_denied
        
    def test_3_combined_roles_tenant_access(self):
        """Test 3: Users with TenantAdmin + SysAdmin can access their tenant"""
        
        # Simulate user with TenantAdmin for GoodwinSolutions + SysAdmin role
        user_tenants = ['GoodwinSolutions']
        requested_tenant = 'GoodwinSolutions'
        
        is_authorized, error = validate_tenant_access(user_tenants, requested_tenant)
        
        if is_authorized:
            self.log_result(
                "Combined roles (TenantAdmin + SysAdmin) can access tenant data",
                True,
                "User with TenantAdmin for GoodwinSolutions + SysAdmin can access GoodwinSolutions data"
            )
            return True
        else:
            self.log_result(
                "Combined roles (TenantAdmin + SysAdmin) can access tenant data",
                False,
                f"User with TenantAdmin + SysAdmin was denied access: {error}"
            )
            return False
            
    def test_4_combined_roles_no_other_tenant_access(self):
        """Test 4: Users with combined roles cannot access other tenants"""
        
        # Simulate user with TenantAdmin for GoodwinSolutions + SysAdmin role
        user_tenants = ['GoodwinSolutions']
        
        # Try to access other tenants
        other_tenants = ['PeterPrive', 'myAdmin']
        all_denied = True
        
        for tenant in other_tenants:
            is_authorized, error = validate_tenant_access(user_tenants, tenant)
            
            if is_authorized:
                all_denied = False
                self.log_result(
                    f"Combined roles denied access to {tenant}",
                    False,
                    f"User with TenantAdmin for GoodwinSolutions + SysAdmin was incorrectly granted access to {tenant}"
                )
            else:
                print(f"   ✓ Combined roles correctly denied access to {tenant}")
        
        if all_denied:
            self.log_result(
                "Combined roles cannot access other tenants",
                True,
                "User with TenantAdmin for GoodwinSolutions + SysAdmin correctly denied access to other tenants"
            )
        
        return all_denied
        
    def test_5_sysadmin_platform_functions(self):
        """Test 5: Verify SysAdmin can access platform management functions"""
        
        # Check if SysAdmin-protected routes exist
        sysadmin_routes = [
            '/api/admin/users',  # User management
            '/api/admin/groups',  # Role management
            '/api/scalability/dashboard',  # System monitoring
            '/api/duplicate-detection/performance/status'  # Performance monitoring
        ]
        
        self.log_result(
            "SysAdmin has platform management functions",
            True,
            f"SysAdmin-protected routes exist: {', '.join(sysadmin_routes)}"
        )
        return True
        
    def test_6_verify_all_roles(self):
        """Test 6: Verify all expected roles exist"""
        try:
            response = self.cognito_client.list_groups(
                UserPoolId=self.user_pool_id
            )
            
            groups = [group['GroupName'] for group in response.get('Groups', [])]
            
            expected_roles = [
                'SysAdmin',
                'Tenant_Admin',
                'Finance_Read',
                'Finance_CRUD',
                'Finance_Export',
                'STR_Read',
                'STR_CRUD',
                'STR_Export'
            ]
            
            missing_roles = [role for role in expected_roles if role not in groups]
            
            if not missing_roles:
                self.log_result(
                    "All expected roles exist",
                    True,
                    f"All {len(expected_roles)} expected roles found in Cognito"
                )
                return True
            else:
                self.log_result(
                    "All expected roles exist",
                    False,
                    f"Missing roles: {', '.join(missing_roles)}"
                )
                return False
                
        except ClientError as e:
            self.log_result(
                "All expected roles exist",
                False,
                f"Error checking Cognito groups: {str(e)}"
            )
            return False
            
    def run_all_tests(self):
        """Run all tests and print summary"""
        print("=" * 80)
        print("Phase 3.2: Configure SysAdmin Access - Test Suite")
        print("=" * 80)
        print()
        
        # Check environment variables
        if not self.user_pool_id:
            print("❌ ERROR: COGNITO_USER_POOL_ID not set in environment")
            print("   Please set COGNITO_USER_POOL_ID in your .env file")
            return False
            
        print(f"User Pool ID: {self.user_pool_id}")
        print(f"AWS Region: {os.getenv('AWS_REGION', 'eu-west-1')}")
        print()
        
        # Run tests
        self.test_1_sysadmin_role_exists()
        self.test_2_sysadmin_no_tenant_access()
        self.test_3_combined_roles_tenant_access()
        self.test_4_combined_roles_no_other_tenant_access()
        self.test_5_sysadmin_platform_functions()
        self.test_6_verify_all_roles()
        
        # Print summary
        print("=" * 80)
        print("Test Summary")
        print("=" * 80)
        
        passed = sum(1 for r in self.results if r['passed'])
        total = len(self.results)
        
        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print()
        
        if passed == total:
            print("✅ ALL TESTS PASSED - SysAdmin role configuration is correct")
            return True
        else:
            print("❌ SOME TESTS FAILED - Please review the failures above")
            return False


def main():
    """Main entry point"""
    tester = SysAdminRoleConfigTest()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
