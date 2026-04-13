"""
Unit tests for ParameterService.

Example-based tests for CRUD operations, encryption delegation, cache behavior,
and edge cases.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
Reference: .kiro/specs/parameter-driven-config/design.md
"""

import sys
import os
import json
import pytest
from unittest.mock import Mock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.parameter_service import ParameterService, VALID_SCOPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_db(stored_params=None):
    stored = dict(stored_params or {})

    def execute_query(query, params=None, fetch=True, commit=False, pool_type='primary'):
        sql = query.strip().upper()
        if sql.startswith('SELECT') and params:
            if len(params) == 4:
                key = (params[0], params[1], params[2], params[3])
                row = stored.get(key)
                return [row] if row else []
            if len(params) == 2:
                ns, tenant = params
                results = []
                for k, v in stored.items():
                    if k[2] == ns and (
                        (k[0] == 'tenant' and k[1] == tenant) or k[0] == 'system'
                    ):
                        results.append({
                            'id': hash(k) % 10000,
                            'scope': k[0], 'scope_id': k[1],
                            'namespace': k[2], 'key': k[3],
                            'value': v['value'],
                            'value_type': v.get('value_type', 'string'),
                            'is_secret': v.get('is_secret', False),
                        })
                results.sort(key=lambda r: (r['key'], 0 if r['scope'] == 'tenant' else 1))
                return results
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
    cs = Mock()
    cs.encrypt_credential = Mock(side_effect=lambda v: f"ENC:{v}")
    cs.decrypt_credential = Mock(
        side_effect=lambda v: v[4:] if isinstance(v, str) and v.startswith("ENC:") else v
    )
    return cs


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------

class TestParameterServiceCRUD:

    def test_set_and_get_string_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T1', 'general', 'name', 'hello')
        assert svc.get_param('general', 'name', tenant='T1') == 'hello'

    def test_set_and_get_number_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T1', 'fin', 'year', 2025, value_type='number')
        assert svc.get_param('fin', 'year', tenant='T1') == 2025

    def test_set_and_get_boolean_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('system', '_system_', 'general', 'debug', True, value_type='boolean')
        assert svc.get_param('general', 'debug') is True

    def test_set_and_get_json_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        val = {'folders': ['a', 'b']}
        svc.set_param('tenant', 'T1', 'storage', 'config', val, value_type='json')
        assert svc.get_param('storage', 'config', tenant='T1') == val

    def test_delete_existing_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T1', 'ns', 'k', 'val')
        assert svc.delete_param('tenant', 'T1', 'ns', 'k') is True
        assert svc.get_param('ns', 'k', tenant='T1') is None

    def test_delete_nonexistent_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        assert svc.delete_param('tenant', 'T1', 'ns', 'k') is False

    def test_overwrite_param(self):
        db = make_mock_db()
        svc = ParameterService(db)
        svc.set_param('tenant', 'T1', 'ns', 'k', 'v1')
        svc.set_param('tenant', 'T1', 'ns', 'k', 'v2')
        assert svc.get_param('ns', 'k', tenant='T1') == 'v2'


# ---------------------------------------------------------------------------
# Encryption Delegation
# ---------------------------------------------------------------------------

class TestEncryptionDelegation:

    def test_secret_param_encrypts_on_write(self):
        db = make_mock_db()
        cs = make_mock_credential_service()
        svc = ParameterService(db, credential_service=cs)

        svc.set_param('tenant', 'T1', 'ns', 'api_key', 'secret123',
                       is_secret=True)
        cs.encrypt_credential.assert_called_once_with('secret123')

    def test_secret_param_decrypts_on_read(self):
        db = make_mock_db()
        cs = make_mock_credential_service()
        svc = ParameterService(db, credential_service=cs)

        svc.set_param('tenant', 'T1', 'ns', 'api_key', 'secret123',
                       is_secret=True)
        result = svc.get_param('ns', 'api_key', tenant='T1')
        assert result == 'secret123'
        cs.decrypt_credential.assert_called()

    def test_secret_without_credential_service_raises(self):
        db = make_mock_db()
        svc = ParameterService(db)  # no credential_service
        with pytest.raises(RuntimeError, match="CredentialService is required"):
            svc.set_param('tenant', 'T1', 'ns', 'k', 'val', is_secret=True)


