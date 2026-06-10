"""
API tests for contact_routes.py

Tests contact management endpoints including auth enforcement,
listing, creation, retrieval, update, deletion, and types.

Requirements: 20.3
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def zzp_auth():
    """Mock authentication with ZZP roles for contact endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['ZZP_CRUD', 'ZZP_Read']):
        mock_creds.return_value = ('test@example.com', ['ZZP_CRUD', 'ZZP_Read'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


@pytest.mark.api
class TestAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_list_contacts_unauthenticated(self, client):
        """Unauthenticated request to list contacts should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/contacts')
        assert response.status_code in (401, 403)

    def test_get_contact_unauthenticated(self, client):
        """Unauthenticated request to get contact should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/contacts/1')
        assert response.status_code in (401, 403)

    def test_create_contact_unauthenticated(self, client):
        """Unauthenticated request to create contact should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/contacts', json={'client_id': 'X'})
        assert response.status_code in (401, 403)

    def test_update_contact_unauthenticated(self, client):
        """Unauthenticated request to update contact should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.put('/api/contacts/1', json={'company_name': 'X'})
        assert response.status_code in (401, 403)

    def test_delete_contact_unauthenticated(self, client):
        """Unauthenticated request to delete contact should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.delete('/api/contacts/1')
        assert response.status_code in (401, 403)

    def test_get_types_unauthenticated(self, client):
        """Unauthenticated request to get types should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/contacts/types')
        assert response.status_code in (401, 403)


# ============================================================================
# List Contacts Tests
# ============================================================================


@pytest.mark.api
class TestListContacts:
    """Tests for GET /api/contacts."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_list_contacts_success(self, mock_get_service, mock_module,
                                   client, zzp_auth):
        """Authenticated user can list contacts."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_contacts.return_value = [
            {'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'}
        ]

        response = client.get('/api/contacts', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_list_contacts_with_type_filter(self, mock_get_service, mock_module,
                                            client, zzp_auth):
        """Contacts can be filtered by contact_type query param."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_contacts.return_value = []

        response = client.get('/api/contacts?contact_type=supplier',
                              headers=zzp_auth)

        assert response.status_code == 200
        mock_service.list_contacts.assert_called_once_with(
            'test-tenant', contact_type='supplier', include_inactive=False
        )

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_list_contacts_server_error(self, mock_get_service, mock_module,
                                        client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_contacts.side_effect = Exception("DB down")

        response = client.get('/api/contacts', headers=zzp_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Get Contact Tests
# ============================================================================


@pytest.mark.api
class TestGetContact:
    """Tests for GET /api/contacts/<id>."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_get_contact_success(self, mock_get_service, mock_module,
                                 client, zzp_auth):
        """Getting existing contact returns contact data."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_contact.return_value = {
            'id': 1, 'client_id': 'ACME', 'company_name': 'Acme Corp'
        }

        response = client.get('/api/contacts/1', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['client_id'] == 'ACME'

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_get_contact_not_found(self, mock_get_service, mock_module,
                                   client, zzp_auth):
        """Non-existent contact returns 404."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_contact.return_value = None

        response = client.get('/api/contacts/9999', headers=zzp_auth)

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_get_contact_server_error(self, mock_get_service, mock_module,
                                      client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_contact.side_effect = Exception("DB error")

        response = client.get('/api/contacts/1', headers=zzp_auth)

        assert response.status_code == 500


# ============================================================================
# Create Contact Tests
# ============================================================================


@pytest.mark.api
class TestCreateContact:
    """Tests for POST /api/contacts."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_create_contact_success(self, mock_get_service, mock_module,
                                    client, zzp_auth):
        """Valid contact creation returns 201."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_contact.return_value = {
            'id': 1, 'client_id': 'NEW', 'company_name': 'New Corp'
        }

        response = client.post(
            '/api/contacts',
            headers=zzp_auth,
            json={'client_id': 'NEW', 'company_name': 'New Corp'}
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_create_contact_no_body(self, mock_get_service, mock_module,
                                    client, zzp_auth):
        """Missing request body returns 400 or 500."""
        response = client.post(
            '/api/contacts',
            headers=zzp_auth,
            json=None
        )

        assert response.status_code in (400, 500)
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_create_contact_value_error(self, mock_get_service, mock_module,
                                        client, zzp_auth):
        """ValueError from service returns 400."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_contact.side_effect = ValueError(
            "client_id already exists"
        )

        response = client.post(
            '/api/contacts',
            headers=zzp_auth,
            json={'client_id': 'DUP'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'already exists' in data['error']

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_create_contact_server_error(self, mock_get_service, mock_module,
                                         client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_contact.side_effect = Exception("DB error")

        response = client.post(
            '/api/contacts',
            headers=zzp_auth,
            json={'client_id': 'X', 'company_name': 'Corp'}
        )

        assert response.status_code == 500


# ============================================================================
# Update Contact Tests
# ============================================================================


@pytest.mark.api
class TestUpdateContact:
    """Tests for PUT /api/contacts/<id>."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_update_contact_success(self, mock_get_service, mock_module,
                                    client, zzp_auth):
        """Valid update returns 200."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.update_contact.return_value = {
            'id': 1, 'company_name': 'Updated Corp'
        }

        response = client.put(
            '/api/contacts/1',
            headers=zzp_auth,
            json={'company_name': 'Updated Corp'}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_update_contact_no_body(self, mock_get_service, mock_module,
                                    client, zzp_auth):
        """Missing request body returns 400 or 500."""
        response = client.put(
            '/api/contacts/1',
            headers=zzp_auth,
            json=None
        )

        assert response.status_code in (400, 500)
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_update_contact_value_error(self, mock_get_service, mock_module,
                                        client, zzp_auth):
        """ValueError from service returns 400."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.update_contact.side_effect = ValueError("Invalid data")

        response = client.put(
            '/api/contacts/1',
            headers=zzp_auth,
            json={'company_name': ''}
        )

        assert response.status_code == 400

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_update_contact_server_error(self, mock_get_service, mock_module,
                                         client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.update_contact.side_effect = Exception("DB error")

        response = client.put(
            '/api/contacts/1',
            headers=zzp_auth,
            json={'company_name': 'X'}
        )

        assert response.status_code == 500


# ============================================================================
# Delete Contact Tests
# ============================================================================


@pytest.mark.api
class TestDeleteContact:
    """Tests for DELETE /api/contacts/<id>."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_delete_contact_success(self, mock_get_service, mock_module,
                                    client, zzp_auth):
        """Successful soft-delete returns 200."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.soft_delete_contact.return_value = True

        response = client.delete('/api/contacts/1', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_delete_contact_in_use(self, mock_get_service, mock_module,
                                   client, zzp_auth):
        """Deleting contact in use returns 400."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.soft_delete_contact.side_effect = ValueError(
            "referenced by existing invoices"
        )

        response = client.delete('/api/contacts/1', headers=zzp_auth)

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'referenced' in data['error']

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_delete_contact_server_error(self, mock_get_service, mock_module,
                                         client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.soft_delete_contact.side_effect = Exception("DB error")

        response = client.delete('/api/contacts/1', headers=zzp_auth)

        assert response.status_code == 500


# ============================================================================
# Get Contact Types Tests
# ============================================================================


@pytest.mark.api
class TestGetContactTypes:
    """Tests for GET /api/contacts/types."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_get_types_success(self, mock_get_service, mock_module,
                               client, zzp_auth):
        """Returns list of contact types."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_contact_types.return_value = [
            'client', 'supplier', 'both', 'other'
        ]

        response = client.get('/api/contacts/types', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'client' in data['data']

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.contact_routes._get_service')
    def test_get_types_server_error(self, mock_get_service, mock_module,
                                    client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_contact_types.side_effect = Exception("DB error")

        response = client.get('/api/contacts/types', headers=zzp_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
