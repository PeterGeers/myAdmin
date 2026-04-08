"""Unit tests for per-tenant role cache."""

import time
import pytest
from unittest.mock import Mock

from auth.role_cache import get_tenant_roles, invalidate_cache, _role_cache, CACHE_TTL_SECONDS


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the role cache before and after each test."""
    _role_cache.clear()
    yield
    _role_cache.clear()


@pytest.fixture
def mock_db():
    """Mock DatabaseManager that returns dict rows."""
    db = Mock()
    db.execute_query.return_value = [
        {'role': 'Finance_CRUD'},
        {'role': 'STR_Read'}
    ]
    return db


class TestCacheMiss:
    """First call for a user+tenant should hit the DB."""

    def test_queries_db_on_first_call(self, mock_db):
        roles = get_tenant_roles('user@example.com', 'TenantA', mock_db)

        assert roles == ['Finance_CRUD', 'STR_Read']
        mock_db.execute_query.assert_called_once_with(
            "SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s",
            ('user@example.com', 'TenantA'),
            fetch=True
        )

    def test_empty_result_returns_empty_list(self, mock_db):
        mock_db.execute_query.return_value = []
        roles = get_tenant_roles('nobody@example.com', 'TenantA', mock_db)

        assert roles == []

    def test_none_result_returns_empty_list(self, mock_db):
        mock_db.execute_query.return_value = None
        roles = get_tenant_roles('nobody@example.com', 'TenantA', mock_db)

        assert roles == []


class TestCacheHit:
    """Second call within TTL should use cache, not DB."""

    def test_second_call_uses_cache(self, mock_db):
        get_tenant_roles('user@example.com', 'TenantA', mock_db)
        get_tenant_roles('user@example.com', 'TenantA', mock_db)

        assert mock_db.execute_query.call_count == 1

    def test_different_tenant_is_separate_cache_entry(self, mock_db):
        mock_db.execute_query.side_effect = [
            [{'role': 'Finance_CRUD'}],
            [{'role': 'STR_Read'}]
        ]

        roles_a = get_tenant_roles('user@example.com', 'TenantA', mock_db)
        roles_b = get_tenant_roles('user@example.com', 'TenantB', mock_db)

        assert roles_a == ['Finance_CRUD']
        assert roles_b == ['STR_Read']
        assert mock_db.execute_query.call_count == 2


class TestTTLExpiry:
    """Cache entries should expire after CACHE_TTL_SECONDS."""

    def test_expired_entry_triggers_db_query(self, mock_db):
        get_tenant_roles('user@example.com', 'TenantA', mock_db)

        # Manually expire the cache entry
        key = 'user@example.com:TenantA'
        roles, _ = _role_cache[key]
        _role_cache[key] = (roles, time.time() - CACHE_TTL_SECONDS - 1)

        get_tenant_roles('user@example.com', 'TenantA', mock_db)

        assert mock_db.execute_query.call_count == 2


class TestInvalidation:
    """invalidate_cache should remove the entry so next call hits DB."""

    def test_invalidate_forces_db_lookup(self, mock_db):
        get_tenant_roles('user@example.com', 'TenantA', mock_db)
        invalidate_cache('user@example.com', 'TenantA')
        get_tenant_roles('user@example.com', 'TenantA', mock_db)

        assert mock_db.execute_query.call_count == 2

    def test_invalidate_nonexistent_key_is_safe(self):
        # Should not raise
        invalidate_cache('nobody@example.com', 'NoTenant')

    def test_invalidate_one_tenant_keeps_other(self, mock_db):
        mock_db.execute_query.side_effect = [
            [{'role': 'Finance_CRUD'}],
            [{'role': 'STR_Read'}],
            [{'role': 'Finance_CRUD'}]
        ]

        get_tenant_roles('user@example.com', 'TenantA', mock_db)
        get_tenant_roles('user@example.com', 'TenantB', mock_db)

        invalidate_cache('user@example.com', 'TenantA')

        # TenantB should still be cached (no extra DB call)
        get_tenant_roles('user@example.com', 'TenantB', mock_db)
        assert mock_db.execute_query.call_count == 2

        # TenantA should hit DB again
        get_tenant_roles('user@example.com', 'TenantA', mock_db)
        assert mock_db.execute_query.call_count == 3
