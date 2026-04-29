#!/usr/bin/env python3
"""
Refresh Google Drive OAuth Token
This script refreshes the expired Google Drive OAuth token by running the OAuth flow.
"""

import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = 'backend/credentials.json'
TOKEN_FILE = 'backend/token.json'

def refresh_token():
    """Refresh or create a new Google Drive OAuth token"""
    creds = None
    
    # Try to load existing token
    if os.path.exists(TOKEN_FILE):
        print(f"📖 Loading existing token from {TOKEN_FILE}...")
        with open(TOKEN_FILE, 'r') as token:
            token_data = json.load(token)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    
    # Check if credentials are valid or need refresh
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            try:
                creds.refresh(Request())
                print("✅ Token refreshed successfully!")
            except Exception as e:
                print(f"❌ Failed to refresh token: {e}")
                print("🔐 Starting new OAuth flow...")
                creds = None
        
        if not creds:
            # Run OAuth flow
            print(f"🔐 Starting OAuth flow using {CREDENTIALS_FILE}...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            print("✅ OAuth flow completed successfully!")
        
        # Save the credentials
        print(f"💾 Saving token to {TOKEN_FILE}...")
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        print("✅ Token saved successfully!")
    else:
        print("✅ Token is still valid!")
    
    return creds

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Google Drive Token Refresh")
    print("=" * 60)
    print()
    
    try:
        creds = refresh_token()
        print()
        print("=" * 60)
        print("✅ Token refresh completed!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Run the migration script to update the database:")
        print("   python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions")
        print("2. Restart the backend container:")
        print("   docker-compose restart backend")
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Token refresh failed: {e}")
        print("=" * 60)
        exit(1)
