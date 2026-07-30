"""
Unit tests for per-tenant MutatiesCache.

Tests tenant partitioning, eviction, thread safety, and backward compatibility.
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime, timedelta
from threading import Thread, Barrier
import time

from mutaties_cache import MutatiesCache, TenantCacheEntry, get_cache, invalidate_cache


def _make_df(tenant="TenantA", year=2025, rows=10):
    """Helper: create a sample DataFrame for a tenant."""
    return pd.DataFrame({
        "Aangifte": ["IB"] * rows,
        "TransactionNumber": [f"T{i}" for i in range(rows)],
        "TransactionDate": pd.to_datetime(f"{year}-06-15"),
        "TransactionDescription": ["Test"] * rows,
        "Amount": [100.0] * rows,
        "Reknum": ["8001"] * rows,
        "AccountName": ["Revenue"] * rows,
        "Parent": ["Income"] * rows,
        "VW": ["Y"] * rows,
        "jaar": [year] * rows,
        "kwartaal": [2] * rows,
        "maand": [6] * rows,
        "week": [24] * rows,
        "ReferenceNumber": ["REF1"] * rows,
        "administration": [tenant] * rows,
        "Ref3": [""] * rows,
        "Ref4": [""] * rows,
    })


class TestTenantCacheEntry:
    """Tests for TenantCacheEntry dataclass."""

    def test_create_entry(self):
        """TenantCacheEntry holds data, timestamps, and years_loaded."""
        df = _make_df()
        now = datetime.now()
        entry = TenantCacheEntry(
            data=df, last_accessed=now, last_loaded=now, years_loaded={2025}
        )
        assert len(entry.data) == 10
        assert entry.last_accessed == now
        assert entry.last_loaded == now
        assert 2025 in entry.years_loaded

    def test_years_loaded_defaults_empty(self):
        """years_loaded defaults to empty set."""
        df = _make_df()
        now = datetime.now()
        entry = TenantCacheEntry(data=df, last_accessed=now, last_loaded=now)
        assert entry.years_loaded == set()


class TestPerTenantGetData:
    """Tests for per-tenant get_data behavior."""

    def test_get_data_with_tenant_loads_per_tenant(self):
        """get_data with tenant loads only that tenant's data."""
        cache = MutatiesCache(ttl_minutes=30)
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        tenant_df = _make_df("TenantA", 2025, 5)

        with patch("pandas.read_sql", return_value=tenant_df):
            result = cache.get_data(mock_db, tenant="TenantA")

        assert len(result) == 5
        assert "TenantA" in cache._tenant_data
        assert cache._tenant_data["TenantA"].data is not None

    def test_get_data_without_tenant_loads_all(self):
        """get_data without tenant uses legacy behavior loading all tenants."""
        cache = MutatiesCache(ttl_minutes=30)
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        df_all = pd.concat([_make_df("A", 2025, 3), _make_df("B", 2025, 4)])

        with patch("pandas.read_sql", return_value=df_all):
            result = cache.get_data(mock_db)

        assert result is not None
        assert len(result) == 7
        assert "A" in cache._tenant_data
        assert "B" in cache._tenant_data

    def test_get_data_uses_cached_data_within_ttl(self):
        """Subsequent calls within TTL return cached data without DB query."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()
        cached_df = _make_df("TenantA", 2025, 8)

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=cached_df,
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        mock_db = MagicMock()
        result = cache.get_data(mock_db, tenant="TenantA")

        assert len(result) == 8
        # No DB call should have been made
        mock_db.get_connection.assert_not_called()

    def test_get_data_refreshes_after_ttl_expires(self):
        """Cache refreshes after TTL expires."""
        cache = MutatiesCache(ttl_minutes=30)
        old_time = datetime.now() - timedelta(minutes=35)
        old_df = _make_df("TenantA", 2025, 5)

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=old_df,
            last_accessed=old_time,
            last_loaded=old_time,
            years_loaded={2025},
        )

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_db.execute_query.return_value = []

        new_df = _make_df("TenantA", 2025, 12)
        with patch("pandas.read_sql", return_value=new_df):
            result = cache.get_data(mock_db, tenant="TenantA")

        assert len(result) == 12

    def test_multiple_tenants_independent(self):
        """Each tenant has independent cache entries."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["A"] = TenantCacheEntry(
            data=_make_df("A", 2025, 3),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )
        cache._tenant_data["B"] = TenantCacheEntry(
            data=_make_df("B", 2025, 7),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        mock_db = MagicMock()
        result_a = cache.get_data(mock_db, tenant="A")
        result_b = cache.get_data(mock_db, tenant="B")

        assert len(result_a) == 3
        assert len(result_b) == 7


class TestEviction:
    """Tests for tenant eviction after 2× TTL inactivity."""

    def test_inactive_tenant_evicted(self):
        """Tenants not accessed for 2× TTL get evicted."""
        cache = MutatiesCache(ttl_minutes=30)
        # Simulate a tenant last accessed 65 minutes ago (> 2×30 = 60)
        old_time = datetime.now() - timedelta(minutes=65)
        now = datetime.now()

        cache._tenant_data["Inactive"] = TenantCacheEntry(
            data=_make_df("Inactive", 2025, 5),
            last_accessed=old_time,
            last_loaded=old_time,
            years_loaded={2025},
        )
        cache._tenant_data["Active"] = TenantCacheEntry(
            data=_make_df("Active", 2025, 5),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        # Trigger eviction
        cache._evict_inactive()

        assert "Inactive" not in cache._tenant_data
        assert "Active" in cache._tenant_data

    def test_active_tenant_not_evicted(self):
        """Tenants accessed within 2× TTL are kept."""
        cache = MutatiesCache(ttl_minutes=30)
        recent_time = datetime.now() - timedelta(minutes=50)  # < 60 min

        cache._tenant_data["Recent"] = TenantCacheEntry(
            data=_make_df("Recent", 2025, 5),
            last_accessed=recent_time,
            last_loaded=recent_time,
            years_loaded={2025},
        )

        cache._evict_inactive()
        assert "Recent" in cache._tenant_data

    def test_eviction_triggered_on_get_data(self):
        """Eviction runs opportunistically during get_data calls."""
        cache = MutatiesCache(ttl_minutes=30)
        old_time = datetime.now() - timedelta(minutes=65)
        now = datetime.now()

        cache._tenant_data["Stale"] = TenantCacheEntry(
            data=_make_df("Stale", 2025, 5),
            last_accessed=old_time,
            last_loaded=old_time,
            years_loaded={2025},
        )
        cache._tenant_data["Fresh"] = TenantCacheEntry(
            data=_make_df("Fresh", 2025, 5),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        mock_db = MagicMock()
        cache.get_data(mock_db, tenant="Fresh")

        assert "Stale" not in cache._tenant_data
        assert "Fresh" in cache._tenant_data


class TestGetStats:
    """Tests for get_stats method."""

    def test_stats_empty_cache(self):
        """Empty cache returns zeroed stats."""
        cache = MutatiesCache(ttl_minutes=30)
        stats = cache.get_stats()

        assert stats["loaded"] is False
        assert stats["tenants_loaded"] == 0
        assert stats["total_rows"] == 0
        assert stats["memory_mb"] == 0.0

    def test_stats_with_tenants(self):
        """Stats reflect loaded tenants."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["A"] = TenantCacheEntry(
            data=_make_df("A", 2025, 10),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )
        cache._tenant_data["B"] = TenantCacheEntry(
            data=_make_df("B", 2025, 20),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        stats = cache.get_stats()

        assert stats["loaded"] is True
        assert stats["tenants_loaded"] == 2
        assert stats["total_rows"] == 30
        assert stats["memory_mb"] > 0
        assert "A" in stats["tenants"]
        assert "B" in stats["tenants"]
        assert stats["tenants"]["A"]["rows"] == 10
        assert stats["tenants"]["B"]["rows"] == 20


class TestGetSnapshot:
    """Tests for get_snapshot backward compatibility."""

    def test_snapshot_returns_tenant_data(self):
        """get_snapshot returns data for the specified tenant."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()
        df = _make_df("TenantA", 2025, 5)

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=df,
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        mock_db = MagicMock()
        snapshot = cache.get_snapshot(mock_db, tenant="TenantA")
        assert len(snapshot) == 5


class TestInvalidate:
    """Tests for invalidate method."""

    def test_invalidate_all(self):
        """invalidate() clears all tenants."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["A"] = TenantCacheEntry(
            data=_make_df("A"), last_accessed=now, last_loaded=now
        )
        cache._tenant_data["B"] = TenantCacheEntry(
            data=_make_df("B"), last_accessed=now, last_loaded=now
        )

        cache.invalidate()
        assert len(cache._tenant_data) == 0

    def test_invalidate_single_tenant(self):
        """invalidate(tenant='A') clears only that tenant."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["A"] = TenantCacheEntry(
            data=_make_df("A"), last_accessed=now, last_loaded=now
        )
        cache._tenant_data["B"] = TenantCacheEntry(
            data=_make_df("B"), last_accessed=now, last_loaded=now
        )

        cache.invalidate(tenant="A")
        assert "A" not in cache._tenant_data
        assert "B" in cache._tenant_data


class TestThreadSafety:
    """Tests for thread safety under concurrent access."""

    def test_concurrent_reads_safe(self):
        """Multiple threads reading the same tenant concurrently is safe."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()
        df = _make_df("Shared", 2025, 100)

        cache._tenant_data["Shared"] = TenantCacheEntry(
            data=df,
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )

        results = []
        errors = []

        def read_cache():
            try:
                mock_db = MagicMock()
                data = cache.get_data(mock_db, tenant="Shared")
                results.append(len(data))
            except Exception as e:
                errors.append(str(e))

        threads = [Thread(target=read_cache) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r == 100 for r in results)

    def test_concurrent_different_tenants(self):
        """Multiple threads accessing different tenants concurrently is safe."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()

        for i in range(5):
            cache._tenant_data[f"Tenant{i}"] = TenantCacheEntry(
                data=_make_df(f"Tenant{i}", 2025, 10 + i),
                last_accessed=now,
                last_loaded=now,
                years_loaded={2025},
            )

        results = {}
        errors = []

        def read_tenant(tenant_id):
            try:
                mock_db = MagicMock()
                data = cache.get_data(mock_db, tenant=tenant_id)
                results[tenant_id] = len(data)
            except Exception as e:
                errors.append(str(e))

        threads = [
            Thread(target=read_tenant, args=(f"Tenant{i}",)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        for i in range(5):
            assert results[f"Tenant{i}"] == 10 + i

    def test_concurrent_read_with_eviction(self):
        """Reading while eviction happens doesn't crash."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()
        old_time = datetime.now() - timedelta(minutes=65)

        cache._tenant_data["Active"] = TenantCacheEntry(
            data=_make_df("Active", 2025, 10),
            last_accessed=now,
            last_loaded=now,
            years_loaded={2025},
        )
        # Add many stale entries to trigger eviction
        for i in range(10):
            cache._tenant_data[f"Stale{i}"] = TenantCacheEntry(
                data=_make_df(f"Stale{i}", 2025, 5),
                last_accessed=old_time,
                last_loaded=old_time,
                years_loaded={2025},
            )

        errors = []

        def trigger_access():
            try:
                mock_db = MagicMock()
                data = cache.get_data(mock_db, tenant="Active")
                assert data is not None
            except Exception as e:
                errors.append(str(e))

        threads = [Thread(target=trigger_access) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert "Active" in cache._tenant_data


class TestBackwardCompatibility:
    """Tests for backward-compatible .data and .last_loaded properties."""

    def test_data_property_returns_combined(self):
        """The .data property returns all tenants combined."""
        cache = MutatiesCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["A"] = TenantCacheEntry(
            data=_make_df("A", 2025, 3),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["B"] = TenantCacheEntry(
            data=_make_df("B", 2025, 4),
            last_accessed=now,
            last_loaded=now,
        )

        combined = cache.data
        assert combined is not None
        assert len(combined) == 7

    def test_data_property_none_when_empty(self):
        """The .data property returns None when no tenants loaded."""
        cache = MutatiesCache(ttl_minutes=30)
        assert cache.data is None

    def test_last_loaded_property(self):
        """The .last_loaded property returns the most recent load time."""
        cache = MutatiesCache(ttl_minutes=30)
        t1 = datetime.now() - timedelta(minutes=10)
        t2 = datetime.now()

        cache._tenant_data["A"] = TenantCacheEntry(
            data=_make_df("A"), last_accessed=t1, last_loaded=t1
        )
        cache._tenant_data["B"] = TenantCacheEntry(
            data=_make_df("B"), last_accessed=t2, last_loaded=t2
        )

        assert cache.last_loaded == t2
