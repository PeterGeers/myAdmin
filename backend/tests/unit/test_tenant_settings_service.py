"""
Unit tests for TenantSettingsService

Tests settings retrieval, update operations, default handling,
and tenant-scoped settings isolation.

All database dependencies are mocked — no real connections allowed.
"""

import pytest
import os
import sys
import json
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tenant_settings_service import TenantSettingsService


@pytest.mark.unit
class TestTenantSettingsServiceInit:
    """Test service initialization."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.execute_query = Mock()
        return db

    def test_initialization(self, mock_db):
        """Test service initializes with db_manager."""
        service = TenantSettingsService(mock_db)
        assert service.db is mock_db


@pytest.mark.unit
class TestGetSettings:
    """Test settings retrieval functionality."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.execute_query = Mock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return TenantSettingsService(mock_db)

    def test_get_settings_simple_keys(self, service, mock_db):
        """Test retrieval of simple (non-nested) settings."""
        mock_db.execute_query.return_value = [
            {'config_key': 'language', 'config_value': 'nl', 'is_secret': False},
            {'config_key': 'currency', 'config_value': 'EUR', 'is_secret': False},
        ]

        result = service.get_settings('tenant_a')

        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert 'tenant_config' in call_args[0][0]
        assert call_args[0][1] == ('tenant_a',)
        assert result == {'language': 'nl', 'currency': 'EUR'}

    def test_get_settings_nested_keys(self, service, mock_db):
        """Test retrieval of dot-notation keys builds nested dict."""
        mock_db.execute_query.return_value = [
            {'config_key': 'storage.facturen_folder_id', 'config_value': 'abc123', 'is_secret': False},
            {'config_key': 'storage.bank_folder_id', 'config_value': 'def456', 'is_secret': False},
        ]

        result = service.get_settings('tenant_b')

        assert result == {
            'storage': {
                'facturen_folder_id': 'abc123',
                'bank_folder_id': 'def456',
            }
        }

    def test_get_settings_json_value_parsed(self, service, mock_db):
        """Test that JSON object values are parsed automatically."""
        mock_db.execute_query.return_value = [
            {'config_key': 'modules', 'config_value': '{"banking": true, "str": false}', 'is_secret': False},
        ]

        result = service.get_settings('tenant_c')

        assert result == {'modules': {'banking': True, 'str': False}}

    def test_get_settings_json_array_parsed(self, service, mock_db):
        """Test that JSON array values are parsed automatically."""
        mock_db.execute_query.return_value = [
            {'config_key': 'tags', 'config_value': '["tag1", "tag2"]', 'is_secret': False},
        ]

        result = service.get_settings('tenant_d')

        assert result == {'tags': ['tag1', 'tag2']}

    def test_get_settings_invalid_json_kept_as_string(self, service, mock_db):
        """Test that invalid JSON starting with { is kept as string."""
        mock_db.execute_query.return_value = [
            {'config_key': 'notes', 'config_value': '{not valid json', 'is_secret': False},
        ]

        result = service.get_settings('tenant_e')

        assert result == {'notes': '{not valid json'}

    def test_get_settings_empty_result(self, service, mock_db):
        """Test retrieval when no settings exist for tenant."""
        mock_db.execute_query.return_value = []

        result = service.get_settings('tenant_empty')

        assert result == {}

    def test_get_settings_deeply_nested_keys(self, service, mock_db):
        """Test deeply nested dot-notation keys."""
        mock_db.execute_query.return_value = [
            {'config_key': 'email.smtp.host', 'config_value': 'smtp.example.com', 'is_secret': False},
            {'config_key': 'email.smtp.port', 'config_value': '587', 'is_secret': False},
            {'config_key': 'email.from', 'config_value': 'noreply@example.com', 'is_secret': False},
        ]

        result = service.get_settings('tenant_f')

        assert result == {
            'email': {
                'smtp': {
                    'host': 'smtp.example.com',
                    'port': '587',
                },
                'from': 'noreply@example.com',
            }
        }

    def test_get_settings_db_error_propagates(self, service, mock_db):
        """Test that database errors propagate as exceptions."""
        mock_db.execute_query.side_effect = Exception("Connection timeout")

        with pytest.raises(Exception, match="Connection timeout"):
            service.get_settings('tenant_x')

    def test_get_settings_tenant_scoped_query(self, service, mock_db):
        """Test that the query filters by administration (tenant isolation)."""
        mock_db.execute_query.return_value = []

        service.get_settings('my_admin')

        query = mock_db.execute_query.call_args[0][0]
        params = mock_db.execute_query.call_args[0][1]
        assert 'administration = %s' in query
        assert params == ('my_admin',)


