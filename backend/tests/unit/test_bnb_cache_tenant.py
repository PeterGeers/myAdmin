"""
Unit tests for BnbCache per-tenant partitioning.

Tests tenant isolation, eviction of inactive tenants,
get_stats(), and backward compatibility.

Requirements: REQ-2.3
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from bnb_cache import BnbCache, TenantCacheEntry, get_bnb_cache


def _make_sample_data(tenant="TenantA", year=2024, n_rows=3):
    """Helper to create sample BNB data for a tenant."""
    return pd.DataFrame({
        "checkinDate": pd.to_datetime(["2024-01-15"] * n_rows),
        "checkoutDate": pd.to_datetime(["2024-01-18"] * n_rows),
        "channel": ["Airbnb"] * n_rows,
        "listing": ["Property1"] * n_rows,
        "nights": [3.0] * n_rows,
        "amountGross": [300.0] * n_rows,
        "amountNett": [270.0] * n_rows,
        "amountChannelFee": [30.0] * n_rows,
        "amountTouristTax": [9.0] * n_rows,
        "amountVat": [15.0] * n_rows,
        "guestName": ["Guest"] * n_rows,
        "guests": [2.0] * n_rows,
        "reservationCode": ["RES1"] * n_rows,
        "status": ["realised"] * n_rows,
        "source_type": ["actual"] * n_rows,
        "administration": [tenant] * n_rows,
        "year": [year] * n_rows,
        "quarter": [1] * n_rows,
        "month": [1] * n_rows,
    })


class TestPerTenantIsolation:
    """Tests that tenants are stored and retrieved independently."""

    def test_different_tenants_stored_separately(self):
        """Each tenant's data lives in its own cache entry."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        data_a = _make_sample_data("TenantA", n_rows=5)
        data_b = _make_sample_data("TenantB", n_rows=3)

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=data_a, last_accessed=now, last_loaded=now
        )
        cache._tenant_data["TenantB"] = TenantCacheEntry(
            data=data_b, last_accessed=now, last_loaded=now
        )

        assert len(cache._tenant_data) == 2
        assert len(cache._tenant_data["TenantA"].data) == 5
        assert len(cache._tenant_data["TenantB"].data) == 3

    def test_get_data_with_tenant_returns_only_that_tenant(self):
        """get_data(db, tenant='X') returns only X's data, not other tenants'."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        data_a = _make_sample_data("TenantA", n_rows=5)
        data_b = _make_sample_data("TenantB", n_rows=3)

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=data_a, last_accessed=now, last_loaded=now
        )
        cache._tenant_data["TenantB"] = TenantCacheEntry(
            data=data_b, last_accessed=now, last_loaded=now
        )

        mock_db = MagicMock()
        result = cache.get_data(mock_db, tenant="TenantA")

        assert len(result) == 5
        assert all(result["administration"] == "TenantA")

    def test_get_data_tenant_not_loaded_triggers_refresh(self):
        """get_data for unknown tenant triggers a DB load."""
        cache = BnbCache(ttl_minutes=30)
        mock_db = MagicMock()

        fresh_data = _make_sample_data("NewTenant", n_rows=2)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("bnb_cache.pd.read_sql", return_value=fresh_data):
            result = cache.get_data(mock_db, tenant="NewTenant")

        assert len(result) == 2
        assert "NewTenant" in cache._tenant_data

    def test_query_by_year_with_tenant_isolates_data(self):
        """query_by_year with tenant only returns that tenant's bookings."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        data_a = _make_sample_data("TenantA", year=2024, n_rows=4)
        data_b = _make_sample_data("TenantB", year=2024, n_rows=2)

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=data_a, last_accessed=now, last_loaded=now
        )
        cache._tenant_data["TenantB"] = TenantCacheEntry(
            data=data_b, last_accessed=now, last_loaded=now
        )

        mock_db = MagicMock()
        result = cache.query_by_year(mock_db, 2024, tenant="TenantA")

        assert len(result) == 4

    def test_query_cancelled_by_year_with_tenant(self):
        """query_cancelled_by_year respects tenant isolation."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        data = _make_sample_data("TenantA", n_rows=3)
        data.loc[0, "status"] = "cancelled"

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=data, last_accessed=now, last_loaded=now
        )

        mock_db = MagicMock()
        result = cache.query_cancelled_by_year(mock_db, 2024, tenant="TenantA")

        assert len(result) == 1
        assert result[0]["status"] == "cancelled"

    def test_query_realised_by_year_with_tenant(self):
        """query_realised_by_year respects tenant isolation."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        data = _make_sample_data("TenantA", n_rows=4)
        data.loc[0, "status"] = "cancelled"

        cache._tenant_data["TenantA"] = TenantCacheEntry(
            data=data, last_accessed=now, last_loaded=now
        )

        mock_db = MagicMock()
        result = cache.query_realised_by_year(mock_db, 2024, tenant="TenantA")

        assert len(result) == 3


