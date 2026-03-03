"""
Check Year-End Closure Setup

Verifies database tables and configuration are ready.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import DatabaseManager
from services.year_end_config import YearEndConfigService
from services.year_end_service import YearEndClosureService

def check_setup():
    """Check if year-end closure is set up correctly"""
    
    print("=" * 60)
    print("YEAR-END CLOSURE SETUP CHECK")
    print("=" * 60)
    
    # Check database table
    print("\n1. Checking database table...")
    db = DatabaseManager(test_mode=False)
    
    try:
        result = db.execute_query("SHOW TABLES LIKE 'year_closure_status'")
        if result and len(result) > 0:
            print("   ✅ year_closure_status table exists")
            
            # Check table structure
            columns = db.execute_query("DESCRIBE year_closure_status")
            print(f"   ✅ Table has {len(columns)} columns")
            for col in columns:
                print(f"      - {col['Field']}: {col['Type']}")
        else:
            print("   ❌ year_closure_status table NOT found")
            return False
    except Exception as e:
        print(f"   ❌ Error checking table: {e}")
        return False
    
    # Check configuration service
    print("\n2. Checking configuration service...")
    try:
        config_service = YearEndConfigService(test_mode=False)
        print("   ✅ YearEndConfigService initialized")
        print(f"   ✅ Required purposes: {list(config_service.REQUIRED_PURPOSES.keys())}")
    except Exception as e:
        print(f"   ❌ Error initializing config service: {e}")
        return False
    
    # Check year-end service
    print("\n3. Checking year-end service...")
    try:
        service = YearEndClosureService(test_mode=False)
        print("   ✅ YearEndClosureService initialized")
    except Exception as e:
        print(f"   ❌ Error initializing service: {e}")
        return False
    
    # Check for configured accounts (example with GoodwinSolutions)
    print("\n4. Checking account configuration (GoodwinSolutions)...")
    try:
        administration = 'GoodwinSolutions'
        validation = config_service.validate_configuration(administration)
        
        if validation['valid']:
            print(f"   ✅ Configuration is valid")
            print(f"   ✅ Configured purposes: {list(validation['configured_purposes'].keys())}")
        else:
            print(f"   ⚠️  Configuration incomplete")
            print(f"   ⚠️  Errors: {validation['errors']}")
            print(f"   ℹ️  This is expected if accounts haven't been configured yet")
    except Exception as e:
        print(f"   ⚠️  Could not check configuration: {e}")
    
    # Check available years
    print("\n5. Checking available years (GoodwinSolutions)...")
    try:
        administration = 'GoodwinSolutions'
        years = service.get_available_years(administration)
        if years:
            print(f"   ✅ Found {len(years)} years available for closure")
            print(f"   ℹ️  Years: {years[:5]}{'...' if len(years) > 5 else ''}")
        else:
            print(f"   ℹ️  No years available (may be all closed or no data)")
    except Exception as e:
        print(f"   ⚠️  Could not check years: {e}")
    
    # Check closed years
    print("\n6. Checking closed years (GoodwinSolutions)...")
    try:
        administration = 'GoodwinSolutions'
        closed = service.get_closed_years(administration)
        if closed:
            print(f"   ✅ Found {len(closed)} closed years")
            for year_info in closed[:3]:
                print(f"      - {year_info['year']}: closed by {year_info['closed_by']}")
        else:
            print(f"   ℹ️  No closed years yet")
    except Exception as e:
        print(f"   ⚠️  Could not check closed years: {e}")
    
    print("\n" + "=" * 60)
    print("SETUP CHECK COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Configure account purposes in Year-End Settings (Tenant Admin)")
    print("2. Test year closure through FIN Reports → Year-End Closure tab")
    print("=" * 60)
    
    return True

if __name__ == '__main__':
    check_setup()
