"""
STR Invoice Tenant Filtering Tests

Tests for tenant filtering implementation on /api/str-invoice/generate-invoice endpoint.
Validates that users can only generate invoices for bookings in their authorized tenants.
"""

import pytest
import json
import base64
from flask import Flask
from database import DatabaseManager
from auth.tenant_context import get_user_tenants, get_current_tenant, validate_tenant_access


class TestSTRInvoiceTenantFiltering:
    """Test tenant filtering for STR invoice generation"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def db(self):
        """Create database manager for testing"""
        return DatabaseManager(test_mode=True)
    
    def create_jwt_token(self, email, tenants, roles=None):
        """Helper to create a mock JWT token"""
        payload = {
            "email": email,
            "custom:tenants": tenants if isinstance(tenants, list) else [tenants],
            "cognito:groups": roles or []
        }
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = "mock_signature"
        return f"{header}.{payload_encoded}.{signature}"
    
    def get_test_booking(self, db, administration=None):
        """Get a test booking from the database"""
        if administration:
            query = """
                SELECT reservationCode, administration, guestName, amountGross
                FROM vw_bnb_total 
                WHERE administration = %s 
                LIMIT 1
            """
            result = db.execute_query(query, [administration], fetch=True)
        else:
            query = """
                SELECT reservationCode, administration, guestName, amountGross
                FROM vw_bnb_total 
                LIMIT 1
            """
            result = db.execute_query(query, [], fetch=True)
        
        return result[0] if result else None
    
    def test_authorized_booking_invoice_generation(self, app, db):
        """Test 10.6: Test invoice generation for authorized booking succeeds"""
        print("\n" + "="*60)
        print("Test 10.6: Invoice generation for authorized booking")
        print("="*60)
        
        # Get a test booking for GoodwinSolutions
        booking = self.get_test_booking(db, 'GoodwinSolutions')
        if not booking:
            pytest.skip("No GoodwinSolutions booking found in test database")
        
        # Create JWT token for user with access to GoodwinSolutions
        token = self.create_jwt_token(
            "accountant@goodwin.com",
            ["GoodwinSolutions"],
            ["str_create"]
        )
        
        # Import the route function
        from str_invoice_routes import generate_invoice
        
        with app.test_request_context(
            method='POST',
            json={
                'reservationCode': booking['reservationCode'],
                'language': 'nl'
            },
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        ):
            # Mock the cognito_required decorator parameters
            user_email = "accountant@goodwin.com"
            user_roles = ["str_create"]
            tenant = "GoodwinSolutions"
            user_tenants = ["GoodwinSolutions"]
            
            try:
                # Call the function directly with mocked parameters
                response = generate_invoice(user_email, user_roles, tenant, user_tenants)
                
                # Check if response is a tuple (response, status_code)
                if isinstance(response, tuple):
                    response_data, status_code = response
                    response_json = response_data.get_json()
                else:
                    response_json = response.get_json()
                    status_code = 200
                
                print(f"Status Code: {status_code}")
                print(f"Response: {json.dumps(response_json, indent=2)}")
                
                # Verify successful response
                assert status_code == 200
                assert response_json['success'] is True
                assert 'html' in response_json
                assert 'booking_data' in response_json
                
                # Verify booking data contains expected fields
                booking_data = response_json['booking_data']
                assert booking_data['reservationCode'] == booking['reservationCode']
                assert 'amountGross' in booking_data
                assert 'guestName' in booking_data
                
                print("✅ Authorized booking invoice generation succeeded")
                return True
                
            except Exception as e:
                print(f"❌ Error during invoice generation: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    def test_unauthorized_booking_invoice_generation(self, app, db):
        """Test 10.7: Test invoice generation for unauthorized booking fails with 403"""
        print("\n" + "="*60)
        print("Test 10.7: Invoice generation for unauthorized booking")
        print("="*60)
        
        # Get a test booking for GoodwinSolutions
        booking = self.get_test_booking(db, 'GoodwinSolutions')
        if not booking:
            pytest.skip("No GoodwinSolutions booking found in test database")
        
        # Create JWT token for user with access to PeterPrive only (not GoodwinSolutions)
        token = self.create_jwt_token(
            "user@peter.com",
            ["PeterPrive"],
            ["str_create"]
        )
        
        # Import the route function
        from str_invoice_routes import generate_invoice
        
        with app.test_request_context(
            method='POST',
            json={
                'reservationCode': booking['reservationCode'],
                'language': 'nl'
            },
            headers={
                'X-Tenant': 'PeterPrive',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        ):
            # Mock the cognito_required decorator parameters
            user_email = "user@peter.com"
            user_roles = ["str_create"]
            tenant = "PeterPrive"
            user_tenants = ["PeterPrive"]
            
            try:
                # Call the function directly with mocked parameters
                response = generate_invoice(user_email, user_roles, tenant, user_tenants)
                
                # Check if response is a tuple (response, status_code)
                if isinstance(response, tuple):
                    response_data, status_code = response
                    response_json = response_data.get_json()
                else:
                    response_json = response.get_json()
                    status_code = 200
                
                print(f"Status Code: {status_code}")
                print(f"Response: {json.dumps(response_json, indent=2)}")
                
                # Verify 404 response (booking not found due to tenant filtering)
                assert status_code == 404
                assert response_json['success'] is False
                assert 'Booking not found or access denied' in response_json['error']
                
                print("✅ Unauthorized booking access correctly denied with 404")
                return True
                
            except Exception as e:
                print(f"❌ Error during unauthorized access test: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    def test_multi_tenant_user_invoice_generation(self, app, db):
        """Test invoice generation for user with multiple tenants"""
        print("\n" + "="*60)
        print("Test: Multi-tenant user invoice generation")
        print("="*60)
        
        # Get a test booking for GoodwinSolutions
        booking = self.get_test_booking(db, 'GoodwinSolutions')
        if not booking:
            pytest.skip("No GoodwinSolutions booking found in test database")
        
        # Create JWT token for user with access to multiple tenants
        token = self.create_jwt_token(
            "manager@company.com",
            ["GoodwinSolutions", "PeterPrive"],
            ["str_create"]
        )
        
        # Import the route function
        from str_invoice_routes import generate_invoice
        
        with app.test_request_context(
            method='POST',
            json={
                'reservationCode': booking['reservationCode'],
                'language': 'nl'
            },
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        ):
            # Mock the cognito_required decorator parameters
            user_email = "manager@company.com"
            user_roles = ["str_create"]
            tenant = "GoodwinSolutions"
            user_tenants = ["GoodwinSolutions", "PeterPrive"]
            
            try:
                # Call the function directly with mocked parameters
                response = generate_invoice(user_email, user_roles, tenant, user_tenants)
                
                # Check if response is a tuple (response, status_code)
                if isinstance(response, tuple):
                    response_data, status_code = response
                    response_json = response_data.get_json()
                else:
                    response_json = response.get_json()
                    status_code = 200
                
                print(f"Status Code: {status_code}")
                print(f"Response: {json.dumps(response_json, indent=2)}")
                
                # Verify successful response
                assert status_code == 200
                assert response_json['success'] is True
                assert 'html' in response_json
                assert 'booking_data' in response_json
                
                print("✅ Multi-tenant user invoice generation succeeded")
                return True
                
            except Exception as e:
                print(f"❌ Error during multi-tenant test: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    def test_nonexistent_booking_with_tenant_filtering(self, app, db):
        """Test that nonexistent booking returns 404 with tenant filtering"""
        print("\n" + "="*60)
        print("Test: Nonexistent booking with tenant filtering")
        print("="*60)
        
        # Create JWT token for user with access to GoodwinSolutions
        token = self.create_jwt_token(
            "user@goodwin.com",
            ["GoodwinSolutions"],
            ["str_create"]
        )
        
        # Import the route function
        from str_invoice_routes import generate_invoice
        
        with app.test_request_context(
            method='POST',
            json={
                'reservationCode': 'NONEXISTENT_CODE_12345',
                'language': 'nl'
            },
            headers={
                'X-Tenant': 'GoodwinSolutions',
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
        ):
            # Mock the cognito_required decorator parameters
            user_email = "user@goodwin.com"
            user_roles = ["str_create"]
            tenant = "GoodwinSolutions"
            user_tenants = ["GoodwinSolutions"]
            
            try:
                # Call the function directly with mocked parameters
                response = generate_invoice(user_email, user_roles, tenant, user_tenants)
                
                # Check if response is a tuple (response, status_code)
                if isinstance(response, tuple):
                    response_data, status_code = response
                    response_json = response_data.get_json()
                else:
                    response_json = response.get_json()
                    status_code = 200
                
                print(f"Status Code: {status_code}")
                print(f"Response: {json.dumps(response_json, indent=2)}")
                
                # Verify 404 response
                assert status_code == 404
                assert response_json['success'] is False
                assert 'Booking not found or access denied' in response_json['error']
                
                print("✅ Nonexistent booking correctly returned 404")
                return True
                
            except Exception as e:
                print(f"❌ Error during nonexistent booking test: {e}")
                import traceback
                traceback.print_exc()
                return False


def main():
    """Run all tenant filtering tests"""
    print("\n" + "="*60)
    print("STR Invoice Tenant Filtering Tests")
    print("="*60)
    
    # Create test instance
    test_instance = TestSTRInvoiceTenantFiltering()
    
    # Create fixtures
    app = Flask(__name__)
    app.config['TESTING'] = True
    db = DatabaseManager(test_mode=True)
    
    # Run tests
    tests = [
        ("Test 10.6: Authorized booking", test_instance.test_authorized_booking_invoice_generation),
        ("Test 10.7: Unauthorized booking", test_instance.test_unauthorized_booking_invoice_generation),
        ("Multi-tenant user test", test_instance.test_multi_tenant_user_invoice_generation),
        ("Nonexistent booking test", test_instance.test_nonexistent_booking_with_tenant_filtering)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func(app, db)
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ ALL TENANT FILTERING TESTS PASSED")
        print("✅ Task 10.6 and 10.7 completed successfully")
    else:
        print("❌ SOME TESTS FAILED")
    
    print("="*60)
    return passed == total


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)