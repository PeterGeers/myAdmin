"""
API tests for SysAdmin Pivot Data Source Management Routes.

Tests GET /api/sysadmin/pivot/datasources and PUT /api/sysadmin/pivot/datasources.
Requirements: 11.1, 11.3, 11.4, 11.8, 11.9
"""
import pytest
import json
import sys
import os
from unittest.mock import Mock, patch, call
from flask import Flask
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────

def _passthrough_cognito_sysadmin(required_roles=None, required_permissions=None):
    """Bypass cognito auth, inject SysAdmin user."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'sysadmin@myadmin.com'
            kwargs['user_roles'] = ['SysAdmin']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_cognito_regular(required_roles=None, required_permissions=None):
    """Bypass cognito auth, inject regular (non-sysadmin) user."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'user@example.com'
            kwargs['user_roles'] = ['Finance_Read']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant(allow_sysadmin=False):
    """Bypass tenant auth, inject tenant context."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _blocking_tenant_for_non_sysadmin(allow_sysadmin=False):
    """Simulate tenant_required that blocks non-sysadmin when allow_sysadmin=True."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_roles = kwargs.get('user_roles', [])
            if allow_sysadmin and 'SysAdmin' not in user_roles:
                from flask import jsonify
                return jsonify({'error': 'Insufficient permissions',
                                'details': 'Required roles: SysAdmin'}), 403
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Shared mock data ────────────────────────────────────────

MOCK_TABLES = [
    {'name': 'vw_mutaties', 'type': 'VIEW'},
    {'name': 'vw_bnb_total', 'type': 'VIEW'},
    {'name': 'mutaties', 'type': 'BASE TABLE'},
]


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return Mock()


@pytest.fixture
def mock_param_service():
    return Mock()


@pytest.fixture
def sysadmin_client(mock_db, mock_param_service):
    """Client with SysAdmin auth — routes accept requests."""
    with patch('auth.cognito_utils.cognito_required',
               side_effect=_passthrough_cognito_sysadmin), \
         patch('auth.tenant_context.tenant_required',
               side_effect=_passthrough_tenant):
        import importlib
        import routes.sysadmin_pivot_routes as spr
        importlib.reload(spr)
        spr._get_db = lambda: mock_db
        spr._get_param_service = lambda db=None: mock_param_service
        spr._get_all_tables = lambda db: list(MOCK_TABLES)

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(spr.sysadmin_pivot_bp, url_prefix='/api/sysadmin/pivot')
        yield app.test_client()


@pytest.fixture
def non_sysadmin_client():
    """Client with regular user auth — routes should reject with 403."""
    with patch('auth.cognito_utils.cognito_required',
               side_effect=_passthrough_cognito_regular), \
         patch('auth.tenant_context.tenant_required',
               side_effect=_blocking_tenant_for_non_sysadmin):
        import importlib
        import routes.sysadmin_pivot_routes as spr
        importlib.reload(spr)

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(spr.sysadmin_pivot_bp, url_prefix='/api/sysadmin/pivot')
        yield app.test_client()


# ── Auth enforcement tests ──────────────────────────────────

@pytest.mark.api
class TestSysadminAuthEnforcement:
    """Validates: Requirement 11.8 — only SysAdmin role can access."""

    def test_get_datasources_non_sysadmin_returns_403(self, non_sysadmin_client):
        resp = non_sysadmin_client.get('/api/sysadmin/pivot/datasources')
        assert resp.status_code == 403

    def test_put_datasources_non_sysadmin_returns_403(self, non_sysadmin_client):
        resp = non_sysadmin_client.put(
            '/api/sysadmin/pivot/datasources',
            data=json.dumps({'sources': []}),
            content_type='application/json',
        )
        assert resp.status_code == 403


# ── GET /datasources tests ──────────────────────────────────

