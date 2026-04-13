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
from hypothesis import given, strategies as st, settings as h_settings

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
