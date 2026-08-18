"""
In-Memory Cache for vw_mutaties View
Provides fast access to mutation data for reporting.

Per-tenant partitioning: each tenant's data is cached independently
with its own TTL and eviction policy.

This module acts as the facade. Implementation is split across:
- mutaties_cache_models.py — TenantCacheEntry dataclass
- mutaties_cache_loader.py — Data loading and refresh logic
- mutaties_cache_queries.py — Query and read operations
"""

import logging
from datetime import datetime, timedelta
from threading import Lock

import pandas as pd

from mutaties_cache_loader import MutatisCacheLoaderMixin
from mutaties_cache_models import TenantCacheEntry
from mutaties_cache_queries import MutatisCacheQueriesMixin

logger = logging.getLogger(__name__)


class MutatiesCache(MutatisCacheLoaderMixin, MutatisCacheQueriesMixin):
    """
    Thread-safe in-memory cache for vw_mutaties data, partitioned by tenant.

    Each tenant's data is stored independently with its own TTL tracking.
    Inactive tenants (not accessed for 2× TTL) are evicted to save memory.

    Thread safety model:
    - Global lock protects all writes to _tenant_data
    - Readers grab a reference to a tenant's DataFrame and work with that snapshot
    - Filtering operations (df[mask]) always return new DataFrames, never mutate
    """

    def __init__(self, ttl_minutes=30):
        """
        Initialize the cache.

        Args:
            ttl_minutes: Time to live in minutes before auto-refresh (default: 30)
        """
        self._tenant_data: dict[str, TenantCacheEntry] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        self.lock = Lock()
        self._loading = False

    @property
    def data(self) -> pd.DataFrame | None:
        """Backward-compatible property: returns combined DataFrame of all tenants or None."""
        if not self._tenant_data:
            return None
        frames = [
            entry.data for entry in self._tenant_data.values() if not entry.data.empty
        ]
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    @data.setter
    def data(self, value):
        """Backward-compatible setter: stores data as a single '_legacy_' tenant entry or clears."""
        if value is None:
            self._tenant_data.clear()
        else:
            now = datetime.now()
            # Split by administration if present, otherwise store as single legacy entry
            if "administration" in value.columns:
                self._tenant_data.clear()
                for admin in value["administration"].dropna().unique():
                    tenant_df = value[value["administration"] == admin].copy()
                    years = (
                        set(tenant_df["jaar"].dropna().unique().astype(int))
                        if "jaar" in tenant_df.columns
                        else set()
                    )
                    self._tenant_data[admin] = TenantCacheEntry(
                        data=tenant_df,
                        last_accessed=now,
                        last_loaded=now,
                        years_loaded=years,
                    )
            else:
                self._tenant_data.clear()
                self._tenant_data["_legacy_"] = TenantCacheEntry(
                    data=value,
                    last_accessed=now,
                    last_loaded=now,
                    years_loaded=set(),
                )

    @property
    def last_loaded(self) -> datetime | None:
        """Backward-compatible property: returns most recent load time across all tenants."""
        if not self._tenant_data:
            return None
        times = [entry.last_loaded for entry in self._tenant_data.values()]
        return max(times) if times else None

    @last_loaded.setter
    def last_loaded(self, value):
        """Backward-compatible setter: sets last_loaded on all tenant entries."""
        if value is None:
            # Setting last_loaded to None means clear (already handled by invalidate)
            return
        for entry in self._tenant_data.values():
            entry.last_loaded = value

    def get_data(self, db_manager, tenant=None, requested_years=None):
        """
        Get cached data for a tenant, refreshing if necessary.

        Args:
            db_manager: DatabaseManager instance for loading data
            tenant: Tenant identifier (administration). If None, returns all cached data.
            requested_years: Optional list of year integers to ensure are loaded

        Returns:
            pandas.DataFrame: Cached mutation data for the tenant
        """
        # Evict inactive tenants opportunistically
        self._evict_inactive()

        if tenant is None:
            # Backward-compatible: return all cached data combined
            if not self._tenant_data:
                # Load without tenant filter (legacy behavior)
                with self.lock:
                    self._refresh_legacy(db_manager)
            return self.data

        # Per-tenant path
        entry = self._tenant_data.get(tenant)

        if entry is None or self._needs_refresh_tenant(entry):
            with self.lock:
                # Double-check after acquiring lock
                entry = self._tenant_data.get(tenant)
                if entry is None or self._needs_refresh_tenant(entry):
                    self._refresh(db_manager, tenant)
                    entry = self._tenant_data.get(tenant)

        if entry is None:
            return pd.DataFrame()

        # Update last_accessed
        entry.last_accessed = datetime.now()

        # Load missing years on demand if specific years are requested
        if requested_years and entry.data is not None and not entry.data.empty:
            self._ensure_years_loaded(db_manager, tenant, requested_years)
            entry = self._tenant_data.get(tenant)

        return entry.data if entry else pd.DataFrame()

    def get_snapshot(self, db_manager, tenant=None, requested_years=None):
        """
        Get a consistent snapshot of cached data for use within a single request.

        Args:
            db_manager: DatabaseManager instance for loading data
            tenant: Tenant identifier (administration). If None, returns all cached data.
            requested_years: Optional list of year integers to ensure are loaded

        Returns:
            pandas.DataFrame: Snapshot reference to cached data
        """
        return self.get_data(db_manager, tenant=tenant, requested_years=requested_years)

    def _needs_refresh_tenant(self, entry: TenantCacheEntry) -> bool:
        """Check if a tenant's cache entry needs to be refreshed."""
        if entry.data is None:
            return True
        return datetime.now() - entry.last_loaded > self.ttl

    def _needs_refresh(self):
        """Backward-compatible: check if any refresh is needed (legacy callers)."""
        if not self._tenant_data:
            return True
        # Check if any tenant is stale
        for entry in self._tenant_data.values():
            if self._needs_refresh_tenant(entry):
                return True
        return False

    def _evict_inactive(self):
        """Remove tenants not accessed for 2× TTL."""
        eviction_threshold = datetime.now() - (2 * self.ttl)
        tenants_to_evict = []

        for tenant_key, entry in self._tenant_data.items():
            if entry.last_accessed < eviction_threshold:
                tenants_to_evict.append(tenant_key)

        if tenants_to_evict:
            with self.lock:
                for tenant_key in tenants_to_evict:
                    if tenant_key in self._tenant_data:
                        entry = self._tenant_data[tenant_key]
                        if entry.last_accessed < eviction_threshold:
                            rows = len(entry.data) if entry.data is not None else 0
                            del self._tenant_data[tenant_key]
                            logger.info(
                                f"Evicted inactive tenant '{tenant_key}' "
                                f"({rows:,} rows, last accessed: {entry.last_accessed})"
                            )

    def invalidate(self, tenant=None):
        """
        Force cache refresh on next request.

        Args:
            tenant: If provided, only invalidate that tenant. Otherwise invalidate all.
        """
        with self.lock:
            if tenant:
                if tenant in self._tenant_data:
                    del self._tenant_data[tenant]
                    logger.info(f"Cache invalidated for tenant '{tenant}'")
            else:
                self._tenant_data.clear()
                logger.info("Cache invalidated - all tenants cleared")

    def get_stats(self):
        """
        Get cache statistics including per-tenant breakdown.

        Returns:
            dict: Cache statistics with tenants_loaded, total_rows, memory_mb
        """
        if not self._tenant_data:
            return {
                "loaded": False,
                "tenants_loaded": 0,
                "total_rows": 0,
                "memory_mb": 0.0,
                "last_loaded": None,
                "age_seconds": None,
                "ttl_seconds": self.ttl.total_seconds(),
                "needs_refresh": True,
            }

        total_rows = 0
        total_memory = 0
        oldest_load = None

        for entry in self._tenant_data.values():
            if entry.data is not None:
                total_rows += len(entry.data)
                total_memory += entry.data.memory_usage(deep=True).sum()
            if oldest_load is None or entry.last_loaded < oldest_load:
                oldest_load = entry.last_loaded

        memory_mb = round(total_memory / 1024 / 1024, 2)
        age = (datetime.now() - oldest_load).total_seconds() if oldest_load else None

        return {
            "loaded": True,
            "tenants_loaded": len(self._tenant_data),
            "total_rows": total_rows,
            "memory_mb": memory_mb,
            "last_loaded": self.last_loaded.isoformat() if self.last_loaded else None,
            "age_seconds": round(age, 1) if age else None,
            "ttl_seconds": self.ttl.total_seconds(),
            "needs_refresh": self._needs_refresh(),
            "tenants": {
                tenant: {
                    "rows": len(entry.data) if entry.data is not None else 0,
                    "years_loaded": sorted(entry.years_loaded),
                    "last_accessed": entry.last_accessed.isoformat(),
                    "memory_mb": round(
                        entry.data.memory_usage(deep=True).sum() / 1024 / 1024, 2
                    )
                    if entry.data is not None
                    else 0,
                }
                for tenant, entry in self._tenant_data.items()
            },
        }


# Global cache instance
_cache = None


def get_cache(ttl_minutes=30):
    """
    Get or create the global cache instance.

    Args:
        ttl_minutes: Time to live in minutes (default: 30)

    Returns:
        MutatiesCache: Global cache instance
    """
    global _cache
    if _cache is None:
        _cache = MutatiesCache(ttl_minutes=ttl_minutes)
    return _cache


def invalidate_cache(tenant=None):
    """
    Invalidate the global cache.

    Args:
        tenant: If provided, only invalidate that tenant. Otherwise invalidate all.
    """
    global _cache
    if _cache:
        _cache.invalidate(tenant=tenant)
