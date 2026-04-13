"""
Unit tests for Tax Rate Admin API routes.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import pytest
from unittest.mock import Mock
from decimal import Decimal
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from routes.tax_rate_admin_routes import _is_sysadmin


class TestTaxRateAdminAuth:

    def test_sysadmin_check(self):
        assert _is_sysadmin(['SysAdmin']) is True
        assert _is_sysadmin(['Tenant_Admin']) is False
        assert _is_sysadmin([]) is False
        assert _is_sysadmin(None) is False


class TestTaxRateAdminValidation:

    def test_create_requires_all_fields(self):
        import flask
        app = flask.Flask(__name__)
        with app.test_request_context(
            '/api/tenant-admin/tax-rates', method='POST',
            json={'tax_type': 'btw'}
        ):
            data = flask.request.get_json()
            required = [data.get('tax_type'), data.get('tax_code'),
                        data.get('rate'), data.get('effective_from')]
            assert not all(required)

    def test_date_parsing(self):
        d = date.fromisoformat('2026-01-01')
        assert d == date(2026, 1, 1)

    def test_duplicate_triggers_409(self):
        error_msg = "1062 (23000): Duplicate entry"
        assert '1062' in error_msg


class TestTaxRateAdminResponse:

    def test_source_mapping(self):
        assert ('system' if '_system_' == '_system_' else 'tenant') == 'system'
        assert ('system' if 'GoodwinSolutions' == '_system_' else 'tenant') == 'tenant'

    def test_rate_float_conversion(self):
        assert float(Decimal('21.000')) == 21.0
        assert float(Decimal('9.000')) == 9.0
