"""
Unit tests for ModuleRegistry, has_module, module_required decorator,
and seed_module_params.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.module_registry import MODULE_REGISTRY, has_module, module_required
from services.parameter_service import ParameterService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        if sql.startswith('DELETE') and commit:
            key = (params[0], params[1], params[2], params[3])
            if key in stored:
                del stored[key]
                return 1
            return 0
        return []

    db = Mock()
    db.execute_query = Mock(side_effect=execute_query)
    db._stored = stored
    return db


# ---------------------------------------------------------------------------
# Registry Structure Validation
# ---------------------------------------------------------------------------

class TestRegistryStructure:

    def test_all_modules_have_required_keys(self):
        required_keys = {'description', 'required_params', 'required_tax_rates', 'required_roles'}
        for name, module in MODULE_REGISTRY.items():
            assert required_keys.issubset(module.keys()), (
                f"Module {name} missing keys: {required_keys - module.keys()}"
            )

    def test_fin_module_exists(self):
        assert 'FIN' in MODULE_REGISTRY
        assert MODULE_REGISTRY['FIN']['description'] == 'Financial Administration'

    def test_str_module_exists(self):
        assert 'STR' in MODULE_REGISTRY
        assert MODULE_REGISTRY['STR']['description'] == 'Short-Term Rental Management'

    def test_tenadmin_module_exists(self):
        assert 'TENADMIN' in MODULE_REGISTRY
        assert MODULE_REGISTRY['TENADMIN']['required_params'] == {}

    def test_fin_required_params(self):
        params = MODULE_REGISTRY['FIN']['required_params']
        assert 'fin.default_currency' in params
        assert params['fin.default_currency']['default'] == 'EUR'
        assert 'fin.fiscal_year_start_month' in params
        assert 'fin.locale' in params

    def test_str_required_params(self):
        params = MODULE_REGISTRY['STR']['required_params']
        assert 'str.platforms' in params
        assert params['str.platforms']['default'] == ['airbnb', 'booking']

    def test_param_defs_have_type_and_default(self):
        for name, module in MODULE_REGISTRY.items():
            for pkey, pdef in module.get('required_params', {}).items():
                assert 'type' in pdef, f"{name}.{pkey} missing 'type'"
                assert 'default' in pdef, f"{name}.{pkey} missing 'default'"


# ---------------------------------------------------------------------------
# has_module Function
# ---------------------------------------------------------------------------

class TestHasModule:

    def test_returns_true_when_active(self):
        db = Mock()
        db.execute_query = Mock(return_value=[{'is_active': True}])
        assert has_module(db, 'T1', 'FIN') is True

    def test_returns_false_when_inactive(self):
        db = Mock()
        db.execute_query = Mock(return_value=[{'is_active': False}])
        assert has_module(db, 'T1', 'FIN') is False

    def test_returns_false_when_not_found(self):
        db = Mock()
        db.execute_query = Mock(return_value=[])
        assert has_module(db, 'T1', 'FIN') is False

    def test_returns_false_on_db_error(self):
        db = Mock()
        db.execute_query = Mock(side_effect=Exception("DB error"))
        assert has_module(db, 'T1', 'FIN') is False

    def test_queries_correct_table(self):
        db = Mock()
        db.execute_query = Mock(return_value=[{'is_active': True}])
        has_module(db, 'T1', 'STR')
        call_args = db.execute_query.call_args
        assert 'tenant_modules' in call_args[0][0]
        assert call_args[0][1] == ('T1', 'STR')


# ---------------------------------------------------------------------------
# module_required Decorator
# ---------------------------------------------------------------------------

class TestModuleRequiredDecorator:

    def test_returns_403_when_no_tenant(self):
        import flask
        app = flask.Flask(__name__)

        @module_required('FIN')
        def dummy(**kwargs):
            return 'ok'

        with app.test_request_context():
            result = dummy()
            assert result[1] == 403

    def test_returns_403_when_module_not_active(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(return_value=[])
                MockDB.return_value = mock_db

                @module_required('FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='T1')
                assert result[1] == 403

    def test_passes_through_when_module_active(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(return_value=[{'is_active': True}])
                MockDB.return_value = mock_db

                @module_required('FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='T1')
                assert result == 'ok'


# ---------------------------------------------------------------------------
# seed_module_params
# ---------------------------------------------------------------------------

class TestSeedModuleParams:

    def test_seeds_fin_params(self):
        db = make_mock_db()
        svc = ParameterService(db)

        count = svc.seed_module_params('T1', 'FIN')

        assert count == 3
        assert svc.get_param('fin', 'default_currency', tenant='T1') == 'EUR'
        assert svc.get_param('fin', 'fiscal_year_start_month', tenant='T1') == 1
        assert svc.get_param('fin', 'locale', tenant='T1') == 'nl'

    def test_seeds_str_params_skips_none_defaults(self):
        db = make_mock_db()
        svc = ParameterService(db)

        count = svc.seed_module_params('T1', 'STR')

        # aantal_kamers and aantal_slaapplaatsen have default=None, not seeded
        assert count == 1
        assert svc.get_param('str', 'platforms', tenant='T1') == ['airbnb', 'booking']
        assert svc.get_param('str', 'aantal_kamers', tenant='T1') is None

    def test_seeds_tenadmin_returns_zero(self):
        db = make_mock_db()
        svc = ParameterService(db)
        assert svc.seed_module_params('T1', 'TENADMIN') == 0

    def test_unknown_module_returns_zero(self):
        db = make_mock_db()
        svc = ParameterService(db)
        assert svc.seed_module_params('T1', 'NONEXISTENT') == 0

    def test_does_not_overwrite_existing(self):
        stored = {
            ('tenant', 'T1', 'fin', 'default_currency'): {
                'value': json.dumps('USD'), 'is_secret': False, 'value_type': 'string',
            }
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        count = svc.seed_module_params('T1', 'FIN')

        assert count == 2
        assert svc.get_param('fin', 'default_currency', tenant='T1') == 'USD'
