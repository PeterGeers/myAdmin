#!/usr/bin/env python3
"""
Add tenants to a Cognito user's custom:tenants attribute
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

def add_tenants_to_user(username, tenants):
    """Add tenants to user's custom:tenants attribute"""
    try:
        client = boto3.client('cognito-idp', region_name=REGION)
        
        # Get current user attributes
        response = client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )
        
        print(f"Current user: {username}")
        print(f"Email: {[attr['Value'] for attr in response['UserAttributes'] if attr['Name'] == 'email'][0]}")
        
        # Get current tenants
        current_tenants = None
        for attr in response['UserAttributes']:
            if attr['Name'] == 'custom:tenants':
                current_tenants = attr['Value']
                break
        
        print(f"Current tenants: {current_tenants if current_tenants else 'None'}")
        
        # Convert tenants list to JSON string
        tenants_json = json.dumps(tenants)
        
        # Update user attributes
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
        return False

def main():
    print("="*60)
    print("ADD TENANTS TO COGNITO USER")
    print("="*60)
    print()
    
    # User to update
    username = "f205f494-c061-7029-0d6d-4d7c85b8767b"
    tenants = ["GoodwinSolutions", "PeterPrive"]
    
    print(f"User Pool ID: {USER_POOL_ID}")
    print(f"Region: {REGION}")
    print(f"Username: {username}")
    print(f"Tenants to add: {tenants}")
    print()
    
    success = add_tenants_to_user(username, tenants)
    
    print()
    print("="*60)
    if success:
        print("✅ COMPLETE")
    else:
        print("❌ FAILED")
    print("="*60)

if __name__ == "__main__":
    main()
