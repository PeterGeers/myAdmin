"""Unit tests for per-tenant role resolution in the cognito_required decorator."""

import base64
import json
import pytest
from unittest.mock import patch, Mock
from flask import Flask

from auth.cognito_utils import cognito_required


def _make_jwt(payload):
    """Create a mock JWT token from a payload dict."""
    header = base64.urlsafe_b64encode(json.dumps({'alg': 'RS256'}).encode()).decode().rstrip('=')
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return f"{header}.{body}.mock_signature"


@pytest.fixture
def app():
    """Minimal Flask app for testing the decorator."""
    app = Flask(__name__)

    @app.route('/test')
    @cognito_required()
    def test_route(user_email, user_roles):
        return {'email': user_email, 'roles': sorted(user_roles)}

    return app


@pytest.fixture
def jwt_sysadmin():
    """JWT with SysAdmin global role."""
    return _make_jwt({
        'email': 'admin@example.com',
        'cognito:groups': ['SysAdmin'],
        'exp': 9999999999
    })


class TestSysAdminGlobalRole:
    """SysAdmin in JWT should always be present regardless of tenant."""

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_sysadmin_kept_with_tenant(self, mock_tenant, mock_get_roles, mock_db_cls, app, jwt_sysadmin):
        mock_get_roles.return_value = ['Finance_CRUD']
        mock_db_cls.return_value = Mock()

        with app.test_client() as client:
            resp = client.get('/test', headers={
                'Authorization': f'Bearer {jwt_sysadmin}',
                'X-Tenant': 'TenantA'
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert 'SysAdmin' in data['roles']
        assert 'Finance_CRUD' in data['roles']

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantB')
    def test_sysadmin_kept_different_tenant(self, mock_tenant, mock_get_roles, mock_db_cls, app, jwt_sysadmin):
        mock_get_roles.return_value = []
        mock_db_cls.return_value = Mock()

        with app.test_client() as client:
            resp = client.get('/test', headers={
                'Authorization': f'Bearer {jwt_sysadmin}',
                'X-Tenant': 'TenantB'
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert 'SysAdmin' in data['roles']

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value=None)
    def test_sysadmin_kept_no_tenant(self, mock_tenant, mock_get_roles, mock_db_cls, app, jwt_sysadmin):
        with app.test_client() as client:
            resp = client.get('/test', headers={
                'Authorization': f'Bearer {jwt_sysadmin}'
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert 'SysAdmin' in data['roles']
        # No tenant → no DB lookup
        mock_get_roles.assert_not_called()


class TestPerTenantRolesFromDB:
    """User gets per-tenant roles from DB for the current tenant."""

    @pytest.fixture
    def jwt_no_groups(self):
        """JWT with no Cognito groups (roles come from DB only)."""
        return _make_jwt({
            'email': 'user@example.com',
            'cognito:groups': [],
            'exp': 9999999999
        })

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_user_gets_tenant_roles_from_db(self, mock_tenant, mock_get_roles, mock_db_cls, app, jwt_no_groups):
        mock_get_roles.return_value = ['Finance_CRUD', 'STR_Read']
        mock_db_cls.return_value = Mock()

        with app.test_client() as client:
            resp = client.get('/test', headers={
                'Authorization': f'Bearer {jwt_no_groups}',
                'X-Tenant': 'TenantA'
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert 'Finance_CRUD' in data['roles']
        assert 'STR_Read' in data['roles']
        mock_get_roles.assert_called_once()

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_user_with_no_db_roles_gets_empty(self, mock_tenant, mock_get_roles, mock_db_cls, app, jwt_no_groups):
        mock_get_roles.return_value = []
        mock_db_cls.return_value = Mock()

        with app.test_client() as client:
            resp = client.get('/test', headers={
                'Authorization': f'Bearer {jwt_no_groups}',
                'X-Tenant': 'TenantA'
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert data['roles'] == []

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_global_and_tenant_roles_merged(self, mock_tenant, mock_get_roles, mock_db_cls, app):
        jwt = _make_jwt({
            'email': 'admin@example.com',
            'cognito:groups': ['SysAdmin', 'Finance_CRUD'],
            'exp': 9999999999
        })
        mock_get_roles.return_value = ['STR_Read']
        mock_db_cls.return_value = Mock()

        with app.test_client() as client:
            resp = client.get('/test', headers={
                'Authorization': f'Bearer {jwt}',
                'X-Tenant': 'TenantA'
            })

        data = resp.get_json()
        assert resp.status_code == 200
        # SysAdmin from JWT (global), STR_Read from DB (per-tenant)
        assert 'SysAdmin' in data['roles']
        assert 'STR_Read' in data['roles']
        # Finance_CRUD was in JWT but not global — should NOT be kept from JWT
        # It would only appear if also in DB
        assert 'Finance_CRUD' not in data['roles']


class TestTenantIsolation:
    """User with roles in TenantA does NOT get those roles when requesting TenantB."""

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant')
    def test_roles_differ_per_tenant(self, mock_tenant, mock_get_roles, mock_db_cls, app):
        jwt = _make_jwt({
            'email': 'user@example.com',
            'cognito:groups': [],
            'exp': 9999999999
        })
        mock_db_cls.return_value = Mock()

        # Request TenantA — has Finance_CRUD
        mock_tenant.return_value = 'TenantA'
        mock_get_roles.return_value = ['Finance_CRUD', 'STR_CRUD']

        with app.test_client() as client:
            resp_a = client.get('/test', headers={
                'Authorization': f'Bearer {jwt}',
                'X-Tenant': 'TenantA'
            })

        assert resp_a.status_code == 200
        roles_a = resp_a.get_json()['roles']
        assert 'Finance_CRUD' in roles_a
        assert 'STR_CRUD' in roles_a

        # Request TenantB — only has STR_Read
        mock_tenant.return_value = 'TenantB'
        mock_get_roles.return_value = ['STR_Read']

        with app.test_client() as client:
            resp_b = client.get('/test', headers={
                'Authorization': f'Bearer {jwt}',
                'X-Tenant': 'TenantB'
            })

        assert resp_b.status_code == 200
        roles_b = resp_b.get_json()['roles']
        assert roles_b == ['STR_Read']
        assert 'Finance_CRUD' not in roles_b
        assert 'STR_CRUD' not in roles_b


class TestRolePermissionsMapping:
    """ROLE_PERMISSIONS mapping works unchanged with merged role list."""

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_permission_check_with_tenant_role(self, mock_tenant, mock_get_roles, mock_db_cls):
        """Route with required_permissions works when role comes from DB."""
        from auth.cognito_utils import cognito_required

        test_app = Flask(__name__)

        @test_app.route('/finance')
        @cognito_required(required_permissions=['finance_read'])
        def finance_route(user_email, user_roles):
            return {'email': user_email, 'roles': sorted(user_roles)}

        jwt = _make_jwt({
            'email': 'user@example.com',
            'cognito:groups': [],
            'exp': 9999999999
        })
        mock_get_roles.return_value = ['Finance_Read']
        mock_db_cls.return_value = Mock()

        with test_app.test_client() as client:
            resp = client.get('/finance', headers={
                'Authorization': f'Bearer {jwt}',
                'X-Tenant': 'TenantA'
            })

        assert resp.status_code == 200
        assert 'Finance_Read' in resp.get_json()['roles']

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_permission_denied_without_role(self, mock_tenant, mock_get_roles, mock_db_cls):
        """Route with required_permissions returns 403 when user lacks the role."""
        from auth.cognito_utils import cognito_required

        test_app = Flask(__name__)

        @test_app.route('/finance')
        @cognito_required(required_permissions=['finance_read'])
        def finance_route(user_email, user_roles):
            return {'email': user_email}

        jwt = _make_jwt({
            'email': 'user@example.com',
            'cognito:groups': [],
            'exp': 9999999999
        })
        mock_get_roles.return_value = ['STR_Read']  # no finance permissions
        mock_db_cls.return_value = Mock()

        with test_app.test_client() as client:
            resp = client.get('/finance', headers={
                'Authorization': f'Bearer {jwt}',
                'X-Tenant': 'TenantA'
            })

        assert resp.status_code == 403

    @patch('database.DatabaseManager')
    @patch('auth.role_cache.get_tenant_roles')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    def test_wildcard_permission_from_global_role(self, mock_tenant, mock_get_roles, mock_db_cls):
        """Administrators global role grants wildcard access via ROLE_PERMISSIONS."""
        from auth.cognito_utils import cognito_required

        test_app = Flask(__name__)

        @test_app.route('/anything')
        @cognito_required(required_permissions=['finance_read', 'str_read'])
        def any_route(user_email, user_roles):
            return {'email': user_email, 'roles': sorted(user_roles)}

        jwt = _make_jwt({
            'email': 'admin@example.com',
            'cognito:groups': ['Administrators'],
            'exp': 9999999999
        })
        mock_get_roles.return_value = []
        mock_db_cls.return_value = Mock()

        with test_app.test_client() as client:
            resp = client.get('/anything', headers={
                'Authorization': f'Bearer {jwt}',
                'X-Tenant': 'TenantA'
            })

        assert resp.status_code == 200
