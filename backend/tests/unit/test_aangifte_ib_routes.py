"""
Unit tests for aangifte_ib_routes.py

Tests the Aangifte IB (Income Tax declaration) reporting endpoints:
- GET /aangifte-ib - Summary data with cache
- GET /aangifte-ib-details - Detail drill-down
- POST /aangifte-ib-export - HTML export
- POST /aangifte-ib-xlsx-export - Bulk XLSX export
- POST /aangifte-ib-xlsx-download - Single XLSX download

Task 47 of Phase 7: Missing Test Coverage
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
            kwargs['user_tenants'] = ['TestTenant', 'OtherTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """Create Flask test client with patched auth decorators."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant):
        import importlib
        import routes.aangifte_ib_routes as aib
        importlib.reload(aib)

        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(aib.aangifte_ib_bp)
        aib.set_test_mode(True)

        with app.test_client() as c:
            with app.app_context():
                yield c


@pytest.fixture
def mock_cache():
    """Mock the mutaties_cache.get_cache function."""
    mock = MagicMock()
    mock.get_data.return_value = MagicMock()
    mock.query_aangifte_ib.return_value = [
        {'parent': 'Income', 'aangifte': 'Box 1', 'total': 50000.0}
    ]
    mock.get_available_years.return_value = [2024, 2025, 2026]
    mock.get_available_administrations.return_value = ['TestTenant', 'OtherTenant']
    mock.query_aangifte_ib_details.return_value = [
        {'account': '8000', 'description': 'Revenue', 'amount': 50000.0}
    ]
    return mock


@pytest.fixture
def mock_db():
    """Mock DatabaseManager."""
    mock = MagicMock()
    return mock


# ── GET /aangifte-ib ───────────────────────────────────────────────────────


class TestAangifteIbEndpoint:

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_success_returns_summary(self, mock_db_cls, mock_get_cache, client, mock_cache):
        """GET /aangifte-ib returns summary data on success."""
        mock_get_cache.return_value = mock_cache
        # Mock the DataFrame returned by get_data with administration column
        import pandas as pd
        mock_cache.get_data.return_value = pd.DataFrame({
            'administration': ['TestTenant', 'OtherTenant']
        })

        resp = client.get('/aangifte-ib?year=2025')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'data' in data
        assert 'available_years' in data
        assert 'available_administrations' in data

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_missing_year_returns_400(self, mock_db_cls, mock_get_cache, client):
        """GET /aangifte-ib without year param returns 400."""
        resp = client.get('/aangifte-ib')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Year is required' in data['error']

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_unauthorized_administration_returns_403(self, mock_db_cls, mock_get_cache, client):
        """GET /aangifte-ib with unauthorized admin returns 403."""
        resp = client.get('/aangifte-ib?year=2025&administration=UnauthorizedTenant')
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['success'] is False
        assert 'Access denied' in data['error']

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_cache_error_returns_500(self, mock_db_cls, mock_get_cache, client):
        """GET /aangifte-ib returns 500 on internal error."""
        mock_get_cache.side_effect = RuntimeError('Cache unavailable')

        resp = client.get('/aangifte-ib?year=2025')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['success'] is False


# ── GET /aangifte-ib-details ───────────────────────────────────────────────


