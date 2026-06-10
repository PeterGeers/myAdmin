"""
API tests for product_routes.py

Tests product CRUD endpoints including auth enforcement,
listing, creation, retrieval, update, deletion, and product types.

Requirements: 20.4
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


@pytest.fixture
def zzp_auth():
    """Mock authentication with ZZP permissions for product endpoints."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['ZZP_CRUD']):
        mock_creds.return_value = ('test@example.com', ['ZZP_CRUD'], None)
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

    def test_list_products_unauthenticated(self, client):
        """Unauthenticated request to list products should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/products')
        assert response.status_code in (401, 403)

    def test_create_product_unauthenticated(self, client):
        """Unauthenticated request to create product should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/products', json={'name': 'Test'})
        assert response.status_code in (401, 403)

    def test_get_product_unauthenticated(self, client):
        """Unauthenticated request to get product should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/products/1')
        assert response.status_code in (401, 403)

    def test_delete_product_unauthenticated(self, client):
        """Unauthenticated request to delete product should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.delete('/api/products/1')
        assert response.status_code in (401, 403)


# ============================================================================
# List Products Tests
# ============================================================================


@pytest.mark.api
class TestListProducts:
    """Tests for GET /api/products."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_list_products_success(self, mock_get_service,
                                   mock_has_module, client, zzp_auth):
        """Authenticated user can list products."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_products.return_value = [
            {'id': 1, 'name': 'Web Development', 'type': 'service'}
        ]

        response = client.get('/api/products', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 1

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_list_products_with_inactive(self, mock_get_service,
                                         mock_has_module, client, zzp_auth):
        """Can request inactive products via query param."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_products.return_value = []

        response = client.get(
            '/api/products?include_inactive=true', headers=zzp_auth
        )

        assert response.status_code == 200
        mock_service.list_products.assert_called_once_with(
            'test-tenant', include_inactive=True
        )

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_list_products_server_error(self, mock_get_service,
                                        mock_has_module, client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.list_products.side_effect = Exception("DB timeout")

        response = client.get('/api/products', headers=zzp_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Get Product Tests
# ============================================================================


@pytest.mark.api
class TestGetProduct:
    """Tests for GET /api/products/<id>."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_get_product_success(self, mock_get_service,
                                  mock_has_module, client, zzp_auth):
        """Getting existing product returns product data."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_product.return_value = {
            'id': 1, 'name': 'Consulting', 'type': 'service'
        }

        response = client.get('/api/products/1', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['data']['id'] == 1

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_get_product_not_found(self, mock_get_service,
                                    mock_has_module, client, zzp_auth):
        """Getting non-existent product returns 404."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_product.return_value = None

        response = client.get('/api/products/9999', headers=zzp_auth)

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'not found' in data['error'].lower()

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_get_product_server_error(self, mock_get_service,
                                       mock_has_module, client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_product.side_effect = Exception("connection error")

        response = client.get('/api/products/1', headers=zzp_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Create Product Tests
# ============================================================================


@pytest.mark.api
class TestCreateProduct:
    """Tests for POST /api/products."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_create_product_success(self, mock_get_service,
                                     mock_has_module, client, zzp_auth):
        """Valid product creation returns 201."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_product.return_value = {
            'id': 1, 'name': 'Web Design', 'type': 'service'
        }

        response = client.post(
            '/api/products',
            headers=zzp_auth,
            json={'name': 'Web Design', 'type': 'service', 'price': 85.00}
        )

        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_create_product_missing_body(self, mock_get_service,
                                          mock_has_module, client, zzp_auth):
        """Missing request body returns 400 or 500."""
        response = client.post(
            '/api/products',
            headers=zzp_auth
        )

        # No JSON body: route returns 400 (body required) or 500 (parse error)
        assert response.status_code in (400, 500)
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_create_product_value_error(self, mock_get_service,
                                         mock_has_module, client, zzp_auth):
        """ValueError from service returns 400."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_product.side_effect = ValueError("Name is required")

        response = client.post(
            '/api/products',
            headers=zzp_auth,
            json={'type': 'service'}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Name is required' in data['error']

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_create_product_server_error(self, mock_get_service,
                                          mock_has_module, client, zzp_auth):
        """Unexpected exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.create_product.side_effect = Exception("DB error")

        response = client.post(
            '/api/products',
            headers=zzp_auth,
            json={'name': 'Broken', 'type': 'service'}
        )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False


# ============================================================================
# Update Product Tests
# ============================================================================


@pytest.mark.api
class TestUpdateProduct:
    """Tests for PUT /api/products/<id>."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_update_product_success(self, mock_get_service,
                                     mock_has_module, client, zzp_auth):
        """Valid update returns 200 with updated data."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.update_product.return_value = {
            'id': 1, 'name': 'Updated Service', 'price': 95.00
        }

        response = client.put(
            '/api/products/1',
            headers=zzp_auth,
            json={'name': 'Updated Service', 'price': 95.00}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_update_product_missing_body(self, mock_get_service,
                                          mock_has_module, client, zzp_auth):
        """Missing request body returns 400 or 500."""
        response = client.put(
            '/api/products/1',
            headers=zzp_auth
        )

        assert response.status_code in (400, 500)
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_update_product_value_error(self, mock_get_service,
                                         mock_has_module, client, zzp_auth):
        """ValueError from service returns 400."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.update_product.side_effect = ValueError("Invalid price")

        response = client.put(
            '/api/products/1',
            headers=zzp_auth,
            json={'price': -10}
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid price' in data['error']

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_update_product_server_error(self, mock_get_service,
                                          mock_has_module, client, zzp_auth):
        """Unexpected exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.update_product.side_effect = Exception("timeout")

        response = client.put(
            '/api/products/1',
            headers=zzp_auth,
            json={'name': 'X'}
        )

        assert response.status_code == 500


# ============================================================================
# Delete Product Tests
# ============================================================================


@pytest.mark.api
class TestDeleteProduct:
    """Tests for DELETE /api/products/<id>."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_delete_product_success(self, mock_get_service,
                                     mock_has_module, client, zzp_auth):
        """Soft-delete returns 200 with success message."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.soft_delete_product.return_value = None

        response = client.delete('/api/products/1', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'deactivated' in data['message'].lower()

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_delete_product_value_error(self, mock_get_service,
                                         mock_has_module, client, zzp_auth):
        """ValueError from service returns 400."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.soft_delete_product.side_effect = ValueError(
            "Product not found"
        )

        response = client.delete('/api/products/9999', headers=zzp_auth)

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_delete_product_server_error(self, mock_get_service,
                                          mock_has_module, client, zzp_auth):
        """Unexpected exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.soft_delete_product.side_effect = Exception("DB error")

        response = client.delete('/api/products/1', headers=zzp_auth)

        assert response.status_code == 500


# ============================================================================
# Product Types Tests
# ============================================================================


@pytest.mark.api
class TestGetProductTypes:
    """Tests for GET /api/products/types."""

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_get_product_types_success(self, mock_get_service,
                                        mock_has_module, client, zzp_auth):
        """Returns list of product types."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_product_types.return_value = [
            {'code': 'service', 'label': 'Service'},
            {'code': 'product', 'label': 'Product'},
        ]

        response = client.get('/api/products/types', headers=zzp_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert len(data['data']) == 2

    @patch('services.module_registry.has_module', return_value=True)
    @patch('routes.product_routes._get_service')
    def test_get_product_types_server_error(self, mock_get_service,
                                             mock_has_module, client, zzp_auth):
        """Service exception returns 500."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.get_product_types.side_effect = Exception("error")

        response = client.get('/api/products/types', headers=zzp_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