class TestEviction:
    """Tests for inactive tenant eviction (2× TTL)."""

    def test_evict_inactive_removes_old_tenants(self):
        """Tenants not accessed for 2× TTL are evicted."""
        cache = BnbCache(ttl_minutes=30)

        now = datetime.now()
        old_time = now - timedelta(minutes=61)  # Beyond 2×30 = 60 minutes

        cache._tenant_data["ActiveTenant"] = TenantCacheEntry(
            data=_make_sample_data("ActiveTenant"),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["InactiveTenant"] = TenantCacheEntry(
            data=_make_sample_data("InactiveTenant"),
            last_accessed=old_time,
            last_loaded=old_time,
        )

        cache._evict_inactive()

        assert "ActiveTenant" in cache._tenant_data
        assert "InactiveTenant" not in cache._tenant_data

    def test_evict_inactive_keeps_recently_accessed(self):
        """Tenants accessed within 2× TTL are kept."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        # Accessed 50 minutes ago — within 2×30=60 minute threshold
        cache._tenant_data["RecentTenant"] = TenantCacheEntry(
            data=_make_sample_data("RecentTenant"),
            last_accessed=now - timedelta(minutes=50),
            last_loaded=now - timedelta(minutes=50),
        )

        cache._evict_inactive()

        assert "RecentTenant" in cache._tenant_data

    def test_eviction_triggered_on_get_data(self):
        """Eviction runs opportunistically when get_data is called."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()
        old_time = now - timedelta(minutes=61)

        cache._tenant_data["Active"] = TenantCacheEntry(
            data=_make_sample_data("Active"),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["Stale"] = TenantCacheEntry(
            data=_make_sample_data("Stale"),
            last_accessed=old_time,
            last_loaded=old_time,
        )

        mock_db = MagicMock()
        cache.get_data(mock_db, tenant="Active")

        assert "Stale" not in cache._tenant_data
        assert "Active" in cache._tenant_data

    def test_eviction_with_no_inactive_tenants_does_nothing(self):
        """No tenants evicted when all are active."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1"),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["T2"] = TenantCacheEntry(
            data=_make_sample_data("T2"),
            last_accessed=now - timedelta(minutes=10),
            last_loaded=now - timedelta(minutes=10),
        )

        cache._evict_inactive()

        assert len(cache._tenant_data) == 2


class TestGetStats:
    """Tests for get_stats() method."""

    def test_get_stats_empty_cache(self):
        """Empty cache returns zeroes."""
        cache = BnbCache(ttl_minutes=30)
        stats = cache.get_stats()

        assert stats["loaded"] is False
        assert stats["tenants_loaded"] == 0
        assert stats["total_rows"] == 0
        assert stats["memory_mb"] == 0.0

    def test_get_stats_with_data(self):
        """Stats reflect loaded tenants."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1", n_rows=5),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["T2"] = TenantCacheEntry(
            data=_make_sample_data("T2", n_rows=3),
            last_accessed=now,
            last_loaded=now,
        )

        stats = cache.get_stats()

        assert stats["loaded"] is True
        assert stats["tenants_loaded"] == 2
        assert stats["total_rows"] == 8
        assert stats["memory_mb"] >= 0
        assert "T1" in stats["tenants"]
        assert "T2" in stats["tenants"]
        assert stats["tenants"]["T1"]["rows"] == 5
        assert stats["tenants"]["T2"]["rows"] == 3


class TestInvalidate:
    """Tests for invalidate with tenant parameter."""

    def test_invalidate_all_clears_everything(self):
        """invalidate() without tenant clears all tenants."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1"),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["T2"] = TenantCacheEntry(
            data=_make_sample_data("T2"),
            last_accessed=now,
            last_loaded=now,
        )

        cache.invalidate()

        assert len(cache._tenant_data) == 0

    def test_invalidate_single_tenant(self):
        """invalidate(tenant='X') removes only X."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1"),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["T2"] = TenantCacheEntry(
            data=_make_sample_data("T2"),
            last_accessed=now,
            last_loaded=now,
        )

        cache.invalidate(tenant="T1")

        assert "T1" not in cache._tenant_data
        assert "T2" in cache._tenant_data


