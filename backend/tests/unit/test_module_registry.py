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

from services.module_registry import (
    MODULE_REGISTRY,
    has_module,
    module_required,
    module_backing,
    resolve_module_api_base,
)
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

        # aantal_kamers and aantal_slaapplaatsen have default=None in MODULE_REGISTRY,
        # so they are NOT seeded to the DB. However, get_param falls back to
        # CODE_DEFAULTS (populated from PARAMETER_SCHEMA), which assigns 0 for
        # number types without an explicit default.
        assert count == 1
        assert svc.get_param('str', 'platforms', tenant='T1') == ['airbnb', 'booking']
        assert svc.get_param('str', 'aantal_kamers', tenant='T1') == 0

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


# ---------------------------------------------------------------------------
# Backing kind: module_backing / resolve_module_api_base (S1 backing kind)
#
# Requirements: 4.1 (four existing modules unchanged / backing-agnostic),
#               4.2 (a SAM module is expressible and resolves its API base)
# Reference: .kiro/specs/multi-tenant/s1-prepare-platform/tasks.md T1.5
# ---------------------------------------------------------------------------

# Names for the temporary SAM fixture entry. Kept module-local so they never
# collide with a real registry module.
_SAM_MODULE_NAME = "SAM_TEST_MODULE"
_SAM_API_BASE_ENV = "SAM_TEST_MODULE_API_BASE"


@pytest.fixture
def sam_module(monkeypatch):
    """
    Inject a temporary SAM-backed module into MODULE_REGISTRY for the duration
    of a single test, then remove it.

    monkeypatch.setitem restores the registry to its prior state on teardown
    (deleting the key we added), so the temporary entry never leaks between
    tests or into the real registry. Returns the module name and env-var name
    so tests can drive resolution.
    """
    entry = {
        "description": "Temporary SAM-backed test module",
        "required_params": {},
        "required_tax_rates": [],
        "required_roles": ["SamTest_Read"],
        "backing": {
            "kind": "sam",
            "api_base_env": _SAM_API_BASE_ENV,
            "data_namespace": "sam_test",
        },
    }
    monkeypatch.setitem(MODULE_REGISTRY, _SAM_MODULE_NAME, entry)
    return _SAM_MODULE_NAME, _SAM_API_BASE_ENV


class TestModuleBacking:

    def test_module_backing_fin_returns_flask(self):
        assert module_backing("FIN") == "flask"

    def test_module_backing_zzp_returns_flask(self):
        assert module_backing("ZZP") == "flask"

    def test_module_backing_str_returns_flask(self):
        assert module_backing("STR") == "flask"

    def test_module_backing_tenadmin_returns_flask(self):
        assert module_backing("TENADMIN") == "flask"

    def test_module_backing_all_existing_modules_are_flask(self):
        # The four shipped modules carry no backing key and must stay implicitly flask.
        for name in ("FIN", "ZZP", "STR", "TENADMIN"):
            assert "backing" not in MODULE_REGISTRY[name], (
                f"{name} unexpectedly gained a backing block"
            )
            assert module_backing(name) == "flask"

    def test_module_backing_unknown_module_raises(self):
        with pytest.raises(ValueError, match="Unknown module"):
            module_backing("DOES_NOT_EXIST")

    def test_module_backing_sam_fixture_returns_sam(self, sam_module):
        name, _ = sam_module
        assert module_backing(name) == "sam"

    def test_sam_fixture_does_not_leak_into_registry(self):
        # Runs without the sam_module fixture: the temporary entry must be gone.
        assert _SAM_MODULE_NAME not in MODULE_REGISTRY


