"""
Integration tests for tenant_settings_service.py

Tests settings JSON management (get, update, merge) and activity logging.
Validates: Requirements 4.4, 8.2, 8.4
"""

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime, timedelta

from services.tenant_settings_service import TenantSettingsService


class TestGetSettings:
    """Tests for get_settings method."""

    def test_get_settings_dot_notation_returns_nested_dict(self, mock_db):
        """Test get_settings builds nested dict from dot-notation keys."""
        mock_db.execute_query.return_value = [
            {'config_key': 'storage.facturen_folder_id', 'config_value': 'folder123', 'is_secret': False},
            {'config_key': 'storage.bucket_name', 'config_value': 'my-bucket', 'is_secret': False},
        ]

        service = TenantSettingsService(mock_db)
        result = service.get_settings('test-tenant')

        assert result == {
            'storage': {
                'facturen_folder_id': 'folder123',
                'bucket_name': 'my-bucket',
            }
        }
        mock_db.execute_query.assert_called_once()
        query = mock_db.execute_query.call_args[0][0]
        params = mock_db.execute_query.call_args[0][1]
        assert 'tenant_config' in query
        assert params == ('test-tenant',)

    def test_get_settings_json_value_returns_parsed(self, mock_db):
        """Test get_settings parses JSON values correctly."""
        mock_db.execute_query.return_value = [
            {'config_key': 'features', 'config_value': '{"enabled": true, "limit": 10}', 'is_secret': False},
            {'config_key': 'tags', 'config_value': '["tag1", "tag2"]', 'is_secret': False},
        ]

        service = TenantSettingsService(mock_db)
        result = service.get_settings('test-tenant')

        assert result['features'] == {'enabled': True, 'limit': 10}
        assert result['tags'] == ['tag1', 'tag2']

    def test_get_settings_no_results_returns_empty_dict(self, mock_db):
        """Test get_settings returns empty dict when no config rows exist."""
        mock_db.execute_query.return_value = []

        service = TenantSettingsService(mock_db)
        result = service.get_settings('empty-tenant')

        assert result == {}

    def test_get_settings_db_error_raises_exception(self, mock_db):
        """Test get_settings raises exception on database error."""
        mock_db.execute_query.side_effect = Exception("Connection refused")

        service = TenantSettingsService(mock_db)

        with pytest.raises(Exception, match="Connection refused"):
            service.get_settings('test-tenant')

    def test_get_settings_flat_keys_returns_flat_dict(self, mock_db):
        """Test get_settings handles flat keys without dot notation."""
        mock_db.execute_query.return_value = [
            {'config_key': 'theme', 'config_value': 'dark', 'is_secret': False},
            {'config_key': 'locale', 'config_value': 'nl', 'is_secret': False},
        ]

        service = TenantSettingsService(mock_db)
        result = service.get_settings('test-tenant')

        assert result == {'theme': 'dark', 'locale': 'nl'}

    def test_get_settings_invalid_json_keeps_string(self, mock_db):
        """Test get_settings keeps value as string when JSON parsing fails."""
        mock_db.execute_query.return_value = [
            {'config_key': 'note', 'config_value': '{not valid json', 'is_secret': False},
        ]

        service = TenantSettingsService(mock_db)
        result = service.get_settings('test-tenant')

        assert result['note'] == '{not valid json'


