#!/usr/bin/env python3
"""
Verify Cognito setup for SysAdmin module
"""
import os
import sys
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

# Get Cognito configuration
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
REGION = os.getenv('AWS_REGION', 'eu-west-1')

def verify_cognito_groups():
    """Verify SysAdmin and Tenant_Admin groups exist"""
    print("="*60)
    print("COGNITO GROUPS VERIFICATION")
    print("="*60)
    print()
    
    try:
        client = boto3.client('cognito-idp', region_name=REGION)
        
        # List all groups
        response = client.list_groups(UserPoolId=USER_POOL_ID)
        groups = response.get('Groups', [])
        
        print(f"Found {len(groups)} groups:")
        print()
        
        group_names = []
        for group in groups:
            name = group['GroupName']
            desc = group.get('Description', 'No description')
            print(f"  ✅ {name}")
            print(f"     Description: {desc}")
            print()
            group_names.append(name)
        
        # Check for required groups
        required_groups = ['SysAdmin', 'Tenant_Admin']
        missing_groups = []
        
        for required in required_groups:
            if required not in group_names:
                missing_groups.append(required)
                print(f"  ❌ {required} - NOT FOUND")
            else:
                print(f"  ✅ {required} - EXISTS")
        
        print()
        return len(missing_groups) == 0, missing_groups
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, []

def verify_custom_attributes():
    """Verify custom:tenants attribute is configured"""
    print("="*60)
    print("CUSTOM ATTRIBUTES VERIFICATION")
    print("="*60)
    print()
    
    try:
        client = boto3.client('cognito-idp', region_name=REGION)
        
        # Describe user pool
        response = client.describe_user_pool(UserPoolId=USER_POOL_ID)
        user_pool = response['UserPool']
        
        schema = user_pool.get('SchemaAttributes', [])
        
        print("Custom attributes:")
        print()
        
        custom_attrs = [attr for attr in schema if attr['Name'].startswith('custom:')]
        
        if not custom_attrs:
            print("  ❌ No custom attributes found")
            return False
        
        tenants_attr = None
        for attr in custom_attrs:
            name = attr['Name']
            attr_type = attr.get('AttributeDataType', 'Unknown')
            mutable = attr.get('Mutable', False)
            
            if name == 'custom:tenants':
                tenants_attr = attr
                max_len = attr.get('StringAttributeConstraints', {}).get('MaxLength', 'N/A')
                print(f"  ✅ {name}")
                print(f"     Type: {attr_type}")
                print(f"     Mutable: {mutable}")
                print(f"     Max Length: {max_len}")
            else:
                print(f"  ℹ️  {name} (Type: {attr_type})")
            print()
        
        if tenants_attr:
            max_len = tenants_attr.get('StringAttributeConstraints', {}).get('MaxLength', 0)
            if int(max_len) >= 2048:
                print(f"  ✅ custom:tenants max length ({max_len}) is sufficient (>= 2048)")
                return True
            else:
                print(f"  ⚠️  custom:tenants max length ({max_len}) may be too small (recommended: 2048)")
                return True  # Still exists, just warning
        else:
            print("  ❌ custom:tenants attribute NOT FOUND")
            return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def list_users():
    """List all users in the user pool"""
    print("="*60)
    print("USERS VERIFICATION")
    print("="*60)
    print()
    
    try:
        client = boto3.client('cognito-idp', region_name=REGION)
        
        # List users
        response = client.list_users(UserPoolId=USER_POOL_ID)
        users = response.get('Users', [])
        
        print(f"Found {len(users)} users:")
        print()
        
        for user in users:
            username = user['Username']
            status = user['UserStatus']
            enabled = user['Enabled']
            created = user['UserCreateDate']
            
            # Get email
            email = None
            for attr in user.get('Attributes', []):
                if attr['Name'] == 'email':
                    email = attr['Value']
                    break
            
            print(f"  Username: {username}")
            print(f"  Email: {email}")
            print(f"  Status: {status}")
            print(f"  Enabled: {enabled}")
            print(f"  Created: {created}")
            
            # Get groups for this user
            try:
                groups_response = client.admin_list_groups_for_user(
                    UserPoolId=USER_POOL_ID,
                    Username=username
                )
                groups = [g['GroupName'] for g in groups_response.get('Groups', [])]
                print(f"  Groups: {', '.join(groups) if groups else 'None'}")
            except:
                print(f"  Groups: Unable to retrieve")
            
            # Get custom:tenants attribute
            tenants = None
            for attr in user.get('Attributes', []):
                if attr['Name'] == 'custom:tenants':
                    tenants = attr['Value']
                    break
            print(f"  Tenants: {tenants if tenants else 'None'}")
            print()
        
        # Check for test users
        test_users = ['peter@pgeers.nl', 'accountant@test.com', 'viewer@test.com']
        found_test_users = [email for email in test_users if any(
            attr['Value'] == email 
            for user in users 
            for attr in user.get('Attributes', []) 
            if attr['Name'] == 'email'
        )]
        
        print("Test users:")
        for test_user in test_users:
            if test_user in found_test_users:
                print(f"  ✅ {test_user} - EXISTS")
            else:
                print(f"  ❌ {test_user} - NOT FOUND")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("="*60)
    print("COGNITO SETUP VERIFICATION FOR SYSADMIN MODULE")
    print("="*60)
    print()
    print(f"User Pool ID: {USER_POOL_ID}")
    print(f"Region: {REGION}")
    print()
    
    # Verify groups
    groups_ok, missing_groups = verify_cognito_groups()
    print()
    
    # Verify custom attributes
    attrs_ok = verify_custom_attributes()
    print()
    
    # List users
    users_ok = list_users()
    print()
    
    # Summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print()
    
    if groups_ok:
        print("✅ All required groups exist (SysAdmin, Tenant_Admin)")
    else:
        print(f"❌ Missing groups: {', '.join(missing_groups)}")
        print("   Run: aws cognito-idp create-group --user-pool-id {USER_POOL_ID} --group-name <GROUP_NAME> --description '<DESCRIPTION>'")
    
    if attrs_ok:
        print("✅ custom:tenants attribute is configured")
    else:
        print("❌ custom:tenants attribute is missing or misconfigured")
        print("   Note: Custom attributes cannot be added after user pool creation")
        print("   You may need to recreate the user pool or use a workaround")
    
    print()
    
    if groups_ok and attrs_ok:
        print("="*60)
        print("✅ COGNITO SETUP IS READY FOR SYSADMIN MODULE")
        print("="*60)
    else:
        print("="*60)
        print("⚠️  COGNITO SETUP NEEDS ATTENTION")
        print("="*60)

if __name__ == "__main__":
    main()