# ---------------------------------------------------------------------------
# Cache Behavior
# ---------------------------------------------------------------------------

class TestCacheBehavior:

    def test_cache_hit_avoids_db_query(self):
        stored = {
            ('tenant', 'T1', 'ns', 'k'): {
                'value': json.dumps('cached'), 'is_secret': False
            }
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        # First call populates cache
        svc.get_param('ns', 'k', tenant='T1')
        call_count_after_first = db.execute_query.call_count

        # Second call should use cache
        svc.get_param('ns', 'k', tenant='T1')
        assert db.execute_query.call_count == call_count_after_first

    def test_set_param_invalidates_cache(self):
        db = make_mock_db()
        svc = ParameterService(db)

        svc.set_param('tenant', 'T1', 'ns', 'k', 'v1')
        svc.get_param('ns', 'k', tenant='T1')  # populate cache

        svc.set_param('tenant', 'T1', 'ns', 'k', 'v2')
        # Cache should be invalidated, so next get hits DB
        result = svc.get_param('ns', 'k', tenant='T1')
        assert result == 'v2'

    def test_delete_param_invalidates_cache(self):
        db = make_mock_db()
        svc = ParameterService(db)

        svc.set_param('tenant', 'T1', 'ns', 'k', 'v1')
        svc.get_param('ns', 'k', tenant='T1')  # populate cache

        svc.delete_param('tenant', 'T1', 'ns', 'k')
        assert svc.get_param('ns', 'k', tenant='T1') is None


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_get_param_returns_none_for_missing(self):
        db = make_mock_db()
        svc = ParameterService(db)
        assert svc.get_param('ns', 'missing') is None

    def test_invalid_scope_raises(self):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Invalid scope"):
            svc.set_param('invalid_scope', 'id', 'ns', 'k', 'v')

    def test_invalid_scope_on_delete_raises(self):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Invalid scope"):
            svc.delete_param('bad', 'id', 'ns', 'k')

    def test_invalid_value_type_raises(self):
        db = make_mock_db()
        svc = ParameterService(db)
        with pytest.raises(ValueError, match="Invalid value_type"):
            svc.set_param('tenant', 'T', 'ns', 'k', 'v', value_type='xml')

    def test_get_params_by_namespace(self):
        stored = {
            ('tenant', 'T1', 'storage', 'provider'): {
                'value': json.dumps('google_drive'), 'is_secret': False, 'value_type': 'string'
            },
            ('system', '_system_', 'storage', 'max_size'): {
                'value': json.dumps(100), 'is_secret': False, 'value_type': 'number'
            },
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        results = svc.get_params_by_namespace('storage', 'T1')
        assert len(results) == 2
        keys = {r['key'] for r in results}
        assert 'provider' in keys
        assert 'max_size' in keys

    def test_get_params_by_namespace_tenant_overrides_system(self):
        stored = {
            ('tenant', 'T1', 'ns', 'k'): {
                'value': json.dumps('tenant_val'), 'is_secret': False, 'value_type': 'string'
            },
            ('system', '_system_', 'ns', 'k'): {
                'value': json.dumps('system_val'), 'is_secret': False, 'value_type': 'string'
            },
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        results = svc.get_params_by_namespace('ns', 'T1')
        assert len(results) == 1
        assert results[0]['value'] == 'tenant_val'
        assert results[0]['scope_origin'] == 'tenant'

    def test_scope_resolution_skips_none_scope_ids(self):
        """When user/role are None, those scopes are skipped."""
        stored = {
            ('tenant', 'T1', 'ns', 'k'): {
                'value': json.dumps('tenant_val'), 'is_secret': False
            },
        }
        db = make_mock_db(stored)
        svc = ParameterService(db)

        result = svc.get_param('ns', 'k', tenant='T1')
        assert result == 'tenant_val'
