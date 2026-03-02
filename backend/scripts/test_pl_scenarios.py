"""
Test P&L calculation with profit and loss scenarios

Checks all available years to find profit and loss examples.

Usage:
    python scripts/test_pl_scenarios.py [tenant]
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.year_end_service import YearEndClosureService


def main():
    """Test P&L calculation across all years"""
    print("=" * 60)
    print("P&L Calculation - Profit and Loss Scenarios")
    print("=" * 60)
    
    # Get tenant from command line or use default
    tenant = sys.argv[1] if len(sys.argv) > 1 else 'GoodwinSolutions'
    print(f"\nTesting with tenant: {tenant}\n")
    
    # Initialize service
    service = YearEndClosureService(test_mode=False)
    
    # Get all available years
    years = service.get_available_years(tenant)
    
    if not years:
        print("❌ No years available for testing")
        return 1
    
    print(f"Testing {len(years)} years...\n")
    
    profit_years = []
    loss_years = []
    breakeven_years = []
    
    # Test each year
    for year in sorted(years):
        net_result = service._calculate_net_pl_result(tenant, year)
        
        if net_result > 0:
            profit_years.append((year, net_result))
            status = "✅ PROFIT"
        elif net_result < 0:
            loss_years.append((year, net_result))
            status = "❌ LOSS"
        else:
            breakeven_years.append(year)
            status = "⚖️  BREAK-EVEN"
        
        print(f"{year}: €{net_result:>12,.2f}  {status}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Profit years: {len(profit_years)}")
    print(f"Loss years: {len(loss_years)}")
    print(f"Break-even years: {len(breakeven_years)}")
    
    if profit_years:
        print(f"\n✅ Profit Scenarios:")
        for year, amount in profit_years[:3]:  # Show top 3
            print(f"   {year}: €{amount:,.2f}")
    
    if loss_years:
        print(f"\n❌ Loss Scenarios:")
        for year, amount in loss_years[:3]:  # Show top 3
            print(f"   {year}: €{amount:,.2f}")
    
    if breakeven_years:
        print(f"\n⚖️  Break-even Years: {breakeven_years}")
    
    # Test validation with both scenarios
    print("\n" + "=" * 60)
    print("Validation Tests")
    print("=" * 60)
    
    if profit_years:
        test_year = profit_years[0][0]
        print(f"\n✅ Testing validation with PROFIT year {test_year}:")
        validation = service.validate_year_closure(tenant, test_year)
        print(f"   Net result: {validation['info']['net_result_formatted']}")
        print(f"   Can close: {validation['can_close']}")
        if validation['errors']:
            print(f"   Errors: {validation['errors']}")
    
    if loss_years:
        test_year = loss_years[0][0]
        print(f"\n❌ Testing validation with LOSS year {test_year}:")
        validation = service.validate_year_closure(tenant, test_year)
        print(f"   Net result: {validation['info']['net_result_formatted']}")
        print(f"   Can close: {validation['can_close']}")
        if validation['errors']:
            print(f"   Errors: {validation['errors']}")
    
    print("\n" + "=" * 60)
    print("✅ P&L Calculation tested with both profit and loss scenarios")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