class TestAangifteIbDetailsEndpoint:

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_success_returns_details(self, mock_db_cls, mock_get_cache, client, mock_cache):
        """GET /aangifte-ib-details returns detail data."""
        mock_get_cache.return_value = mock_cache
        import pandas as pd
        mock_cache.get_data.return_value = pd.DataFrame({
            'administration': ['TestTenant']
        })

        resp = client.get(
            '/aangifte-ib-details?year=2025&parent=Income&aangifte=Box1'
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'data' in data
        assert data['parent'] == 'Income'
        assert data['aangifte'] == 'Box1'

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_missing_params_returns_400(self, mock_db_cls, mock_get_cache, client):
        """GET /aangifte-ib-details without required params returns 400."""
        resp = client.get('/aangifte-ib-details?year=2025')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'required' in data['error'].lower()

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_unauthorized_admin_returns_403(self, mock_db_cls, mock_get_cache, client):
        """GET /aangifte-ib-details with unauthorized admin returns 403."""
        resp = client.get(
            '/aangifte-ib-details?year=2025&parent=Inc&aangifte=Box1'
            '&administration=ForbiddenTenant'
        )
        assert resp.status_code == 403


# ── POST /aangifte-ib-export ───────────────────────────────────────────────


class TestAangifteIbExportEndpoint:

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_missing_year_returns_400(self, mock_db_cls, mock_get_cache, client):
        """POST /aangifte-ib-export without year returns 400."""
        resp = client.post(
            '/aangifte-ib-export',
            json={'data': []}
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Year is required' in data['error']

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_unauthorized_admin_returns_403(self, mock_db_cls, mock_get_cache, client):
        """POST /aangifte-ib-export with unauthorized admin returns 403."""
        resp = client.post(
            '/aangifte-ib-export',
            json={'year': 2025, 'administration': 'ForbiddenTenant', 'data': []}
        )
        assert resp.status_code == 403

    @patch('routes.aangifte_ib_routes.get_cache')
    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_export_download_success(self, mock_db_cls, mock_get_cache, client, mock_cache):
        """POST /aangifte-ib-export returns HTML on download destination."""
        mock_get_cache.return_value = mock_cache
        import pandas as pd
        mock_cache.get_data.return_value = pd.DataFrame({
            'administration': ['TestTenant']
        })

        with patch('report_generators.generate_table_rows', return_value=[]), \
             patch('services.template_service.TemplateService') as mock_ts, \
             patch('services.output_service.OutputService') as mock_os:

            mock_ts_instance = MagicMock()
            mock_ts.return_value = mock_ts_instance
            mock_ts_instance.get_template_metadata.return_value = None
            mock_ts_instance.apply_field_mappings.return_value = '<html>report</html>'

            mock_os_instance = MagicMock()
            mock_os.return_value = mock_os_instance
            mock_os_instance.handle_output.return_value = {
                'content': '<html>report</html>',
                'filename': 'Aangifte_IB_TestTenant_2025.html'
            }

            # Mock template file existence
            with patch('os.path.exists', return_value=True), \
                 patch('builtins.open', MagicMock(
                     return_value=MagicMock(
                         __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value='<html>{{year}}</html>'))),
                         __exit__=MagicMock(return_value=False)
                     )
                 )):
                resp = client.post(
                    '/aangifte-ib-export',
                    json={'year': 2025, 'data': [], 'output_destination': 'download'}
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'html' in data


# ── POST /aangifte-ib-xlsx-export ──────────────────────────────────────────


class TestAangifteIbXlsxExportEndpoint:

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_missing_params_returns_400(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-export without required params returns 400."""
        resp = client.post('/aangifte-ib-xlsx-export', json={'administrations': []})
        assert resp.status_code == 400

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_unauthorized_admins_returns_403(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-export with unauthorized admins returns 403."""
        resp = client.post(
            '/aangifte-ib-xlsx-export',
            json={'administrations': ['ForbiddenTenant'], 'years': [2025]}
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert 'Access denied' in data['error']

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_success_returns_results(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-export returns results on success."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{'administration': 'TestTenant'}]
        mock_conn.cursor.return_value = mock_cursor
        mock_db_cls.return_value.get_connection.return_value = mock_conn

        with patch('xlsx_export.XLSXExportProcessor') as mock_xlsx:
            mock_xlsx.return_value.generate_xlsx_export.return_value = [
                {'success': True, 'administration': 'TestTenant', 'year': 2025}
            ]
            resp = client.post(
                '/aangifte-ib-xlsx-export',
                json={'administrations': ['TestTenant'], 'years': [2025]}
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['results']) == 1


# ── POST /aangifte-ib-xlsx-download ────────────────────────────────────────


class TestAangifteIbXlsxDownloadEndpoint:

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_missing_params_returns_400(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-download without required params returns 400."""
        resp = client.post('/aangifte-ib-xlsx-download', json={'administration': 'TestTenant'})
        assert resp.status_code == 400

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_empty_json_body_returns_400(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-download with empty JSON object returns 400."""
        resp = client.post('/aangifte-ib-xlsx-download', json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_unauthorized_admin_returns_403(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-download with unauthorized admin returns 403."""
        resp = client.post(
            '/aangifte-ib-xlsx-download',
            json={'administration': 'ForbiddenTenant', 'year': 2025}
        )
        assert resp.status_code == 403

    @patch('routes.aangifte_ib_routes.DatabaseManager')
    def test_no_data_returns_404(self, mock_db_cls, client):
        """POST /aangifte-ib-xlsx-download returns 404 if no data found."""
        with patch('xlsx_export.XLSXExportProcessor') as mock_xlsx:
            mock_xlsx.return_value.make_ledgers.return_value = None
            resp = client.post(
                '/aangifte-ib-xlsx-download',
                json={'administration': 'TestTenant', 'year': 2025}
            )

        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