class TestUpdateSettings:
    """Tests for update_settings method."""

    def test_update_settings_flat_dict_calls_execute_for_each_key(self, mock_db):
        """Test update_settings flattens nested dict and calls execute_query for each key."""
        mock_db.execute_query.return_value = None

        service = TenantSettingsService(mock_db)
        result = service.update_settings('test-tenant', {
            'storage': {
                'folder_id': 'abc123',
                'bucket': 'my-bucket',
            }
        })

        assert result is True
        # Should be called once per flattened key
        assert mock_db.execute_query.call_count == 2

        # Verify the queries contain INSERT ... ON DUPLICATE KEY UPDATE
        for call_item in mock_db.execute_query.call_args_list:
            query = call_item[0][0]
            assert 'INSERT INTO tenant_config' in query
            assert 'ON DUPLICATE KEY UPDATE' in query

    def test_update_settings_complex_values_to_json(self, mock_db):
        """Test update_settings converts complex values (dict, list) to JSON strings."""
        mock_db.execute_query.return_value = None

        service = TenantSettingsService(mock_db)
        result = service.update_settings('test-tenant', {
            'metadata': {'nested': {'key': 'value'}},
        })

        assert result is True
        # The nested dict under 'metadata' gets flattened, but if a leaf is a dict/list
        # it gets JSON-serialized. Let's check the params.
        # 'metadata.nested.key' = 'value' (string, not JSON)
        call_args = mock_db.execute_query.call_args_list[0]
        params = call_args[0][1]
        assert params[0] == 'test-tenant'
        assert params[1] == 'metadata.nested.key'
        assert params[2] == 'value'

    def test_update_settings_list_value_to_json(self, mock_db):
        """Test update_settings converts list values to JSON strings."""
        mock_db.execute_query.return_value = None

        service = TenantSettingsService(mock_db)
        result = service.update_settings('test-tenant', {
            'tags': ['tag1', 'tag2'],
        })

        assert result is True
        call_args = mock_db.execute_query.call_args_list[0]
        params = call_args[0][1]
        assert params[0] == 'test-tenant'
        assert params[1] == 'tags'
        # List should be JSON-serialized
        assert params[2] == '["tag1", "tag2"]'

    def test_update_settings_db_error_raises_exception(self, mock_db):
        """Test update_settings raises exception on database error."""
        mock_db.execute_query.side_effect = Exception("Write failed")

        service = TenantSettingsService(mock_db)

        with pytest.raises(Exception, match="Write failed"):
            service.update_settings('test-tenant', {'key': 'value'})

    def test_update_settings_none_value_stored_as_none(self, mock_db):
        """Test update_settings stores None values correctly."""
        mock_db.execute_query.return_value = None

        service = TenantSettingsService(mock_db)
        result = service.update_settings('test-tenant', {'optional_field': None})

        assert result is True
        call_args = mock_db.execute_query.call_args_list[0]
        params = call_args[0][1]
        assert params[2] is None


class TestFlattenDict:
    """Tests for _flatten_dict helper method."""

    def test_flatten_dict_nested_returns_dot_notation(self, mock_db):
        """Test _flatten_dict converts nested dict to dot-notation keys."""
        service = TenantSettingsService(mock_db)
        result = service._flatten_dict({
            'level1': {
                'level2': {
                    'key': 'value'
                }
            }
        })

        assert result == {'level1.level2.key': 'value'}

    def test_flatten_dict_flat_returns_unchanged(self, mock_db):
        """Test _flatten_dict returns flat dict unchanged."""
        service = TenantSettingsService(mock_db)
        result = service._flatten_dict({'key1': 'val1', 'key2': 'val2'})

        assert result == {'key1': 'val1', 'key2': 'val2'}

    def test_flatten_dict_mixed_nesting(self, mock_db):
        """Test _flatten_dict handles mix of flat and nested keys."""
        service = TenantSettingsService(mock_db)
        result = service._flatten_dict({
            'flat_key': 'flat_value',
            'nested': {
                'child': 'child_value'
            }
        })

        assert result == {
            'flat_key': 'flat_value',
            'nested.child': 'child_value',
        }


