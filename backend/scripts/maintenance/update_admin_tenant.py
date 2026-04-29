#!/usr/bin/env python3
"""
Add myAdmin tenant to peter@pgeers.nl's custom:tenants attribute
This ensures the SysAdmin user has access to the myAdmin platform tenant
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

def update_admin_tenants():
    """Add myAdmin to peter@pgeers.nl's tenants (restore GoodwinSolutions and PeterPrive)"""
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
        
        print(f"Found user: {username}")
        print(f"Email: peter@pgeers.nl")
        
        # Get current tenants
        current_tenants = None
        current_tenants_raw = None
        for attr in user['Attributes']:
            if attr['Name'] == 'custom:tenants':
                current_tenants_raw = attr['Value']
                try:
                    # Handle escaped quotes in Cognito response
                    if '\\' in current_tenants_raw:
                        # Remove escape characters
                        fixed_json = current_tenants_raw.replace('\\', '')
                        current_tenants = json.loads(fixed_json)
                    else:
                        current_tenants = json.loads(current_tenants_raw)
                except json.JSONDecodeError as e:
                    print(f"⚠️ Could not parse tenants JSON: {current_tenants_raw}")
                    print(f"⚠️ Error: {e}")
                    # Try to handle as plain string or fix format
                    current_tenants = None
                break
        
        print(f"Current tenants (raw): {current_tenants_raw}")
        print(f"Current tenants (parsed): {current_tenants}")
        
        # Set correct tenants: myAdmin, GoodwinSolutions, PeterPrive
        correct_tenants = ["myAdmin", "GoodwinSolutions", "PeterPrive"]
        
        if current_tenants == correct_tenants:
            print("✅ Tenants already correct")
            return True
        
        print(f"Setting tenants to: {correct_tenants}")
        
        # Update user attributes
        tenants_json = json.dumps(correct_tenants)
        client.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=username,
            UserAttributes=[
                {
                    'Name': 'custom:tenants',
                    'Value': tenants_json
                }
            ]
        )
        
        print(f"✅ Updated tenants to: {tenants_json}")
        
        # Verify update
        response = client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        for attr in response['UserAttributes']:
            if attr['Name'] == 'custom:tenants':
                print(f"✅ Verified: {attr['Value']}")
                return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*60)
    print("ADD myAdmin TENANT TO SYSADMIN USER")
    print("="*60)
    print()
    
    print(f"User Pool ID: {USER_POOL_ID}")
    print(f"Region: {REGION}")
    print(f"User: peter@pgeers.nl")
    print(f"Action: Add 'myAdmin' to custom:tenants")
    print()
    
    success = update_admin_tenants()
    
    print()
    print("="*60)
    if success:
        print("✅ COMPLETE")
        print()
        print("peter@pgeers.nl now has access to:")
        print("  - myAdmin (platform management)")
        print("  - GoodwinSolutions (client tenant)")
        print("  - PeterPrive (client tenant)")
    else:
        print("❌ FAILED")
    print("="*60)

if __name__ == "__main__":
    main()
