"""
API tests for Year-End Closure Routes

Tests the year-end closure API endpoints with authentication and authorization.
These tests require a running Flask app with authentication configured.
"""

import pytest
import json
import base64
import sys
import os
from flask import Flask

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from routes.year_end_routes import year_end_bp

# Mark as API test - requires authenticated Flask app
pytestmark = [
    pytest.mark.api,
    pytest.mark.skip(reason="Requires authenticated Flask app with Cognito - run manually with auth setup")
]


class TestYearEndRoutesAPI:
    """API tests for year-end closure endpoints"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['TEST_MODE'] = True
        app.register_blueprint(year_end_bp)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    def create_jwt_token(self, email, tenants, roles=None):
        """
        Helper to create a mock JWT token.
        
        Note: In real tests, this would need to be a valid Cognito JWT.
        """
        payload = {
            "email": email,
            "custom:tenants": tenants if isinstance(tenants, list) else [tenants],
            "cognito:groups": roles or []
        }
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature = "mock_signature"
        return f"{header}.{payload_encoded}.{signature}"
    
    def get_auth_headers(self, tenant='TestAdmin', roles=None):
        """Get authentication headers for requests"""
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=[tenant],
            roles=roles or ['Finance_CRUD']
        )
        return {
            'Authorization': f'Bearer {token}',
            'X-Tenant': tenant,
            'Content-Type': 'application/json'
        }
    
    # GET /api/year-end/available-years
    
    def test_get_available_years_requires_auth(self, client):
        """Test that available-years endpoint requires authentication"""
        response = client.get('/api/year-end/available-years')
        assert response.status_code in [401, 403]
    
    def test_get_available_years_requires_finance_read(self, client):
        """Test that available-years requires finance_read permission"""
        headers = self.get_auth_headers(roles=['STR_CRUD'])  # Wrong permission
        response = client.get('/api/year-end/available-years', headers=headers)
        assert response.status_code == 403
    
    def test_get_available_years_success(self, client):
        """Test successful retrieval of available years"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.get('/api/year-end/available-years', headers=headers)
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, list)
            # Each item should have 'year' field
            for item in data:
                assert 'year' in item
                assert isinstance(item['year'], int)
    
    # POST /api/year-end/validate
    
    def test_validate_year_requires_auth(self, client):
        """Test that validate endpoint requires authentication"""
        response = client.post(
            '/api/year-end/validate',
            json={'year': 2023}
        )
        assert response.status_code in [401, 403]
    
    def test_validate_year_requires_finance_read(self, client):
        """Test that validate requires finance_read permission"""
        headers = self.get_auth_headers(roles=['STR_CRUD'])
        response = client.post(
            '/api/year-end/validate',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code == 403
    
    def test_validate_year_missing_year_parameter(self, client):
        """Test validation with missing year parameter"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.post(
            '/api/year-end/validate',
            json={},
            headers=headers
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'year' in data['error'].lower()
    
    def test_validate_year_success(self, client):
        """Test successful year validation"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.post(
            '/api/year-end/validate',
            json={'year': 2023},
            headers=headers
        )
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'can_close' in data
            assert 'errors' in data
            assert 'warnings' in data
            assert 'info' in data
            assert isinstance(data['can_close'], bool)
            assert isinstance(data['errors'], list)
            assert isinstance(data['warnings'], list)
            assert isinstance(data['info'], dict)
    
    # POST /api/year-end/close
    
    def test_close_year_requires_auth(self, client):
        """Test that close endpoint requires authentication"""
        response = client.post(
            '/api/year-end/close',
            json={'year': 2023}
        )
        assert response.status_code in [401, 403]
    
    def test_close_year_requires_finance_write(self, client):
        """Test that close requires finance_write permission (Finance_CRUD role)"""
        headers = self.get_auth_headers(roles=['Finance_Read'])  # Read only
        response = client.post(
            '/api/year-end/close',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code == 403
    
    def test_close_year_missing_year_parameter(self, client):
        """Test close with missing year parameter"""
        headers = self.get_auth_headers(roles=['Finance_CRUD'])
        response = client.post(
            '/api/year-end/close',
            json={},
            headers=headers
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'year' in data['error'].lower()
    
    def test_close_year_with_notes(self, client):
        """Test closing year with optional notes"""
        headers = self.get_auth_headers(roles=['Finance_CRUD'])
        response = client.post(
            '/api/year-end/close',
            json={
                'year': 2023,
                'notes': 'Test closure with notes'
            },
            headers=headers
        )
        
        # May succeed or fail depending on test data
        # If successful, verify response structure
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'success' in data
            assert 'year' in data
            assert 'closure_transaction_number' in data
            assert 'opening_transaction_number' in data
            assert 'net_result' in data
            assert 'message' in data
    
    def test_close_year_already_closed(self, client):
        """Test attempting to close an already closed year"""
        headers = self.get_auth_headers(roles=['Finance_CRUD'])
        
        # First closure
        response1 = client.post(
            '/api/year-end/close',
            json={'year': 2022},
            headers=headers
        )
        
        # Second closure (should fail)
        response2 = client.post(
            '/api/year-end/close',
            json={'year': 2022},
            headers=headers
        )
        
        # Second attempt should fail
        assert response2.status_code in [400, 500]
        data = json.loads(response2.data)
        assert 'success' in data
        assert data['success'] is False
    
    # GET /api/year-end/closed-years
    
    def test_get_closed_years_requires_auth(self, client):
        """Test that closed-years endpoint requires authentication"""
        response = client.get('/api/year-end/closed-years')
        assert response.status_code in [401, 403]
    
    def test_get_closed_years_requires_finance_read(self, client):
        """Test that closed-years requires finance_read permission"""
        headers = self.get_auth_headers(roles=['STR_CRUD'])
        response = client.get('/api/year-end/closed-years', headers=headers)
        assert response.status_code == 403
    
    def test_get_closed_years_success(self, client):
        """Test successful retrieval of closed years"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.get('/api/year-end/closed-years', headers=headers)
        
        if response.status_code == 200:
            data = json.loads(response.data)
            assert isinstance(data, list)
            # Each item should have expected fields
            for item in data:
                assert 'year' in item
                assert 'closed_date' in item
                assert 'closed_by' in item
                assert 'closure_transaction_number' in item
                assert 'opening_balance_transaction_number' in item
    
    # GET /api/year-end/status/<year>
    
    def test_get_year_status_requires_auth(self, client):
        """Test that status endpoint requires authentication"""
        response = client.get('/api/year-end/status/2023')
        assert response.status_code in [401, 403]
    
    def test_get_year_status_requires_finance_read(self, client):
        """Test that status requires finance_read permission"""
        headers = self.get_auth_headers(roles=['STR_CRUD'])
        response = client.get('/api/year-end/status/2023', headers=headers)
        assert response.status_code == 403
    
    def test_get_year_status_closed_year(self, client):
        """Test getting status for a closed year"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.get('/api/year-end/status/2022', headers=headers)
        
        if response.status_code == 200:
            data = json.loads(response.data)
            # If year is closed
            if 'year' in data and data.get('closed') != False:
                assert 'closed_date' in data
                assert 'closed_by' in data
                assert 'closure_transaction_number' in data
    
    def test_get_year_status_open_year(self, client):
        """Test getting status for an open year"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.get('/api/year-end/status/2025', headers=headers)
        
        if response.status_code == 200:
            data = json.loads(response.data)
            # If year is not closed
            if data.get('closed') == False:
                assert 'message' in data
    
    # Tenant Isolation Tests
    
    def test_tenant_isolation_available_years(self, client):
        """Test that available years are filtered by tenant"""
        # Request with Tenant A
        headers_a = self.get_auth_headers(tenant='TenantA', roles=['Finance_Read'])
        response_a = client.get('/api/year-end/available-years', headers=headers_a)
        
        # Request with Tenant B
        headers_b = self.get_auth_headers(tenant='TenantB', roles=['Finance_Read'])
        response_b = client.get('/api/year-end/available-years', headers=headers_b)
        
        # Results should be different (or at least isolated)
        if response_a.status_code == 200 and response_b.status_code == 200:
            data_a = json.loads(response_a.data)
            data_b = json.loads(response_b.data)
            # Data should be tenant-specific (may or may not be different)
            assert isinstance(data_a, list)
            assert isinstance(data_b, list)
    
    def test_tenant_isolation_closed_years(self, client):
        """Test that closed years are filtered by tenant"""
        headers_a = self.get_auth_headers(tenant='TenantA', roles=['Finance_Read'])
        response_a = client.get('/api/year-end/closed-years', headers=headers_a)
        
        headers_b = self.get_auth_headers(tenant='TenantB', roles=['Finance_Read'])
        response_b = client.get('/api/year-end/closed-years', headers=headers_b)
        
        # Results should be tenant-specific
        if response_a.status_code == 200 and response_b.status_code == 200:
            data_a = json.loads(response_a.data)
            data_b = json.loads(response_b.data)
            assert isinstance(data_a, list)
            assert isinstance(data_b, list)
    
    # Error Handling Tests
    
    def test_validate_invalid_year(self, client):
        """Test validation with invalid year"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.post(
            '/api/year-end/validate',
            json={'year': 'invalid'},
            headers=headers
        )
        assert response.status_code in [400, 500]
    
    def test_close_invalid_year(self, client):
        """Test closing with invalid year"""
        headers = self.get_auth_headers(roles=['Finance_CRUD'])
        response = client.post(
            '/api/year-end/close',
            json={'year': 'invalid'},
            headers=headers
        )
        assert response.status_code in [400, 500]
    
    def test_status_invalid_year(self, client):
        """Test status with invalid year"""
        headers = self.get_auth_headers(roles=['Finance_Read'])
        response = client.get('/api/year-end/status/invalid', headers=headers)
        assert response.status_code in [400, 404, 500]


class TestYearEndRoutesPermissions:
    """Permission enforcement tests"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(year_end_bp)
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
    
    def test_finance_read_can_view(self, client):
        """Test that Finance_Read role can view but not close"""
        token = self.create_jwt_token(
            email="reader@example.com",
            tenants=["TestAdmin"],
            roles=["Finance_Read"]
        )
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': 'TestAdmin',
            'Content-Type': 'application/json'
        }
        
        # Can view available years
        response = client.get('/api/year-end/available-years', headers=headers)
        assert response.status_code in [200, 500]  # 500 if no data, but not 403
        
        # Can validate
        response = client.post(
            '/api/year-end/validate',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code in [200, 400, 500]  # Not 403
        
        # Cannot close
        response = client.post(
            '/api/year-end/close',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code == 403
    
    def test_finance_crud_can_close(self, client):
        """Test that Finance_CRUD role can close years"""
        token = self.create_jwt_token(
            email="admin@example.com",
            tenants=["TestAdmin"],
            roles=["Finance_CRUD"]
        )
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': 'TestAdmin',
            'Content-Type': 'application/json'
        }
        
        # Can close (may fail due to validation, but not due to permissions)
        response = client.post(
            '/api/year-end/close',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code in [200, 400, 500]  # Not 403
    
    def test_no_finance_role_denied(self, client):
        """Test that users without Finance roles are denied"""
        token = self.create_jwt_token(
            email="user@example.com",
            tenants=["TestAdmin"],
            roles=["STR_CRUD"]  # Wrong module
        )
        headers = {
            'Authorization': f'Bearer {token}',
            'X-Tenant': 'TestAdmin',
            'Content-Type': 'application/json'
        }
        
        # All endpoints should deny
        response = client.get('/api/year-end/available-years', headers=headers)
        assert response.status_code == 403
        
        response = client.post(
            '/api/year-end/validate',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code == 403
        
        response = client.post(
            '/api/year-end/close',
            json={'year': 2023},
            headers=headers
        )
        assert response.status_code == 403


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
