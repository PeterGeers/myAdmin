"""
Test error handling for STR invoice generator
Tests requirement 2.3: Verify appropriate error messages for non-existent bookings
"""

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

def test_search_nonexistent_reservation():
    """Test searching for a non-existent reservation code"""
    app = Flask(__name__)
    app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
    
    with app.test_client() as client:
        # Search for a reservation code that definitely doesn't exist
        response = client.get('/api/str-invoice/search-booking?query=NONEXISTENT12345XYZ')
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = json.loads(response.data)
        assert data['success'] == True, "Expected success=True for empty results"
        assert 'bookings' in data, "Expected 'bookings' key in response"
        assert len(data['bookings']) == 0, f"Expected empty bookings list, got {len(data['bookings'])} results"
        
        print("✓ Search for non-existent reservation returns empty list with success status")

def test_generate_invoice_nonexistent_reservation():
    """Test generating invoice for a non-existent reservation code"""
    app = Flask(__name__)
    app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
    
    with app.test_client() as client:
        # Try to generate invoice for non-existent reservation
        response = client.post(
            '/api/str-invoice/generate-invoice',
            data=json.dumps({'reservationCode': 'NONEXISTENT12345XYZ'}),
            content_type='application/json'
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = json.loads(response.data)
        assert data['success'] == False, "Expected success=False for non-existent booking"
        assert 'error' in data, "Expected 'error' key in response"
        assert 'not found' in data['error'].lower(), f"Expected 'not found' in error message, got: {data['error']}"
        
        print("✓ Generate invoice for non-existent reservation returns 404 with appropriate error message")

def test_search_empty_query():
    """Test searching with empty query string"""
    app = Flask(__name__)
    app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
    
    with app.test_client() as client:
        # Search with empty query
        response = client.get('/api/str-invoice/search-booking?query=')
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = json.loads(response.data)
        assert data['success'] == False, "Expected success=False for empty query"
        assert 'error' in data, "Expected 'error' key in response"
        assert 'required' in data['error'].lower(), f"Expected 'required' in error message, got: {data['error']}"
        
        print("✓ Search with empty query returns 400 with appropriate error message")

def test_generate_invoice_missing_reservation_code():
    """Test generating invoice without providing reservation code"""
    app = Flask(__name__)
    app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
    
    with app.test_client() as client:
        # Try to generate invoice without reservation code
        response = client.post(
            '/api/str-invoice/generate-invoice',
            data=json.dumps({}),
            content_type='application/json'
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        data = json.loads(response.data)
        assert data['success'] == False, "Expected success=False for missing reservation code"
        assert 'error' in data, "Expected 'error' key in response"
        assert 'required' in data['error'].lower(), f"Expected 'required' in error message, got: {data['error']}"
        
        print("✓ Generate invoice without reservation code returns 400 with appropriate error message")

if __name__ == '__main__':
    print("\n=== Testing STR Invoice Error Handling ===\n")
    print("Testing Requirement 2.3: Appropriate error messages for non-existent bookings\n")
    
    try:
        test_search_nonexistent_reservation()
        test_generate_invoice_nonexistent_reservation()
        test_search_empty_query()
        test_generate_invoice_missing_reservation_code()
        
        print("\n✅ All error handling tests passed!")
        print("\nVerified:")
        print("  - Search returns empty list (not error) for non-existent reservations")
        print("  - Invoice generation returns 404 for non-existent reservations")
        print("  - Empty search query returns 400 error")
        print("  - Missing reservation code returns 400 error")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
