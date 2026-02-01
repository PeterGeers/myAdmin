"""
Country Detection Integration Test

This is a standalone test script, not a pytest test file.
Run it directly with: python scripts/test_country_integration.py
"""

# Prevent pytest from collecting this file
__test__ = False

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from country_detector import detect_country

# Test data samples
test_cases = [
    {
        'name': 'AirBNB with phone',
        'channel': 'airbnb',
        'phone': '+31 6 12345678',
        'addinfo': '',
        'expected': 'NL'
    },
    {
        'name': 'AirBNB with US phone',
        'channel': 'airbnb',
        'phone': '+1 212 555 1234',
        'addinfo': '',
        'expected': 'US'
    },
    {
        'name': 'Booking.com with country in addInfo (new format)',
        'channel': 'booking.com',
        'phone': '',
        'addinfo': '6455735369|Hesselink, Stijn|Stijn Hesselink|2025-10-10|2025-10-12|2025-09-15 21:58:13|ok|1|2|nan|nan|nan|276.6449 EUR|12|33.197388 EUR|Paid online|nan|You have a booker|nan|nl|Leisure|Mobile|Rode huis|1|NA',
        'expected': 'NL'
    },
    {
        'name': 'Booking.com with country in addInfo (old format)',
        'channel': 'booking.com',
        'phone': '',
        'addinfo': 'Booking.com|6438303279|Ruda, Luis|2025-06-26 11:19:30|NA|ok|91.3212 EUR|12|10.958544 EUR|Paid online|NA|NA|NA|es|Leisure|Mobile|Rode huis|1|NA',
        'expected': 'ES'
    },
    {
        'name': 'Direct booking (no country data)',
        'channel': 'direct',
        'phone': '',
        'addinfo': 'direct_booking.xlsx | John Doe | reservation | goodwin | details | 12345 | EUR | 100 | 10 | 0',
        'expected': None
    },
    {
        'name': 'AirBNB without phone',
        'channel': 'airbnb',
        'phone': '',
        'addinfo': '',
        'expected': None
    }
]

def run_tests():
    """Run the country detection tests"""
    print("\n" + "="*80)
    print("Country Detection Integration Test")
    print("="*80 + "\n")

    passed = 0
    failed = 0

    for test in test_cases:
        result = detect_country(test['channel'], test['phone'], test['addinfo'])
        
        if result == test['expected']:
            status = "✓ PASS"
            passed += 1
        else:
            status = "✗ FAIL"
            failed += 1
        
        print(f"{status} | {test['name']}")
        print(f"  Channel: {test['channel']}")
        if test['phone']:
            print(f"  Phone: {test['phone']}")
        if test['addinfo']:
            print(f"  AddInfo: {test['addinfo'][:80]}...")
        print(f"  Expected: {test['expected']}")
        print(f"  Got: {result}")
        print()

    print("="*80)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("="*80 + "\n")

    if failed > 0:
        sys.exit(1)
    else:
        print("✓ All tests passed! Country detection is working correctly.")
        sys.exit(0)

if __name__ == "__main__":
    run_tests()
