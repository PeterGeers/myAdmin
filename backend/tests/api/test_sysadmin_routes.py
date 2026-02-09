"""
Test SysAdmin Routes

Tests for SysAdmin API endpoints using pytest with mocked Cognito authentication.
Based on existing test patterns from test_tenant_admin_template_preview.py
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from flask import Flask


@pytest.fixture
def app():
    """Create Flask app for testing"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    # Mock cognito_required decorator to bypass authentication
    with patch('routes.sysadmin_tenants.cognito_required') as mock_cognito_tenants, \
         patch('routes.sysadmin_roles.cognito_required') as mock_cognito_roles:
        
        # Make decorator pass through and inject SysAdmin user
        def decorator_passthrough(required_roles=None, required_permissions=None):
            def decorator(f):
                def wrapper(*args, **kwargs):
                    # Inject SysAdmin user credentials
                    return f('sysadmin@myadmin.com', ['SysAdmin'], *args, **kwargs)
                wrapper.__name__ = f.__name__
                return wrapper
            return decorator
        
        mock_cognito_tenants.side_effect = decorator_passthrough
        mock_cognito_roles.side_effect = decorator_passthrough
        
        # Import and register blueprints after mocking
        from routes.sysadmin_routes import sysadmin_bp
        app.register_blueprint(sysadmin_bp)
    
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


# ============================================================================
# Tenant Management Tests
# ============================================================================


@patch('routes.sysadmin_tenants.DatabaseManager')
def test_create_tenant_success(mock_db_class, client):
    """Test successful tenant creation"""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    
    # Mock database responses
    mock_db.execute_query.side_effect = [
        [],  # Check if tenant exists (empty = doesn't exist)
        None,  # Insert tenant
        None,  # Insert FIN module
        None,  # Insert TENADMIN module
    ]
    
    response = client.post(
        '/api/sysadmin/tenants',
        json={
            'administration': 'TestCorp',
            'display_name': 'Test Corporation',
            'contact_email': 'admin@testcorp.com',
            'enabled_modules': ['FIN']
        },
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['administration'] == 'TestCorp'


@patch('routes.sysadmin_tenants.DatabaseManager')
def test_create_tenant_duplicate(mock_db_class, client):
    """Test creating duplicate tenant returns 400"""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    mock_db.execute_query.return_value = [{'administration': 'TestCorp'}]
    
    response = client.post(
        '/api/sysadmin/tenants',
        json={
            'administration': 'TestCorp',
            'display_name': 'Test Corporation',
            'contact_email': 'admin@testcorp.com'
        },
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'already exists' in data['error']


def test_create_tenant_missing_fields(client):
    """Test creating tenant with missing required fields"""
    response = client.post(
        '/api/sysadmin/tenants',
        json={'administration': 'TestCorp'},
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Missing required field' in data['error']


def test_create_tenant_invalid_name(client):
    """Test creating tenant with invalid administration name"""
    response = client.post(
        '/api/sysadmin/tenants',
        json={
            'administration': 'AB',  # Too short
            'display_name': 'Test Corporation',
            'contact_email': 'admin@testcorp.com'
        },
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'at least 3 characters' in data['error']


# ============================================================================
# Role Management Tests
# ============================================================================


@patch('routes.sysadmin_roles.cognito_client')
def test_list_roles_success(mock_cognito, client):
    """Test successful role listing"""
    mock_cognito.list_groups.return_value = {
        'Groups': [
            {'GroupName': 'SysAdmin', 'Description': 'System Administrator', 'CreationDate': '2026-01-01T00:00:00'},
            {'GroupName': 'Finance_Read', 'Description': 'Finance Read Access', 'CreationDate': '2026-01-01T00:00:00'}
        ]
    }
    
    mock_cognito.list_users_in_group.side_effect = [
        {'Users': [{'Username': 'user1'}]},  # SysAdmin has 1 user
        {'Users': []}  # Finance_Read has 0 users
    ]
    
    response = client.get('/api/sysadmin/roles')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert len(data['roles']) == 2


@patch('routes.sysadmin_roles.cognito_client')
def test_create_role_success(mock_cognito, client):
    """Test successful role creation"""
    # Mock Cognito - group doesn't exist
    mock_cognito.get_group.side_effect = Exception('ResourceNotFoundException')
    mock_cognito.create_group.return_value = {}
    mock_cognito.exceptions.ResourceNotFoundException = Exception
    
    response = client.post(
        '/api/sysadmin/roles',
        json={
            'name': 'NewRole',
            'description': 'New Role Description'
        },
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['name'] == 'NewRole'


def test_create_role_missing_name(client):
    """Test creating role without name"""
    response = client.post(
        '/api/sysadmin/roles',
        json={'description': 'Description'},
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Missing required field: name' in data['error']


@patch('routes.sysadmin_roles.cognito_client')
def test_delete_role_success(mock_cognito, client):
    """Test successful role deletion"""
    mock_cognito.get_group.return_value = {'Group': {'GroupName': 'TestRole'}}
    mock_cognito.list_users_in_group.return_value = {'Users': []}
    mock_cognito.delete_group.return_value = {}
    
    response = client.delete('/api/sysadmin/roles/TestRole')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True


@patch('routes.sysadmin_roles.cognito_client')
def test_delete_role_with_users(mock_cognito, client):
    """Test deleting role with users returns 409"""
    mock_cognito.get_group.return_value = {'Group': {'GroupName': 'TestRole'}}
    mock_cognito.list_users_in_group.return_value = {'Users': [{'Username': 'user1'}]}
    
    response = client.delete('/api/sysadmin/roles/TestRole')
    
    assert response.status_code == 409
    data = json.loads(response.data)
    assert 'Cannot delete role with active users' in data['error']


# ============================================================================
# Module Management Tests
# ============================================================================


@patch('routes.sysadmin_tenants.DatabaseManager')
def test_get_modules_success(mock_db_class, client):
    """Test successful module retrieval"""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    
    mock_db.execute_query.side_effect = [
        [{'administration': 'GoodwinSolutions'}],  # Check tenant exists
        [  # Modules query
            {'module_name': 'FIN', 'is_active': True, 'created_at': '2026-01-15T10:00:00', 'updated_at': '2026-01-15T10:00:00'},
            {'module_name': 'STR', 'is_active': True, 'created_at': '2026-01-15T10:00:00', 'updated_at': '2026-01-15T10:00:00'}
        ]
    ]
    
    response = client.get('/api/sysadmin/tenants/GoodwinSolutions/modules')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert len(data['modules']) == 2


@patch('routes.sysadmin_tenants.DatabaseManager')
def test_update_modules_success(mock_db_class, client):
    """Test successful module update"""
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    
    mock_db.execute_query.side_effect = [
        [{'administration': 'GoodwinSolutions'}],  # Check tenant exists
        [{'id': 1}],  # Check FIN module exists
        None,  # Update FIN module
    ]
    
    response = client.put(
        '/api/sysadmin/tenants/GoodwinSolutions/modules',
        json={
            'modules': [
                {'name': 'FIN', 'is_active': True}
            ]
        },
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True


def test_update_modules_missing_field(client):
    """Test updating modules without modules field"""
    response = client.put(
        '/api/sysadmin/tenants/GoodwinSolutions/modules',
        json={},
        headers={'Content-Type': 'application/json'}
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Missing required field: modules' in data['error']
