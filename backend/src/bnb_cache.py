"""
BNB Data Cache Module

Provides in-memory caching of BNB booking data using pandas DataFrame
for fast querying and filtering operations.

Per-tenant partitioning: each tenant's data is cached independently
with its own TTL and eviction policy.
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional
import logging
from dialect_helpers import dialect

logger = logging.getLogger(__name__)


@dataclass
class TenantCacheEntry:
    """Cache entry holding one tenant's BNB data."""

    data: pd.DataFrame
    last_accessed: datetime
    last_loaded: datetime


class BnbCache:
    """
    Thread-safe in-memory cache for BNB booking data, partitioned by tenant.

    Each tenant's data is stored independently with its own TTL tracking.
    Inactive tenants (not accessed for 2× TTL) are evicted to save memory.

    Thread safety model:
    - Global lock protects all writes to _tenant_data
    - Readers grab a reference to a tenant's DataFrame and work with that snapshot
    - Filtering operations (df[mask]) always return new DataFrames, never mutate
    """

    def __init__(self, ttl_minutes=30):
        self._tenant_data: Dict[str, TenantCacheEntry] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        self.lock = Lock()
        logger.info(f"BnbCache initialized with TTL={ttl_minutes} minutes")

    # ──────────────────────────────────────────────────────────────────────────
    # Backward-compatible properties for legacy callers / existing tests
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def data(self) -> Optional[pd.DataFrame]:
        """Backward-compatible: returns combined DataFrame of all tenants or None."""
        if not self._tenant_data:
            return None
        frames = [entry.data for entry in self._tenant_data.values()
                  if entry.data is not None and not entry.data.empty]
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    @data.setter
    def data(self, value):
        """Backward-compatible setter: stores data or clears."""
        if value is None:
            self._tenant_data.clear()
        else:
            now = datetime.now()
            if "administration" in value.columns:
                self._tenant_data.clear()
                for admin in value["administration"].dropna().unique():
                    tenant_df = value[value["administration"] == admin].copy()
                    self._tenant_data[admin] = TenantCacheEntry(
                        data=tenant_df,
                        last_accessed=now,
                        last_loaded=now,
                    )
            else:
                self._tenant_data.clear()
                self._tenant_data["_legacy_"] = TenantCacheEntry(
                    data=value,
                    last_accessed=now,
                    last_loaded=now,
                )

    @property
    def last_refresh(self) -> Optional[datetime]:
        """Backward-compatible: returns most recent load time across all tenants."""
        if not self._tenant_data:
            return None
        times = [entry.last_loaded for entry in self._tenant_data.values()]
        return max(times) if times else None

    @last_refresh.setter
    def last_refresh(self, value):
        """Backward-compatible setter."""
        if value is None:
            self._tenant_data.clear()
            return
        for entry in self._tenant_data.values():
            entry.last_loaded = value

    # ──────────────────────────────────────────────────────────────────────────
    # Core cache methods
    # ──────────────────────────────────────────────────────────────────────────

    def is_valid(self, tenant=None):
        """Check if cache is still valid for a given tenant (or any tenant)."""
        if tenant:
            entry = self._tenant_data.get(tenant)
            if entry is None or entry.data is None:
                return False
            return (datetime.now() - entry.last_loaded) < self.ttl

        # Legacy: check if there's any valid data
        if not self._tenant_data:
            return False
        for entry in self._tenant_data.values():
            if entry.data is not None and (datetime.now() - entry.last_loaded) < self.ttl:
                return True
        return False

    def get_data(self, db, tenant=None):
        """
        Get cached data, refresh if needed.

        Args:
            db: DatabaseManager instance
            tenant: Tenant identifier (administration). If None, returns all cached data.

        Returns:
            pandas.DataFrame: Cached BNB data for the tenant
        """
        # Evict inactive tenants opportunistically
        self._evict_inactive()

        if tenant is None:
            # Legacy path: load all data without tenant filter
            if not self._tenant_data or not self.is_valid():
                self.refresh(db)
            return self.data

        # Per-tenant path
        entry = self._tenant_data.get(tenant)

        if entry is None or self._needs_refresh_tenant(entry):
            with self.lock:
                # Double-check after acquiring lock
                entry = self._tenant_data.get(tenant)
                if entry is None or self._needs_refresh_tenant(entry):
                    self._refresh_tenant(db, tenant)
                    entry = self._tenant_data.get(tenant)

        if entry is None:
            return pd.DataFrame()

        # Update last_accessed
        entry.last_accessed = datetime.now()
        return entry.data if entry.data is not None else pd.DataFrame()

    def _needs_refresh_tenant(self, entry: TenantCacheEntry) -> bool:
        """Check if a tenant's cache entry needs to be refreshed."""
        if entry.data is None:
            return True
        return (datetime.now() - entry.last_loaded) > self.ttl

    def _refresh_tenant(self, db, tenant):
        """
        Refresh cache from database for a specific tenant.

        Args:
            db: DatabaseManager instance
            tenant: Tenant identifier (administration)
        """
        start_time = datetime.now()
        logger.info(f"Loading BNB data for tenant '{tenant}'...")

        try:
            query = f"""
            SELECT 
                checkinDate,
                checkoutDate,
                channel,
                listing,
                nights,
                amountGross,
                amountNett,
                amountChannelFee,
                amountTouristTax,
                amountVat,
                guestName,
                guests,
                reservationCode,
                status,
                source_type,
                administration,
                {dialect.year("checkinDate")} as year,
                {dialect.quarter("checkinDate")} as quarter,
                {dialect.month("checkinDate")} as month
            FROM vw_bnb_total
            WHERE administration = %s
            ORDER BY checkinDate DESC
            """

            with db.get_cursor() as (cursor, conn):
                data = pd.read_sql(query, conn, params=[tenant])

            self._process_dataframe(data)

            now = datetime.now()
            self._tenant_data[tenant] = TenantCacheEntry(
                data=data,
                last_accessed=now,
                last_loaded=now,
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            memory_mb = data.memory_usage(deep=True).sum() / 1024 / 1024
            actual_count = len(data[data["source_type"] == "actual"]) if not data.empty else 0
            planned_count = len(data[data["source_type"] == "planned"]) if not data.empty else 0

            logger.info(
                f"Cache loaded for tenant '{tenant}': "
                f"{len(data):,} rows ({actual_count:,} actual, {planned_count:,} planned) "
                f"in {elapsed:.2f}s, ~{memory_mb:.1f} MB"
            )

        except Exception as e:
            logger.error(f"Failed to refresh BNB cache for tenant '{tenant}': {e}")
            raise

    def refresh(self, db, tenant=None):
        """
        Refresh cache from database.

        Args:
            db: DatabaseManager instance
            tenant: If provided, refresh only that tenant. Otherwise refresh all (legacy).
        """
        if tenant:
            with self.lock:
                self._refresh_tenant(db, tenant)
            return

        # Legacy: load all data
        start_time = datetime.now()
        logger.info("Loading BNB data into memory cache (all tenants)...")

        try:
            query = f"""
            SELECT 
                checkinDate,
                checkoutDate,
                channel,
                listing,
                nights,
                amountGross,
                amountNett,
                amountChannelFee,
                amountTouristTax,
                amountVat,
                guestName,
                guests,
                reservationCode,
                status,
                source_type,
                administration,
                {dialect.year("checkinDate")} as year,
                {dialect.quarter("checkinDate")} as quarter,
                {dialect.month("checkinDate")} as month
            FROM vw_bnb_total
            ORDER BY checkinDate DESC
            """

            with db.get_cursor() as (cursor, conn):
                data = pd.read_sql(query, conn)

            self._process_dataframe(data)

            # Split by tenant
            now = datetime.now()
            with self.lock:
                self._tenant_data.clear()
                if "administration" in data.columns:
                    for admin in data["administration"].dropna().unique():
                        tenant_df = data[data["administration"] == admin].copy()
                        self._tenant_data[admin] = TenantCacheEntry(
                            data=tenant_df,
                            last_accessed=now,
                            last_loaded=now,
                        )
                else:
                    # No administration column — store as legacy
                    self._tenant_data["_legacy_"] = TenantCacheEntry(
                        data=data,
                        last_accessed=now,
                        last_loaded=now,
                    )

            elapsed = (datetime.now() - start_time).total_seconds()
            memory_mb = data.memory_usage(deep=True).sum() / 1024 / 1024
            actual_count = len(data[data["source_type"] == "actual"]) if not data.empty else 0
            planned_count = len(data[data["source_type"] == "planned"]) if not data.empty else 0

            logger.info(
                f"Cache loaded: {len(data):,} rows ({actual_count:,} actual, "
                f"{planned_count:,} planned) across {len(self._tenant_data)} tenants "
                f"in {elapsed:.2f}s, ~{memory_mb:.1f} MB"
            )

        except Exception as e:
            logger.error(f"Failed to refresh BNB cache: {e}")
            raise

    def _process_dataframe(self, data):
        """Process loaded DataFrame: convert types, fill NaN."""
        if data.empty:
            return

        # Convert date columns to datetime
        if "checkinDate" in data.columns:
            data["checkinDate"] = pd.to_datetime(data["checkinDate"])
        if "checkoutDate" in data.columns:
            data["checkoutDate"] = pd.to_datetime(data["checkoutDate"])

        # Ensure numeric columns are float
        numeric_cols = [
            "nights", "amountGross", "amountNett", "amountChannelFee",
            "amountTouristTax", "amountVat", "guests",
        ]
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

        # Fill NaN values in string columns
        string_cols = [
            "channel", "listing", "guestName", "reservationCode",
            "status", "source_type",
        ]
        for col in string_cols:
            if col in data.columns:
                data[col] = data[col].fillna("")

    # ──────────────────────────────────────────────────────────────────────────
    # Eviction
    # ──────────────────────────────────────────────────────────────────────────

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
                                f"Evicted inactive BNB tenant '{tenant_key}' "
                                f"({rows:,} rows, last accessed: {entry.last_accessed})"
                            )

    # ──────────────────────────────────────────────────────────────────────────
    # Cache management
    # ──────────────────────────────────────────────────────────────────────────

    def invalidate(self, tenant=None):
        """
        Invalidate cache (will auto-refresh on next query).

        Args:
            tenant: If provided, only invalidate that tenant. Otherwise invalidate all.
        """
        with self.lock:
            if tenant:
                if tenant in self._tenant_data:
                    del self._tenant_data[tenant]
                    logger.info(f"BNB cache invalidated for tenant '{tenant}'")
            else:
                self._tenant_data.clear()
                logger.info("BNB cache invalidated - all tenants cleared")

    def get_status(self):
        """
        Get cache status information (backward-compatible).

        Returns:
            dict: Cache status with loaded, row_count, memory_mb, etc.
        """
        if not self._tenant_data:
            return {
                "loaded": False,
                "row_count": 0,
                "memory_mb": 0,
                "last_refresh": None,
                "ttl_minutes": self.ttl.total_seconds() / 60,
                "is_valid": False,
            }

        total_rows = 0
        total_memory = 0
        for entry in self._tenant_data.values():
            if entry.data is not None:
                total_rows += len(entry.data)
                total_memory += entry.data.memory_usage(deep=True).sum()

        memory_mb = round(total_memory / 1024 / 1024, 1)

        return {
            "loaded": True,
            "row_count": total_rows,
            "memory_mb": memory_mb,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "ttl_minutes": self.ttl.total_seconds() / 60,
            "is_valid": self.is_valid(),
        }

    def get_stats(self):
        """
        Get detailed cache statistics including per-tenant breakdown.

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
                "ttl_seconds": self.ttl.total_seconds(),
            }

        total_rows = 0
        total_memory = 0

        for entry in self._tenant_data.values():
            if entry.data is not None:
                total_rows += len(entry.data)
                total_memory += entry.data.memory_usage(deep=True).sum()

        memory_mb = round(total_memory / 1024 / 1024, 2)

        return {
            "loaded": True,
            "tenants_loaded": len(self._tenant_data),
            "total_rows": total_rows,
            "memory_mb": memory_mb,
            "last_loaded": self.last_refresh.isoformat() if self.last_refresh else None,
            "ttl_seconds": self.ttl.total_seconds(),
            "tenants": {
                tenant_key: {
                    "rows": len(entry.data) if entry.data is not None else 0,
                    "last_accessed": entry.last_accessed.isoformat(),
                    "memory_mb": round(
                        entry.data.memory_usage(deep=True).sum() / 1024 / 1024, 2
                    ) if entry.data is not None else 0,
                }
                for tenant_key, entry in self._tenant_data.items()
            },
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Query methods
    # ──────────────────────────────────────────────────────────────────────────

    def query_by_year(self, db, year, tenant=None, status=None):
        """
        Query bookings by year and optional status.

        Args:
            db: DatabaseManager instance
            year: Year to filter
            tenant: Tenant identifier (administration)
            status: Optional status filter

        Returns:
            list: List of booking dicts
        """
        df = self.get_data(db, tenant=tenant)
        if df is None or df.empty:
            return []

        df = df[df["year"] == int(year)].copy()

        if status:
            df = df[df["status"] == status]

        return df.to_dict("records")

    def query_cancelled_by_year(self, db, year, tenant=None):
        """Get cancelled bookings for a specific year."""
        return self.query_by_year(db, year, tenant=tenant, status="cancelled")

    def query_realised_by_year(self, db, year, tenant=None):
        """Get realised (non-cancelled) bookings for a specific year."""
        df = self.get_data(db, tenant=tenant)
        if df is None or df.empty:
            return []

        df = df[(df["year"] == int(year)) & (df["status"] != "cancelled")].copy()
        return df.to_dict("records")


# Global cache instance
_bnb_cache = None


def get_bnb_cache():
    """Get or create global BNB cache instance"""
    global _bnb_cache
    if _bnb_cache is None:
        _bnb_cache = BnbCache(ttl_minutes=30)
    return _bnb_cache
