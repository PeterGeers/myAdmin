"""
API tests for Pivot Routes: execute, columns, sources, model CRUD, export.
Requirements: 3.9, 4.4, 6.5, 9.10
"""
import pytest
import json
import sys
import os
from unittest.mock import Mock, patch
from flask import Flask
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────

def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['Reports_Read', 'Reports_Export']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_pivot_service():
    return Mock()


@pytest.fixture
def mock_model_store():
    return Mock()


@pytest.fixture
def pivot_client(mock_pivot_service, mock_model_store):
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
        import importlib
        import routes.pivot_routes as pr
        importlib.reload(pr)
        pr._get_service = lambda: mock_pivot_service
        pr._get_store = lambda: mock_model_store
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(pr.pivot_bp)
        yield app.test_client()

@pytest.fixture
def valid_definition():
    return {
        'data_source': 'vw_mutaties',
        'group_columns': ['Aangifte', 'jaar'],
        'aggregate_measures': [{'function': 'SUM', 'column': 'Amount'}],
        'filters': {'years': [2024, 2025]},
        'column_pivot': None,
        'column_nest_levels': [],
        'display_mode': 'hierarchical',
    }

@pytest.fixture
def pivot_execute_result():
    return {
        'success': True,
        'data': [
            {'Aangifte': 'BTW', 'jaar': 2024, 'SUM_Amount': 12345.67, 'COUNT': 42},
        ],
        'columns': [
            {'name': 'Aangifte', 'type': 'group', 'dataType': 'varchar'},
            {'name': 'jaar', 'type': 'group', 'dataType': 'int'},
            {'name': 'SUM_Amount', 'type': 'aggregate', 'function': 'SUM',
             'sourceColumn': 'Amount', 'dataType': 'decimal'},
        ],
        'row_count': 1,
    }


# ── Execute pivot tests ─────────────────────────────────────

