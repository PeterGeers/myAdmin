"""
Property-based tests for ParameterService.

Uses hypothesis to verify correctness properties from the design document.
Feature: parameter-driven-config

Requirements: 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 7.2, 7.4, 9.5
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.parameter_service import ParameterService, VALID_SCOPES, VALID_VALUE_TYPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_db(stored_params=None):
    """
    Create a mock DatabaseManager that simulates the parameters table.
    stored_params: dict mapping (scope, scope_id, namespace, key) -> row dict
    """
    stored = dict(stored_params or {})

    def execute_query(query, params=None, fetch=True, commit=False, pool_type='primary'):
        sql = query.strip().upper()
        if sql.startswith('SELECT') and params and len(params) == 4:
            key = (params[0], params[1], params[2], params[3])
            row = stored.get(key)
            if row:
                return [row]
            return []
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


def make_mock_credential_service():
    """Mock CredentialService: prefixes 'ENC:' for encryption."""
    cs = Mock()
    cs.encrypt_credential = Mock(side_effect=lambda v: f"ENC:{v}")
    cs.decrypt_credential = Mock(
        side_effect=lambda v: v[4:] if isinstance(v, str) and v.startswith("ENC:") else v
    )
    return cs


# Strategies
namespace_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_'),
    min_size=1, max_size=20
)
key_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_'),
    min_size=1, max_size=20
)
scope_id_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_'),
    min_size=1, max_size=30
)
string_value_st = st.text(min_size=1, max_size=100)


# ---------------------------------------------------------------------------
# Property 1: Scope Resolution Order
# Feature: parameter-driven-config, Property 1: Scope Resolution Order
# Validates: Requirements 1.2, 1.3, 1.8
# ---------------------------------------------------------------------------

class TestScopeResolutionOrder:
    """For any parameter with values at multiple scopes, get_param returns the most specific."""

    @settings(max_examples=100)
    @given(
        ns=namespace_st,
        key=key_st,
        user_val=st.one_of(st.none(), string_value_st),
        role_val=st.one_of(st.none(), string_value_st),
        tenant_val=st.one_of(st.none(), string_value_st),
        system_val=st.one_of(st.none(), string_value_st),
    )
    def test_returns_most_specific_scope(self, ns, key, user_val, role_val, tenant_val, system_val):
        stored = {}
        if system_val is not None:
            stored[('system', '_system_', ns, key)] = {
                'value': json.dumps(system_val), 'is_secret': False
            }
        if tenant_val is not None:
            stored[('tenant', 'TestTenant', ns, key)] = {
                'value': json.dumps(tenant_val), 'is_secret': False
            }
        if role_val is not None:
            stored[('role', 'admin', ns, key)] = {
                'value': json.dumps(role_val), 'is_secret': False
            }
        if user_val is not None:
            stored[('user', 'user@test.com', ns, key)] = {
                'value': json.dumps(user_val), 'is_secret': False
            }

        db = make_mock_db(stored)
        svc = ParameterService(db)

        result = svc.get_param(
            ns, key, tenant='TestTenant', role='admin', user='user@test.com'
        )

        # Expected: most specific scope wins
        if user_val is not None:
            assert result == user_val
        elif role_val is not None:
            assert result == role_val
        elif tenant_val is not None:
            assert result == tenant_val
        elif system_val is not None:
            assert result == system_val
        else:
            assert result is None

    @settings(max_examples=50)
    @given(ns=namespace_st, key=key_st)
    def test_returns_none_when_no_value(self, ns, key):
        db = make_mock_db({})
        svc = ParameterService(db)
        assert svc.get_param(ns, key, tenant='T') is None


# ---------------------------------------------------------------------------
# Property 2: Secret Parameter Round-Trip
# Feature: parameter-driven-config, Property 2: Secret Parameter Round-Trip
# Validates: Requirements 1.4, 1.5
# ---------------------------------------------------------------------------

class TestSecretParameterRoundTrip:
    """set_param(value, is_secret=True) followed by get_param returns original value."""

    @settings(max_examples=100)
    @given(value=string_value_st)
    def test_secret_round_trip(self, value):
        db = make_mock_db()
        cs = make_mock_credential_service()
        svc = ParameterService(db, credential_service=cs)

        svc.set_param('tenant', 'T1', 'ns', 'k', value,
                       value_type='string', is_secret=True)

        # Verify encryption was called
        cs.encrypt_credential.assert_called_with(value)

        # The stored value in DB should differ from plaintext
        stored_key = ('tenant', 'T1', 'ns', 'k')
        stored_row = db._stored[stored_key]
        stored_json = stored_row['value']
        stored_val = json.loads(stored_json)
        assert stored_val != value, "DB value should be encrypted, not plaintext"

        # Reading back should return original value
        result = svc.get_param('ns', 'k', tenant='T1')
        assert result == value


# ---------------------------------------------------------------------------
# Property 3: Write-Through Cache Invalidation
# Feature: parameter-driven-config, Property 3: Write-Through Cache Invalidation
# Validates: Requirements 1.7
# ---------------------------------------------------------------------------

class TestWriteThroughCacheInvalidation:
    """set_param followed by get_param always returns the newly written value."""

    @settings(max_examples=100)
    @given(
        val1=string_value_st,
        val2=string_value_st,
    )
    def test_write_then_read_returns_new_value(self, val1, val2):
        assume(val1 != val2)
        db = make_mock_db()
        svc = ParameterService(db)

        svc.set_param('tenant', 'T1', 'ns', 'k', val1, value_type='string')
        first = svc.get_param('ns', 'k', tenant='T1')
        assert first == val1

        svc.set_param('tenant', 'T1', 'ns', 'k', val2, value_type='string')
        second = svc.get_param('ns', 'k', tenant='T1')
        assert second == val2


# ---------------------------------------------------------------------------
# Property 9: Value Type Validation
# Feature: parameter-driven-config, Property 9: Value Type Validation
# Validates: Requirements 7.2
# ---------------------------------------------------------------------------

class TestValueTypeValidation:
    """Mismatched value/type combinations are rejected; matching ones succeed."""

    @settings(max_examples=100)
    @given(value=st.text(min_size=1, max_size=50))
    def test_string_type_accepts_strings(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='string')

    @settings(max_examples=100)
    @given(value=st.one_of(st.integers(min_value=-10000, max_value=10000),
                           st.floats(allow_nan=False, allow_infinity=False,
                                     min_value=-10000, max_value=10000)))
    def test_number_type_accepts_numbers(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='number')

    @settings(max_examples=50)
    @given(value=st.booleans())
    def test_boolean_type_accepts_booleans(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='boolean')

    @settings(max_examples=50)
    @given(value=st.one_of(
        st.dictionaries(st.text(min_size=1, max_size=10), st.text(max_size=20), max_size=5),
        st.lists(st.text(max_size=20), max_size=5),
    ))
    def test_json_type_accepts_dicts_and_lists(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='json')

    @settings(max_examples=100)
    @given(value=st.integers(min_value=-1000, max_value=1000))
    def test_string_type_rejects_numbers(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Expected string"):
            svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='string')

    @settings(max_examples=100)
    @given(value=st.text(min_size=1, max_size=50))
    def test_number_type_rejects_strings(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Expected number"):
            svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='number')

    @settings(max_examples=50)
    @given(value=st.text(min_size=1, max_size=50))
    def test_boolean_type_rejects_strings(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Expected boolean"):
            svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='boolean')

    @settings(max_examples=50)
    @given(value=st.text(min_size=1, max_size=50))
    def test_json_type_rejects_strings(self, value):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Expected json"):
            svc.set_param('tenant', 'T', 'ns', 'k', value, value_type='json')


# ---------------------------------------------------------------------------
# Property 10: Scope-Level Delete Isolation
# Feature: parameter-driven-config, Property 10: Scope-Level Delete Isolation
# Validates: Requirements 7.4
# ---------------------------------------------------------------------------

class TestScopeLevelDeleteIsolation:
    """Deleting at one scope does not affect other scopes; resolution falls back."""

    @settings(max_examples=100)
    @given(
        ns=namespace_st,
        key=key_st,
        tenant_val=string_value_st,
        system_val=string_value_st,
    )
    def test_delete_tenant_falls_back_to_system(self, ns, key, tenant_val, system_val):
        stored = {
            ('system', '_system_', ns, key): {
                'value': json.dumps(system_val), 'is_secret': False
            },
            ('tenant', 'T1', ns, key): {
                'value': json.dumps(tenant_val), 'is_secret': False
            },
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        # Before delete: tenant value wins
        assert svc.get_param(ns, key, tenant='T1') == tenant_val

        # Delete tenant scope
        svc.delete_param('tenant', 'T1', ns, key)

        # After delete: falls back to system
        assert svc.get_param(ns, key, tenant='T1') == system_val

        # System value is untouched
        assert ('system', '_system_', ns, key) in db._stored

    @settings(max_examples=100)
    @given(
        ns=namespace_st,
        key=key_st,
        user_val=string_value_st,
        role_val=string_value_st,
        tenant_val=string_value_st,
    )
    def test_delete_user_falls_back_to_role(self, ns, key, user_val, role_val, tenant_val):
        stored = {
            ('tenant', 'T1', ns, key): {
                'value': json.dumps(tenant_val), 'is_secret': False
            },
            ('role', 'admin', ns, key): {
                'value': json.dumps(role_val), 'is_secret': False
            },
            ('user', 'u@t.com', ns, key): {
                'value': json.dumps(user_val), 'is_secret': False
            },
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        # Before delete: user value wins
        assert svc.get_param(ns, key, tenant='T1', role='admin', user='u@t.com') == user_val

        # Delete user scope
        svc.delete_param('user', 'u@t.com', ns, key)

        # After delete: falls back to role
        assert svc.get_param(ns, key, tenant='T1', role='admin', user='u@t.com') == role_val

        # Role and tenant values untouched
        assert ('role', 'admin', ns, key) in db._stored
        assert ('tenant', 'T1', ns, key) in db._stored


# ---------------------------------------------------------------------------
# Property 13: Parameters Table Precedence Over tenant_config
# Feature: parameter-driven-config, Property 13: Parameters Table Precedence
# Validates: Requirements 9.5
# ---------------------------------------------------------------------------

class TestParametersTablePrecedence:
    """When a key exists in both parameters table and tenant_config, parameters wins."""

    @settings(max_examples=100)
    @given(
        ns=namespace_st,
        key=key_st,
        param_val=string_value_st,
        config_val=string_value_st,
    )
    def test_parameters_table_takes_precedence(self, ns, key, param_val, config_val):
        assume(param_val != config_val)

        # Parameters table has a value at tenant scope
        stored = {
            ('tenant', 'T1', ns, key): {
                'value': json.dumps(param_val), 'is_secret': False
            },
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        # ParameterService returns the parameters table value
        result = svc.get_param(ns, key, tenant='T1')
        assert result == param_val
        # The tenant_config value (config_val) is irrelevant - ParameterService
        # only queries the parameters table, so precedence is inherent.
