"""
API tests for cache_routes.py

Tests cache management endpoints including warmup, refresh,
invalidation, and status for both mutaties cache and BNB cache.

Requirements: 20.2
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import pytest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock


@pytest.fixture
def cache_auth():
    """Mock authentication with Finance_CRUD role (has actuals_read permission)."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Finance_CRUD']):
        mock_creds.return_value = ('test@example.com', ['Finance_CRUD'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


@pytest.mark.api
class TestCacheAuthEnforcement:
    """Verify 401/403 for unauthenticated requests to cache endpoints."""

    def test_cache_warmup_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to cache warmup should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/cache/warmup')
        assert response.status_code in (401, 403)

    def test_cache_status_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to cache status should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/cache/status')
        assert response.status_code in (401, 403)

    def test_cache_refresh_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to cache refresh should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/cache/refresh')
        assert response.status_code in (401, 403)

    def test_cache_invalidate_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to cache invalidate should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/cache/invalidate')
        assert response.status_code in (401, 403)

    def test_bnb_cache_status_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to BNB cache status should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/bnb-cache/status')
        assert response.status_code in (401, 403)

    def test_bnb_cache_refresh_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to BNB cache refresh should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/bnb-cache/refresh')
        assert response.status_code in (401, 403)

    def test_bnb_cache_invalidate_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to BNB cache invalidate should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post('/api/bnb-cache/invalidate')
        assert response.status_code in (401, 403)


# ============================================================================
# Cache Warmup Tests
# ============================================================================


@pytest.mark.api
class TestCacheWarmup:
    """Tests for POST /api/cache/warmup."""

    @patch('routes.cache_routes.DatabaseManager')
    @patch('routes.cache_routes.get_cache')
    def test_warmup_cache_already_loaded(self, mock_get_cache, mock_db_class,
                                         client, cache_auth):
        """Warmup when cache is already loaded returns existing stats."""
        mock_cache = MagicMock()
        mock_cache.data = [{'id': 1}, {'id': 2}]
        mock_cache.last_loaded = datetime(2024, 6, 15, 10, 30, 0)
        mock_get_cache.return_value = mock_cache

        response = client.post('/api/cache/warmup', headers=cache_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == 'Cache already loaded'
        assert data['record_count'] == 2
        assert data['last_refresh'] is not None

    @patch('routes.cache_routes.DatabaseManager')
    @patch('routes.cache_routes.get_cache')
    def test_warmup_cache_loads_fresh(self, mock_get_cache, mock_db_class,
                                      client, cache_auth):
        """Warmup when cache is empty loads data from database."""
        mock_cache = MagicMock()
        mock_cache.data = None
        mock_cache.last_loaded = None
        mock_get_cache.return_value = mock_cache

        # After get_data is called, cache becomes populated
        def populate_cache(db):
            mock_cache.data = [{'id': 1}]
            mock_cache.last_loaded = datetime(2024, 6, 15, 11, 0, 0)

        mock_cache.get_data.side_effect = populate_cache

        response = client.post('/api/cache/warmup', headers=cache_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == 'Cache loaded successfully'
        mock_cache.get_data.assert_called_once()

    @patch('routes.cache_routes.get_cache')
    def test_warmup_error_returns_500(self, mock_get_cache, client, cache_auth):
        """Warmup failure returns 500 with error details."""
        mock_get_cache.side_effect = Exception("Database connection failed")

        response = client.post('/api/cache/warmup', headers=cache_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data


# ============================================================================
# Cache Status Tests
# ============================================================================


@pytest.mark.api
class TestCacheStatus:
    """Tests for GET /api/cache/status."""

    @patch('routes.cache_routes.get_cache')
    def test_cache_status_active(self, mock_get_cache, client,
                                 mock_auth_sysadmin):
        """Status returns cache info when active."""
        mock_cache = MagicMock()
        mock_cache.data = [{'id': 1}, {'id': 2}, {'id': 3}]
        mock_cache.last_loaded = datetime(2024, 6, 15, 10, 30, 0)
        mock_get_cache.return_value = mock_cache

        response = client.get('/api/cache/status',
                              headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['cache_active'] is True
        assert data['record_count'] == 3
        assert data['auto_refresh_enabled'] is True
        assert data['refresh_threshold_minutes'] == 30

    @patch('routes.cache_routes.get_cache')
    def test_cache_status_inactive(self, mock_get_cache, client,
                                   mock_auth_sysadmin):
        """Status returns inactive when cache has no data."""
        mock_cache = MagicMock()
        mock_cache.data = None
        mock_cache.last_loaded = None
        mock_get_cache.return_value = mock_cache

        response = client.get('/api/cache/status',
                              headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['cache_active'] is False
        assert data['record_count'] == 0

    @patch('routes.cache_routes.get_cache')
    def test_cache_status_error_returns_500(self, mock_get_cache, client,
                                            mock_auth_sysadmin):
        """Status failure returns 500."""
        mock_get_cache.side_effect = Exception("Unexpected error")

        response = client.get('/api/cache/status',
                              headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data

    def test_cache_status_non_sysadmin_rejected(self, client, mock_auth):
        """Non-SysAdmin cannot access cache status."""
        response = client.get('/api/cache/status', headers=mock_auth)
        assert response.status_code in (401, 403)


# ============================================================================
# Cache Refresh Tests
# ============================================================================


@pytest.mark.api
class TestCacheRefresh:
    """Tests for POST /api/cache/refresh."""

    @patch('routes.cache_routes.DatabaseManager')
    @patch('routes.cache_routes.get_cache')
    def test_cache_refresh_success(self, mock_get_cache, mock_db_class,
                                   client, mock_auth_sysadmin):
        """Refresh invalidates and reloads cache."""
        mock_cache = MagicMock()
        mock_cache.data = [{'id': 1}, {'id': 2}]
        mock_cache.last_loaded = datetime(2024, 6, 15, 12, 0, 0)
        mock_get_cache.return_value = mock_cache

        response = client.post('/api/cache/refresh',
                               headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == 'Cache refreshed successfully'
        mock_cache.invalidate.assert_called_once()
        mock_cache.get_data.assert_called_once()

    @patch('routes.cache_routes.get_cache')
    def test_cache_refresh_error_returns_500(self, mock_get_cache, client,
                                             mock_auth_sysadmin):
        """Refresh failure returns 500."""
        mock_get_cache.side_effect = Exception("Refresh failed")

        response = client.post('/api/cache/refresh',
                               headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data

    def test_cache_refresh_non_sysadmin_rejected(self, client, mock_auth):
        """Non-SysAdmin cannot refresh cache."""
        response = client.post('/api/cache/refresh', headers=mock_auth)
        assert response.status_code in (401, 403)


# ============================================================================
# Cache Invalidate Tests
# ============================================================================


@pytest.mark.api
class TestCacheInvalidate:
    """Tests for POST /api/cache/invalidate."""

    @patch('routes.cache_routes.invalidate_cache')
    def test_cache_invalidate_success(self, mock_invalidate, client,
                                      cache_auth):
        """Invalidation succeeds and returns confirmation."""
        response = client.post('/api/cache/invalidate', headers=cache_auth)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == 'Cache invalidated successfully'
        mock_invalidate.assert_called_once()

    @patch('routes.cache_routes.invalidate_cache')
    def test_cache_invalidate_error_returns_500(self, mock_invalidate, client,
                                                cache_auth):
        """Invalidation failure returns 500."""
        mock_invalidate.side_effect = Exception("Invalidation failed")

        response = client.post('/api/cache/invalidate', headers=cache_auth)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data


# ============================================================================
# BNB Cache Status Tests
# ============================================================================


@pytest.mark.api
class TestBnbCacheStatus:
    """Tests for GET /api/bnb-cache/status."""

    @patch('routes.cache_routes.get_bnb_cache')
    def test_bnb_cache_status_success(self, mock_get_bnb_cache, client,
                                      mock_auth_sysadmin):
        """BNB cache status returns cache info."""
        mock_bnb_cache = MagicMock()
        mock_bnb_cache.get_status.return_value = {
            'cache_active': True,
            'record_count': 50,
            'last_refresh': '2024-06-15T10:00:00'
        }
        mock_get_bnb_cache.return_value = mock_bnb_cache

        response = client.get('/api/bnb-cache/status',
                              headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['cache_active'] is True
        assert data['record_count'] == 50

    @patch('routes.cache_routes.get_bnb_cache')
    def test_bnb_cache_status_error_returns_500(self, mock_get_bnb_cache,
                                                client, mock_auth_sysadmin):
        """BNB cache status failure returns 500."""
        mock_get_bnb_cache.side_effect = Exception("BNB cache error")

        response = client.get('/api/bnb-cache/status',
                              headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data

    def test_bnb_cache_status_non_sysadmin_rejected(self, client, mock_auth):
        """Non-SysAdmin cannot access BNB cache status."""
        response = client.get('/api/bnb-cache/status', headers=mock_auth)
        assert response.status_code in (401, 403)


# ============================================================================
# BNB Cache Refresh Tests
# ============================================================================


@pytest.mark.api
class TestBnbCacheRefresh:
    """Tests for POST /api/bnb-cache/refresh."""

    @patch('routes.cache_routes.DatabaseManager')
    @patch('routes.cache_routes.get_bnb_cache')
    def test_bnb_cache_refresh_success(self, mock_get_bnb_cache, mock_db_class,
                                       client, mock_auth_sysadmin):
        """BNB cache refresh reloads data."""
        mock_bnb_cache = MagicMock()
        mock_bnb_cache.get_status.return_value = {
            'cache_active': True,
            'record_count': 75,
            'last_refresh': '2024-06-15T12:00:00'
        }
        mock_get_bnb_cache.return_value = mock_bnb_cache

        response = client.post('/api/bnb-cache/refresh',
                               headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == 'BNB cache refreshed successfully'
        mock_bnb_cache.refresh.assert_called_once()

    @patch('routes.cache_routes.get_bnb_cache')
    def test_bnb_cache_refresh_error_returns_500(self, mock_get_bnb_cache,
                                                  client, mock_auth_sysadmin):
        """BNB cache refresh failure returns 500."""
        mock_get_bnb_cache.side_effect = Exception("Refresh failed")

        response = client.post('/api/bnb-cache/refresh',
                               headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data

    def test_bnb_cache_refresh_non_sysadmin_rejected(self, client, mock_auth):
        """Non-SysAdmin cannot refresh BNB cache."""
        response = client.post('/api/bnb-cache/refresh', headers=mock_auth)
        assert response.status_code in (401, 403)


# ============================================================================
# BNB Cache Invalidate Tests
# ============================================================================


@pytest.mark.api
class TestBnbCacheInvalidate:
    """Tests for POST /api/bnb-cache/invalidate."""

    @patch('routes.cache_routes.get_bnb_cache')
    def test_bnb_cache_invalidate_success(self, mock_get_bnb_cache, client,
                                          mock_auth_sysadmin):
        """BNB cache invalidation succeeds."""
        mock_bnb_cache = MagicMock()
        mock_get_bnb_cache.return_value = mock_bnb_cache

        response = client.post('/api/bnb-cache/invalidate',
                               headers=mock_auth_sysadmin)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['message'] == 'BNB cache invalidated successfully'
        mock_bnb_cache.invalidate.assert_called_once()

    @patch('routes.cache_routes.get_bnb_cache')
    def test_bnb_cache_invalidate_error_returns_500(self, mock_get_bnb_cache,
                                                     client,
                                                     mock_auth_sysadmin):
        """BNB cache invalidation failure returns 500."""
        mock_get_bnb_cache.side_effect = Exception("Invalidation error")

        response = client.post('/api/bnb-cache/invalidate',
                               headers=mock_auth_sysadmin)

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'error' in data

    def test_bnb_cache_invalidate_non_sysadmin_rejected(self, client,
                                                         mock_auth):
        """Non-SysAdmin cannot invalidate BNB cache."""
        response = client.post('/api/bnb-cache/invalidate', headers=mock_auth)
        assert response.status_code in (401, 403)
