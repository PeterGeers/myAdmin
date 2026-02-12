"""
Example usage of CredentialService

This script demonstrates how to use the CredentialService to store and retrieve
tenant credentials securely.
"""

import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from services.credential_service import CredentialService

load_dotenv()


def main():
    """Demonstrate CredentialService usage"""
    
    print("=" * 60)
    print("CredentialService Example")
    print("=" * 60)
    
    # Initialize database and service
    print("\n1. Initializing database and credential service...")
    db = DatabaseManager()
    
    # Get encryption key from environment or use a test key
    encryption_key = os.getenv('CREDENTIALS_ENCRYPTION_KEY', 'example_key_12345')
    service = CredentialService(db, encryption_key)
    print("✓ Service initialized")
    
    # Example 1: Store Google Drive credentials
    print("\n2. Storing Google Drive credentials for GoodwinSolutions...")
    google_drive_creds = {
        "type": "service_account",
        "project_id": "myadmin-project",
        "private_key_id": "key123abc",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...(truncated)\n-----END PRIVATE KEY-----\n",
        "client_email": "service@myadmin.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
    
    service.store_credential("GoodwinSolutions", "google_drive", google_drive_creds)
    print("✓ Google Drive credentials stored")
    
    # Example 2: Store S3 credentials
    print("\n3. Storing S3 credentials for PeterPrive...")
    s3_creds = {
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "eu-west-1",
        "bucket": "peterprive-storage"
    }
    
    service.store_credential("PeterPrive", "s3", s3_creds)
    print("✓ S3 credentials stored")
    
    # Example 3: Retrieve credentials
    print("\n4. Retrieving credentials...")
    retrieved_google = service.get_credential("GoodwinSolutions", "google_drive")
    print(f"✓ Retrieved Google Drive credentials for GoodwinSolutions")
    print(f"  Project ID: {retrieved_google['project_id']}")
    print(f"  Client Email: {retrieved_google['client_email']}")
    
    retrieved_s3 = service.get_credential("PeterPrive", "s3")
    print(f"✓ Retrieved S3 credentials for PeterPrive")
    print(f"  Region: {retrieved_s3['region']}")
    print(f"  Bucket: {retrieved_s3['bucket']}")
    
    # Example 4: List all credential types for a tenant
    print("\n5. Listing all credentials for GoodwinSolutions...")
    credentials = service.list_credential_types("GoodwinSolutions")
    for cred in credentials:
        print(f"  - {cred['type']} (created: {cred['created_at']})")
    
    # Example 5: Check if credential exists
    print("\n6. Checking credential existence...")
    exists = service.credential_exists("GoodwinSolutions", "google_drive")
    print(f"✓ Google Drive credentials exist for GoodwinSolutions: {exists}")
    
    exists = service.credential_exists("GoodwinSolutions", "nonexistent")
    print(f"✓ Nonexistent credentials exist for GoodwinSolutions: {exists}")
    
    # Example 6: Update existing credential
    print("\n7. Updating S3 credentials for PeterPrive...")
    updated_s3_creds = {
        "access_key_id": "AKIAIOSFODNN7NEWKEY",
        "secret_access_key": "newSecretKey123456789",
        "region": "eu-west-1",
        "bucket": "peterprive-storage-v2"
    }
    service.store_credential("PeterPrive", "s3", updated_s3_creds)
    print("✓ S3 credentials updated")
    
    # Verify update
    updated = service.get_credential("PeterPrive", "s3")
    print(f"  New bucket: {updated['bucket']}")
    
    # Example 7: Delete credential
    print("\n8. Deleting S3 credentials for PeterPrive...")
    deleted = service.delete_credential("PeterPrive", "s3")
    print(f"✓ Deletion successful: {deleted}")
    
    # Verify deletion
    exists = service.credential_exists("PeterPrive", "s3")
    print(f"✓ S3 credentials still exist: {exists}")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
