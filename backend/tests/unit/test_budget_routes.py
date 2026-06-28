"""
Unit tests for budget_routes.py

Tests all budget management endpoints:
- Budget version CRUD (list, create, status transition, activate, delete)
- Budget line CRUD (list, create, update, delete)
- Budget copy
- Budget dashboard
- AI routes (narrative, query, draft-suggestions, generate-lines)

Task 48 of Phase 7: Missing Test Coverage
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from functools import wraps

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ── Auth decorator mocks ───────────────────────────────────────────────────


def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['Finance_CRUD']
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


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_budget_service():
    """Mock BudgetService instance."""
    return MagicMock()


@pytest.fixture
def mock_budget_ai_service():
    """Mock BudgetAIService instance."""
    return MagicMock()


@pytest.fixture
def client(mock_budget_service, mock_budget_ai_service):
    """Create Flask test client with patched auth and services."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
        import importlib
        import routes.budget_routes as br
        importlib.reload(br)

        # Inject mock services
        br.budget_service = mock_budget_service
        br.budget_ai_service = mock_budget_ai_service

        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(br.budget_bp)

        with app.test_client() as c:
            with app.app_context():
                yield c


# ── Version CRUD ───────────────────────────────────────────────────────────


class TestBudgetVersionList:

    def test_list_versions_success(self, client, mock_budget_service):
        """GET /api/budget/versions returns versions."""
        mock_budget_service.list_versions.return_value = {
            'success': True, 'data': [{'id': 1, 'name': 'Budget 2025'}]
        }
        resp = client.get('/api/budget/versions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_list_versions_with_year_filter(self, client, mock_budget_service):
        """GET /api/budget/versions?year=2025 filters by year."""
        mock_budget_service.list_versions.return_value = {'success': True, 'data': []}
        resp = client.get('/api/budget/versions?year=2025')
        assert resp.status_code == 200
        mock_budget_service.list_versions.assert_called_with('TestTenant', year=2025)

    def test_list_versions_invalid_year(self, client):
        """GET /api/budget/versions?year=abc returns 400."""
        resp = client.get('/api/budget/versions?year=abc')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Invalid year' in data['error']


class TestBudgetVersionCreate:

    def test_create_version_success(self, client, mock_budget_service):
        """POST /api/budget/versions creates a new version."""
        mock_budget_service.create_version.return_value = {
            'success': True, 'data': {'id': 1, 'name': 'Budget 2026', 'status': 'Draft'}
        }
        resp = client.post(
            '/api/budget/versions',
            json={'name': 'Budget 2026', 'fiscal_year': 2026}
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True

    def test_create_version_missing_name(self, client):
        """POST /api/budget/versions without name returns 400."""
        resp = client.post(
            '/api/budget/versions',
            json={'fiscal_year': 2026}
        )
        assert resp.status_code == 400
        assert 'Name is required' in resp.get_json()['error']

    def test_create_version_missing_fiscal_year(self, client):
        """POST /api/budget/versions without fiscal_year returns 400."""
        resp = client.post(
            '/api/budget/versions',
            json={'name': 'Test'}
        )
        assert resp.status_code == 400
        assert 'Fiscal year is required' in resp.get_json()['error']

    def test_create_version_name_too_long(self, client):
        """POST /api/budget/versions with name > 100 chars returns 400."""
        resp = client.post(
            '/api/budget/versions',
            json={'name': 'x' * 101, 'fiscal_year': 2026}
        )
        assert resp.status_code == 400
        assert '100 characters' in resp.get_json()['error']

    def test_create_version_invalid_fiscal_year(self, client):
        """POST /api/budget/versions with invalid year returns 400."""
        resp = client.post(
            '/api/budget/versions',
            json={'name': 'Test', 'fiscal_year': 99}
        )
        assert resp.status_code == 400
        assert '4-digit year' in resp.get_json()['error']

    def test_create_version_no_body(self, client):
        """POST /api/budget/versions without body returns 400."""
        resp = client.post('/api/budget/versions', json={})
        assert resp.status_code == 400


class TestBudgetVersionStatus:

    def test_transition_status_success(self, client, mock_budget_service):
        """PUT /api/budget/versions/<id>/status transitions status."""
        mock_budget_service.transition_status.return_value = {
            'success': True, 'data': {'status': 'Approved'}
        }
        resp = client.put(
            '/api/budget/versions/1/status',
            json={'action': 'approve'}
        )
        assert resp.status_code == 200
        mock_budget_service.transition_status.assert_called_with('TestTenant', 1, 'approve')

    def test_transition_status_missing_action(self, client):
        """PUT /api/budget/versions/<id>/status without action returns 400."""
        resp = client.put('/api/budget/versions/1/status', json={'foo': 'bar'})
        assert resp.status_code == 400
        assert 'Action is required' in resp.get_json()['error']

    def test_transition_status_service_failure(self, client, mock_budget_service):
        """PUT /api/budget/versions/<id>/status returns 400 on service failure."""
        mock_budget_service.transition_status.return_value = {
            'success': False, 'error': 'Invalid transition'
        }
        resp = client.put('/api/budget/versions/1/status', json={'action': 'approve'})
        assert resp.status_code == 400


class TestBudgetVersionActivate:

    def test_activate_version_success(self, client, mock_budget_service):
        """PUT /api/budget/versions/<id>/activate toggles active flag."""
        mock_budget_service.activate_version.return_value = {
            'success': True, 'data': {'active': True}
        }
        resp = client.put('/api/budget/versions/1/activate', json={'active': True})
        assert resp.status_code == 200

    def test_activate_version_defaults_to_true(self, client, mock_budget_service):
        """PUT /api/budget/versions/<id>/activate defaults to active=True."""
        mock_budget_service.activate_version.return_value = {'success': True}
        resp = client.put('/api/budget/versions/1/activate', json={})
        assert resp.status_code == 200
        mock_budget_service.activate_version.assert_called_with('TestTenant', 1, active=True)


class TestBudgetVersionDelete:

    def test_delete_version_success(self, client, mock_budget_service):
        """DELETE /api/budget/versions/<id> deletes draft version."""
        mock_budget_service.delete_version.return_value = {'success': True}
        resp = client.delete('/api/budget/versions/1')
        assert resp.status_code == 200

    def test_delete_version_failure(self, client, mock_budget_service):
        """DELETE /api/budget/versions/<id> returns 400 on failure."""
        mock_budget_service.delete_version.return_value = {
            'success': False, 'error': 'Cannot delete approved version'
        }
        resp = client.delete('/api/budget/versions/1')
        assert resp.status_code == 400


# ── Budget Line CRUD ───────────────────────────────────────────────────────


class TestBudgetLineList:

    def test_list_lines_success(self, client, mock_budget_service):
        """GET /api/budget/versions/<id>/lines returns lines."""
        mock_budget_service.list_lines.return_value = {
            'success': True, 'data': [{'id': 1, 'account_code': '8000'}]
        }
        resp = client.get('/api/budget/versions/1/lines')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True


class TestBudgetLineCreate:

    def test_create_monthly_line_success(self, client, mock_budget_service):
        """POST /api/budget/versions/<id>/lines creates monthly line."""
        mock_budget_service.create_line.return_value = {'success': True, 'data': {'id': 1}}
        resp = client.post(
            '/api/budget/versions/1/lines',
            json={
                'account_code': '8000',
                'period_mode': 'Monthly',
                'amounts': [100.0] * 12
            }
        )
        assert resp.status_code == 201

    def test_create_annual_line_success(self, client, mock_budget_service):
        """POST /api/budget/versions/<id>/lines creates annual line."""
        mock_budget_service.create_line.return_value = {'success': True, 'data': {'id': 2}}
        resp = client.post(
            '/api/budget/versions/1/lines',
            json={
                'account_code': '4000',
                'period_mode': 'Annual',
                'annual_amount': 12000.0
            }
        )
        assert resp.status_code == 201

    def test_create_line_missing_account_code(self, client):
        """POST without account_code returns 400."""
        resp = client.post(
            '/api/budget/versions/1/lines',
            json={'period_mode': 'Monthly', 'amounts': [0] * 12}
        )
        assert resp.status_code == 400
        assert 'account_code is required' in resp.get_json()['error']

    def test_create_line_invalid_period_mode(self, client):
        """POST with invalid period_mode returns 400."""
        resp = client.post(
            '/api/budget/versions/1/lines',
            json={'account_code': '8000', 'period_mode': 'Weekly'}
        )
        assert resp.status_code == 400
        assert 'Monthly' in resp.get_json()['error']

    def test_create_monthly_line_wrong_amounts_length(self, client):
        """POST monthly with != 12 amounts returns 400."""
        resp = client.post(
            '/api/budget/versions/1/lines',
            json={'account_code': '8000', 'period_mode': 'Monthly', 'amounts': [100] * 6}
        )
        assert resp.status_code == 400
        assert '12' in resp.get_json()['error']

    def test_create_annual_line_missing_amount(self, client):
        """POST annual without annual_amount returns 400."""
        resp = client.post(
            '/api/budget/versions/1/lines',
            json={'account_code': '8000', 'period_mode': 'Annual'}
        )
        assert resp.status_code == 400
        assert 'annual_amount is required' in resp.get_json()['error']


class TestBudgetLineUpdate:

    def test_update_line_success(self, client, mock_budget_service):
        """PUT /api/budget/lines/<id> updates amounts."""
        mock_budget_service.update_line.return_value = {'success': True}
        resp = client.put(
            '/api/budget/lines/1',
            json={'amounts': [200.0] * 12}
        )
        assert resp.status_code == 200

    def test_update_line_no_body(self, client):
        """PUT /api/budget/lines/<id> with empty body returns 400."""
        # {} is falsy in Python so route returns 'Request body is required'
        resp = client.put('/api/budget/lines/1', json={})
        assert resp.status_code == 400
        assert 'Request body is required' in resp.get_json()['error']


class TestBudgetLineDelete:

    def test_delete_line_success(self, client, mock_budget_service):
        """DELETE /api/budget/lines/<id> deletes line."""
        mock_budget_service.delete_line.return_value = {'success': True}
        resp = client.delete('/api/budget/lines/1')
        assert resp.status_code == 200


# ── Copy ───────────────────────────────────────────────────────────────────


class TestBudgetCopy:

    def test_copy_success(self, client, mock_budget_service):
        """POST /api/budget/copy copies budget version."""
        mock_budget_service.copy_budget.return_value = {
            'success': True, 'data': {'id': 2}
        }
        resp = client.post(
            '/api/budget/copy',
            json={
                'source_version_id': 1,
                'target_fiscal_year': 2027,
                'version_name': 'Budget 2027'
            }
        )
        assert resp.status_code == 201

    def test_copy_missing_source(self, client):
        """POST /api/budget/copy without source_version_id returns 400."""
        resp = client.post(
            '/api/budget/copy',
            json={'target_fiscal_year': 2027, 'version_name': 'Test'}
        )
        assert resp.status_code == 400
        assert 'source_version_id is required' in resp.get_json()['error']

    def test_copy_missing_target_year(self, client):
        """POST /api/budget/copy without target_fiscal_year returns 400."""
        resp = client.post(
            '/api/budget/copy',
            json={'source_version_id': 1, 'version_name': 'Test'}
        )
        assert resp.status_code == 400

    def test_copy_name_too_long(self, client):
        """POST /api/budget/copy with name > 100 chars returns 400."""
        resp = client.post(
            '/api/budget/copy',
            json={'source_version_id': 1, 'target_fiscal_year': 2027, 'version_name': 'a' * 101}
        )
        assert resp.status_code == 400
        assert '100 characters' in resp.get_json()['error']


# ── Dashboard ──────────────────────────────────────────────────────────────


class TestBudgetDashboard:

    def test_dashboard_by_version_id(self, client, mock_budget_service):
        """GET /api/budget/dashboard?version_id=1 returns dashboard data."""
        mock_budget_service.get_dashboard.return_value = {
            'success': True, 'data': {'rows': []}
        }
        resp = client.get('/api/budget/dashboard?version_id=1')
        assert resp.status_code == 200

    def test_dashboard_by_year(self, client, mock_budget_service):
        """GET /api/budget/dashboard?year=2025 returns dashboard data."""
        mock_budget_service.get_dashboard.return_value = {
            'success': True, 'data': {'rows': []}
        }
        resp = client.get('/api/budget/dashboard?year=2025')
        assert resp.status_code == 200

    def test_dashboard_missing_params(self, client):
        """GET /api/budget/dashboard without version_id or year returns 400."""
        resp = client.get('/api/budget/dashboard')
        assert resp.status_code == 400
        assert 'Either version_id or year' in resp.get_json()['error']

    def test_dashboard_invalid_version_id(self, client):
        """GET /api/budget/dashboard?version_id=abc returns 400."""
        resp = client.get('/api/budget/dashboard?version_id=abc')
        assert resp.status_code == 400
        assert 'number' in resp.get_json()['error']


# ── AI Routes ──────────────────────────────────────────────────────────────


class TestBudgetAINarrative:

    def test_narrative_success(self, client, mock_budget_service, mock_budget_ai_service):
        """POST /api/budget/ai/narrative generates narrative."""
        mock_budget_service.get_dashboard.return_value = {
            'success': True, 'data': {'rows': []}
        }
        mock_budget_ai_service.generate_narrative.return_value = {
            'success': True, 'data': {'narrative': 'Budget is on track.'}
        }
        resp = client.post('/api/budget/ai/narrative', json={'year': 2025})
        assert resp.status_code == 200

    def test_narrative_missing_year(self, client):
        """POST /api/budget/ai/narrative without year returns 400."""
        resp = client.post('/api/budget/ai/narrative', json={'year': None})
        assert resp.status_code == 400
        assert 'year is required' in resp.get_json()['error']


class TestBudgetAIQuery:

    def test_query_success(self, client, mock_budget_service, mock_budget_ai_service):
        """POST /api/budget/ai/query translates question to params."""
        mock_budget_service.get_rollup.return_value = {'success': True, 'data': []}
        mock_budget_ai_service.translate_query.return_value = {
            'success': True, 'data': {
                'interpreted_params': {'level': 'parent', 'period': 'ytd'},
                'filter_description': 'Showing all parents YTD'
            }
        }
        mock_budget_service.get_dashboard.return_value = {
            'success': True, 'data': {'rows': []}
        }
        resp = client.post(
            '/api/budget/ai/query',
            json={'question': 'What are our biggest expenses?', 'year': 2025}
        )
        assert resp.status_code == 200

    def test_query_missing_question(self, client):
        """POST /api/budget/ai/query without question returns 400."""
        resp = client.post('/api/budget/ai/query', json={'year': 2025})
        assert resp.status_code == 400
        assert 'question is required' in resp.get_json()['error']

    def test_query_missing_year(self, client):
        """POST /api/budget/ai/query without year returns 400."""
        resp = client.post(
            '/api/budget/ai/query',
            json={'question': 'What is our revenue?'}
        )
        assert resp.status_code == 400
        assert 'year is required' in resp.get_json()['error']


class TestBudgetAIDraftSuggestions:

    def test_suggestions_success(self, client, mock_budget_service, mock_budget_ai_service):
        """POST /api/budget/ai/draft-suggestions returns suggestions."""
        mock_budget_service.list_lines.return_value = {
            'success': True, 'data': [{'account_code': '8000', 'amounts': [100] * 12}]
        }
        mock_budget_ai_service.suggest_adjustments.return_value = {
            'success': True, 'data': {'suggestions': []}
        }
        resp = client.post(
            '/api/budget/ai/draft-suggestions',
            json={'version_id': 1}
        )
        assert resp.status_code == 200

    def test_suggestions_missing_version_id(self, client):
        """POST /api/budget/ai/draft-suggestions without version_id returns 400."""
        resp = client.post('/api/budget/ai/draft-suggestions', json={'version_id': None})
        assert resp.status_code == 400
        assert 'version_id is required' in resp.get_json()['error']


class TestBudgetAIGenerateLines:

    def test_generate_lines_success(self, client, mock_budget_service, mock_budget_ai_service):
        """POST /api/budget/ai/generate-lines generates budget lines."""
        mock_budget_service.db = MagicMock()
        mock_budget_service.db.execute_query.return_value = []
        mock_budget_ai_service.generate_lines.return_value = {
            'success': True, 'data': {'lines': []}
        }
        resp = client.post(
            '/api/budget/ai/generate-lines',
            json={'fiscal_year': 2026}
        )
        assert resp.status_code == 200

    def test_generate_lines_missing_fiscal_year(self, client):
        """POST /api/budget/ai/generate-lines without fiscal_year returns 400."""
        resp = client.post('/api/budget/ai/generate-lines', json={'fiscal_year': None})
        assert resp.status_code == 400
        assert 'fiscal_year is required' in resp.get_json()['error']
