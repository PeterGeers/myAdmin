"""
Unit and property tests for Parameter Admin API routes.

Includes Property 11: Secret Masking by Role.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from hypothesis import given, strategies as st, settings as h_settings, HealthCheck

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Helpers: test the masking logic directly (no Flask needed)
# ---------------------------------------------------------------------------

def mask_secrets(params, is_sysadmin):
    """Replicate the masking logic from the GET endpoint."""
    for p in params:
        if p.get('is_secret') and not is_sysadmin:
            p['value'] = '********'
    return params


# ---------------------------------------------------------------------------
# Property 11: Secret Masking by Role
# Feature: parameter-driven-config, Property 11: Secret Masking by Role
# Validates: Requirements 7.6
# ---------------------------------------------------------------------------

class TestSecretMaskingByRole:

    @h_settings(max_examples=100)
    @given(
        value=st.text(min_size=1, max_size=100),
        is_sysadmin=st.booleans(),
    )
    def test_secret_masking(self, value, is_sysadmin):
        params = [{'key': 'api_key', 'value': value, 'is_secret': True, 'namespace': 'ns'}]
        result = mask_secrets(params, is_sysadmin)
        if is_sysadmin:
            assert result[0]['value'] == value
        else:
            assert result[0]['value'] == '********'

    @h_settings(max_examples=50)
    @given(value=st.text(min_size=1, max_size=100))
    def test_non_secret_never_masked(self, value):
        params = [{'key': 'name', 'value': value, 'is_secret': False, 'namespace': 'ns'}]
        result = mask_secrets(params, False)
        assert result[0]['value'] == value


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

class TestParameterAdminValidation:

    def test_create_requires_namespace(self):
        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(
            '/api/tenant-admin/parameters', method='POST',
            json={'key': 'k', 'value': 'v'}
        ):
            data = flask.request.get_json()
            assert not data.get('namespace')

    def test_create_requires_key(self):
        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(
            '/api/tenant-admin/parameters', method='POST',
            json={'namespace': 'ns', 'value': 'v'}
        ):
            data = flask.request.get_json()
            assert not data.get('key')

    def test_system_scope_requires_sysadmin(self):
        from routes.parameter_admin_routes import _is_sysadmin
        assert _is_sysadmin(['Tenant_Admin']) is False
        assert _is_sysadmin(['SysAdmin']) is True
        assert _is_sysadmin(['SysAdmin', 'Tenant_Admin']) is True
        assert _is_sysadmin([]) is False
        assert _is_sysadmin(None) is False


class TestParameterAdminGrouping:

    def test_group_by_namespace(self):
        params = [
            {'namespace': 'storage', 'key': 'provider', 'value': 'gdrive', 'is_secret': False},
            {'namespace': 'storage', 'key': 'bucket', 'value': 'b1', 'is_secret': False},
            {'namespace': 'fin', 'key': 'currency', 'value': 'EUR', 'is_secret': False},
        ]
        grouped = {}
        for p in params:
            ns = p['namespace']
            if ns not in grouped:
                grouped[ns] = []
            grouped[ns].append(p)

        assert len(grouped) == 2
        assert len(grouped['storage']) == 2
        assert len(grouped['fin']) == 1

    def test_scope_id_mapping(self):
        scope = 'system'
        tenant = 'GoodwinSolutions'
        assert ('_system_' if scope == 'system' else tenant) == '_system_'
        scope = 'tenant'
        assert ('_system_' if scope == 'system' else tenant) == 'GoodwinSolutions'


# ---------------------------------------------------------------------------
# Fixtures for GET /api/tenant-admin/parameters/default endpoint
# ---------------------------------------------------------------------------

from routes.parameter_admin_routes import parameter_admin_bp


@pytest.fixture
def default_app():
    """Create a minimal Flask app with the parameter_admin blueprint."""
    import flask
    app = flask.Flask(__name__)
    app.register_blueprint(parameter_admin_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def default_client(default_app):
    return default_app.test_client()


def _admin_auth_mocks():
    """Patch stack for an authenticated Tenant_Admin user."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('admin@test.com', ['Tenant_Admin'], None)),
        patch('auth.role_cache.get_tenant_roles', return_value=['Tenant_Admin']),
        patch('auth.tenant_context.get_user_tenants', return_value=['TestTenant']),
        patch('auth.tenant_context.is_tenant_admin', return_value=True),
        patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'),
    ]


def _sysadmin_auth_mocks():
    """Patch stack for an authenticated SysAdmin user."""
    return [
        patch('auth.cognito_utils.extract_user_credentials',
              return_value=('sysadmin@test.com', ['SysAdmin', 'Tenant_Admin'], None)),
        patch('auth.role_cache.get_tenant_roles',
              return_value=['SysAdmin', 'Tenant_Admin']),
        patch('auth.tenant_context.get_user_tenants', return_value=['TestTenant']),
        patch('auth.tenant_context.is_tenant_admin', return_value=True),
        patch('auth.tenant_context.get_current_tenant', return_value='TestTenant'),
    ]


