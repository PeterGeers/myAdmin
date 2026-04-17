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
    
    from routes.sysadmin_routes import sysadmin_bp
    app.register_blueprint(sysadmin_bp)
    
    return app


@pytest.fixture
def client(app):
    """Create test client with mocked auth"""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth:
        # Return SysAdmin user for all requests
        mock_auth.return_value = ('sysadmin@myadmin.com', ['SysAdmin'], None)
        yield app.test_client()


# ============================================================================
# Tenant Management Tests
# ============================================================================


@patch('routes.sysadmin_tenants.DatabaseManager')
@patch('services.tenant_provisioning_service.TenantProvisioningService.create_and_provision_tenant')
def test_create_tenant_success(mock_provision, mock_db_class, client):
    """Test successful tenant creation"""
    mock_provision.return_value = {
        'tenant': 'created',
        'modules': [{'name': 'FIN', 'status': 'created'}],
        'chart': 'created',
        'chart_rows': 50,
        'warnings': [],
    }
    
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
@patch('services.tenant_provisioning_service.TenantProvisioningService.create_and_provision_tenant')
def test_create_tenant_duplicate(mock_provision, mock_db_class, client):
    """Test creating duplicate tenant — provisioning returns skipped"""
    mock_provision.return_value = {
        'tenant': 'skipped',
        'modules': [],
        'chart': 'skipped',
        'chart_rows': 0,
        'warnings': ['Tenant already exists'],
    }
    
    response = client.post(
        '/api/sysadmin/tenants',
        json={
            'administration': 'TestCorp',
            'display_name': 'Test Corporation',
            'contact_email': 'admin@testcorp.com'
        },
        headers={'Content-Type': 'application/json'}
    )
    
    # Route returns 201 even for skipped (idempotent)
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['success'] is True


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
    from datetime import datetime
    mock_cognito.list_groups.return_value = {
        'Groups': [
            {'GroupName': 'SysAdmin', 'Description': 'System Administrator', 'CreationDate': datetime(2026, 1, 1)},
            {'GroupName': 'Finance_Read', 'Description': 'Finance Read Access', 'CreationDate': datetime(2026, 1, 1)}
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
    """Test successful module retrieval including registered_modules from registry"""
    from datetime import datetime
    mock_db = MagicMock()
    mock_db_class.return_value = mock_db
    
    mock_db.execute_query.side_effect = [
        [{'administration': 'GoodwinSolutions'}],  # Check tenant exists
        [  # Modules query
            {'module_name': 'FIN', 'is_active': True, 'created_at': datetime(2026, 1, 15, 10, 0), 'updated_at': datetime(2026, 1, 15, 10, 0)},
            {'module_name': 'STR', 'is_active': True, 'created_at': datetime(2026, 1, 15, 10, 0), 'updated_at': datetime(2026, 1, 15, 10, 0)}
        ]
    ]
    
    response = client.get('/api/sysadmin/tenants/GoodwinSolutions/modules')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert len(data['modules']) == 2

    # Verify registered_modules is returned from MODULE_REGISTRY
    assert 'registered_modules' in data
    reg_names = [m['name'] for m in data['registered_modules']]
    assert 'FIN' in reg_names
    assert 'ZZP' in reg_names
    assert 'TENADMIN' in reg_names

    # Verify each registered module has required fields
    for reg in data['registered_modules']:
        assert 'name' in reg
        assert 'description' in reg
        assert 'depends_on' in reg
        assert 'readonly' in reg

    # Verify ZZP depends on FIN
    zzp_reg = next(m for m in data['registered_modules'] if m['name'] == 'ZZP')
    assert 'FIN' in zzp_reg['depends_on']

    # Verify TENADMIN is readonly
    tenadmin_reg = next(m for m in data['registered_modules'] if m['name'] == 'TENADMIN')
    assert tenadmin_reg['readonly'] is True


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
