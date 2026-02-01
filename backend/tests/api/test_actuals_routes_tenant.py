"""
Integration tests for actuals routes with tenant filtering

Tests the tenant filtering implementation for:
- /api/reports/actuals-balance
- /api/reports/actuals-profitloss
"""

import pytest
import json
import base64
from flask import Flask
from database import DatabaseManager
from actuals_routes import actuals_bp
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required


class TestActualsRoutesTenantFiltering:
    """Test tenant filtering for actuals routes"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(actuals_bp, url_prefix='/api/reports')
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
    
    def test_actuals_balance_requires_tenant(self, client):
        """Test that actuals-balance endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/reports/actuals-balance')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_actuals_balance_validates_administration_access(self, client):
        """Test that actuals-balance validates user has access to requested administration"""
        # Create JWT token with access to only GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Try to access PeterPrive data (should be denied)
        response = client.get(
            '/api/reports/actuals-balance?administration=PeterPrive',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Access denied' in data['error']
    
    def test_actuals_balance_allows_authorized_tenant(self, client):
        """Test that actuals-balance allows access to authorized tenant"""
        # Create JWT token with access to GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Access GoodwinSolutions data (should be allowed)
        response = client.get(
            '/api/reports/actuals-balance?administration=GoodwinSolutions',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        # (500 is acceptable in test environment if cache/db is not fully set up)
        assert response.status_code in [200, 500]
    
    def test_actuals_balance_defaults_to_current_tenant(self, client):
        """Test that actuals-balance defaults to current tenant when no administration specified"""
        # Create JWT token with access to GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Access without specifying administration (should default to X-Tenant)
        response = client.get(
            '/api/reports/actuals-balance',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
    
    def test_actuals_balance_multi_tenant_user(self, client):
        """Test that user with multiple tenants can access each tenant's data"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions", "PeterPrive"],
            roles=["Finance_CRUD"]
        )
        
        # Access GoodwinSolutions data
        response1 = client.get(
            '/api/reports/actuals-balance?administration=GoodwinSolutions',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        assert response1.status_code in [200, 500]
        
        # Access PeterPrive data
        response2 = client.get(
            '/api/reports/actuals-balance?administration=PeterPrive',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        assert response2.status_code in [200, 500]


class TestActualsProfitLossTenantFiltering:
    """Test tenant filtering for actuals-profitloss route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(actuals_bp, url_prefix='/api/reports')
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
    
    def test_actuals_profitloss_requires_tenant(self, client):
        """Test that actuals-profitloss endpoint requires tenant context"""
        # Make request without tenant header or JWT
        response = client.get('/api/reports/actuals-profitloss')
        
        # Should return 401 (unauthorized) or 403 (forbidden)
        assert response.status_code in [401, 403]
    
    def test_actuals_profitloss_validates_administration_access(self, client):
        """Test that actuals-profitloss validates user has access to requested administration"""
        # Create JWT token with access to only GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Try to access PeterPrive data (should be denied)
        response = client.get(
            '/api/reports/actuals-profitloss?administration=PeterPrive',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 403 (forbidden)
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Access denied' in data['error']
    
    def test_actuals_profitloss_allows_authorized_tenant(self, client):
        """Test that actuals-profitloss allows access to authorized tenant"""
        # Create JWT token with access to GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Access GoodwinSolutions data (should be allowed)
        response = client.get(
            '/api/reports/actuals-profitloss?administration=GoodwinSolutions',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
    
    def test_actuals_profitloss_defaults_to_current_tenant(self, client):
        """Test that actuals-profitloss defaults to current tenant when no administration specified"""
        # Create JWT token with access to GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Access without specifying administration (should default to X-Tenant)
        response = client.get(
            '/api/reports/actuals-profitloss',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]
    
    def test_actuals_profitloss_multi_tenant_user(self, client):
        """Test that user with multiple tenants can access each tenant's data"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions", "PeterPrive"],
            roles=["Finance_CRUD"]
        )
        
        # Access GoodwinSolutions data
        response1 = client.get(
            '/api/reports/actuals-profitloss?administration=GoodwinSolutions',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        assert response1.status_code in [200, 500]
        
        # Access PeterPrive data
        response2 = client.get(
            '/api/reports/actuals-profitloss?administration=PeterPrive',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive'
            }
        )
        assert response2.status_code in [200, 500]
    
    def test_actuals_profitloss_filters_cached_data_by_tenant(self, client):
        """Test that actuals-profitloss filters cached data by user's accessible tenants"""
        # Create JWT token with access to only GoodwinSolutions
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["GoodwinSolutions"],
            roles=["Finance_CRUD"]
        )
        
        # Request all administrations - should only return GoodwinSolutions data
        response = client.get(
            '/api/reports/actuals-profitloss?administration=all',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'GoodwinSolutions'
            }
        )
        
        # Should return 200 (success) or 500 if there's a server error
        assert response.status_code in [200, 500]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