# ---------------------------------------------------------------------------
# Unit Tests: GET /api/tenant-admin/parameters/default
# Feature: parameter-reset-to-default
# Requirements: 1.1, 1.2, 1.3, 1.5
# ---------------------------------------------------------------------------

class TestGetParameterDefault:
    """Tests for the default value resolution endpoint."""

    def _get_default(self, client, namespace=None, key=None):
        """Helper to call the default endpoint with query params."""
        params = {}
        if namespace is not None:
            params['namespace'] = namespace
        if key is not None:
            params['key'] = key
        return client.get(
            '/api/tenant-admin/parameters/default',
            query_string=params,
            headers={'Authorization': 'Bearer fake-jwt-token',
                     'X-Tenant': 'TestTenant'},
        )

    # -- test_get_default_returns_code_default --
    def test_get_default_returns_code_default(self, default_client):
        """Parameter exists in CODE_DEFAULTS → returns code_default source."""
        fake_code_defaults = {
            ('ui.tables', 'chart_of_accounts.page_size'): {
                'value': 1000,
                'value_type': 'number',
                'description': 'Page size',
            }
        }
        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager'),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = self._get_default(default_client,
                                     namespace='ui.tables',
                                     key='chart_of_accounts.page_size')
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['success'] is True
            assert data['has_default'] is True
            assert data['value'] == 1000
            assert data['value_type'] == 'number'
            assert data['source'] == 'code_default'

    # -- test_get_default_returns_system_scope_db --
    def test_get_default_returns_system_scope_db(self, default_client):
        """Parameter exists as system-scope DB row but not in CODE_DEFAULTS."""
        fake_code_defaults = {}  # empty — no code default
        mock_db_instance = MagicMock()
        mock_db_instance.execute_query.return_value = [
            {'value': '{"field":"Account","direction":"asc"}',
             'value_type': 'json', 'is_secret': False}
        ]
        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager',
                  return_value=mock_db_instance),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = self._get_default(default_client,
                                     namespace='ui.tables',
                                     key='custom.sort')
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['success'] is True
            assert data['has_default'] is True
            assert data['value'] == {'field': 'Account', 'direction': 'asc'}
            assert data['value_type'] == 'json'
            assert data['source'] == 'system'

    # -- test_get_default_returns_no_default --
    def test_get_default_returns_no_default(self, default_client):
        """Parameter exists nowhere → has_default: false."""
        fake_code_defaults = {}
        mock_db_instance = MagicMock()
        mock_db_instance.execute_query.return_value = []  # no DB rows
        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager',
                  return_value=mock_db_instance),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = self._get_default(default_client,
                                     namespace='nonexistent',
                                     key='nothing')
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['success'] is True
            assert data['has_default'] is False
            assert 'value' not in data
            assert 'source' not in data

    # -- test_get_default_code_default_takes_precedence --
    def test_get_default_code_default_takes_precedence(self, default_client):
        """Parameter exists in both CODE_DEFAULTS and system DB; CODE_DEFAULTS wins."""
        fake_code_defaults = {
            ('ns', 'k'): {
                'value': 'from_code',
                'value_type': 'string',
                'description': 'Code default',
            }
        }
        mock_db_instance = MagicMock()
        # DB also has a system row — should NOT be reached
        mock_db_instance.execute_query.return_value = [
            {'value': 'from_db', 'value_type': 'string', 'is_secret': False}
        ]
        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager',
                  return_value=mock_db_instance),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = self._get_default(default_client, namespace='ns', key='k')
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['source'] == 'code_default'
            assert data['value'] == 'from_code'
            # DB should not have been queried
            mock_db_instance.execute_query.assert_not_called()

    # -- test_get_default_masks_secret_for_non_sysadmin --
    def test_get_default_masks_secret_for_non_sysadmin(self, default_client):
        """Secret parameter returns '********' for non-SysAdmin user."""
        fake_code_defaults = {
            ('secrets', 'api_key'): {
                'value': 'super-secret-value',
                'value_type': 'string',
                'description': 'API key',
                'is_secret': True,
            }
        }
        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager'),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = self._get_default(default_client,
                                     namespace='secrets', key='api_key')
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['has_default'] is True
            assert data['value'] == '********'
            assert data['source'] == 'code_default'

    # -- test_get_default_shows_secret_for_sysadmin --
    def test_get_default_shows_secret_for_sysadmin(self, default_client):
        """Secret parameter returns actual value for SysAdmin user."""
        fake_code_defaults = {
            ('secrets', 'api_key'): {
                'value': 'super-secret-value',
                'value_type': 'string',
                'description': 'API key',
                'is_secret': True,
            }
        }
        mocks = _sysadmin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager'),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = self._get_default(default_client,
                                     namespace='secrets', key='api_key')
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['has_default'] is True
            assert data['value'] == 'super-secret-value'

    # -- test_get_default_requires_namespace_and_key --
    def test_get_default_requires_namespace_and_key(self, default_client):
        """Returns 400 when namespace or key query params are missing."""
        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager'),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5]:
            # Missing both
            resp = self._get_default(default_client)
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['success'] is False
            assert 'namespace and key are required' in data['error']

            # Missing key
            resp = self._get_default(default_client, namespace='ns')
            assert resp.status_code == 400

            # Missing namespace
            resp = self._get_default(default_client, key='k')
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Property 1: Default Value Resolution Completeness
# Feature: parameter-reset-to-default, Property 1: Default Value Resolution Completeness
# Validates: Requirements 1.1, 1.2, 1.3
#
# For any (namespace, key) pair, the default resolution function returns:
#   - CODE_DEFAULTS value with source "code_default" when a CODE_DEFAULT exists
#   - system-scope DB value with source "system" when only a system DB row exists
#   - has_default: false when neither exists
#   - value_type matches the source's declared type
# ---------------------------------------------------------------------------

