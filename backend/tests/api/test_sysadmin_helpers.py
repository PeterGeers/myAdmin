"""
API tests for sysadmin_helpers.py (unit-level helper function tests).

Tests helper functions used by sysadmin routes: attribute extraction,
user group retrieval, tenant user operations, and name validation.

Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestGetUserAttribute:
    """Tests for get_user_attribute helper function."""

    def test_get_user_attribute_extracts_email_correctly(self):
        """Should extract email attribute from Cognito user object."""
        from routes.sysadmin_helpers import get_user_attribute

        user = {
            'Username': 'test-user',
            'Attributes': [
                {'Name': 'email', 'Value': 'user@example.com'},
                {'Name': 'sub', 'Value': 'abc-123'},
            ]
        }
        result = get_user_attribute(user, 'email')
        assert result == 'user@example.com'

    def test_get_user_attribute_handles_custom_tenants_json_parsing(self):
        """Should parse custom:tenants JSON array attribute."""
        from routes.sysadmin_helpers import get_user_attribute

        user = {
            'Username': 'test-user',
            'Attributes': [
                {'Name': 'custom:tenants', 'Value': '["tenant-a","tenant-b"]'},
            ]
        }
        result = get_user_attribute(user, 'custom:tenants')
        assert isinstance(result, list)
        assert 'tenant-a' in result
        assert 'tenant-b' in result

    def test_get_user_attribute_returns_none_for_missing_attribute(self):
        """Should return None when attribute is not present."""
        from routes.sysadmin_helpers import get_user_attribute

        user = {
            'Username': 'test-user',
            'Attributes': [
                {'Name': 'email', 'Value': 'user@example.com'},
            ]
        }
        result = get_user_attribute(user, 'phone_number')
        assert result is None

    def test_get_user_attribute_handles_empty_attributes_list(self):
        """Should return None when Attributes list is empty."""
        from routes.sysadmin_helpers import get_user_attribute

        user = {'Username': 'test-user', 'Attributes': []}
        result = get_user_attribute(user, 'email')
        assert result is None

    def test_get_user_attribute_handles_escaped_tenants_json(self):
        """Should handle escaped quotes in custom:tenants value."""
        from routes.sysadmin_helpers import get_user_attribute

        user = {
            'Username': 'test-user',
            'Attributes': [
                {'Name': 'custom:tenants', 'Value': '[\\"tenant-a\\",\\"tenant-b\\"]'},
            ]
        }
        result = get_user_attribute(user, 'custom:tenants')
        assert isinstance(result, list)
        assert 'tenant-a' in result


class TestValidateAdministrationName:
    """Tests for validate_administration_name helper function."""

    def test_validate_administration_name_valid_name_passes(self):
        """A valid administration name should pass validation."""
        from routes.sysadmin_helpers import validate_administration_name

        is_valid, error = validate_administration_name('my-tenant')
        assert is_valid is True
        assert error is None

    def test_validate_administration_name_too_short_fails(self):
        """Name shorter than 3 characters should fail."""
        from routes.sysadmin_helpers import validate_administration_name

        is_valid, error = validate_administration_name('ab')
        assert is_valid is False
        assert 'at least 3' in error.lower()

    def test_validate_administration_name_starts_with_number_fails(self):
        """Name starting with a number should fail."""
        from routes.sysadmin_helpers import validate_administration_name

        is_valid, error = validate_administration_name('1tenant')
        assert is_valid is False
        assert 'start with a letter' in error.lower()

    def test_validate_administration_name_contains_spaces_fails(self):
        """Name containing spaces should fail."""
        from routes.sysadmin_helpers import validate_administration_name

        is_valid, error = validate_administration_name('my tenant')
        assert is_valid is False
        # The validation catches spaces via the alphanumeric check
        assert error is not None

    def test_validate_administration_name_with_underscores_passes(self):
        """Name with underscores should pass."""
        from routes.sysadmin_helpers import validate_administration_name

        is_valid, error = validate_administration_name('my_tenant_name')
        assert is_valid is True
        assert error is None

    def test_validate_administration_name_empty_fails(self):
        """Empty name should fail."""
        from routes.sysadmin_helpers import validate_administration_name

        is_valid, error = validate_administration_name('')
        assert is_valid is False
        assert 'required' in error.lower()


class TestGetUserGroups:
    """Tests for get_user_groups with mocked Cognito client."""

    @patch('routes.sysadmin_helpers.cognito_client')
    def test_get_user_groups_returns_group_names(self, mock_cognito):
        """Should return list of group names for a user."""
        from routes.sysadmin_helpers import get_user_groups

        mock_cognito.admin_list_groups_for_user.return_value = {
            'Groups': [
                {'GroupName': 'TenantAdmin'},
                {'GroupName': 'Finance_CRUD'},
            ]
        }

        result = get_user_groups('test-user')
        assert result == ['TenantAdmin', 'Finance_CRUD']

    @patch('routes.sysadmin_helpers.cognito_client')
    def test_get_user_groups_returns_empty_on_error(self, mock_cognito):
        """Should return empty list when Cognito call fails."""
        from routes.sysadmin_helpers import get_user_groups

        mock_cognito.admin_list_groups_for_user.side_effect = Exception('Cognito error')

        result = get_user_groups('test-user')
        assert result == []


class TestGetTenantUserCount:
    """Tests for get_tenant_user_count with mocked Cognito client."""

    @patch('routes.sysadmin_helpers.cognito_client')
    def test_get_tenant_user_count_counts_matching_users(self, mock_cognito):
        """Should count users that have the specified tenant in custom:tenants."""
        from routes.sysadmin_helpers import get_tenant_user_count

        mock_cognito.list_users.return_value = {
            'Users': [
                {
                    'Username': 'user1',
                    'Attributes': [
                        {'Name': 'custom:tenants', 'Value': '["tenant-a","tenant-b"]'}
                    ]
                },
                {
                    'Username': 'user2',
                    'Attributes': [
                        {'Name': 'custom:tenants', 'Value': '["tenant-a"]'}
                    ]
                },
                {
                    'Username': 'user3',
                    'Attributes': [
                        {'Name': 'custom:tenants', 'Value': '["tenant-c"]'}
                    ]
                },
            ]
        }

        result = get_tenant_user_count('tenant-a')
        assert result == 2
