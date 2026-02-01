"""
Integration tests for STR Channel routes with tenant filtering

Tests the tenant filtering implementation for:
- /api/str-channel/save
"""

import pytest
import json
import base64
from unittest.mock import patch, MagicMock
from flask import Flask
from str_channel_routes import str_channel_bp


class TestStrChannelSaveTenantFiltering:
    """Test tenant filtering for str-channel/save route"""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(str_channel_bp, url_prefix='/api/str-channel')
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
    
    def create_sample_transactions(self, administration):
        """Helper to create sample transactions"""
        return [
            {
                'TransactionDate': '2025-01-31',
                'TransactionNumber': 'AirBnB 2025-01-31',
                'TransactionDescription': 'AirBnB omzet 2025-01-31',
                'TransactionAmount': 1090.0,
                'Debet': '1600',
                'Credit': '8003',
                'ReferenceNumber': 'AirBnB',
                'Ref1': 'BnB 202501',
                'Ref2': '',
                'Ref3': '',
                'Ref4': '',
                'Administration': administration
            },
            {
                'TransactionDate': '2025-01-31',
                'TransactionNumber': 'AirBnB 2025-01-31',
                'TransactionDescription': 'AirBnB Btw 2025-01-31',
                'TransactionAmount': 90.0,
                'Debet': '8003',
                'Credit': '2021',
                'ReferenceNumber': 'AirBnB',
                'Ref1': 'BnB 202501',
                'Ref2': '',
                'Ref3': '',
                'Ref4': '',
                'Administration': administration
            }
        ]
    
    @patch('str_channel_routes.DatabaseManager')
    def test_save_transactions_authorized_tenant_succeeds(self, mock_db_manager, client):
        """Test that saving transactions for authorized tenant succeeds"""
        # Create JWT token with access to PeterPrive
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_CRUD"]  # STR_CRUD has bookings_create permission
        )
        
        # Mock database operations
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db_manager.return_value = mock_db
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Create transactions for authorized tenant
        transactions = self.create_sample_transactions('PeterPrive')
        
        # Make request
        response = client.post(
            '/api/str-channel/save',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive',
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'transactions': transactions,
                'test_mode': True
            })
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['saved_count'] == 2
        
        # Verify database operations were called
        assert mock_cursor.execute.call_count == 2  # Two transactions
        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('str_channel_routes.DatabaseManager')
    def test_save_transactions_unauthorized_tenant_fails(self, mock_db_manager, client):
        """Test that saving transactions for unauthorized tenant fails with 403"""
        # Create JWT token with access to PeterPrive only
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_CRUD"]
        )
        
        # Create transactions for unauthorized tenant
        transactions = self.create_sample_transactions('GoodwinSolutions')
        
        # Make request
        response = client.post(
            '/api/str-channel/save',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive',
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'transactions': transactions,
                'test_mode': True
            })
        )
        
        # Verify response
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Access denied to administration: GoodwinSolutions' in data['error']
        
        # Verify database operations were NOT called
        mock_db_manager.assert_not_called()
    
    @patch('str_channel_routes.DatabaseManager')
    def test_save_mixed_authorized_unauthorized_transactions_rejected(self, mock_db_manager, client):
        """Test that mixed authorized/unauthorized transactions are rejected"""
        # Create JWT token with access to PeterPrive only
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_CRUD"]
        )
        
        # Create mixed transactions - some authorized, some not
        authorized_transactions = self.create_sample_transactions('PeterPrive')
        unauthorized_transactions = self.create_sample_transactions('GoodwinSolutions')
        mixed_transactions = authorized_transactions + unauthorized_transactions
        
        # Make request
        response = client.post(
            '/api/str-channel/save',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive',
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'transactions': mixed_transactions,
                'test_mode': True
            })
        )
        
        # Verify response
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Access denied to administration: GoodwinSolutions' in data['error']
        
        # Verify database operations were NOT called
        mock_db_manager.assert_not_called()
    
    @patch('str_channel_routes.DatabaseManager')
    def test_save_transactions_multi_tenant_user_succeeds(self, mock_db_manager, client):
        """Test that multi-tenant user can save transactions for any of their tenants"""
        # Create JWT token with access to multiple tenants
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            roles=["STR_CRUD"]
        )
        
        # Mock database operations
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_db_manager.return_value = mock_db
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Create transactions for one of the authorized tenants
        transactions = self.create_sample_transactions('GoodwinSolutions')
        
        # Make request
        response = client.post(
            '/api/str-channel/save',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive',  # Current tenant doesn't matter for validation
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'transactions': transactions,
                'test_mode': True
            })
        )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['saved_count'] == 2
        
        # Verify database operations were called
        assert mock_cursor.execute.call_count == 2
        mock_conn.commit.assert_called_once()
    
    def test_save_transactions_missing_administration_field(self, client):
        """Test that transactions missing Administration field are rejected"""
        # Create JWT token
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_CRUD"]
        )
        
        # Create transactions without Administration field
        transactions = [
            {
                'TransactionDate': '2025-01-31',
                'TransactionNumber': 'AirBnB 2025-01-31',
                'TransactionDescription': 'AirBnB omzet 2025-01-31',
                'TransactionAmount': 1090.0,
                'Debet': '1600',
                'Credit': '8003',
                'ReferenceNumber': 'AirBnB',
                'Ref1': 'BnB 202501'
                # Missing Administration field
            }
        ]
        
        # Make request
        response = client.post(
            '/api/str-channel/save',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive',
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'transactions': transactions,
                'test_mode': True
            })
        )
        
        # Verify response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Transaction 1 missing Administration field' in data['error']
    
    def test_save_transactions_empty_list(self, client):
        """Test that empty transaction list is rejected"""
        # Create JWT token
        token = self.create_jwt_token(
            email="test@example.com",
            tenants=["PeterPrive"],
            roles=["STR_CRUD"]
        )
        
        # Make request with empty transactions
        response = client.post(
            '/api/str-channel/save',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant': 'PeterPrive',
                'Content-Type': 'application/json'
            },
            data=json.dumps({
                'transactions': [],
                'test_mode': True
            })
        )
        
        # Verify response
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'No transactions to save' in data['error']


if __name__ == '__main__':
    pytest.main([__file__])