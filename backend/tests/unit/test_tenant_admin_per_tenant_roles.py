"""
Tests for per-tenant role management in tenant admin routes.

Verifies that assign/remove/delete operations write to user_tenant_roles
table and invalidate the role cache correctly.
"""

import base64
import json
import pytest
from unittest.mock import patch, Mock
from flask import Flask

from routes.tenant_admin_roles import tenant_admin_roles_bp
from routes.tenant_admin_users import tenant_admin_users_bp


# The registry-resolved pool id the migrated role/group admin ops thread into
# admin_get_user (cognito-admin-pool-resolution). Token mode is exercised
# end-to-end in the resolver's own tests; here we stub the resolver to a
# deterministic pool id so the route wiring is tested and we can assert the pool
# is threaded through.
RESOLVED_POOL_ID = "eu-west-1_xyrlzfqbl"


@pytest.fixture(autouse=True)
def no_jwt_verifier():
    """Force the base64 JWT fallback so the mock token is accepted.

    In an environment where Cognito env vars are configured, ``cognito_required``
    would cryptographically verify the token and reject our mock JWT (401). These
    unit tests exercise the ROUTE logic, not JWT crypto, so we disable the verifier
    singleton and let ``extract_user_credentials`` decode the unverified payload
    (the same fallback used in local dev / verifier-less CI).
    """
    with patch("auth.cognito_utils._get_jwt_verifier", return_value=None), patch(
        "auth.cognito_utils.get_verified_tenants", return_value=None
    ):
        yield


@pytest.fixture(autouse=True)
def mock_pool():
    """Stub token-mode pool resolution to a deterministic pool id.

    The migrated role/group admin ops resolve the target Cognito pool via the
    shared registry-backed resolver (token mode) instead of the legacy
    ``COGNITO_USER_POOL_ID`` module var. In this verifier-less unit env the
    resolver would otherwise raise ``PoolResolutionError``; patching it keeps the
    route logic under test and lets us assert the resolved pool is threaded into
    the Cognito admin calls.
    """
    with patch(
        "routes.tenant_admin_roles._resolve_pool_id", return_value=RESOLVED_POOL_ID
    ), patch(
        "routes.tenant_admin_users._resolve_pool_id", return_value=RESOLVED_POOL_ID
    ):
        yield


def _make_jwt(payload):
    header = base64.urlsafe_b64encode(json.dumps({'alg': 'RS256'}).encode()).decode().rstrip('=')
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return f"{header}.{body}.mock_signature"


JWT_ADMIN = _make_jwt({
    'email': 'admin@example.com',
    'cognito:groups': ['Tenant_Admin'],
    'custom:tenants': '["TenantA", "TenantB"]',
    'exp': 9999999999
})


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(tenant_admin_roles_bp)
    app.register_blueprint(tenant_admin_users_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def mock_cognito():
    with patch('routes.tenant_admin_roles.cognito_client') as mock:
        mock.admin_get_user.return_value = {
            'UserAttributes': [
                {'Name': 'email', 'Value': 'user@example.com'},
                {'Name': 'name', 'Value': 'Test User'},
                {'Name': 'custom:tenants', 'Value': '["TenantA"]'}
            ]
        }
        yield mock


@pytest.fixture
def mock_db():
    """Mock DatabaseManager at both route module levels."""
    with patch('routes.tenant_admin_roles.DatabaseManager') as cls_roles, \
         patch('routes.tenant_admin_users.DatabaseManager') as cls_users:
        db = Mock()
        db.execute_query.return_value = None
        cls_roles.return_value = db
        cls_users.return_value = db
        yield db


class TestAssignRolePerTenant:
    """3.7: Assign Finance_CRUD in TenantA writes to DB for that tenant."""

    @patch('routes.tenant_admin_users.get_tenant_enabled_modules', return_value=['FIN', 'STR'])
    @patch('auth.role_cache.invalidate_cache')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    def test_assign_writes_to_db_for_tenant(
        self, mock_roles, mock_tenant, mock_invalidate, mock_modules, app, mock_cognito, mock_db
    ):
        with app.test_client() as client:
            resp = client.post(
                '/api/tenant-admin/users/user@example.com/groups',
                headers={
                    'Authorization': f'Bearer {JWT_ADMIN}',
                    'X-Tenant': 'TenantA',
                    'Content-Type': 'application/json'
                },
                json={'groupName': 'Finance_CRUD'}
            )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        insert_calls = [
            c for c in mock_db.execute_query.call_args_list
            if 'INSERT INTO user_tenant_roles' in str(c)
        ]
        assert len(insert_calls) == 1
        assert insert_calls[0][0][1] == ('user@example.com', 'TenantA', 'Finance_CRUD', 'admin@example.com')
        mock_invalidate.assert_called_with('user@example.com', 'TenantA')
        # The target-user lookup targets the registry-RESOLVED pool (token mode),
        # not the legacy COGNITO_USER_POOL_ID var (cognito-admin-pool-resolution).
        assert mock_cognito.admin_get_user.call_args.kwargs['UserPoolId'] == RESOLVED_POOL_ID


class TestRemoveRolePerTenant:
    """3.8: Remove role deletes from DB and invalidates cache."""

    @patch('routes.tenant_admin_users.get_tenant_enabled_modules', return_value=['FIN', 'STR'])
    @patch('auth.role_cache.invalidate_cache')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    def test_remove_deletes_from_db_and_invalidates(
        self, mock_roles, mock_tenant, mock_invalidate, mock_modules, app, mock_cognito, mock_db
    ):
        with app.test_client() as client:
            resp = client.delete(
                '/api/tenant-admin/users/user@example.com/groups/Finance_CRUD',
                headers={
                    'Authorization': f'Bearer {JWT_ADMIN}',
                    'X-Tenant': 'TenantA'
                }
            )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if 'DELETE FROM user_tenant_roles' in str(c)
        ]
        assert len(delete_calls) == 1
        assert delete_calls[0][0][1] == ('user@example.com', 'TenantA', 'Finance_CRUD')
        mock_invalidate.assert_called_with('user@example.com', 'TenantA')


class TestDeleteUserPerTenant:
    """3.9: Delete user from tenant cleans up all role entries."""

    @patch('routes.tenant_admin_users.cognito_service')
    @patch('auth.role_cache.invalidate_cache')
    @patch('auth.tenant_context.get_current_tenant', return_value='TenantA')
    @patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin'])
    def test_delete_cleans_up_all_roles(
        self, mock_roles, mock_tenant, mock_invalidate, mock_cog_svc, app, mock_cognito, mock_db
    ):
        mock_cog_svc.get_user_tenants.return_value = ['TenantA']
        mock_cog_svc.remove_tenant_from_user.return_value = (True, True)

        with app.test_client() as client:
            resp = client.delete(
                '/api/tenant-admin/users/user@example.com',
                headers={
                    'Authorization': f'Bearer {JWT_ADMIN}',
                    'X-Tenant': 'TenantA'
                }
            )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        delete_calls = [
            c for c in mock_db.execute_query.call_args_list
            if 'DELETE FROM user_tenant_roles' in str(c)
        ]
        assert len(delete_calls) == 1
        assert delete_calls[0][0][1] == ('user@example.com', 'TenantA')
        mock_invalidate.assert_called_with('user@example.com', 'TenantA')
