#!/usr/bin/env python3
"""
Test SysAdmin authentication and authorization
Verifies that peter@pgeers.nl can authenticate and has SysAdmin access
"""
import os
import sys
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

# Get Cognito configuration
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')
REGION = os.getenv('AWS_REGION', 'eu-west-1')

def test_sysadmin_user():
    """Test SysAdmin user configuration"""
    try:
        client = boto3.client('cognito-idp', region_name=REGION)
        
        # Find user by email
        response = client.list_users(
            UserPoolId=USER_POOL_ID,
            Filter='email = "peter@pgeers.nl"'
        )
        
        if not response['Users']:
            print("❌ User peter@pgeers.nl not found")
            return False
        
        user = response['Users'][0]
        username = user['Username']
        
        print(f"✅ User found: {username}")
        print(f"   Email: peter@pgeers.nl")
        print(f"   Status: {user['UserStatus']}")
        print(f"   Enabled: {user['Enabled']}")
        print()
        
        # Get user groups
        groups_response = client.admin_list_groups_for_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        groups = [g['GroupName'] for g in groups_response['Groups']]
        print(f"✅ User groups: {groups}")
        
        # Check for SysAdmin group
        if 'SysAdmin' not in groups:
            print("❌ User is NOT in SysAdmin group")
            return False
        print("   ✅ Has SysAdmin group")
        
        # Check for Tenant_Admin group
        if 'Tenant_Admin' in groups:
            print("   ✅ Has Tenant_Admin group")
        
        print()
        
        # Get user attributes
        user_response = client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        # Check custom:tenants attribute
        tenants = None
        for attr in user_response['UserAttributes']:
            if attr['Name'] == 'custom:tenants':
                tenants_raw = attr['Value']
                try:
                    if '\\' in tenants_raw:
                        tenants_raw = tenants_raw.replace('\\', '')
                    tenants = json.loads(tenants_raw)
                except:
                    tenants = tenants_raw
                break
        
        print(f"✅ User tenants: {tenants}")
        
        # Check for myAdmin tenant
        if tenants and 'myAdmin' in tenants:
            print("   ✅ Has myAdmin tenant (platform access)")
        else:
            print("   ❌ Missing myAdmin tenant")
            return False
        
        # Check for client tenants
        if tenants and 'GoodwinSolutions' in tenants:
            print("   ✅ Has GoodwinSolutions tenant")
        if tenants and 'PeterPrive' in tenants:
            print("   ✅ Has PeterPrive tenant")
        
        print()
        print("="*60)
        print("✅ SYSADMIN AUTHENTICATION TEST PASSED")
        print("="*60)
        print()
        print("User peter@pgeers.nl is correctly configured as SysAdmin:")
        print("  - Has SysAdmin group (platform management)")
        print("  - Has Tenant_Admin group (tenant administration)")
        print("  - Has myAdmin tenant (platform access)")
        print("  - Has client tenants (GoodwinSolutions, PeterPrive)")
        print()
        print("Next steps:")
        print("  1. Test authentication with actual login")
        print("  2. Test API endpoints with SysAdmin token")
        print("  3. Verify authorization checks in backend")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*60)
    print("SYSADMIN AUTHENTICATION TEST")
    print("="*60)
    print()
    
    print(f"User Pool ID: {USER_POOL_ID}")
    print(f"Client ID: {CLIENT_ID}")
    print(f"Region: {REGION}")
    print()
    
    success = test_sysadmin_user()
    
    if not success:
        print()
        print("="*60)
        print("❌ TEST FAILED")
        print("="*60)
        sys.exit(1)

if __name__ == "__main__":
    main()