@pytest.mark.api
class TestGetDatasources:
    """Validates: Requirements 11.1, 11.3"""

    def test_returns_all_tables_with_pivot_status(
        self, sysadmin_client, mock_param_service
    ):
        mock_param_service.get_param.side_effect = lambda namespace, key, **kw: {
            'registered_sources': ['vw_mutaties'],
            'datasource_module.vw_mutaties': 'FIN',
            'datasource_label.vw_mutaties': 'Financial Transactions',
        }.get(key)

        resp = sysadmin_client.get('/api/sysadmin/pivot/datasources')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 3

        by_name = {d['name']: d for d in data['data']}
        assert by_name['vw_mutaties']['pivot_enabled'] is True
        assert by_name['vw_mutaties']['module'] == 'FIN'
        assert by_name['vw_mutaties']['label'] == 'Financial Transactions'
        assert by_name['vw_bnb_total']['pivot_enabled'] is False
        assert by_name['mutaties']['pivot_enabled'] is False

    def test_returns_all_tables_with_no_registered_sources(
        self, sysadmin_client, mock_param_service
    ):
        # No registered sources — all tables should have pivot_enabled=False
        mock_param_service.get_param.return_value = None

        resp = sysadmin_client.get('/api/sysadmin/pivot/datasources')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 3
        for item in data['data']:
            assert item['pivot_enabled'] is False
            assert item['module'] is None
            assert item['label'] is None


# ── PUT /datasources tests ──────────────────────────────────

