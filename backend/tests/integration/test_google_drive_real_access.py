"""
Real Google Drive Access Test
Tests actual Google Drive API access for both tenants.

This is a manual test to verify Google Drive access works correctly.
Run with: python backend/tests/integration/test_google_drive_real_access.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv('backend/.env')

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from google_drive_service import GoogleDriveService


def test_tenant_access(tenant_name):
    """Test Google Drive access for a specific tenant"""
    print(f"\n{'='*60}")
    print(f"Testing Google Drive access for: {tenant_name}")
    print(f"{'='*60}")
    
    try:
        # Initialize service
        print(f"1. Initializing GoogleDriveService for {tenant_name}...")
        drive_service = GoogleDriveService(tenant_name)
        print(f"   ✅ Service initialized successfully")
        
        # Test listing subfolders
        print(f"2. Testing list_subfolders()...")
        folders = drive_service.list_subfolders()
        print(f"   ✅ Found {len(folders)} folders")
        
        if folders:
            print(f"   First 3 folders:")
            for folder in folders[:3]:
                print(f"     - {folder['name']}")
        
        print(f"\n✅ All tests passed for {tenant_name}!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed for {tenant_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("\n" + "="*60)
    print("Google Drive Real Access Test")
    print("="*60)
    
    tenants = ['GoodwinSolutions', 'PeterPrive']
    results = {}
    
    for tenant in tenants:
        results[tenant] = test_tenant_access(tenant)
    
    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for tenant, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{tenant}: {status}")
    
    # Exit with appropriate code
    all_passed = all(results.values())
    if all_passed:
        print("\n✅ All tenants can access Google Drive successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tenants failed to access Google Drive")
        sys.exit(1)


if __name__ == '__main__':
    main()