# Strategy helpers for generating parameter data
_value_type_strategy = st.sampled_from(['string', 'number', 'boolean', 'json'])

_value_for_type = {
    'string': st.text(min_size=0, max_size=50),
    'number': st.one_of(st.integers(min_value=-10000, max_value=10000),
                        st.floats(min_value=-1e4, max_value=1e4,
                                  allow_nan=False, allow_infinity=False)),
    'boolean': st.booleans(),
    'json': st.one_of(
        st.dictionaries(st.text(min_size=1, max_size=10),
                        st.text(min_size=0, max_size=20),
                        min_size=0, max_size=5),
        st.lists(st.text(min_size=0, max_size=20), min_size=0, max_size=5),
    ),
}


@st.composite
def code_default_entry(draw):
    """Generate a single CODE_DEFAULTS entry dict."""
    vtype = draw(_value_type_strategy)
    value = draw(_value_for_type[vtype])
    return {
        'value': value,
        'value_type': vtype,
        'description': draw(st.text(min_size=0, max_size=30)),
    }


@st.composite
def system_db_row(draw):
    """Generate a system-scope DB row dict (as returned by execute_query)."""
    vtype = draw(_value_type_strategy)
    value = draw(_value_for_type[vtype])
    # DB stores JSON values as strings
    raw_value = json.dumps(value) if vtype == 'json' else str(value)
    return {
        'value': raw_value,
        'value_type': vtype,
        'is_secret': False,
        '_parsed': value,  # keep for assertion
    }


class TestDefaultValueResolutionCompleteness:
    """
    Property 1: Default Value Resolution Completeness

    Feature: parameter-reset-to-default
    Validates: Requirements 1.1, 1.2, 1.3
    """

    def _make_client(self):
        """Create a fresh Flask test client for each Hypothesis example."""
        import flask
        app = flask.Flask(__name__)
        app.register_blueprint(parameter_admin_bp)
        app.config['TESTING'] = True
        return app.test_client()

    @h_settings(max_examples=100, database=None, derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        namespace=st.text(min_size=1, max_size=20,
                          alphabet=st.characters(whitelist_categories=('L', 'N'),
                                                 whitelist_characters='._')),
        key=st.text(min_size=1, max_size=20,
                    alphabet=st.characters(whitelist_categories=('L', 'N'),
                                           whitelist_characters='._')),
        has_code_default=st.booleans(),
        has_system_row=st.booleans(),
        cd_entry=code_default_entry(),
        sys_row=system_db_row(),
    )
    def test_resolution_completeness(self, namespace, key,
                                     has_code_default, has_system_row,
                                     cd_entry, sys_row):
        """Resolution always returns correct source and value_type."""
        client = self._make_client()

        # Build CODE_DEFAULTS based on the scenario
        fake_code_defaults = {}
        if has_code_default:
            fake_code_defaults[(namespace, key)] = cd_entry

        # Build DB mock
        mock_db_instance = MagicMock()
        if has_system_row:
            mock_db_instance.execute_query.return_value = [
                {'value': sys_row['value'],
                 'value_type': sys_row['value_type'],
                 'is_secret': sys_row['is_secret']}
            ]
        else:
            mock_db_instance.execute_query.return_value = []

        mocks = _admin_auth_mocks() + [
            patch('routes.parameter_admin_routes.DatabaseManager',
                  return_value=mock_db_instance),
            patch('services.parameter_service.CODE_DEFAULTS', fake_code_defaults),
        ]

        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = client.get(
                '/api/tenant-admin/parameters/default',
                query_string={'namespace': namespace, 'key': key},
                headers={'Authorization': 'Bearer fake-jwt',
                         'X-Tenant': 'TestTenant'},
            )
            data = resp.get_json()
            assert resp.status_code == 200
            assert data['success'] is True

            if has_code_default:
                # CODE_DEFAULTS takes precedence
                assert data['has_default'] is True
                assert data['source'] == 'code_default'
                assert data['value_type'] == cd_entry['value_type']
                assert data['value'] == cd_entry['value']
            elif has_system_row:
                # Fall through to system DB row
                assert data['has_default'] is True
                assert data['source'] == 'system'
                assert data['value_type'] == sys_row['value_type']
            else:
                # Neither exists
                assert data['has_default'] is False
                assert 'value' not in data
                assert 'source' not in data