class TestBackwardCompatibility:
    """Tests that legacy (tenant=None) callers still work."""

    def test_get_data_without_tenant_returns_all_data(self):
        """get_data(db) with no tenant returns combined data from all tenants."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1", n_rows=2),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["T2"] = TenantCacheEntry(
            data=_make_sample_data("T2", n_rows=3),
            last_accessed=now,
            last_loaded=now,
        )

        mock_db = MagicMock()
        result = cache.get_data(mock_db, tenant=None)

        # Combined should have all 5 rows
        assert len(result) == 5

    def test_data_property_backward_compat(self):
        """The .data property returns combined DataFrame."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1", n_rows=2),
            last_accessed=now,
            last_loaded=now,
        )

        assert cache.data is not None
        assert len(cache.data) == 2

    def test_data_property_none_when_empty(self):
        """The .data property returns None when no tenants loaded."""
        cache = BnbCache(ttl_minutes=30)
        assert cache.data is None

    def test_data_setter_splits_by_administration(self):
        """Setting .data splits by administration column."""
        cache = BnbCache(ttl_minutes=30)

        combined = pd.concat([
            _make_sample_data("T1", n_rows=2),
            _make_sample_data("T2", n_rows=3),
        ], ignore_index=True)

        cache.data = combined

        assert "T1" in cache._tenant_data
        assert "T2" in cache._tenant_data
        assert len(cache._tenant_data["T1"].data) == 2
        assert len(cache._tenant_data["T2"].data) == 3

    def test_get_status_backward_compat(self):
        """get_status() still returns the expected shape."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1", n_rows=5),
            last_accessed=now,
            last_loaded=now,
        )

        status = cache.get_status()

        assert status["loaded"] is True
        assert status["row_count"] == 5
        assert status["memory_mb"] >= 0
        assert "ttl_minutes" in status
        assert "is_valid" in status

    def test_query_by_year_without_tenant_uses_all_data(self):
        """query_by_year without tenant queries all cached data."""
        cache = BnbCache(ttl_minutes=30)
        now = datetime.now()

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1", year=2024, n_rows=2),
            last_accessed=now,
            last_loaded=now,
        )
        cache._tenant_data["T2"] = TenantCacheEntry(
            data=_make_sample_data("T2", year=2024, n_rows=3),
            last_accessed=now,
            last_loaded=now,
        )

        mock_db = MagicMock()
        result = cache.query_by_year(mock_db, 2024)

        assert len(result) == 5


class TestRefreshWithTenant:
    """Tests for refresh with tenant parameter."""

    def test_refresh_with_tenant_loads_only_that_tenant(self):
        """refresh(db, tenant='X') only loads X's data."""
        cache = BnbCache(ttl_minutes=30)
        mock_db = MagicMock()

        data = _make_sample_data("TenantX", n_rows=4)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("bnb_cache.pd.read_sql", return_value=data):
            cache.refresh(mock_db, tenant="TenantX")

        assert "TenantX" in cache._tenant_data
        assert len(cache._tenant_data["TenantX"].data) == 4

    def test_refresh_all_splits_by_administration(self):
        """refresh(db) without tenant loads all and splits by administration."""
        cache = BnbCache(ttl_minutes=30)
        mock_db = MagicMock()

        combined = pd.concat([
            _make_sample_data("T1", n_rows=3),
            _make_sample_data("T2", n_rows=2),
        ], ignore_index=True)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("bnb_cache.pd.read_sql", return_value=combined):
            cache.refresh(mock_db)

        assert "T1" in cache._tenant_data
        assert "T2" in cache._tenant_data
        assert len(cache._tenant_data["T1"].data) == 3
        assert len(cache._tenant_data["T2"].data) == 2


class TestTTLAndAccess:
    """Tests for TTL tracking and last_accessed updates."""

    def test_get_data_updates_last_accessed(self):
        """Accessing data updates the last_accessed timestamp."""
        cache = BnbCache(ttl_minutes=30)
        old_time = datetime.now() - timedelta(minutes=10)

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1"),
            last_accessed=old_time,
            last_loaded=datetime.now(),
        )

        mock_db = MagicMock()
        cache.get_data(mock_db, tenant="T1")

        # last_accessed should be updated to now
        assert cache._tenant_data["T1"].last_accessed > old_time

    def test_stale_tenant_triggers_refresh(self):
        """Tenant with expired TTL triggers a refresh."""
        cache = BnbCache(ttl_minutes=30)
        stale_time = datetime.now() - timedelta(minutes=31)

        cache._tenant_data["T1"] = TenantCacheEntry(
            data=_make_sample_data("T1", n_rows=1),
            last_accessed=stale_time,
            last_loaded=stale_time,
        )

        mock_db = MagicMock()
        fresh_data = _make_sample_data("T1", n_rows=5)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_cursor.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.get_cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("bnb_cache.pd.read_sql", return_value=fresh_data):
            result = cache.get_data(mock_db, tenant="T1")

        assert len(result) == 5
        assert (datetime.now() - cache._tenant_data["T1"].last_loaded).total_seconds() < 5
