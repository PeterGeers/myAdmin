#!/usr/bin/env python3
"""
Verify Template Folders

Quick verification script to check that template folders exist and are accessible.
"""

import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager
from google_drive_service import GoogleDriveService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_tenant_folders(administration: str):
    """Verify folders for a tenant"""
    print(f"\n{'='*60}")
    print(f"Verifying folders for: {administration}")
    print(f"{'='*60}")
    
    db = DatabaseManager()
    
    # Get folder IDs from database
    query = """
        SELECT config_key, config_value 
        FROM tenant_config 
        WHERE administration = %s AND config_key LIKE '%folder%'
        ORDER BY config_key
    """
    configs = db.execute_query(query, (administration,))
    
    if not configs:
        print(f"❌ No folder configuration found for {administration}")
        return False
    
    print(f"\n📋 Folder Configuration:")
    for config in configs:
        print(f"  {config['config_key']}: {config['config_value']}")
    
    # Try to authenticate and list folders
    try:
        drive_service = GoogleDriveService(administration)
        print(f"\n✅ Successfully authenticated with Google Drive")
        
        # Verify each folder exists
        print(f"\n🔍 Verifying folder access:")
        for config in configs:
            if config['config_key'] == 'google_drive_root_folder_id':
                continue
            
            folder_id = config['config_value']
            folder_name = config['config_key'].replace('google_drive_', '').replace('_folder_id', '').title()
            
            try:
                # Try to get folder metadata
                folder = drive_service.service.files().get(
                    fileId=folder_id,
                    fields='id,name,webViewLink'
                ).execute()
                
                print(f"  ✅ {folder_name}: {folder['name']} ({folder_id})")
                print(f"     URL: {folder.get('webViewLink', 'N/A')}")
            except Exception as e:
                print(f"  ❌ {folder_name}: Failed to access ({folder_id})")
                print(f"     Error: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to authenticate: {e}")
        return False


def main():
    """Main entry point"""
    db = DatabaseManager()
    
    # Get all tenants with credentials
    query = "SELECT DISTINCT administration FROM tenant_credentials WHERE credential_type = 'google_drive_oauth'"
    tenants = db.execute_query(query)
    
    if not tenants:
        print("❌ No tenants found with Google Drive credentials")
        return
    
    print("="*60)
    print("Template Folders Verification")
    print("="*60)
    
    results = {}
    for tenant in tenants:
        administration = tenant['administration']
        results[administration] = verify_tenant_folders(administration)
    
    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    for administration, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{administration}: {status}")


if __name__ == '__main__':
    main()
