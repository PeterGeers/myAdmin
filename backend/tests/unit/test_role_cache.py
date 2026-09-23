"""Unit tests for auth.role_cache — focus on the negative-result (empty) policy.

The key behaviour under test: a populated role list is cached for the TTL, but an
EMPTY result is NOT cached, so a role granted out-of-band (direct SQL / seed
script — not via the tenant-admin routes that call invalidate_cache) is picked up
on the very next request rather than being pinned to a stale "no roles" answer.

Uses the shared ``mock_db`` fixture (tests/conftest.py) per backend testing
standards — no ad-hoc DB mocks, no real connections (autouse guard enforces this).
"""

import pytest

import auth.role_cache as role_cache


@pytest.fixture(autouse=True)
def _clear_role_cache():
    """Clear the process-global cache around each test so they don't leak."""
    role_cache._role_cache.clear()
    yield
    role_cache._role_cache.clear()


def test_get_tenant_roles_populated_result_is_cached(mock_db):
    mock_db.execute_query.return_value = [
        {"role": "Tenant_Admin"},
        {"role": "Members_CRUD"},
    ]

    first = role_cache.get_tenant_roles("webmaster@h-dcn.nl", "h-dcn", mock_db)
    second = role_cache.get_tenant_roles("webmaster@h-dcn.nl", "h-dcn", mock_db)

    assert first == ["Tenant_Admin", "Members_CRUD"]
    assert second == ["Tenant_Admin", "Members_CRUD"]
    # Cached: the DB was hit only once despite two calls.
    assert mock_db.execute_query.call_count == 1


def test_get_tenant_roles_empty_result_is_not_cached(mock_db):
    mock_db.execute_query.return_value = []

    role_cache.get_tenant_roles("new@h-dcn.nl", "h-dcn", mock_db)
    role_cache.get_tenant_roles("new@h-dcn.nl", "h-dcn", mock_db)

    # Not cached: every call re-queries the DB.
    assert mock_db.execute_query.call_count == 2
    assert "new@h-dcn.nl:h-dcn" not in role_cache._role_cache


def test_get_tenant_roles_out_of_band_grant_seen_on_next_request(mock_db):
    """The exact scenario that caused the 'role not assigned' symptom."""
    # 1st request: no roles yet (empty). 2nd request: role now present in DB
    # (inserted out-of-band, so no invalidate_cache was called).
    mock_db.execute_query.side_effect = [[], [{"role": "Tenant_Admin"}]]

    before = role_cache.get_tenant_roles("webmaster@h-dcn.nl", "h-dcn", mock_db)
    after = role_cache.get_tenant_roles("webmaster@h-dcn.nl", "h-dcn", mock_db)

    assert before == []
    assert after == ["Tenant_Admin"]  # picked up immediately, no TTL wait


def test_invalidate_cache_forces_requery(mock_db):
    mock_db.execute_query.return_value = [{"role": "Finance_CRUD"}]

    role_cache.get_tenant_roles("u@t.nl", "t", mock_db)      # caches
    role_cache.invalidate_cache("u@t.nl", "t")               # clears
    role_cache.get_tenant_roles("u@t.nl", "t", mock_db)      # must re-query

    assert mock_db.execute_query.call_count == 2
