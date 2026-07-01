"""
Query Optimization for Duplicate Detection System

This module provides query optimization, caching, and performance tuning
specifically for duplicate detection database operations.

Requirements: 5.5, 6.4
"""

import hashlib
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class QueryCache:
    """
    Simple in-memory cache for duplicate detection queries.

    Implements TTL-based caching with automatic expiration.
    """

    def __init__(self, default_ttl: int = 300):
        """
        Initialize query cache.

        Args:
            default_ttl: Default time-to-live in seconds (default: 5 minutes)
        """
        self.cache = {}
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _generate_cache_key(
        self, reference_number: str, transaction_date: str, transaction_amount: float
    ) -> str:
        """
        Generate cache key for duplicate check query.

        Args:
            reference_number: Reference number to check
            transaction_date: Transaction date
            transaction_amount: Transaction amount

        Returns:
            Cache key string
        """
        key_data = f"{reference_number}|{transaction_date}|{transaction_amount}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(
        self, reference_number: str, transaction_date: str, transaction_amount: float
    ) -> Optional[List[Dict]]:
        """
        Get cached duplicate check result.

        Args:
            reference_number: Reference number to check
            transaction_date: Transaction date
            transaction_amount: Transaction amount

        Returns:
            Cached result or None if not found/expired
        """
        cache_key = self._generate_cache_key(
            reference_number, transaction_date, transaction_amount
        )

        if cache_key in self.cache:
            entry = self.cache[cache_key]

            # Check if entry has expired
            if datetime.now() < entry["expires_at"]:
                self.hits += 1
                logger.debug(f"Cache hit for key: {cache_key}")
                return entry["data"]
            else:
                # Remove expired entry
                del self.cache[cache_key]
                self.evictions += 1
                logger.debug(f"Cache entry expired: {cache_key}")

        self.misses += 1
        logger.debug(f"Cache miss for key: {cache_key}")
        return None

    def set(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float,
        data: List[Dict],
        ttl: Optional[int] = None,
    ) -> None:
        """
        Store duplicate check result in cache.

        Args:
            reference_number: Reference number
            transaction_date: Transaction date
            transaction_amount: Transaction amount
            data: Query result to cache
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        cache_key = self._generate_cache_key(
            reference_number, transaction_date, transaction_amount
        )

        ttl = ttl or self.default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)

        self.cache[cache_key] = {
            "data": data,
            "cached_at": datetime.now(),
            "expires_at": expires_at,
            "ttl": ttl,
        }

        logger.debug(f"Cached result for key: {cache_key} (TTL: {ttl}s)")

    def invalidate(
        self,
        reference_number: Optional[str] = None,
        transaction_date: Optional[str] = None,
        transaction_amount: Optional[float] = None,
    ) -> int:
        """
        Invalidate cache entries.

        If all parameters are provided, invalidates specific entry.
        If no parameters provided, clears entire cache.

        Args:
            reference_number: Reference number to invalidate
            transaction_date: Transaction date to invalidate
            transaction_amount: Transaction amount to invalidate

        Returns:
            Number of entries invalidated
        """
        if reference_number and transaction_date and transaction_amount:
            # Invalidate specific entry
            cache_key = self._generate_cache_key(
                reference_number, transaction_date, transaction_amount
            )
            if cache_key in self.cache:
                del self.cache[cache_key]
                logger.info(f"Invalidated cache entry: {cache_key}")
                return 1
            return 0
        else:
            # Clear entire cache
            count = len(self.cache)
            self.cache.clear()
            logger.info(f"Cleared entire cache: {count} entries")
            return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries removed
        """
        now = datetime.now()
        expired_keys = [
            key for key, entry in self.cache.items() if now >= entry["expires_at"]
        ]

        for key in expired_keys:
            del self.cache[key]

        self.evictions += len(expired_keys)

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "total_entries": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "evictions": self.evictions,
            "total_requests": total_requests,
        }

    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0


class DuplicateQueryOptimizer:
    """
    Query optimizer for duplicate detection operations.

    Provides query optimization, execution planning, and performance tuning.
    """

    def __init__(self, db_manager, cache_ttl: int = 300):
        """
        Initialize query optimizer.

        Args:
            db_manager: DatabaseManager instance
            cache_ttl: Cache time-to-live in seconds
        """
        self.db = db_manager
        self.cache = QueryCache(default_ttl=cache_ttl)
        self.query_stats = {
            "total_queries": 0,
            "cached_queries": 0,
            "optimized_queries": 0,
            "slow_queries": 0,
        }


# Global query optimizer instance
_global_optimizer = None


def get_query_optimizer(
    db_manager=None, cache_ttl: int = 300
) -> DuplicateQueryOptimizer:
    """
    Get or create global query optimizer instance.

    Args:
        db_manager: DatabaseManager instance (required for first call)
        cache_ttl: Cache TTL in seconds

    Returns:
        DuplicateQueryOptimizer instance
    """
    global _global_optimizer

    if _global_optimizer is None:
        if db_manager is None:
            raise ValueError("db_manager required for first initialization")
        _global_optimizer = DuplicateQueryOptimizer(db_manager, cache_ttl)

    return _global_optimizer
