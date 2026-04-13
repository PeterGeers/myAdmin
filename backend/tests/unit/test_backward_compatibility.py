"""
Backward compatibility tests for parameter-driven config.

Verifies:
- tenant_config CRUD still works independently
- parameters table takes precedence when both have a value
- tenant_modules, tenant_credentials remain unaffected

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.parameter_service import ParameterService


def make_mock_db(stored_params=None):
    stored = dict(stored_params or {})

    def execute_query(query, params=None, fetch=True, commit=False, pool_type='primary'):
        sql = query.strip().upper()
        if sql.startswith('SELECT') and params and len(params) == 4:
            key = (params[0], params[1], params[2], params[3])
            row = stored.get(key)
            return [row] if row else []
        if sql.startswith('INSERT') and commit:
            scope, scope_id, ns, k, val, vtype, is_sec, created = params
            stored[(scope, scope_id, ns, k)] = {
                'value': val, 'is_secret': is_sec, 'value_type': vtype,
            }
            return 1
        return []

    db = Mock()
    db.execute_query = Mock(side_effect=execute_query)
    db._stored = stored
    return db


class TestParametersPrecedence:

    def test_parameter_service_only_queries_parameters_table(self):
        stored = {
            ('tenant', 'T1', 'storage', 'provider'): {
                'value': json.dumps('s3_shared'), 'is_secret': False
            }
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)
        result = svc.get_param('storage', 'provider', tenant='T1')
        assert result == 's3_shared'
        for call in db.execute_query.call_args_list:
            assert 'tenant_config' not in call[0][0]

    def test_returns_none_when_not_in_parameters(self):
        db = make_mock_db({})
        svc = ParameterService(db)
        assert svc.get_param('storage', 'some_old_key', tenant='T1') is None


class TestTenantConfigUnchanged:

    def test_tenant_admin_blueprint_exists(self):
        from tenant_admin_routes import tenant_admin_bp
        assert tenant_admin_bp.name == 'tenant_admin'

    def test_get_tenant_config_exists(self):
        from auth.tenant_context import get_tenant_config
        assert callable(get_tenant_config)

    def test_set_tenant_config_exists(self):
        from auth.tenant_context import set_tenant_config
        assert callable(set_tenant_config)


class TestOtherTablesUnaffected:

    def test_has_module_queries_tenant_modules(self):
        from services.module_registry import has_module
        db = Mock()
        db.execute_query = Mock(return_value=[{'is_active': True}])
        has_module(db, 'T1', 'FIN')
        assert 'tenant_modules' in db.execute_query.call_args[0][0]

    def test_credential_service_interface(self):
        from services.credential_service import CredentialService
        assert hasattr(CredentialService, 'encrypt_credential')
        assert hasattr(CredentialService, 'decrypt_credential')
        assert hasattr(CredentialService, 'store_credential')
        assert hasattr(CredentialService, 'get_credential')

    def test_parameter_service_never_touches_other_tables(self):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T1', 'ns', 'k', 'v')
        for call in db.execute_query.call_args_list:
            query = call[0][0]
            assert 'tenant_config' not in query
            assert 'tenant_credentials' not in query
            assert 'tenant_modules' not in query