class TestResolveModuleApiBase:

    def test_resolve_flask_module_returns_none(self):
        # Flask modules have no API base on the module plane.
        for name in ("FIN", "ZZP", "STR", "TENADMIN"):
            assert resolve_module_api_base(name) is None

    def test_resolve_sam_module_reads_env_var(self, sam_module, monkeypatch):
        name, env_var = sam_module
        monkeypatch.setenv(env_var, "https://sam.example.com/prod")
        assert resolve_module_api_base(name) == "https://sam.example.com/prod"

    def test_resolve_sam_module_missing_env_var_raises(self, sam_module, monkeypatch):
        name, env_var = sam_module
        monkeypatch.delenv(env_var, raising=False)
        with pytest.raises(ValueError, match="unset or empty"):
            resolve_module_api_base(name)

    def test_resolve_sam_module_empty_env_var_raises(self, sam_module, monkeypatch):
        name, env_var = sam_module
        monkeypatch.setenv(env_var, "")
        with pytest.raises(ValueError, match="unset or empty"):
            resolve_module_api_base(name)

    def test_resolve_unknown_module_raises(self):
        with pytest.raises(ValueError, match="Unknown module"):
            resolve_module_api_base("DOES_NOT_EXIST")


# ---------------------------------------------------------------------------
# MEMBERS module registration (S5 C7)
#
# Requirements: R4.2 (h-dcn roles expressed as generic entitlement config),
#               R6.1 (module authorizes via entitlement — sam-backed).
# Reference: .kiro/specs/multi-tenant/s5-members-first-migration/design.md C7
# ---------------------------------------------------------------------------

_MEMBERS_API_BASE_ENV = "MEMBERS_MODULE_API_BASE"


class TestMembersModuleRegistration:

    def test_members_module_exists_with_required_keys(self):
        assert "MEMBERS" in MODULE_REGISTRY
        entry = MODULE_REGISTRY["MEMBERS"]
        required_keys = {
            "description",
            "required_params",
            "required_tax_rates",
            "required_roles",
        }
        assert required_keys.issubset(entry.keys())

    def test_module_backing_members_returns_sam(self):
        assert module_backing("MEMBERS") == "sam"

    def test_members_backing_stores_env_var_name_not_url(self):
        backing = MODULE_REGISTRY["MEMBERS"]["backing"]
        assert backing["api_base_env"] == _MEMBERS_API_BASE_ENV
        # The registry must never store a URL — only the env var NAME.
        assert "://" not in backing["api_base_env"]

    def test_members_backing_declares_data_namespace(self):
        assert MODULE_REGISTRY["MEMBERS"]["backing"]["data_namespace"] == "members"

    def test_members_required_roles_present_and_generic(self):
        roles = MODULE_REGISTRY["MEMBERS"]["required_roles"]
        # Members_CRUD backs the scope-requiring capability (design C4/C7).
        assert "Members_CRUD" in roles
        # Follows the <Module>_<Action> convention used by other modules.
        assert set(roles) == {"Members_CRUD", "Members_Read", "Members_Export"}

    def test_resolve_members_api_base_reads_env_var(self, monkeypatch):
        monkeypatch.setenv(_MEMBERS_API_BASE_ENV, "https://members.example.com/prod")
        assert (
            resolve_module_api_base("MEMBERS")
            == "https://members.example.com/prod"
        )

    def test_resolve_members_api_base_unset_env_var_raises(self, monkeypatch):
        monkeypatch.delenv(_MEMBERS_API_BASE_ENV, raising=False)
        with pytest.raises(ValueError, match="unset or empty"):
            resolve_module_api_base("MEMBERS")

    def test_resolve_members_api_base_empty_env_var_raises(self, monkeypatch):
        monkeypatch.setenv(_MEMBERS_API_BASE_ENV, "")
        with pytest.raises(ValueError, match="unset or empty"):
            resolve_module_api_base("MEMBERS")


class TestIntersectionAuthUnchanged:
    """
    Guard that S1's backing kind did not alter the tenant module intersection-auth.
    get_user_module_roles derives module access purely from Cognito role prefixes;
    it must not inspect the backing kind. (R4.2)
    """

    def test_module_role_mapping_ignores_backing(self):
        from tenant_module_routes import get_user_module_roles

        modules = get_user_module_roles(
            ["Finance_Read", "STR_CRUD", "ZZP_Export", "Unrelated_Role"]
        )
        assert set(modules) == {"FIN", "STR", "ZZP"}

    def test_module_role_mapping_empty_roles(self):
        from tenant_module_routes import get_user_module_roles

        assert get_user_module_roles([]) == []