@pytest.mark.api
class TestPutDatasources:
    """Validates: Requirements 11.3, 11.4, 11.8, 11.9"""

    def test_missing_sources_returns_400(self, sysadmin_client):
        resp = sysadmin_client.put(
            '/api/sysadmin/pivot/datasources',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'sources' in resp.get_json()['error'].lower()

    def test_invalid_source_name_returns_400(
        self, sysadmin_client, mock_param_service
    ):
        mock_param_service.get_param.return_value = []

        resp = sysadmin_client.put(
            '/api/sysadmin/pivot/datasources',
            data=json.dumps({
                'sources': [{'name': 'nonexistent_table', 'pivot_enabled': True}]
            }),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'nonexistent_table' in resp.get_json()['error']

    def test_invalid_module_returns_400(
        self, sysadmin_client, mock_param_service
    ):
        mock_param_service.get_param.return_value = []

        resp = sysadmin_client.put(
            '/api/sysadmin/pivot/datasources',
            data=json.dumps({
                'sources': [{
                    'name': 'vw_mutaties',
                    'pivot_enabled': True,
                    'module': 'INVALID',
                }]
            }),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'INVALID' in resp.get_json()['error']

    def test_successful_enable_sources(
        self, sysadmin_client, mock_param_service
    ):
        # Previously no sources registered
        mock_param_service.get_param.return_value = []

        with patch('routes.sysadmin_pivot_routes._auto_create_defaults') as mock_auto:
            resp = sysadmin_client.put(
                '/api/sysadmin/pivot/datasources',
                data=json.dumps({
                    'sources': [
                        {'name': 'vw_mutaties', 'pivot_enabled': True,
                         'module': 'FIN', 'label': 'Financial Transactions'},
                        {'name': 'vw_bnb_total', 'pivot_enabled': True,
                         'module': 'STR', 'label': 'STR Revenue'},
                    ]
                }),
                content_type='application/json',
            )

        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

        # Verify registered_sources was written at system scope
        set_calls = mock_param_service.set_param.call_args_list
        reg_call = [c for c in set_calls
                    if c[1].get('key') == 'registered_sources'
                    or (c[0] and len(c[0]) > 3 and c[0][3] == 'registered_sources')]
        assert len(reg_call) >= 1

    def test_auto_creates_defaults_for_new_sources(
        self, sysadmin_client, mock_db, mock_param_service
    ):
        # No previously registered sources
        mock_param_service.get_param.return_value = []

        with patch('routes.sysadmin_pivot_routes._auto_create_defaults') as mock_auto:
            resp = sysadmin_client.put(
                '/api/sysadmin/pivot/datasources',
                data=json.dumps({
                    'sources': [
                        {'name': 'vw_mutaties', 'pivot_enabled': True,
                         'module': 'FIN', 'label': 'Financial Transactions'},
                    ]
                }),
                content_type='application/json',
            )

        assert resp.status_code == 200
        # _auto_create_defaults should be called for the newly enabled source
        mock_auto.assert_called_once()
        args = mock_auto.call_args[0]
        assert args[2] == 'vw_mutaties'  # source_name
        assert args[3] == 'sysadmin@myadmin.com'  # created_by

    def test_disables_source_cleans_up_params(
        self, sysadmin_client, mock_param_service
    ):
        # Previously had vw_mutaties registered
        def get_param_side_effect(namespace, key, **kw):
            if key == 'registered_sources':
                return ['vw_mutaties']
            return None
        mock_param_service.get_param.side_effect = get_param_side_effect

        with patch('routes.sysadmin_pivot_routes._auto_create_defaults'):
            resp = sysadmin_client.put(
                '/api/sysadmin/pivot/datasources',
                data=json.dumps({
                    'sources': [
                        {'name': 'vw_bnb_total', 'pivot_enabled': True,
                         'module': 'STR', 'label': 'STR Revenue'},
                    ]
                }),
                content_type='application/json',
            )

        assert resp.status_code == 200
        # Verify delete_param was called for the disabled source's module/label
        delete_calls = mock_param_service.delete_param.call_args_list
        deleted_keys = [c[0][3] for c in delete_calls]
        assert 'datasource_module.vw_mutaties' in deleted_keys
        assert 'datasource_label.vw_mutaties' in deleted_keys


# ── _auto_create_defaults integration test ───────────────────

@pytest.mark.api
class TestAutoCreateDefaults:
    """Validates: Requirement 11.9 — auto-create exclude/force_groupable."""

    def test_auto_create_writes_exclude_and_force_groupable(self):
        """Test _auto_create_defaults writes default params for a new source."""
        mock_db = Mock()
        mock_ps = Mock()
        # No existing values
        mock_ps.get_param.return_value = None

        with patch('routes.sysadmin_pivot_routes.derive_columns_from_schema') as mock_derive:
            mock_derive.return_value = (
                ['channel', 'listing'],   # groupable
                ['amountGross', 'year'],   # aggregatable
                {'channel': 'varchar', 'listing': 'varchar',
                 'amountGross': 'decimal', 'year': 'int'},
            )

            from routes.sysadmin_pivot_routes import _auto_create_defaults
            _auto_create_defaults(mock_db, mock_ps, 'vw_bnb_total', 'admin@test.com')

        set_calls = mock_ps.set_param.call_args_list
        keys_written = [c[1]['key'] for c in set_calls]
        assert 'exclude_columns.vw_bnb_total' in keys_written
        assert 'force_groupable.vw_bnb_total' in keys_written

        # exclude_columns should be empty list by default
        exclude_call = [c for c in set_calls
                        if c[1]['key'] == 'exclude_columns.vw_bnb_total'][0]
        assert exclude_call[1]['value'] == []

    def test_auto_create_detects_category_hint_columns(self):
        """Numeric columns with category-like names go into force_groupable."""
        mock_db = Mock()
        mock_ps = Mock()
        mock_ps.get_param.return_value = None

        with patch('routes.sysadmin_pivot_routes.derive_columns_from_schema') as mock_derive:
            mock_derive.return_value = (
                ['channel'],                    # groupable
                ['amountGross', 'year', 'month'],  # aggregatable
                {'channel': 'varchar', 'amountGross': 'decimal',
                 'year': 'int', 'month': 'int'},
            )

            from routes.sysadmin_pivot_routes import _auto_create_defaults
            _auto_create_defaults(mock_db, mock_ps, 'test_view', 'admin@test.com')

        fg_call = [c for c in mock_ps.set_param.call_args_list
                   if c[1]['key'] == 'force_groupable.test_view'][0]
        fg_value = fg_call[1]['value']
        assert 'year' in fg_value
        assert 'month' in fg_value
        assert 'amountGross' not in fg_value

    def test_auto_create_skips_existing_values(self):
        """Don't overwrite manually configured exclude/force_groupable."""
        mock_db = Mock()
        mock_ps = Mock()
        # Existing values present
        mock_ps.get_param.return_value = ['some_existing_value']

        with patch('routes.sysadmin_pivot_routes.derive_columns_from_schema') as mock_derive:
            mock_derive.return_value = ([], ['Amount'], {'Amount': 'decimal'})

            from routes.sysadmin_pivot_routes import _auto_create_defaults
            _auto_create_defaults(mock_db, mock_ps, 'vw_test', 'admin@test.com')

        # set_param should NOT be called since values already exist
        mock_ps.set_param.assert_not_called()