@pytest.mark.unit
class TestUpdateSettings:
    """Test settings update operations."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.execute_query = Mock(return_value=None)
        return db

    @pytest.fixture
    def service(self, mock_db):
        return TenantSettingsService(mock_db)

    def test_update_simple_settings(self, service, mock_db):
        """Test updating flat key-value settings."""
        settings = {'language': 'en', 'currency': 'USD'}

        result = service.update_settings('tenant_a', settings)

        assert result is True
        assert mock_db.execute_query.call_count == 2

    def test_update_nested_settings_flattened(self, service, mock_db):
        """Test that nested dicts are flattened to dot-notation keys."""
        settings = {
            'storage': {
                'facturen_folder_id': 'new_id',
                'bank_folder_id': 'other_id',
            }
        }

        result = service.update_settings('tenant_b', settings)

        assert result is True
        # Should result in 2 calls: storage.facturen_folder_id and storage.bank_folder_id
        assert mock_db.execute_query.call_count == 2

        # Check that the keys are flattened
        all_keys = []
        for call in mock_db.execute_query.call_args_list:
            # Positional args: (query, params_tuple, ...)
            params = call[0][1]  # second positional arg is the params tuple
            # params is (administration, key, value_str)
            all_keys.append(params[1])

        assert 'storage.facturen_folder_id' in all_keys
        assert 'storage.bank_folder_id' in all_keys

    def test_update_settings_uses_upsert(self, service, mock_db):
        """Test that update uses INSERT ... ON DUPLICATE KEY UPDATE."""
        service.update_settings('tenant_c', {'key': 'value'})

        query = mock_db.execute_query.call_args[0][0]
        assert 'INSERT INTO tenant_config' in query
        assert 'ON DUPLICATE KEY UPDATE' in query

    def test_update_settings_includes_tenant(self, service, mock_db):
        """Test that the administration column is included in the insert."""
        service.update_settings('my_tenant', {'key': 'value'})

        params = mock_db.execute_query.call_args[0][1]
        assert params[0] == 'my_tenant'

    def test_update_settings_dict_value_serialized_as_json(self, service, mock_db):
        """Test that dict values are serialized as JSON strings."""
        settings = {'complex': {'nested': 'value'}}

        service.update_settings('tenant_d', settings)

        # The nested dict gets flattened, so 'complex.nested' = 'value'
        params = mock_db.execute_query.call_args[0][1]
        assert params[1] == 'complex.nested'
        assert params[2] == 'value'

    def test_update_settings_list_value_serialized_as_json(self, service, mock_db):
        """Test that list values are serialized as JSON strings."""
        settings = {'tags': ['a', 'b', 'c']}

        service.update_settings('tenant_e', settings)

        params = mock_db.execute_query.call_args[0][1]
        assert params[1] == 'tags'
        assert params[2] == json.dumps(['a', 'b', 'c'])

    def test_update_settings_none_value(self, service, mock_db):
        """Test that None values are stored as None."""
        settings = {'optional_field': None}

        service.update_settings('tenant_f', settings)

        params = mock_db.execute_query.call_args[0][1]
        assert params[2] is None

    def test_update_settings_commits(self, service, mock_db):
        """Test that each setting update is committed."""
        service.update_settings('tenant_g', {'key': 'val'})

        call_kwargs = mock_db.execute_query.call_args[1] if mock_db.execute_query.call_args[1] else {}
        # The call uses keyword args fetch=False, commit=True
        _, kwargs = mock_db.execute_query.call_args
        assert kwargs.get('fetch') is False
        assert kwargs.get('commit') is True

    def test_update_settings_db_error_propagates(self, service, mock_db):
        """Test that database errors during update propagate."""
        mock_db.execute_query.side_effect = Exception("Deadlock found")

        with pytest.raises(Exception, match="Deadlock found"):
            service.update_settings('tenant_h', {'key': 'value'})


@pytest.mark.unit
class TestFlattenDict:
    """Test the _flatten_dict helper method."""

    @pytest.fixture
    def service(self):
        mock_db = Mock()
        return TenantSettingsService(mock_db)

    def test_flat_dict_unchanged(self, service):
        """Test that a flat dict is returned as-is."""
        d = {'a': 1, 'b': 'hello'}
        assert service._flatten_dict(d) == {'a': 1, 'b': 'hello'}

    def test_nested_dict_flattened(self, service):
        """Test that nested dicts use dot-notation."""
        d = {'level1': {'level2': 'value'}}
        assert service._flatten_dict(d) == {'level1.level2': 'value'}

    def test_deeply_nested(self, service):
        """Test multiple levels of nesting."""
        d = {'a': {'b': {'c': 'deep'}}}
        assert service._flatten_dict(d) == {'a.b.c': 'deep'}

    def test_mixed_flat_and_nested(self, service):
        """Test mix of flat keys and nested keys."""
        d = {'flat': 'value', 'nested': {'key': 'val'}}
        result = service._flatten_dict(d)
        assert result == {'flat': 'value', 'nested.key': 'val'}

    def test_empty_dict(self, service):
        """Test flattening an empty dict."""
        assert service._flatten_dict({}) == {}


@pytest.mark.unit
class TestGetActivity:
    """Test activity retrieval functionality."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        db.execute_query = Mock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return TenantSettingsService(mock_db)

    def test_get_activity_with_date_range(self, service, mock_db):
        """Test activity retrieval with explicit date range."""
        mock_db.execute_query.side_effect = [
            [{'count': 5}],                              # total actions
            [{'action_type': 'login', 'count': 3}],     # by type
            [{'user_email': 'user@test.com', 'count': 5}],  # by user
            [],                                          # recent actions
        ]

        date_range = {'start_date': '2024-01-01', 'end_date': '2024-01-31'}
        result = service.get_activity('tenant_a', date_range)

        assert result['date_range']['start'] == '2024-01-01'
        assert result['date_range']['end'] == '2024-01-31'
        assert result['total_actions'] == 5
        assert result['actions_by_type'] == {'login': 3}
        assert result['actions_by_user'] == {'user@test.com': 5}

    def test_get_activity_default_date_range(self, service, mock_db):
        """Test that default date range is last 30 days."""
        mock_db.execute_query.side_effect = [
            [{'count': 0}],
            [],
            [],
            [],
        ]

        result = service.get_activity('tenant_b')

        assert 'date_range' in result
        assert result['date_range']['start'] is not None
        assert result['date_range']['end'] is not None

    def test_get_activity_audit_log_unavailable(self, service, mock_db):
        """Test graceful fallback when audit_log table is unavailable."""
        mock_db.execute_query.side_effect = Exception("Table 'audit_log' doesn't exist")

        result = service.get_activity('tenant_c')

        assert result['error'] == 'Audit log not available'
        assert result['total_actions'] == 0

    def test_get_activity_tenant_scoped(self, service, mock_db):
        """Test that activity queries are scoped to the tenant."""
        mock_db.execute_query.side_effect = [
            [{'count': 0}],
            [],
            [],
            [],
        ]

        service.get_activity('specific_tenant')

        # All queries should include the tenant parameter
        for call in mock_db.execute_query.call_args_list:
            params = call[0][1]
            assert params[0] == 'specific_tenant'


