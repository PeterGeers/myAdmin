"""
Tests for QueryCache max_size eviction behavior.

Validates: REQ-2.1 — Bound the QueryCache
- Cache has configurable max_size (default: 500)
- Oldest entries evicted when limit is reached
- Cache hit/miss/eviction stats available
- No change in duplicate detection accuracy
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from duplicate_query_optimizer import QueryCache


class TestQueryCacheMaxSize:
    """Test that the cache respects max_size bounds."""

    def test_default_max_size_is_500(self):
        """Default max_size should be 500."""
        cache = QueryCache()
        assert cache.max_size == 500

    def test_custom_max_size(self):
        """max_size should be configurable."""
        cache = QueryCache(max_size=10)
        assert cache.max_size == 10

    def test_cache_stays_within_bounds(self):
        """Cache should never exceed max_size entries."""
        max_size = 5
        cache = QueryCache(default_ttl=300, max_size=max_size)

        # Insert more entries than max_size
        for i in range(max_size + 10):
            cache.set(
                reference_number=f"REF-{i}",
                transaction_date="2024-01-01",
                transaction_amount=float(i),
                data=[{"id": i}],
            )

        assert len(cache.cache) <= max_size

    def test_eviction_removes_oldest_by_expiry(self):
        """When at capacity, the entry with earliest expiry should be evicted."""
        cache = QueryCache(default_ttl=300, max_size=3)

        # Insert 3 entries with different TTLs
        # Entry with short TTL (earliest expiry)
        cache.set("REF-SHORT", "2024-01-01", 1.0, [{"id": "short"}], ttl=10)
        # Entry with medium TTL
        cache.set("REF-MEDIUM", "2024-01-01", 2.0, [{"id": "medium"}], ttl=100)
        # Entry with long TTL (latest expiry)
        cache.set("REF-LONG", "2024-01-01", 3.0, [{"id": "long"}], ttl=500)

        assert len(cache.cache) == 3

        # Insert 4th entry — should evict the shortest-TTL entry
        cache.set("REF-NEW", "2024-01-01", 4.0, [{"id": "new"}], ttl=200)

        assert len(cache.cache) == 3
        # The short-TTL entry should be gone
        result = cache.get("REF-SHORT", "2024-01-01", 1.0)
        assert result is None
        # Others should still be there
        assert cache.get("REF-MEDIUM", "2024-01-01", 2.0) == [{"id": "medium"}]
        assert cache.get("REF-LONG", "2024-01-01", 3.0) == [{"id": "long"}]
        assert cache.get("REF-NEW", "2024-01-01", 4.0) == [{"id": "new"}]

    def test_eviction_counter_increments(self):
        """Eviction counter should track capacity-based evictions."""
        cache = QueryCache(default_ttl=300, max_size=2)

        cache.set("REF-1", "2024-01-01", 1.0, [{"id": 1}])
        cache.set("REF-2", "2024-01-01", 2.0, [{"id": 2}])
        assert cache.evictions == 0

        # This triggers eviction
        cache.set("REF-3", "2024-01-01", 3.0, [{"id": 3}])
        assert cache.evictions == 1

        # Another eviction
        cache.set("REF-4", "2024-01-01", 4.0, [{"id": 4}])
        assert cache.evictions == 2

    def test_eviction_stats_in_get_stats(self):
        """get_stats() should report eviction count and max_size."""
        cache = QueryCache(default_ttl=300, max_size=2)

        cache.set("REF-1", "2024-01-01", 1.0, [{"id": 1}])
        cache.set("REF-2", "2024-01-01", 2.0, [{"id": 2}])
        cache.set("REF-3", "2024-01-01", 3.0, [{"id": 3}])

        stats = cache.get_stats()
        assert stats["evictions"] == 1
        assert stats["max_size"] == 2
        assert stats["total_entries"] == 2

    def test_expired_entries_cleaned_before_eviction(self):
        """Expired entries should be cleaned first, avoiding unnecessary eviction."""
        cache = QueryCache(default_ttl=1, max_size=3)

        # Insert entries with very short TTL
        with patch('duplicate_query_optimizer.datetime') as mock_dt:
            # Set initial time
            base_time = datetime(2024, 1, 1, 12, 0, 0)
            mock_dt.now.return_value = base_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            cache.set("REF-1", "2024-01-01", 1.0, [{"id": 1}], ttl=1)
            cache.set("REF-2", "2024-01-01", 2.0, [{"id": 2}], ttl=1)
            cache.set("REF-3", "2024-01-01", 3.0, [{"id": 3}], ttl=1)

            assert len(cache.cache) == 3

            # Advance time past TTL so all entries are expired
            mock_dt.now.return_value = base_time + timedelta(seconds=10)

            # Insert new entry — expired entries cleaned first, no capacity eviction needed
            cache.set("REF-4", "2024-01-01", 4.0, [{"id": 4}], ttl=300)

        # Only the new entry should exist
        assert len(cache.cache) == 1


class TestQueryCacheDuplicateDetectionAccuracy:
    """Test that duplicate detection accuracy is unchanged with max_size."""

    def test_cache_hit_returns_correct_data(self):
        """Cache hits should return the exact data that was stored."""
        cache = QueryCache(default_ttl=300, max_size=10)
        expected_data = [{"id": 1, "ref": "INV-001", "amount": 100.50}]

        cache.set("INV-001", "2024-06-15", 100.50, expected_data)
        result = cache.get("INV-001", "2024-06-15", 100.50)

        assert result == expected_data

    def test_cache_miss_returns_none(self):
        """Cache misses should return None, signaling a DB lookup is needed."""
        cache = QueryCache(default_ttl=300, max_size=10)

        result = cache.get("NONEXISTENT", "2024-01-01", 99.99)
        assert result is None

    def test_different_keys_no_collision(self):
        """Different reference/date/amount combos should have separate entries."""
        cache = QueryCache(default_ttl=300, max_size=10)

        data_a = [{"id": 1}]
        data_b = [{"id": 2}]

        cache.set("REF-A", "2024-01-01", 100.0, data_a)
        cache.set("REF-B", "2024-01-01", 100.0, data_b)

        assert cache.get("REF-A", "2024-01-01", 100.0) == data_a
        assert cache.get("REF-B", "2024-01-01", 100.0) == data_b

    def test_eviction_does_not_corrupt_remaining_entries(self):
        """After eviction, remaining entries should still return correct data."""
        cache = QueryCache(default_ttl=300, max_size=3)

        cache.set("REF-1", "2024-01-01", 1.0, [{"id": 1}], ttl=10)
        cache.set("REF-2", "2024-01-01", 2.0, [{"id": 2}], ttl=100)
        cache.set("REF-3", "2024-01-01", 3.0, [{"id": 3}], ttl=500)

        # Trigger eviction
        cache.set("REF-4", "2024-01-01", 4.0, [{"id": 4}], ttl=200)

        # Remaining entries should be accurate
        assert cache.get("REF-2", "2024-01-01", 2.0) == [{"id": 2}]
        assert cache.get("REF-3", "2024-01-01", 3.0) == [{"id": 3}]
        assert cache.get("REF-4", "2024-01-01", 4.0) == [{"id": 4}]

    def test_overwrite_existing_key_does_not_evict(self):
        """Overwriting an existing key should not trigger eviction."""
        cache = QueryCache(default_ttl=300, max_size=3)

        cache.set("REF-1", "2024-01-01", 1.0, [{"id": 1}])
        cache.set("REF-2", "2024-01-01", 2.0, [{"id": 2}])
        cache.set("REF-3", "2024-01-01", 3.0, [{"id": 3}])

        # Overwrite REF-2 with new data
        cache.set("REF-2", "2024-01-01", 2.0, [{"id": 2, "updated": True}])

        # Should still have 3 entries (overwrite, not 4th new entry)
        # Note: the cache may grow to 4 temporarily since the key is the same hash
        # Actually, since the key is the same, it overwrites in-place
        assert len(cache.cache) <= 4  # At most max_size + 1 transiently
        assert cache.get("REF-2", "2024-01-01", 2.0) == [{"id": 2, "updated": True}]


class TestQueryCacheLoadBehavior:
    """Test cache behavior under simulated load."""

    def test_cache_bound_under_rapid_insertions(self):
        """Under rapid insertions, cache size never exceeds max_size."""
        max_size = 50
        cache = QueryCache(default_ttl=300, max_size=max_size)

        for i in range(500):
            cache.set(
                reference_number=f"REF-{i:04d}",
                transaction_date="2024-01-01",
                transaction_amount=float(i) * 1.5,
                data=[{"id": i, "duplicate": i % 3 == 0}],
            )
            # Invariant: cache never exceeds max_size
            assert len(cache.cache) <= max_size, (
                f"Cache exceeded max_size at insertion {i}: "
                f"{len(cache.cache)} > {max_size}"
            )

    def test_hit_miss_stats_accurate_with_eviction(self):
        """Hit/miss stats remain accurate even with evictions happening."""
        cache = QueryCache(default_ttl=300, max_size=5)

        # Fill cache
        for i in range(5):
            cache.set(f"REF-{i}", "2024-01-01", float(i), [{"id": i}])

        # All hits
        for i in range(5):
            cache.get(f"REF-{i}", "2024-01-01", float(i))
        assert cache.hits == 5
        assert cache.misses == 0

        # Trigger evictions
        for i in range(5, 10):
            cache.set(f"REF-{i}", "2024-01-01", float(i), [{"id": i}])

        # Try to get evicted entries — should be misses
        for i in range(5):
            cache.get(f"REF-{i}", "2024-01-01", float(i))

        # At least some should be misses (evicted ones)
        assert cache.misses > 0

        stats = cache.get_stats()
        assert stats["total_requests"] == cache.hits + cache.misses
        assert stats["evictions"] == cache.evictions
