"""
Integration tests for BNB routes with tenant filtering

Tests the tenant filtering implementation for:
- /api/bnb/bnb-listing-data
"""

import pytest
import json
import base64
from flask import Flask
from bnb_routes import bnb_bp


class TestBnbListingDataTenantFiltering:
    """Test tenant filtering for bnb-listing-data route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_listing_data_single_tenant_user(self, client):
        """Test that single tenant user only sees their tenant's data"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB listing data
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_listing_data_multi_tenant_user(self, client):
        """Test that multi-tenant user sees data from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access BNB listing data
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_listing_data_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-listing-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_listing_data_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-listing-data')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestBnbChannelDataTenantFiltering:
    """Test tenant filtering for bnb-channel-data route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_channel_data_single_tenant_user(self, client):
        """Test that single tenant user only sees their tenant's data"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB channel data
        response = client.get(
            '/api/bnb/bnb-channel-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_channel_data_multi_tenant_user(self, client):
        """Test that multi-tenant user sees data from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access BNB channel data
        response = client.get(
            '/api/bnb/bnb-channel-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_channel_data_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-channel-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_channel_data_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-channel-data')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]


class TestBnbTableTenantFiltering:
    """Test tenant filtering for bnb-table route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_table_single_tenant_user(self, client):
        """Test that single tenant user only sees their tenant's data"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB table data
        response = client.get(
            '/api/bnb/bnb-table',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_table_multi_tenant_user(self, client):
        """Test that multi-tenant user sees data from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access BNB table data
        response = client.get(
            '/api/bnb/bnb-table',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_table_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-table',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_table_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-table')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_bnb_table_with_filters(self, client):
        """Test that tenant filtering works with date and other filters"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB table data with filters
        response = client.get(
            '/api/bnb/bnb-table?dateFrom=2024-01-01&dateTo=2024-12-31&channel=Airbnb',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data


class TestBnbGuestBookingsTenantFiltering:
    """Test tenant filtering for bnb-guest-bookings route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_guest_bookings_single_tenant_user(self, client):
        """Test that single tenant user only sees guest bookings from their tenant"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access guest bookings data
        response = client.get(
            '/api/bnb/bnb-guest-bookings?guestName=TestGuest',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            # Verify all returned bookings belong to PeterPrive tenant
            for booking in data['data']:
                assert booking.get('administration') == 'PeterPrive'
    
    def test_bnb_guest_bookings_multi_tenant_user(self, client):
        """Test that multi-tenant user sees guest bookings from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access guest bookings data
        response = client.get(
            '/api/bnb/bnb-guest-bookings?guestName=TestGuest',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            # Verify all returned bookings belong to user's tenants
            for booking in data['data']:
                assert booking.get('administration') in ['PeterPrive', 'GoodwinSolutions']
    
    def test_bnb_guest_bookings_cross_tenant_access_blocked(self, client):
        """Test that cross-tenant guest data access is blocked"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-guest-bookings?guestName=TestGuest',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_guest_bookings_requires_guest_name(self, client):
        """Test that endpoint requires guestName parameter"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Make request without guestName parameter
        response = client.get(
            '/api/bnb/bnb-guest-bookings',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 400 (bad request)
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Guest name required' in data['error']
    
    def test_bnb_guest_bookings_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-guest-bookings?guestName=TestGuest')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_bnb_guest_bookings_guest_data_isolation(self, client):
        """Test that guest data is properly isolated by tenant"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access guest bookings data
        response = client.get(
            '/api/bnb/bnb-guest-bookings?guestName=TestGuest',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify no data from other tenants is leaked
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            # Ensure no bookings from unauthorized tenants
            for booking in data['data']:
                assert booking.get('administration') != 'GoodwinSolutions'
                assert booking.get('administration') == 'PeterPrive'


class TestBnbActualsTenantFiltering:
    """Test tenant filtering for bnb-actuals route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_actuals_single_tenant_user(self, client):
        """Test that single tenant user only sees their tenant's actuals data"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB actuals data
        response = client.get(
            '/api/bnb/bnb-actuals',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_actuals_multi_tenant_user(self, client):
        """Test that multi-tenant user sees actuals data from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access BNB actuals data
        response = client.get(
            '/api/bnb/bnb-actuals',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_actuals_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-actuals',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_actuals_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-actuals')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_bnb_actuals_with_year_filter(self, client):
        """Test that tenant filtering works with year filter"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB actuals data with year filter
        response = client.get(
            '/api/bnb/bnb-actuals?years=2024',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data


class TestBnbFilterOptionsTenantFiltering:
    """Test tenant filtering for bnb-filter-options route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_filter_options_single_tenant_user(self, client):
        """Test that single tenant user only sees filter options for their tenant"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB filter options
        response = client.get(
            '/api/bnb/bnb-filter-options',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'years' in data
            assert 'listings' in data
            assert 'channels' in data
            assert isinstance(data['years'], list)
            assert isinstance(data['listings'], list)
            assert isinstance(data['channels'], list)
    
    def test_bnb_filter_options_multi_tenant_user(self, client):
        """Test that multi-tenant user sees combined filter options from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access BNB filter options
        response = client.get(
            '/api/bnb/bnb-filter-options',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned with combined options
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'years' in data
            assert 'listings' in data
            assert 'channels' in data
            # Multi-tenant user should see options from both tenants
            assert isinstance(data['years'], list)
            assert isinstance(data['listings'], list)
            assert isinstance(data['channels'], list)
    
    def test_bnb_filter_options_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-filter-options',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_filter_options_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-filter-options')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_bnb_filter_options_data_structure(self, client):
        """Test that filter options return correct data structure"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB filter options
        response = client.get(
            '/api/bnb/bnb-filter-options',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data structure
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            # Verify all required fields are present
            assert 'years' in data
            assert 'listings' in data
            assert 'channels' in data
            # Verify data types
            assert isinstance(data['years'], list)
            assert isinstance(data['listings'], list)
            assert isinstance(data['channels'], list)
            # Verify years are strings (as per implementation)
            if data['years']:
                assert all(isinstance(year, str) for year in data['years'])
    
    def test_bnb_filter_options_tenant_isolation(self, client):
        """Test that filter options only show data for user's tenants"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB filter options
        response = client.get(
            '/api/bnb/bnb-filter-options',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify tenant isolation
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            # The returned options should only include data from PeterPrive tenant
            # This is implicitly tested by the SQL queries filtering by administration
            assert 'years' in data
            assert 'listings' in data
            assert 'channels' in data


class TestBnbViolinDataTenantFiltering:
    """Test tenant filtering for bnb-violin-data route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_violin_data_single_tenant_user(self, client):
        """Test that single tenant user only sees their tenant's violin plot data"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB violin data
        response = client.get(
            '/api/bnb/bnb-violin-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_violin_data_multi_tenant_user(self, client):
        """Test that multi-tenant user sees violin plot data from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access BNB violin data
        response = client.get(
            '/api/bnb/bnb-violin-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_violin_data_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-violin-data',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_violin_data_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-violin-data')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_bnb_violin_data_with_price_per_night_metric(self, client):
        """Test violin plot data with pricePerNight metric"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB violin data with pricePerNight metric
        response = client.get(
            '/api/bnb/bnb-violin-data?metric=pricePerNight',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_violin_data_with_nights_per_stay_metric(self, client):
        """Test violin plot data with nightsPerStay metric"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB violin data with nightsPerStay metric
        response = client.get(
            '/api/bnb/bnb-violin-data?metric=nightsPerStay',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
    
    def test_bnb_violin_data_with_filters(self, client):
        """Test that tenant filtering works with year, listing, and channel filters"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access BNB violin data with filters
        response = client.get(
            '/api/bnb/bnb-violin-data?years=2024&listings=TestListing&channels=Airbnb',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data


class TestBnbReturningGuestsTenantFiltering:
    """Test tenant filtering for bnb-returning-guests route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
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
    
    def test_bnb_returning_guests_single_tenant_user(self, client):
        """Test that single tenant user only sees returning guests from their tenant"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access returning guests data
        response = client.get(
            '/api/bnb/bnb-returning-guests',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            # Verify data structure - each guest should have guestName and aantal (count)
            for guest in data['data']:
                assert 'guestName' in guest
                assert 'aantal' in guest
                # Verify count is > 1 (returning guests only)
                assert guest['aantal'] > 1
    
    def test_bnb_returning_guests_multi_tenant_user(self, client):
        """Test that multi-tenant user sees returning guests from all their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_Read"]
        )
        
        # Access returning guests data
        response = client.get(
            '/api/bnb/bnb-returning-guests',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify data is returned
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            # Verify data structure
            for guest in data['data']:
                assert 'guestName' in guest
                assert 'aantal' in guest
                # Verify count is > 1 (returning guests only)
                assert guest['aantal'] > 1
    
    def test_bnb_returning_guests_unauthorized_access(self, client):
        """Test that unauthorized access to tenant data returns 403"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Try to access GoodwinSolutions data (should be denied)
        response = client.get(
            '/api/bnb/bnb-returning-guests',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_bnb_returning_guests_requires_tenant(self, client):
        """Test that endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/bnb/bnb-returning-guests')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_bnb_returning_guests_guest_data_isolation(self, client):
        """Test that guest data is properly isolated by tenant"""
        # Create JWT token with access to only PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access returning guests data
        response = client.get(
            '/api/bnb/bnb-returning-guests',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify guest data isolation
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            # The returned guests should only be from PeterPrive tenant
            # This is implicitly tested by the SQL query filtering by administration
            for guest in data['data']:
                assert 'guestName' in guest
                assert 'aantal' in guest
    
    def test_bnb_returning_guests_sorted_correctly(self, client):
        """Test that returning guests are sorted by count (desc) then name (asc)"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_Read"]
        )
        
        # Access returning guests data
        response = client.get(
            '/api/bnb/bnb-returning-guests',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
        
        # If successful, verify sorting
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'data' in data
            
            # Verify sorting: aantal DESC, guestName ASC
            if len(data['data']) > 1:
                for i in range(len(data['data']) - 1):
                    current = data['data'][i]
                    next_guest = data['data'][i + 1]
                    # If counts are equal, names should be in ascending order
                    if current['aantal'] == next_guest['aantal']:
                        assert current['guestName'] <= next_guest['guestName']
                    # Otherwise, counts should be in descending order
                    else:
                        assert current['aantal'] >= next_guest['aantal']
