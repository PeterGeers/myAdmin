#!/usr/bin/env python3
"""
Google Drive Token Health Check
Checks if Google Drive OAuth tokens are valid and will expire soon.
Can be run as a cron job to monitor token health.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add backend/src to path for imports
backend_src = Path(__file__).parent / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager
from services.credential_service import CredentialService

# Configuration
TENANTS = ['GoodwinSolutions', 'PeterPrive']
WARNING_DAYS = 7  # Warn if token expires within this many days
TOKEN_FILE = 'backend/token.json'


def check_token_expiry(token_data):
    """
    Check if token is expired or will expire soon.
    
    Returns:
        tuple: (is_expired, days_until_expiry, expiry_date)
    """
    if not token_data or 'expiry' not in token_data:
        return (True, 0, None)
    
    expiry_str = token_data['expiry']
    
    # Parse expiry date (format: "28-1-2026 15:50:49" or ISO format)
    try:
        # Try ISO format first
        expiry_date = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
    except:
        try:
            # Try custom format
            expiry_date = datetime.strptime(expiry_str, "%d-%m-%Y %H:%M:%S")
        except:
            print(f"⚠️  Warning: Could not parse expiry date: {expiry_str}")
            return (True, 0, None)
    
    now = datetime.now()
    if expiry_date.tzinfo:
        # Make now timezone-aware if expiry_date is
        from datetime import timezone
        now = datetime.now(timezone.utc)
    
    is_expired = now >= expiry_date
    days_until_expiry = (expiry_date - now).days
    
    return (is_expired, days_until_expiry, expiry_date)


def check_file_token():
    """Check the token.json file"""
    print("=" * 60)
    print("📄 Checking token.json file")
    print("=" * 60)
    
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ Token file not found: {TOKEN_FILE}")
        return False
    
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
        
        is_expired, days_until_expiry, expiry_date = check_token_expiry(token_data)
        
        if is_expired:
            print(f"❌ Token is EXPIRED (expired on {expiry_date})")
            print(f"📝 Action required: Run 'python backend/refresh_google_token.py'")
            return False
        elif days_until_expiry <= WARNING_DAYS:
            print(f"⚠️  Token will expire in {days_until_expiry} days (on {expiry_date})")
            print(f"📝 Recommended: Run 'python backend/refresh_google_token.py' soon")
            return True
        else:
            print(f"✅ Token is valid (expires in {days_until_expiry} days on {expiry_date})")
            return True
    
    except Exception as e:
        print(f"❌ Error checking token file: {e}")
        return False


def check_database_tokens():
    """Check tokens stored in the database for all tenants"""
    print("\n" + "=" * 60)
    print("🗄️  Checking database tokens for tenants")
    print("=" * 60)
    
    try:
        db = DatabaseManager()
        credential_service = CredentialService(db)
        
        all_healthy = True
        
        for tenant in TENANTS:
            print(f"\n📊 Tenant: {tenant}")
            print("-" * 40)
            
            # Check if credentials exist
            oauth_creds = credential_service.get_credential(tenant, 'google_drive_oauth')
            token_data = credential_service.get_credential(tenant, 'google_drive_token')
            
            if not oauth_creds:
                print(f"❌ OAuth credentials not found in database")
                all_healthy = False
                continue
            
            if not token_data:
                print(f"❌ Token not found in database")
                all_healthy = False
                continue
            
            # Check token expiry
            is_expired, days_until_expiry, expiry_date = check_token_expiry(token_data)
            
            if is_expired:
                print(f"❌ Token is EXPIRED (expired on {expiry_date})")
                print(f"📝 Action required:")
                print(f"   1. Run: python backend/refresh_google_token.py")
                print(f"   2. Run: python scripts/credentials/migrate_credentials_to_db.py --tenant {tenant}")
                print(f"   3. Run: docker-compose restart backend")
                all_healthy = False
            elif days_until_expiry <= WARNING_DAYS:
                print(f"⚠️  Token will expire in {days_until_expiry} days (on {expiry_date})")
                print(f"📝 Recommended: Refresh token soon")
            else:
                print(f"✅ Token is valid (expires in {days_until_expiry} days on {expiry_date})")
        
        return all_healthy
    
    except Exception as e:
        print(f"❌ Error checking database tokens: {e}")
        return False


def main():
    """Main entry point"""
    print("🔍 Google Drive Token Health Check")
    print(f"⏰ Check time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check file token
    file_healthy = check_file_token()
    
    # Check database tokens
    db_healthy = check_database_tokens()
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Summary")
    print("=" * 60)
    
    if file_healthy and db_healthy:
        print("✅ All tokens are healthy!")
        return 0
    elif not file_healthy:
        print("❌ Token file needs attention")
        print("\n🔧 Quick fix:")
        print("   python backend/refresh_google_token.py")
        print("   python scripts/credentials/migrate_credentials_to_db.py --tenant GoodwinSolutions")
        print("   docker-compose restart backend")
        return 1
    else:
        print("⚠️  Some tokens need attention (see details above)")
        return 1


if __name__ == '__main__':
    sys.exit(main())