@pytest.mark.api
class TestExecutePivot:

    def test_successful_execution_returns_200(
        self, pivot_client, mock_pivot_service, pivot_execute_result
    ):
        mock_pivot_service.execute_pivot.return_value = pivot_execute_result
        resp = pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({'data_source': 'vw_mutaties', 'group_columns': ['Aangifte']}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 1

    def test_missing_body_returns_400(self, pivot_client):
        resp = pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'Request body required' in resp.get_json()['error']

    def test_missing_columns_value_error_returns_400(
        self, pivot_client, mock_pivot_service
    ):
        mock_pivot_service.execute_pivot.side_effect = ValueError(
            'At least one group column and one aggregate measure are required'
        )
        resp = pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({'data_source': 'vw_mutaties'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'group column' in resp.get_json()['error']

    def test_disallowed_column_value_error_returns_400(
        self, pivot_client, mock_pivot_service
    ):
        mock_pivot_service.execute_pivot.side_effect = ValueError(
            "Column 'secret' is not allowed for data source 'vw_mutaties'"
        )
        resp = pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({'data_source': 'vw_mutaties', 'group_columns': ['secret']}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'not allowed' in resp.get_json()['error']

    def test_runtime_error_returns_500(self, pivot_client, mock_pivot_service):
        mock_pivot_service.execute_pivot.side_effect = RuntimeError(
            'Query execution failed. Please check your configuration.'
        )
        resp = pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({'data_source': 'vw_mutaties', 'group_columns': ['Aangifte']}),
            content_type='application/json',
        )
        assert resp.status_code == 500
        assert 'execution failed' in resp.get_json()['error']

    def test_tenant_passed_to_service(self, pivot_client, mock_pivot_service, pivot_execute_result):
        mock_pivot_service.execute_pivot.return_value = pivot_execute_result
        pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({'data_source': 'vw_mutaties'}),
            content_type='application/json',
        )
        call_args = mock_pivot_service.execute_pivot.call_args
        assert call_args[0][0] == 'TestTenant'
        assert call_args[0][1] == ['TestTenant']


# ── Column discovery tests ──────────────────────────────────

@pytest.mark.api
class TestColumnDiscovery:

    def test_get_columns_returns_groupable_and_aggregatable(
        self, pivot_client, mock_pivot_service
    ):
        mock_pivot_service.get_available_columns.return_value = {
            'groupable': ['Aangifte', 'jaar'],
            'aggregatable': ['Amount'],
        }
        resp = pivot_client.get('/api/pivot/columns/vw_mutaties')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'groupable' in data
        assert 'aggregatable' in data

    def test_unknown_source_returns_400(self, pivot_client, mock_pivot_service):
        mock_pivot_service.get_available_columns.side_effect = ValueError(
            "Unknown data source 'nonexistent'"
        )
        resp = pivot_client.get('/api/pivot/columns/nonexistent')
        assert resp.status_code == 400
        assert 'Unknown' in resp.get_json()['error']

    def test_tenant_passed_to_column_service(self, pivot_client, mock_pivot_service):
        mock_pivot_service.get_available_columns.return_value = {
            'groupable': [], 'aggregatable': [],
        }
        pivot_client.get('/api/pivot/columns/vw_mutaties')
        call_args = mock_pivot_service.get_available_columns.call_args
        assert call_args[0][1] == 'TestTenant'


# ── Sources discovery tests ─────────────────────────────────

@pytest.mark.api
class TestSourcesDiscovery:

    def test_get_sources_returns_list(self, pivot_client, mock_pivot_service):
        mock_pivot_service.get_registered_sources.return_value = [
            {'name': 'vw_mutaties', 'label': 'Financial Transactions'},
        ]
        resp = pivot_client.get('/api/pivot/sources')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 1
        assert data['data'][0]['name'] == 'vw_mutaties'


# ── Model CRUD tests ────────────────────────────────────────

@pytest.mark.api
class TestModelCRUD:

    def test_list_models_returns_200(self, pivot_client, mock_model_store):
        mock_model_store.list_models.return_value = [
            {'id': 1, 'name': 'My Model', 'data_source': 'vw_mutaties',
             'created_by': 'test@example.com', 'created_at': '2024-01-01'},
        ]
        resp = pivot_client.get('/api/pivot/models')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 1

    def test_save_model_valid_returns_201(
        self, pivot_client, mock_model_store, valid_definition
    ):
        mock_model_store.save_model.return_value = {'success': True, 'id': 1}
        resp = pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({'name': 'Test Model', 'definition': valid_definition}),
            content_type='application/json',
        )
        assert resp.status_code == 201
        assert resp.get_json()['success'] is True
        assert resp.get_json()['id'] == 1

    def test_save_model_duplicate_name_returns_409(
        self, pivot_client, mock_model_store, valid_definition
    ):
        mock_model_store.save_model.side_effect = ValueError(
            "A model with name 'Test Model' already exists"
        )
        resp = pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({'name': 'Test Model', 'definition': valid_definition}),
            content_type='application/json',
        )
        assert resp.status_code == 409
        assert 'already exists' in resp.get_json()['error']

    def test_save_model_missing_name_returns_400(
        self, pivot_client, valid_definition
    ):
        resp = pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({'definition': valid_definition}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'name' in resp.get_json()['error'].lower()

    def test_save_model_missing_definition_returns_400(self, pivot_client):
        resp = pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({'name': 'Test Model'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'definition' in resp.get_json()['error'].lower()

    def test_save_model_invalid_definition_returns_400(
        self, pivot_client, mock_model_store
    ):
        mock_model_store.save_model.side_effect = ValueError(
            "Invalid model definition: missing required field 'data_source'"
        )
        resp = pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({'name': 'Bad', 'definition': {'group_columns': []}}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'Invalid' in resp.get_json()['error']

    def test_save_model_no_body_returns_400(self, pivot_client):
        resp = pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_load_model_returns_200(self, pivot_client, mock_model_store, valid_definition):
        mock_model_store.load_model.return_value = {
            'id': 1, 'name': 'My Model', 'data_source': 'vw_mutaties',
            'definition': valid_definition,
            'created_by': 'test@example.com', 'created_at': '2024-01-01',
            'updated_at': None,
        }
        resp = pivot_client.get('/api/pivot/models/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['name'] == 'My Model'

    def test_load_model_not_found_returns_404(self, pivot_client, mock_model_store):
        mock_model_store.load_model.side_effect = ValueError('Pivot model not found')
        resp = pivot_client.get('/api/pivot/models/999')
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_update_model_returns_200(
        self, pivot_client, mock_model_store, valid_definition
    ):
        mock_model_store.update_model.return_value = {'success': True}
        resp = pivot_client.put(
            '/api/pivot/models/1',
            data=json.dumps({'definition': valid_definition}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_update_model_not_found_returns_404(
        self, pivot_client, mock_model_store, valid_definition
    ):
        mock_model_store.update_model.side_effect = ValueError('Pivot model not found')
        resp = pivot_client.put(
            '/api/pivot/models/1',
            data=json.dumps({'definition': valid_definition}),
            content_type='application/json',
        )
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_update_model_missing_definition_returns_400(self, pivot_client):
        resp = pivot_client.put(
            '/api/pivot/models/1',
            data=json.dumps({'name': 'Updated'}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'definition' in resp.get_json()['error'].lower()

    def test_update_model_no_body_returns_400(self, pivot_client):
        resp = pivot_client.put(
            '/api/pivot/models/1',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_delete_model_returns_200(self, pivot_client, mock_model_store):
        mock_model_store.delete_model.return_value = True
        resp = pivot_client.delete('/api/pivot/models/1')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_delete_model_not_found_returns_404(self, pivot_client, mock_model_store):
        mock_model_store.delete_model.return_value = False
        resp = pivot_client.delete('/api/pivot/models/999')
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()


# ── Export tests ─────────────────────────────────────────────

@pytest.mark.api
class TestExport:

    def test_successful_export_returns_200(self, pivot_client, mock_pivot_service):
        mock_pivot_service.build_underlying_query.return_value = ('SELECT * FROM vw_mutaties WHERE 1=1', [])
        mock_pivot_service.db = Mock()
        mock_pivot_service.db.execute_query.return_value = [
            {'Aangifte': 'BTW', 'Amount': 100.0},
        ]
        resp = pivot_client.post(
            '/api/pivot/export',
            data=json.dumps({'data_source': 'vw_mutaties', 'filters': {}}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['row_count'] == 1

    def test_export_missing_body_returns_400(self, pivot_client):
        resp = pivot_client.post(
            '/api/pivot/export',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400
        assert 'Request body required' in resp.get_json()['error']

    def test_export_runtime_error_returns_500(self, pivot_client, mock_pivot_service):
        mock_pivot_service.build_underlying_query.return_value = ('SELECT ...', [])
        mock_pivot_service.db = Mock()
        mock_pivot_service.db.execute_query.side_effect = Exception('DB error')
        resp = pivot_client.post(
            '/api/pivot/export',
            data=json.dumps({'data_source': 'vw_mutaties'}),
            content_type='application/json',
        )
        assert resp.status_code == 500


# ── Tenant isolation tests ───────────────────────────────────

@pytest.mark.api
class TestTenantIsolation:

    def test_list_models_passes_tenant(self, pivot_client, mock_model_store):
        mock_model_store.list_models.return_value = []
        pivot_client.get('/api/pivot/models')
        mock_model_store.list_models.assert_called_once_with('TestTenant')

    def test_save_model_passes_tenant_and_email(
        self, pivot_client, mock_model_store, valid_definition
    ):
        mock_model_store.save_model.return_value = {'success': True, 'id': 1}
        pivot_client.post(
            '/api/pivot/models',
            data=json.dumps({'name': 'M', 'definition': valid_definition}),
            content_type='application/json',
        )
        call_args = mock_model_store.save_model.call_args
        assert call_args[0][0] == 'TestTenant'
        assert call_args[0][1] == 'test@example.com'

    def test_load_model_passes_tenant(self, pivot_client, mock_model_store, valid_definition):
        mock_model_store.load_model.return_value = {
            'id': 1, 'name': 'M', 'data_source': 'vw_mutaties',
            'definition': valid_definition,
            'created_by': 'test@example.com', 'created_at': None, 'updated_at': None,
        }
        pivot_client.get('/api/pivot/models/1')
        mock_model_store.load_model.assert_called_once_with('TestTenant', 1)

    def test_update_model_passes_tenant(
        self, pivot_client, mock_model_store, valid_definition
    ):
        mock_model_store.update_model.return_value = {'success': True}
        pivot_client.put(
            '/api/pivot/models/1',
            data=json.dumps({'definition': valid_definition}),
            content_type='application/json',
        )
        call_args = mock_model_store.update_model.call_args
        assert call_args[0][0] == 'TestTenant'

    def test_delete_model_passes_tenant(self, pivot_client, mock_model_store):
        mock_model_store.delete_model.return_value = True
        pivot_client.delete('/api/pivot/models/1')
        mock_model_store.delete_model.assert_called_once_with('TestTenant', 1)

    def test_execute_passes_user_tenants(
        self, pivot_client, mock_pivot_service, pivot_execute_result
    ):
        mock_pivot_service.execute_pivot.return_value = pivot_execute_result
        pivot_client.post(
            '/api/pivot/execute',
            data=json.dumps({'data_source': 'vw_mutaties'}),
            content_type='application/json',
        )
        call_args = mock_pivot_service.execute_pivot.call_args
        assert call_args[0][1] == ['TestTenant']

    def test_export_passes_user_tenants(self, pivot_client, mock_pivot_service):
        mock_pivot_service.build_underlying_query.return_value = ('SELECT 1', [])
        mock_pivot_service.db = Mock()
        mock_pivot_service.db.execute_query.return_value = []
        pivot_client.post(
            '/api/pivot/export',
            data=json.dumps({'data_source': 'vw_mutaties'}),
            content_type='application/json',
        )
        call_args = mock_pivot_service.build_underlying_query.call_args
        assert call_args[0][1] == 'TestTenant'