@pytest.mark.unit
class TestDeepMerge:
    """Test the _deep_merge helper method."""

    @pytest.fixture
    def service(self):
        mock_db = Mock()
        return TenantSettingsService(mock_db)

    def test_merge_non_overlapping(self, service):
        """Test merging dicts with no overlapping keys."""
        result = service._deep_merge({'a': 1}, {'b': 2})
        assert result == {'a': 1, 'b': 2}

    def test_merge_overlapping_scalar(self, service):
        """Test that overlapping scalar keys are overwritten by dict2."""
        result = service._deep_merge({'a': 1}, {'a': 2})
        assert result == {'a': 2}

    def test_merge_nested_dicts(self, service):
        """Test recursive merging of nested dicts."""
        dict1 = {'config': {'a': 1, 'b': 2}}
        dict2 = {'config': {'b': 3, 'c': 4}}
        result = service._deep_merge(dict1, dict2)
        assert result == {'config': {'a': 1, 'b': 3, 'c': 4}}

    def test_merge_does_not_mutate_originals(self, service):
        """Test that originals are not mutated."""
        dict1 = {'a': 1}
        dict2 = {'b': 2}
        service._deep_merge(dict1, dict2)
        assert dict1 == {'a': 1}
        assert dict2 == {'b': 2}