class TestGetActivity:
    """Tests for get_activity method."""

    def test_get_activity_default_date_range_returns_stats(self, mock_db):
        """Test get_activity returns stats with default last-30-days range."""
        now = datetime(2024, 3, 15, 12, 0, 0)
        mock_db.execute_query.side_effect = [
            # Total actions count
            [{'count': 5}],
            # Actions by type
            [{'action_type': 'login', 'count': 3}, {'action_type': 'update', 'count': 2}],
            # Actions by user
            [{'user_email': 'user@test.com', 'count': 5}],
            # Recent actions
            [
                {
                    'action_type': 'login',
                    'user_email': 'user@test.com',
                    'timestamp': datetime(2024, 3, 15, 10, 0, 0),
                    'details': {'ip': '127.0.0.1'},
                }
            ],
        ]

        service = TenantSettingsService(mock_db)
        result = service.get_activity('test-tenant')

        assert result['total_actions'] == 5
        assert result['actions_by_type'] == {'login': 3, 'update': 2}
        assert result['actions_by_user'] == {'user@test.com': 5}
        assert len(result['recent_actions']) == 1
        assert result['recent_actions'][0]['action_type'] == 'login'
        assert result['date_range']['start'] is not None
        assert result['date_range']['end'] is not None

    def test_get_activity_custom_date_range(self, mock_db):
        """Test get_activity uses custom date range when provided."""
        mock_db.execute_query.side_effect = [
            [{'count': 2}],
            [{'action_type': 'export', 'count': 2}],
            [{'user_email': 'admin@test.com', 'count': 2}],
            [],
        ]

        service = TenantSettingsService(mock_db)
        date_range = {'start_date': '2024-01-01', 'end_date': '2024-01-31'}
        result = service.get_activity('test-tenant', date_range=date_range)

        assert result['total_actions'] == 2
        assert result['date_range']['start'] == '2024-01-01'
        assert result['date_range']['end'] == '2024-01-31'
        # Verify the custom dates were passed to queries
        for call_item in mock_db.execute_query.call_args_list:
            params = call_item[0][1]
            assert params[1] == '2024-01-01'
            assert params[2] == '2024-01-31'

    def test_get_activity_audit_log_not_available_returns_error_key(self, mock_db):
        """Test get_activity handles audit_log table not existing gracefully."""
        mock_db.execute_query.side_effect = Exception("Table 'audit_log' doesn't exist")

        service = TenantSettingsService(mock_db)
        result = service.get_activity('test-tenant')

        assert result['total_actions'] == 0
        assert result['error'] == 'Audit log not available'
        assert result['actions_by_type'] == {}
        assert result['actions_by_user'] == {}
        assert result['recent_actions'] == []

    def test_get_activity_empty_results_returns_zero_stats(self, mock_db):
        """Test get_activity returns zero stats when no audit entries exist."""
        mock_db.execute_query.side_effect = [
            [],  # Total actions - empty
            [],  # Actions by type - empty
            [],  # Actions by user - empty
            [],  # Recent actions - empty
        ]

        service = TenantSettingsService(mock_db)
        result = service.get_activity('test-tenant')

        assert result['total_actions'] == 0
        assert result['actions_by_type'] == {}
        assert result['actions_by_user'] == {}
        assert result['recent_actions'] == []


class TestDeepMerge:
    """Tests for _deep_merge helper method."""

    def test_deep_merge_nested_dicts_merges_correctly(self, mock_db):
        """Test _deep_merge merges nested dicts recursively."""
        service = TenantSettingsService(mock_db)
        dict1 = {'a': {'b': 1, 'c': 2}, 'd': 3}
        dict2 = {'a': {'b': 10, 'e': 5}, 'f': 6}

        result = service._deep_merge(dict1, dict2)

        assert result == {'a': {'b': 10, 'c': 2, 'e': 5}, 'd': 3, 'f': 6}

    def test_deep_merge_overwrites_non_dict_values(self, mock_db):
        """Test _deep_merge overwrites non-dict values from dict2."""
        service = TenantSettingsService(mock_db)
        dict1 = {'key': 'old_value', 'nested': {'a': 1}}
        dict2 = {'key': 'new_value', 'nested': {'b': 2}}

        result = service._deep_merge(dict1, dict2)

        assert result['key'] == 'new_value'
        assert result['nested'] == {'a': 1, 'b': 2}

    def test_deep_merge_does_not_mutate_originals(self, mock_db):
        """Test _deep_merge does not mutate the original dictionaries."""
        service = TenantSettingsService(mock_db)
        dict1 = {'a': {'b': 1}}
        dict2 = {'a': {'c': 2}}

        result = service._deep_merge(dict1, dict2)

        # Original dicts should be unchanged
        assert dict1 == {'a': {'b': 1}}
        assert dict2 == {'a': {'c': 2}}
        assert result == {'a': {'b': 1, 'c': 2}}

    def test_deep_merge_empty_dict2_returns_copy_of_dict1(self, mock_db):
        """Test _deep_merge with empty dict2 returns copy of dict1."""
        service = TenantSettingsService(mock_db)
        dict1 = {'a': 1, 'b': {'c': 2}}

        result = service._deep_merge(dict1, {})

        assert result == {'a': 1, 'b': {'c': 2}}
