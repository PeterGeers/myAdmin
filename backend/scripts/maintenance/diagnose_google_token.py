#!/usr/bin/env python3
"""
Diagnostic script to check Google Drive token status
Compares file-based token vs database-stored token
"""

import sys
import os
import json
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from src.database import DatabaseManager
from src.services.credential_service import CredentialService

def check_file_token():
    """Check token.json file"""
    print("\n" + "="*60)
    print("CHECKING FILE-BASED TOKEN (token.json)")
    print("="*60)
    
    token_path = 'token.json'
    if not os.path.exists(token_path):
        print("❌ token.json NOT FOUND")
        return None
    
    try:
        with open(token_path, 'r') as f:
            token_data = json.load(f)
        
        print("✅ token.json found")
        print(f"   Token URI: {token_data.get('token_uri', 'N/A')}")
        print(f"   Client ID: {token_data.get('client_id', 'N/A')[:50]}...")
        print(f"   Has refresh_token: {'✅' if token_data.get('refresh_token') else '❌'}")
        
        if 'expiry' in token_data:
            expiry = datetime.fromisoformat(token_data['expiry'].replace('Z', '+00:00'))
            now = datetime.now(expiry.tzinfo)
            is_expired = expiry < now
            days_until_expiry = (expiry - now).days
            
            print(f"   Expiry: {expiry}")
            print(f"   Status: {'❌ EXPIRED' if is_expired else f'✅ Valid ({days_until_expiry} days remaining)'}")
        else:
            print(f"   Expiry: ⚠️  No expiry field")
        
        return token_data
    except Exception as e:
        print(f"❌ Error reading token.json: {e}")
        return None

def check_database_token(administration='GoodwinSolutions'):
    """Check database-stored token"""
    print("\n" + "="*60)
    print(f"CHECKING DATABASE TOKEN (administration: {administration})")
    print("="*60)
    
    try:
        db = DatabaseManager(test_mode=False)
        credential_service = CredentialService(db)
        
        # Check OAuth credentials
        print("\n1. OAuth Credentials (credentials.json equivalent):")
        try:
            oauth_creds = credential_service.get_credential(administration, 'google_drive_oauth')
            if oauth_creds:
                print("   ✅ OAuth credentials found")
                print(f"   Client ID: {oauth_creds.get('client_id', 'N/A')[:50]}...")
                print(f"   Project ID: {oauth_creds.get('project_id', 'N/A')}")
            else:
                print("   ❌ OAuth credentials NOT FOUND")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Check token
        print("\n2. Access Token:")
        try:
            token_data = credential_service.get_credential(administration, 'google_drive_token')
            if token_data:
                print("   ✅ Token found")
                print(f"   Token URI: {token_data.get('token_uri', 'N/A')}")
                print(f"   Client ID: {token_data.get('client_id', 'N/A')[:50]}...")
                print(f"   Has refresh_token: {'✅' if token_data.get('refresh_token') else '❌'}")
                
                if 'expiry' in token_data:
                    expiry_str = token_data['expiry']
                    try:
                        expiry = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                        now = datetime.now(expiry.tzinfo)
                        is_expired = expiry < now
                        days_until_expiry = (expiry - now).days
                        
                        print(f"   Expiry: {expiry}")
                        print(f"   Status: {'❌ EXPIRED' if is_expired else f'✅ Valid ({days_until_expiry} days remaining)'}")
                    except Exception as e:
                        print(f"   Expiry: ⚠️  Invalid format: {expiry_str}")
                else:
                    print(f"   Expiry: ⚠️  No expiry field")
                
                return token_data
            else:
                print("   ❌ Token NOT FOUND in database")
                return None
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None
            
    except Exception as e:
        print(f"❌ Database error: {e}")
        return None

def compare_tokens(file_token, db_token):
    """Compare file and database tokens"""
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    
    if not file_token and not db_token:
        print("❌ Both tokens missing!")
        return
    
    if not file_token:
        print("⚠️  File token missing, but database token exists")
        return
    
    if not db_token:
        print("⚠️  Database token missing, but file token exists")
        print("\n💡 SOLUTION: Run migration script:")
        print("   python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions")
        return
    
    # Compare refresh tokens
    file_refresh = file_token.get('refresh_token', '')
    db_refresh = db_token.get('refresh_token', '')
    
    if file_refresh == db_refresh:
        print("✅ Refresh tokens MATCH")
    else:
        print("❌ Refresh tokens DIFFER")
        print(f"   File:     {file_refresh[:30]}...")
        print(f"   Database: {db_refresh[:30]}...")
        print("\n💡 SOLUTION: Database token is outdated. Run migration:")
        print("   python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions")

def main():
    print("\n" + "="*60)
    print("GOOGLE DRIVE TOKEN DIAGNOSTIC")
    print("="*60)
    
    file_token = check_file_token()
    db_token = check_database_token('GoodwinSolutions')
    compare_tokens(file_token, db_token)
    
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    if not file_token:
        print("1. ❌ No file token - run: python backend/refresh_google_token.py")
    elif not db_token:
        print("1. ⚠️  Token not in database - run migration script")
    else:
        print("1. ✅ Both tokens exist")
    
    print("\n" + "="*60)

if __name__ == '__main__':
    main()
