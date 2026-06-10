"""
API tests for routes/sysadmin_tenants.py

Tests tenant CRUD operations: create, list, get, update, delete.
Also covers module management endpoints nested under tenants.

Requirements: 20.7
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import pytest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock
from flask import Flask


@pytest.fixture
def app():
    """Create Flask app with sysadmin blueprint registered."""
    app = Flask(__name__)
    app.config['TESTING'] = True

    from routes.sysadmin_routes import sysadmin_bp
    app.register_blueprint(sysadmin_bp)

    return app


@pytest.fixture
def client(app):
    """Create test client with mocked SysAdmin auth."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth:
        mock_auth.return_value = ('sysadmin@myadmin.com', ['SysAdmin'], None)
        yield app.test_client()


@pytest.fixture
def non_admin_client(app):
    """Create test client with non-SysAdmin auth for auth enforcement tests."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_auth:
        mock_auth.return_value = ('user@example.com', ['TenantAdmin'], None)
        yield app.test_client()


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


@pytest.mark.api
class TestSysadminTenantAuth:
    """Verify only SysAdmin role can access tenant endpoints."""

    def test_list_tenants_unauthenticated(self, app):
        """Unauthenticated request to list tenants should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            with app.test_client() as c:
                response = c.get('/api/sysadmin/tenants')
        assert response.status_code in (401, 403)

    def test_create_tenant_unauthenticated(self, app):
        """Unauthenticated request to create tenant should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            with app.test_client() as c:
                response = c.post('/api/sysadmin/tenants', json={
                    'administration': 'TestCorp',
                    'display_name': 'Test',
                    'contact_email': 'a@b.com'
                })
        assert response.status_code in (401, 403)

    def test_list_tenants_non_sysadmin(self, non_admin_client):
        """TenantAdmin user should be rejected from sysadmin endpoints."""
        response = non_admin_client.get('/api/sysadmin/tenants')
        assert response.status_code == 403


# ============================================================================
# Create Tenant Tests
# ============================================================================


@pytest.mark.api
class TestCreateTenant:
    """Tests for POST /api/sysadmin/tenants."""

    @patch('routes.sysadmin_tenants.DatabaseManager')
    @patch('services.tenant_provisioning_service.TenantProvisioningService.create_and_provision_tenant')
    def test_create_tenant_success(self, mock_provision, mock_db_class, client):
        """Successful tenant creation returns 201."""
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
                'administration': 'NewTenant',
                'display_name': 'New Tenant Corp',
                'contact_email': 'admin@newtenant.com',
                'enabled_modules': ['FIN'],
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['administration'] == 'NewTenant'
        assert data['status'] == 'active'

    @patch('routes.sysadmin_tenants.DatabaseManager')
    @patch('services.tenant_provisioning_service.TenantProvisioningService.create_and_provision_tenant')
    def test_create_tenant_with_initial_admin(self, mock_provision, mock_db_class, client):
        """Tenant creation with initial admin email includes admin info in response."""
        mock_provision.return_value = {
            'tenant': 'created',
            'modules': [],
            'chart': 'created',
            'chart_rows': 50,
            'warnings': [],
            'initial_admin': {'email': 'john@newcorp.com', 'status': 'invited'},
        }

        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'administration': 'AdminTenant',
                'display_name': 'Admin Tenant',
                'contact_email': 'admin@admintenant.com',
                'initial_admin_email': 'john@newcorp.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['initial_admin']['email'] == 'john@newcorp.com'

    def test_create_tenant_missing_administration(self, client):
        """Missing administration field returns 400."""
        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'display_name': 'Test',
                'contact_email': 'a@b.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Missing required field' in data['error']

    def test_create_tenant_missing_display_name(self, client):
        """Missing display_name field returns 400."""
        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'administration': 'TestCorp',
                'contact_email': 'a@b.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Missing required field: display_name' in data['error']

    def test_create_tenant_missing_contact_email(self, client):
        """Missing contact_email field returns 400."""
        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'administration': 'TestCorp',
                'display_name': 'Test Corp',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Missing required field: contact_email' in data['error']

    def test_create_tenant_name_too_short(self, client):
        """Administration name < 3 chars returns 400."""
        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'administration': 'AB',
                'display_name': 'Test',
                'contact_email': 'a@b.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'at least 3 characters' in data['error']

    def test_create_tenant_name_invalid_chars(self, client):
        """Administration name with spaces/special chars returns 400."""
        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'administration': 'Test Corp!',
                'display_name': 'Test',
                'contact_email': 'a@b.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_create_tenant_name_starts_with_number(self, client):
        """Administration name starting with number returns 400."""
        response = client.post(
            '/api/sysadmin/tenants',
            json={
                'administration': '123Corp',
                'display_name': 'Test',
                'contact_email': 'a@b.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'must start with a letter' in data['error']


# ============================================================================
# List Tenants Tests
# ============================================================================


@pytest.mark.api
class TestListTenants:
    """Tests for GET /api/sysadmin/tenants."""

    @patch('routes.sysadmin_tenants.get_tenant_user_count', return_value=2)
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_list_tenants_success(self, mock_db_class, mock_user_count, client):
        """Successful tenant listing returns paginated results."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'total': 1}],  # COUNT query
            [{  # Tenant list query
                'administration': 'TestCorp',
                'display_name': 'Test Corporation',
                'status': 'active',
                'contact_email': 'admin@testcorp.com',
                'phone_number': '+31123456789',
                'street_address': 'Main St 1',
                'city': 'Amsterdam',
                'zipcode': '1000AA',
                'country': 'Netherlands',
                'created_at': datetime(2026, 1, 15, 10, 0),
                'updated_at': datetime(2026, 2, 1, 12, 0),
            }],
            [{'module_name': 'FIN'}, {'module_name': 'STR'}],  # Modules for TestCorp
        ]

        response = client.get('/api/sysadmin/tenants')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total'] == 1
        assert len(data['tenants']) == 1
        assert data['tenants'][0]['administration'] == 'TestCorp'
        assert data['tenants'][0]['enabled_modules'] == ['FIN', 'STR']
        assert data['page'] == 1
        assert data['per_page'] == 50

    @patch('routes.sysadmin_tenants.get_tenant_user_count', return_value=0)
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_list_tenants_with_status_filter(self, mock_db_class, mock_user_count, client):
        """Status filter is applied to query."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'total': 0}],  # COUNT query
            [],  # No results
        ]

        response = client.get('/api/sysadmin/tenants?status=suspended')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['total'] == 0
        assert data['tenants'] == []

    @patch('routes.sysadmin_tenants.get_tenant_user_count', return_value=0)
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_list_tenants_with_search(self, mock_db_class, mock_user_count, client):
        """Search parameter filters tenants."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        response = client.get('/api/sysadmin/tenants?search=corp')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.sysadmin_tenants.get_tenant_user_count', return_value=0)
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_list_tenants_pagination(self, mock_db_class, mock_user_count, client):
        """Pagination parameters are respected."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'total': 5}],
            [],
        ]

        response = client.get('/api/sysadmin/tenants?page=2&per_page=2')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['page'] == 2
        assert data['per_page'] == 2


# ============================================================================
# Get Tenant Tests
# ============================================================================


@pytest.mark.api
class TestGetTenant:
    """Tests for GET /api/sysadmin/tenants/<administration>."""

    @patch('routes.sysadmin_tenants.get_tenant_users', return_value=[
        {'email': 'user1@corp.com', 'groups': ['TenantAdmin']},
    ])
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_get_tenant_success(self, mock_db_class, mock_users, client):
        """Successful tenant retrieval returns full tenant details."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{  # Tenant query
                'administration': 'TestCorp',
                'display_name': 'Test Corporation',
                'status': 'active',
                'contact_email': 'admin@testcorp.com',
                'phone_number': '+31123456789',
                'street_address': 'Main St 1',
                'city': 'Amsterdam',
                'zipcode': '1000AA',
                'country': 'Netherlands',
                'created_at': datetime(2026, 1, 15, 10, 0),
                'updated_at': datetime(2026, 2, 1, 12, 0),
                'updated_by': 'admin@myadmin.com',
            }],
            [{'module_name': 'FIN'}],  # Modules query
        ]

        response = client.get('/api/sysadmin/tenants/TestCorp')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['tenant']['administration'] == 'TestCorp'
        assert data['tenant']['enabled_modules'] == ['FIN']
        assert data['tenant']['user_count'] == 1
        assert len(data['tenant']['users']) == 1

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_get_tenant_not_found(self, mock_db_class, client):
        """Non-existent tenant returns 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.return_value = []

        response = client.get('/api/sysadmin/tenants/NonExistent')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error']


# ============================================================================
# Update Tenant Tests
# ============================================================================


@pytest.mark.api
class TestUpdateTenant:
    """Tests for PUT /api/sysadmin/tenants/<administration>."""

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_tenant_success(self, mock_db_class, client):
        """Successful tenant update returns success message."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
            None,  # UPDATE query
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp',
            json={
                'display_name': 'Updated Corp Name',
                'contact_email': 'new@testcorp.com',
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['administration'] == 'TestCorp'

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_tenant_not_found(self, mock_db_class, client):
        """Updating non-existent tenant returns 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.return_value = []

        response = client.put(
            '/api/sysadmin/tenants/NonExistent',
            json={'display_name': 'New Name'},
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error']

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_tenant_no_fields(self, mock_db_class, client):
        """Updating with no valid fields returns 400."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp',
            json={'invalid_field': 'value'},
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No fields to update' in data['error']

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_tenant_invalid_status(self, mock_db_class, client):
        """Updating with invalid status returns 400."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp',
            json={'status': 'bogus_status'},
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid status' in data['error']

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_tenant_valid_status(self, mock_db_class, client):
        """Updating with valid status succeeds."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
            None,  # UPDATE query
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp',
            json={'status': 'suspended'},
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True


# ============================================================================
# Delete Tenant Tests
# ============================================================================


@pytest.mark.api
class TestDeleteTenant:
    """Tests for DELETE /api/sysadmin/tenants/<administration>."""

    @patch('routes.sysadmin_tenants.get_tenant_user_count', return_value=0)
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_delete_tenant_success(self, mock_db_class, mock_user_count, client):
        """Successful soft delete returns success message."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp', 'status': 'active'}],  # Check exists
            None,  # UPDATE status to deleted
        ]

        response = client.delete('/api/sysadmin/tenants/TestCorp')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'deleted successfully' in data['message']

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_delete_tenant_not_found(self, mock_db_class, client):
        """Deleting non-existent tenant returns 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.return_value = []

        response = client.delete('/api/sysadmin/tenants/NonExistent')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error']

    @patch('routes.sysadmin_tenants.get_tenant_user_count', return_value=3)
    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_delete_tenant_with_active_users(self, mock_db_class, mock_user_count, client):
        """Deleting tenant with active users returns 409."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp', 'status': 'active'}],  # Check exists
        ]

        response = client.delete('/api/sysadmin/tenants/TestCorp')

        assert response.status_code == 409
        data = json.loads(response.data)
        assert 'Cannot delete tenant with active users' in data['error']
        assert '3 user(s)' in data['error']


# ============================================================================
# Get Tenant Modules Tests
# ============================================================================


@pytest.mark.api
class TestGetTenantModules:
    """Tests for GET /api/sysadmin/tenants/<administration>/modules."""

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_get_modules_success(self, mock_db_class, client):
        """Successful module retrieval returns modules and registry."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
            [  # Modules query
                {'module_name': 'FIN', 'is_active': True,
                 'created_at': datetime(2026, 1, 1), 'updated_at': datetime(2026, 1, 1)},
            ],
        ]

        response = client.get('/api/sysadmin/tenants/TestCorp/modules')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['administration'] == 'TestCorp'
        assert len(data['modules']) == 1
        assert data['modules'][0]['module_name'] == 'FIN'
        # registered_modules comes from MODULE_REGISTRY
        assert 'registered_modules' in data
        assert len(data['registered_modules']) > 0

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_get_modules_tenant_not_found(self, mock_db_class, client):
        """Getting modules for non-existent tenant returns 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [],  # Tenant not found
        ]

        response = client.get('/api/sysadmin/tenants/NonExistent/modules')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error']


# ============================================================================
# Update Tenant Modules Tests
# ============================================================================


@pytest.mark.api
class TestUpdateTenantModules:
    """Tests for PUT /api/sysadmin/tenants/<administration>/modules."""

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_modules_success(self, mock_db_class, client):
        """Successful module update returns success."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
            [{'id': 1}],  # Module exists (FIN)
            None,  # Update FIN
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp/modules',
            json={
                'modules': [{'name': 'FIN', 'is_active': True}]
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_modules_insert_new(self, mock_db_class, client):
        """Adding a new module inserts it into the database."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [{'administration': 'TestCorp'}],  # Check exists
            [],  # Module doesn't exist yet (STR)
            None,  # Insert STR
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp/modules',
            json={
                'modules': [{'name': 'STR', 'is_active': True}]
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    def test_update_modules_missing_modules_field(self, client):
        """Missing modules field returns 400."""
        response = client.put(
            '/api/sysadmin/tenants/TestCorp/modules',
            json={},
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Missing required field: modules' in data['error']

    @patch('routes.sysadmin_tenants.DatabaseManager')
    def test_update_modules_tenant_not_found(self, mock_db_class, client):
        """Updating modules for non-existent tenant returns 404."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_db.execute_query.side_effect = [
            [],  # Tenant not found
        ]

        response = client.put(
            '/api/sysadmin/tenants/TestCorp/modules',
            json={
                'modules': [{'name': 'FIN', 'is_active': True}]
            },
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'not found' in data['error']
