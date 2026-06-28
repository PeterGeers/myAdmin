"""
Tests verifying dead code removal for the ledger-account-hardcode-fix spec.

Validates:
- ReportingService no longer has get_financial_summary() method
- /api/reports/financial-summary endpoint returns 404
- reporting_routes_tenant_example.py file does not exist
- All other reporting routes still function

Requirements: 2.1, 2.2, 3.1, 3.2
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, Mock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

pytestmark = pytest.mark.unit


class TestDeadCodeRemoval:
    """Verify dead code has been removed from reporting module."""

    def test_reporting_service_has_no_get_financial_summary(self):
        """ReportingService should not have get_financial_summary method."""
        from reporting_routes import ReportingService
        assert not hasattr(ReportingService, 'get_financial_summary'), \
            "ReportingService still has get_financial_summary — dead code not removed"

    def test_reporting_routes_tenant_example_file_deleted(self):
        """reporting_routes_tenant_example.py should not exist."""
        src_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'src')
        dead_file = os.path.join(src_dir, 'reporting_routes_tenant_example.py')
        assert not os.path.exists(dead_file), \
            "reporting_routes_tenant_example.py still exists — dead code file not deleted"

    def test_reporting_tenant_example_bp_not_importable(self):
        """reporting_tenant_example_bp should not be importable."""
        with pytest.raises(ImportError):
            from reporting_routes_tenant_example import reporting_tenant_example_bp  # noqa: F401


class TestFinancialSummaryEndpointRemoved:
    """Verify the /financial-summary endpoint is gone."""

    @pytest.fixture
    def app(self):
        """Create Flask app with reporting blueprint."""
        from flask import Flask
        from reporting_routes import reporting_bp

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(reporting_bp, url_prefix='/api/reports')
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_financial_summary_returns_404(self, client):
        """/api/reports/financial-summary should return 404."""
        response = client.get('/api/reports/financial-summary')
        assert response.status_code == 404, \
            f"Expected 404 for removed endpoint, got {response.status_code}"


class TestOtherReportingRoutesStillRegistered:
    """Verify all non-removed reporting routes are still registered."""

    @pytest.fixture
    def app(self):
        from flask import Flask
        from reporting_routes import reporting_bp
        from routes.financial_reporting_routes import financial_reporting_bp

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(reporting_bp, url_prefix='/api/reports')
        app.register_blueprint(financial_reporting_bp, url_prefix='/api/reports')
        return app

    def _get_registered_rules(self, app):
        """Extract registered URL rules from the app."""
        return [rule.rule for rule in app.url_map.iter_rules()]

    def test_str_revenue_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/str-revenue' in rules

    def test_account_summary_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/account-summary' in rules

    def test_mutaties_table_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/mutaties-table' in rules

    def test_balance_data_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/balance-data' in rules

    def test_trends_data_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/trends-data' in rules

    def test_filter_options_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/filter-options' in rules

    def test_check_reference_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/check-reference' in rules

    def test_reference_analysis_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/reference-analysis' in rules

    def test_available_years_route_exists(self, app):
        rules = self._get_registered_rules(app)
        assert '/api/reports/available-<data_type>' in rules

    def test_financial_summary_route_not_registered(self, app):
        """Confirm /financial-summary is NOT in the registered routes."""
        rules = self._get_registered_rules(app)
        assert '/api/reports/financial-summary' not in rules, \
            "financial-summary route is still registered — dead code not removed"


class TestReportingServicePreservedMethods:
    """Verify ReportingService still has all non-removed methods."""

    def test_has_init(self):
        from reporting_routes import ReportingService
        assert hasattr(ReportingService, '__init__')

    def test_has_get_cursor(self):
        from reporting_routes import ReportingService
        assert hasattr(ReportingService, 'get_cursor')

    def test_has_build_where_clause(self):
        from reporting_routes import ReportingService
        assert hasattr(ReportingService, 'build_where_clause')

    def test_has_get_str_revenue_summary(self):
        from reporting_routes import ReportingService
        assert hasattr(ReportingService, 'get_str_revenue_summary')
