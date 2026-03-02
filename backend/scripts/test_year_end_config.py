"""
Quick test script for Year-End Configuration Service

Tests the YearEndConfigService to verify Phase 1 implementation.
Run this to validate the backend service works correctly.

Usage:
    python scripts/test_year_end_config.py
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.year_end_config import YearEndConfigService


def test_service_initialization():
    """Test 1: Service initialization"""
    print("\n1. Testing YearEndConfigService initialization...")
    try:
        service = YearEndConfigService(test_mode=False)
        print("   ✅ Service initialized successfully")
        return service
    except Exception as e:
        print(f"   ❌ Failed to initialize service: {e}")
        return None


def test_required_purposes(service):
    """Test 2: REQUIRED_PURPOSES contains 3 purposes"""
    print("\n2. Testing REQUIRED_PURPOSES...")
    try:
        purposes = service.REQUIRED_PURPOSES
        assert len(purposes) == 3, f"Expected 3 purposes, got {len(purposes)}"
        assert 'equity_result' in purposes
        assert 'pl_closing' in purposes
        assert 'interim_opening_balance' in purposes
        print(f"   ✅ REQUIRED_PURPOSES contains 3 purposes: {list(purposes.keys())}")
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_validate_no_config(service, tenant):
    """Test 3: validate_configuration() with no config (should fail)"""
    print(f"\n3. Testing validate_configuration() with no config for tenant '{tenant}'...")
    try:
        validation = service.validate_configuration(tenant)
        
        if validation['valid']:
            print(f"   ⚠️  Warning: Configuration is valid (expected invalid)")
            print(f"   Configured purposes: {validation['configured_purposes']}")
        else:
            print(f"   ✅ Validation correctly failed")
            print(f"   Errors: {len(validation['errors'])}")
            for error in validation['errors']:
                print(f"      - {error}")
        
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_get_available_accounts(service, tenant):
    """Test 4: get_available_accounts() with VW filter"""
    print(f"\n4. Testing get_available_accounts() with VW filter for tenant '{tenant}'...")
    try:
        # Test with VW='N' (Balance Sheet)
        accounts_n = service.get_available_accounts(tenant, vw_filter='N')
        print(f"   ✅ Found {len(accounts_n)} accounts with VW='N' (Balance Sheet)")
        if accounts_n:
            print(f"      Example: {accounts_n[0]['Account']} - {accounts_n[0]['AccountName']}")
        
        # Test with VW='Y' (P&L)
        accounts_y = service.get_available_accounts(tenant, vw_filter='Y')
        print(f"   ✅ Found {len(accounts_y)} accounts with VW='Y' (P&L)")
        if accounts_y:
            print(f"      Example: {accounts_y[0]['Account']} - {accounts_y[0]['AccountName']}")
        
        # Test without filter
        accounts_all = service.get_available_accounts(tenant)
        print(f"   ✅ Found {len(accounts_all)} total accounts (no filter)")
        
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_set_account_purpose(service, tenant, account_code, purpose):
    """Test 5: set_account_purpose() updates database"""
    print(f"\n5. Testing set_account_purpose() for tenant '{tenant}'...")
    try:
        # First, get an account to test with
        accounts = service.get_available_accounts(tenant, vw_filter='N')
        if not accounts:
            print("   ⚠️  No accounts available for testing")
            return False
        
        test_account = account_code or accounts[0]['Account']
        test_purpose = purpose or 'equity_result'
        
        print(f"   Setting purpose '{test_purpose}' for account {test_account}...")
        service.set_account_purpose(tenant, test_account, test_purpose)
        print(f"   ✅ Purpose set successfully")
        
        # Verify it was set
        configured = service.get_all_configured_purposes(tenant)
        if test_purpose in configured:
            print(f"   ✅ Verified: {configured[test_purpose]}")
        else:
            print(f"   ❌ Purpose not found in configured purposes")
            return False
        
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def test_get_configured_purposes(service, tenant):
    """Test 6: get_configured_purposes() returns correct data"""
    print(f"\n6. Testing get_configured_purposes() for tenant '{tenant}'...")
    try:
        configured = service.get_all_configured_purposes(tenant)
        print(f"   ✅ Found {len(configured)} configured purposes")
        
        for purpose, info in configured.items():
            print(f"      - {purpose}: {info['account_code']} - {info['account_name']} (VW={info['vw']})")
        
        return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Year-End Configuration Service Tests")
    print("=" * 60)
    
    # Get tenant from command line or use default
    tenant = sys.argv[1] if len(sys.argv) > 1 else 'GoodwinSolutions'
    print(f"\nTesting with tenant: {tenant}")
    
    # Test 1: Initialize service
    service = test_service_initialization()
    if not service:
        print("\n❌ Cannot continue without service initialization")
        return 1
    
    # Test 2: Required purposes
    test_required_purposes(service)
    
    # Test 3: Validate with no config
    test_validate_no_config(service, tenant)
    
    # Test 4: Get available accounts
    test_get_available_accounts(service, tenant)
    
    # Test 5: Set account purpose (optional - only if account code provided)
    if len(sys.argv) > 2:
        account_code = sys.argv[2]
        purpose = sys.argv[3] if len(sys.argv) > 3 else 'equity_result'
        test_set_account_purpose(service, tenant, account_code, purpose)
    else:
        print("\n5. Skipping set_account_purpose() test (no account code provided)")
        print("   To test: python scripts/test_year_end_config.py <tenant> <account_code> <purpose>")
    
    # Test 6: Get configured purposes
    test_get_configured_purposes(service, tenant)
    
    print("\n" + "=" * 60)
    print("Tests Complete")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
