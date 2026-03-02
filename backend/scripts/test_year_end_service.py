"""
Test script for Year-End Closure Service

Tests the YearEndClosureService methods implemented so far.

Usage:
    python scripts/test_year_end_service.py [tenant]
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.year_end_service import YearEndClosureService


def test_service_initialization():
    """Test: Service initialization"""
    print("\n1. Testing YearEndClosureService initialization...")
    try:
        service = YearEndClosureService(test_mode=False)
        print("   ✅ Service initialized successfully")
        return service
    except Exception as e:
        print(f"   ❌ Failed to initialize service: {e}")
        return None


def test_get_available_years(service, tenant):
    """Test: Get available years"""
    print(f"\n2. Testing get_available_years() for tenant '{tenant}'...")
    try:
        years = service.get_available_years(tenant)
        print(f"   ✅ Found {len(years)} available years: {years}")
        return years
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return []


def test_get_closed_years(service, tenant):
    """Test: Get closed years"""
    print(f"\n3. Testing get_closed_years() for tenant '{tenant}'...")
    try:
        closed = service.get_closed_years(tenant)
        print(f"   ✅ Found {len(closed)} closed years")
        for year_info in closed:
            print(f"      - Year {year_info['year']}: closed on {year_info['closed_date']} by {year_info['closed_by']}")
        return closed
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return []


def test_get_year_status(service, tenant, year):
    """Test: Get year status"""
    print(f"\n4. Testing get_year_status() for year {year}...")
    try:
        status = service.get_year_status(tenant, year)
        if status:
            print(f"   ✅ Year {year} is closed:")
            print(f"      - Closed date: {status['closed_date']}")
            print(f"      - Closed by: {status['closed_by']}")
            print(f"      - Closure transaction: {status['closure_transaction_number']}")
            print(f"      - Opening balance transaction: {status['opening_balance_transaction_number']}")
        else:
            print(f"   ✅ Year {year} is not closed")
        return status
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return None


def test_calculate_net_pl_result(service, tenant, year):
    """Test: Calculate net P&L result"""
    print(f"\n5. Testing _calculate_net_pl_result() for year {year}...")
    try:
        net_result = service._calculate_net_pl_result(tenant, year)
        print(f"   ✅ Net P&L result for {year}: €{net_result:,.2f}")
        if net_result > 0:
            print(f"      → Profit")
        elif net_result < 0:
            print(f"      → Loss")
        else:
            print(f"      → Break-even")
        return net_result
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return None


def test_count_balance_sheet_accounts(service, tenant, year):
    """Test: Count balance sheet accounts"""
    print(f"\n6. Testing _count_balance_sheet_accounts() for year {year}...")
    try:
        count = service._count_balance_sheet_accounts(tenant, year)
        print(f"   ✅ Found {count} balance sheet accounts with non-zero balances")
        return count
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return None


def test_validate_year_closure(service, tenant, year):
    """Test: Validate year closure"""
    print(f"\n7. Testing validate_year_closure() for year {year}...")
    try:
        validation = service.validate_year_closure(tenant, year)
        
        print(f"   Can close: {validation['can_close']}")
        
        if validation['errors']:
            print(f"   ❌ Errors ({len(validation['errors'])}):")
            for error in validation['errors']:
                print(f"      - {error}")
        else:
            print(f"   ✅ No errors")
        
        if validation['warnings']:
            print(f"   ⚠️  Warnings ({len(validation['warnings'])}):")
            for warning in validation['warnings']:
                print(f"      - {warning}")
        
        if validation['info']:
            print(f"   ℹ️  Information:")
            for key, value in validation['info'].items():
                print(f"      - {key}: {value}")
        
        return validation
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return None


def test_is_year_closed(service, tenant, year):
    """Test: Check if year is closed"""
    print(f"\n8. Testing _is_year_closed() for year {year}...")
    try:
        is_closed = service._is_year_closed(tenant, year)
        print(f"   ✅ Year {year} is {'closed' if is_closed else 'open'}")
        return is_closed
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return None


def test_get_first_year(service, tenant):
    """Test: Get first year"""
    print(f"\n9. Testing _get_first_year() for tenant '{tenant}'...")
    try:
        first_year = service._get_first_year(tenant)
        print(f"   ✅ First year with transactions: {first_year}")
        return first_year
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return None


def main():
    """Run all tests"""
    print("=" * 60)
    print("Year-End Closure Service Tests")
    print("=" * 60)
    
    # Get tenant from command line or use default
    tenant = sys.argv[1] if len(sys.argv) > 1 else 'GoodwinSolutions'
    print(f"\nTesting with tenant: {tenant}")
    
    # Test 1: Initialize service
    service = test_service_initialization()
    if not service:
        print("\n❌ Cannot continue without service initialization")
        return 1
    
    # Test 2: Get available years
    available_years = test_get_available_years(service, tenant)
    
    # Test 3: Get closed years
    closed_years = test_get_closed_years(service, tenant)
    
    # Test 4: Get first year
    first_year = test_get_first_year(service, tenant)
    
    # Pick a year to test with (use first available or first year)
    test_year = available_years[0] if available_years else (first_year if first_year else 2024)
    print(f"\n📅 Using year {test_year} for remaining tests")
    
    # Test 5: Get year status
    test_get_year_status(service, tenant, test_year)
    
    # Test 6: Check if year is closed
    test_is_year_closed(service, tenant, test_year)
    
    # Test 7: Calculate net P&L result
    test_calculate_net_pl_result(service, tenant, test_year)
    
    # Test 8: Count balance sheet accounts
    test_count_balance_sheet_accounts(service, tenant, test_year)
    
    # Test 9: Validate year closure
    test_validate_year_closure(service, tenant, test_year)
    
    # Test with multiple years if available
    if len(available_years) > 1:
        print(f"\n📅 Testing with additional year: {available_years[1]}")
        test_calculate_net_pl_result(service, tenant, available_years[1])
        test_validate_year_closure(service, tenant, available_years[1])
    
    print("\n" + "=" * 60)
    print("Tests Complete")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
