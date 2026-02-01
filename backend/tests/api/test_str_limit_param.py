"""Test the new limit parameter for STR invoice search"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from flask import Flask
from src.str_invoice_routes import str_invoice_bp
import json

# Skip all API tests - they require authenticated Flask app
pytestmark = [
    pytest.mark.api,
    pytest.mark.skip(reason="Requires authenticated Flask app - TODO: add auth fixtures")
]

def test_limit_parameter():
    """Test the limit parameter functionality"""
    app = Flask(__name__)
    app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
    
    with app.test_client() as client:
        print("\n=== Testing STR Invoice Limit Parameter ===\n")
        
        # Test 1: Default limit (20)
        print("1. Testing default limit (should return max 20)...")
        response = client.get('/api/str-invoice/search-booking?query=a')
        data = json.loads(response.data)
        print(f"   Results: {len(data.get('bookings', []))} bookings")
        assert len(data.get('bookings', [])) <= 20, "Default limit should be 20"
        print("   ✓ Default limit works\n")
        
        # Test 2: Custom limit
        print("2. Testing custom limit=5...")
        response = client.get('/api/str-invoice/search-booking?query=a&limit=5')
        data = json.loads(response.data)
        print(f"   Results: {len(data.get('bookings', []))} bookings")
        assert len(data.get('bookings', [])) <= 5, "Custom limit should be 5"
        print("   ✓ Custom limit works\n")
        
        # Test 3: No limit (all results)
        print("3. Testing limit=all (should return ALL bookings)...")
        response = client.get('/api/str-invoice/search-booking?query=%20&limit=all')
        data = json.loads(response.data)
        count = len(data.get('bookings', []))
        print(f"   Results: {count} bookings")
        assert count > 20, f"Should return more than 20 bookings, got {count}"
        print(f"   ✓ No limit works - returned {count} bookings\n")
        
        # Test 4: limit=0 (same as all)
        print("4. Testing limit=0 (should return ALL bookings)...")
        response = client.get('/api/str-invoice/search-booking?query=%20&limit=0')
        data = json.loads(response.data)
        count2 = len(data.get('bookings', []))
        print(f"   Results: {count2} bookings")
        assert count2 == count, "limit=0 should return same as limit=all"
        print(f"   ✓ limit=0 works - returned {count2} bookings\n")
        
        print("✅ All limit parameter tests passed!")
        print(f"\nSummary:")
        print(f"  - Default limit: 20 bookings max")
        print(f"  - Custom limit: Works as expected")
        print(f"  - No limit (all): Returns {count} bookings")
        print(f"  - Frontend can now load all {count} bookings on page load!")

if __name__ == '__main__':
    test_limit_parameter()
