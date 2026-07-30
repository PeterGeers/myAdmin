"""
In-Memory Cache for vw_mutaties View
Provides fast access to mutation data for reporting.

Per-tenant partitioning: each tenant's data is cached independently
with its own TTL and eviction policy.
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Set, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TenantCacheEntry:
    """Cache entry holding one tenant's mutation data."""

    data: pd.DataFrame
    last_accessed: datetime
    last_loaded: datetime
    years_loaded: Set[int] = field(default_factory=set)


class MutatiesCache:
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
        self._tenant_data: Dict[str, TenantCacheEntry] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        self.lock = Lock()
        self._loading = False

    @property
    def data(self) -> Optional[pd.DataFrame]:
        """Backward-compatible property: returns combined DataFrame of all tenants or None."""
        if not self._tenant_data:
            return None
        frames = [entry.data for entry in self._tenant_data.values() if not entry.data.empty]
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
    def last_loaded(self) -> Optional[datetime]:
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
        if (datetime.now() - entry.last_loaded) > self.ttl:
            return True
        return False

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

    def _get_years_to_load(self, db_manager, tenant=None):
        """
        Determine which years to load into cache.

        Strategy (Hybrid Approach):
        1. Get all years that are NOT closed (open years)
        2. Get the most recent closed year (for comparisons)
        3. Return set of years to load

        Args:
            db_manager: DatabaseManager instance
            tenant: Optional tenant filter

        Returns:
            set: Set of years (integers) to load
        """
        try:
            current_year = datetime.now().year

            # Query closed years
            query = """
                SELECT DISTINCT year
                FROM year_closure_status
                ORDER BY year DESC
            """
            closed_years_result = db_manager.execute_query(query, fetch=True)
            closed_years = (
                [row["year"] for row in closed_years_result]
                if closed_years_result
                else []
            )

            # Get all years that have transactions for this tenant
            if tenant:
                query_all_years = """
                    SELECT DISTINCT jaar as year
                    FROM vw_mutaties
                    WHERE jaar IS NOT NULL AND administration = %s
                    ORDER BY year DESC
                """
                all_years_result = db_manager.execute_query(
                    query_all_years, params=[tenant], fetch=True
                )
            else:
                query_all_years = """
                    SELECT DISTINCT jaar as year
                    FROM vw_mutaties
                    WHERE jaar IS NOT NULL
                    ORDER BY year DESC
                """
                all_years_result = db_manager.execute_query(query_all_years, fetch=True)

            all_years = (
                [row["year"] for row in all_years_result] if all_years_result else []
            )

            if not all_years:
                logger.info("No transaction years found, loading current year")
                return {current_year}

            # Determine open years
            open_years = [year for year in all_years if year not in closed_years]
            if not open_years:
                open_years = [current_year]

            last_closed_year = closed_years[0] if closed_years else None

            years_to_load = set(open_years)
            if last_closed_year:
                years_to_load.add(last_closed_year)

            logger.info(
                f"Years analysis for tenant '{tenant}': "
                f"All={len(all_years)}, Closed={len(closed_years)}, "
                f"Open={len(open_years)}, Loading={len(years_to_load)}"
            )
            return years_to_load

        except Exception as e:
            logger.error(f"Error determining years to load: {e}")
            return set()

    def _refresh(self, db_manager, tenant):
        """
        Refresh cache from database for a specific tenant.

        Args:
            db_manager: DatabaseManager instance
            tenant: Tenant identifier (administration)
        """
        try:
            self._loading = True
            start_time = datetime.now()

            logger.info(f"Loading vw_mutaties for tenant '{tenant}'...")

            conn = db_manager.get_connection()

            years_to_load = self._get_years_to_load(db_manager, tenant)

            if years_to_load:
                year_filter = " OR ".join([f"jaar = {year}" for year in years_to_load])
                query = f"""
                    SELECT 
                        Aangifte, TransactionNumber, TransactionDate,
                        TransactionDescription, Amount, Reknum, AccountName,
                        Parent, VW, jaar, kwartaal, maand, week,
                        ReferenceNumber, administration, Ref3, Ref4
                    FROM vw_mutaties
                    WHERE administration = %s AND ({year_filter})
                """
                data = pd.read_sql(query, conn, params=[tenant])
            else:
                query = """
                    SELECT 
                        Aangifte, TransactionNumber, TransactionDate,
                        TransactionDescription, Amount, Reknum, AccountName,
                        Parent, VW, jaar, kwartaal, maand, week,
                        ReferenceNumber, administration, Ref3, Ref4
                    FROM vw_mutaties
                    WHERE administration = %s
                """
                data = pd.read_sql(query, conn, params=[tenant])

            conn.close()

            # Convert date column
            if "TransactionDate" in data.columns:
                data["TransactionDate"] = pd.to_datetime(data["TransactionDate"])

            now = datetime.now()
            self._tenant_data[tenant] = TenantCacheEntry(
                data=data,
                last_accessed=now,
                last_loaded=now,
                years_loaded=years_to_load if years_to_load else set(),
            )

            load_time = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Cache loaded for tenant '{tenant}': "
                f"{len(data):,} rows in {load_time:.2f}s, "
                f"~{data.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB"
            )

        except Exception as e:
            logger.error(f"Error refreshing cache for tenant '{tenant}': {e}")
            if tenant not in self._tenant_data:
                raise
        finally:
            self._loading = False

    def _refresh_legacy(self, db_manager):
        """
        Legacy refresh: loads all data without tenant filter.
        Used when get_data() is called without a tenant parameter.

        Args:
            db_manager: DatabaseManager instance
        """
        try:
            self._loading = True
            start_time = datetime.now()
            logger.info("Loading vw_mutaties into memory cache (legacy/all tenants)...")

            conn = db_manager.get_connection()
            years_to_load = self._get_years_to_load(db_manager)

            if years_to_load:
                year_filter = " OR ".join([f"jaar = {year}" for year in years_to_load])
                query = f"""
                    SELECT 
                        Aangifte, TransactionNumber, TransactionDate,
                        TransactionDescription, Amount, Reknum, AccountName,
                        Parent, VW, jaar, kwartaal, maand, week,
                        ReferenceNumber, administration, Ref3, Ref4
                    FROM vw_mutaties
                    WHERE {year_filter}
                """
            else:
                query = """
                    SELECT 
                        Aangifte, TransactionNumber, TransactionDate,
                        TransactionDescription, Amount, Reknum, AccountName,
                        Parent, VW, jaar, kwartaal, maand, week,
                        ReferenceNumber, administration, Ref3, Ref4
                    FROM vw_mutaties
                """

            data = pd.read_sql(query, conn)
            conn.close()

            if "TransactionDate" in data.columns:
                data["TransactionDate"] = pd.to_datetime(data["TransactionDate"])

            # Split by tenant into individual entries
            now = datetime.now()
            if "administration" in data.columns:
                for admin in data["administration"].dropna().unique():
                    tenant_df = data[data["administration"] == admin].copy()
                    tenant_years = (
                        set(tenant_df["jaar"].dropna().unique().astype(int))
                        if "jaar" in tenant_df.columns
                        else set()
                    )
                    self._tenant_data[admin] = TenantCacheEntry(
                        data=tenant_df,
                        last_accessed=now,
                        last_loaded=now,
                        years_loaded=tenant_years,
                    )

            load_time = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Legacy cache loaded: {len(data):,} rows across "
                f"{len(self._tenant_data)} tenants in {load_time:.2f}s"
            )

        except Exception as e:
            logger.error(f"Error in legacy refresh: {e}")
            if not self._tenant_data:
                raise
        finally:
            self._loading = False

    def _ensure_years_loaded(self, db_manager, tenant, requested_years):
        """
        Load missing years into cache on demand for a specific tenant.

        Args:
            db_manager: DatabaseManager instance
            tenant: Tenant identifier
            requested_years: List of year integers to ensure are loaded
        """
        entry = self._tenant_data.get(tenant)
        if entry is None or entry.data is None or entry.data.empty:
            return

        cached_years = (
            set(entry.data["jaar"].unique()) if "jaar" in entry.data.columns else set()
        )
        missing_years = [int(y) for y in requested_years if int(y) not in cached_years]

        if not missing_years:
            return

        logger.info(
            f"On-demand loading for tenant '{tenant}': "
            f"missing years {sorted(missing_years)} (cached: {sorted(cached_years)})"
        )

        with self.lock:
            # Double-check after acquiring lock
            entry = self._tenant_data.get(tenant)
            if entry is None or entry.data is None:
                return

            cached_years = (
                set(entry.data["jaar"].unique())
                if "jaar" in entry.data.columns
                else set()
            )
            missing_years = [
                int(y) for y in requested_years if int(y) not in cached_years
            ]
            if not missing_years:
                return

            try:
                conn = db_manager.get_connection()
                year_filter = " OR ".join([f"jaar = {year}" for year in missing_years])

                query = f"""
                    SELECT 
                        Aangifte, TransactionNumber, TransactionDate,
                        TransactionDescription, Amount, Reknum, AccountName,
                        Parent, VW, jaar, kwartaal, maand, week,
                        ReferenceNumber, administration, Ref3, Ref4
                    FROM vw_mutaties
                    WHERE administration = %s AND ({year_filter})
                """
                new_data = pd.read_sql(query, conn, params=[tenant])
                conn.close()

                if not new_data.empty:
                    if "TransactionDate" in new_data.columns:
                        new_data["TransactionDate"] = pd.to_datetime(
                            new_data["TransactionDate"]
                        )
                    entry.data = pd.concat(
                        [entry.data, new_data], ignore_index=True
                    )
                    entry.years_loaded.update(missing_years)
                    logger.info(
                        f"Loaded {len(new_data):,} rows for tenant '{tenant}' "
                        f"years {sorted(missing_years)}. "
                        f"Total: {len(entry.data):,} rows."
                    )
                else:
                    logger.info(
                        f"No data for tenant '{tenant}' years {sorted(missing_years)}"
                    )

            except Exception as e:
                logger.error(
                    f"Error loading years {missing_years} for tenant '{tenant}': {e}"
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

    def load_additional_year(self, db_manager, year, tenant=None):
        """
        Load an additional year into the cache on-demand.

        Args:
            db_manager: DatabaseManager instance
            year: Year to load (integer)
            tenant: Optional tenant filter

        Returns:
            bool: True if year was loaded, False if already cached or error
        """
        if tenant:
            entry = self._tenant_data.get(tenant)
            if entry and entry.data is not None and year in entry.data["jaar"].unique():
                return False
            self._ensure_years_loaded(db_manager, tenant, [year])
            return True

        # Legacy: check if year exists in any tenant's data
        for entry in self._tenant_data.values():
            if entry.data is not None and "jaar" in entry.data.columns:
                if year in entry.data["jaar"].unique():
                    logger.info(f"Year {year} already in cache")
                    return False

        # Load for all tenants
        with self.lock:
            try:
                conn = db_manager.get_connection()
                query = """
                    SELECT 
                        Aangifte, TransactionNumber, TransactionDate,
                        TransactionDescription, Amount, Reknum, AccountName,
                        Parent, VW, jaar, kwartaal, maand, week,
                        ReferenceNumber, administration, Ref3, Ref4
                    FROM vw_mutaties
                    WHERE jaar = %s
                """
                year_data = pd.read_sql(query, conn, params=[int(year)])
                conn.close()

                if "TransactionDate" in year_data.columns:
                    year_data["TransactionDate"] = pd.to_datetime(
                        year_data["TransactionDate"]
                    )

                # Distribute to tenant entries
                now = datetime.now()
                if "administration" in year_data.columns:
                    for admin in year_data["administration"].dropna().unique():
                        tenant_df = year_data[
                            year_data["administration"] == admin
                        ].copy()
                        if admin in self._tenant_data:
                            entry = self._tenant_data[admin]
                            entry.data = pd.concat(
                                [entry.data, tenant_df], ignore_index=True
                            )
                            entry.years_loaded.add(int(year))
                        else:
                            self._tenant_data[admin] = TenantCacheEntry(
                                data=tenant_df,
                                last_accessed=now,
                                last_loaded=now,
                                years_loaded={int(year)},
                            )

                return True
            except Exception as e:
                logger.error(f"Error loading additional year {year}: {e}")
                return False

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
        age = (
            (datetime.now() - oldest_load).total_seconds() if oldest_load else None
        )

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
                    ) if entry.data is not None else 0,
                }
                for tenant, entry in self._tenant_data.items()
            },
        }

    def query_aangifte_ib(
        self,
        year,
        administration="all",
        db_manager=None,
        tenant=None,
        user_tenants=None,
        snapshot=None,
        start_year=None,
    ):
        """
        Query Aangifte IB data from cache.

        Uses closure-aware filtering:
        - Balance sheet accounts (VW='N'): Cumulate from start_year through target year
        - P&L accounts (VW='Y'): Current year only (period-based)

        Args:
            year: Year to filter (string or int)
            administration: Administration to filter (default: 'all')
            db_manager: DatabaseManager instance (for on-demand loading)
            tenant: Tenant identifier for per-tenant cache lookup
            user_tenants: List of tenants user has access to
            snapshot: Optional DataFrame snapshot for consistent reads
            start_year: First year to include for balance sheet cumulation

        Returns:
            dict: Summary data grouped by Parent and Aangifte
        """
        if snapshot is not None:
            source = snapshot
        elif tenant and tenant in self._tenant_data:
            entry = self._tenant_data[tenant]
            entry.last_accessed = datetime.now()
            source = entry.data
        elif self.data is not None:
            source = self.data
        else:
            raise ValueError("Cache not loaded")

        year_int = int(year)

        # Check if year is in cache, load if needed
        if source is not None and year_int not in source["jaar"].unique():
            if db_manager:
                logger.info(f"Year {year_int} not in cache, loading on-demand...")
                self.load_additional_year(db_manager, year_int, tenant=tenant)
                # Re-read source after load
                if tenant and tenant in self._tenant_data:
                    source = self._tenant_data[tenant].data
                else:
                    source = self.data

        df = source

        # SECURITY: Filter by user's accessible tenants first
        if user_tenants is not None:
            df = df[df["administration"].isin(user_tenants)]

        # Closure-aware filtering
        if start_year is not None:
            mask = (
                (df["VW"] == "N")
                & (df["jaar"] >= start_year)
                & (df["jaar"] <= year_int)
            ) | ((df["VW"] == "Y") & (df["jaar"] == year_int))
        else:
            mask = ((df["VW"] == "N") & (df["jaar"] <= year_int)) | (
                (df["VW"] == "Y") & (df["jaar"] == year_int)
            )
        df = df[mask]

        # Filter by administration
        if administration != "all":
            df = df[df["administration"] == administration]

        # Group by Parent and Aangifte
        summary = df.groupby(["Parent", "Aangifte"])["Amount"].sum().reset_index()
        summary.columns = ["Parent", "Aangifte", "Amount"]
        summary = summary.sort_values(["Parent", "Aangifte"], ascending=[True, True])

        return summary.to_dict("records")

    def query_aangifte_ib_details(
        self,
        year,
        administration,
        parent,
        aangifte,
        user_tenants=None,
        tenant=None,
        snapshot=None,
        start_year=None,
    ):
        """
        Query detailed accounts for specific Parent and Aangifte.

        Args:
            year: Year to filter
            administration: Administration to filter
            parent: Parent category
            aangifte: Aangifte category
            user_tenants: List of tenants user has access to
            tenant: Tenant identifier for per-tenant cache lookup
            snapshot: Optional DataFrame snapshot
            start_year: First year for balance sheet cumulation

        Returns:
            list: Account details with amounts
        """
        if snapshot is not None:
            source = snapshot
        elif tenant and tenant in self._tenant_data:
            entry = self._tenant_data[tenant]
            entry.last_accessed = datetime.now()
            source = entry.data
        elif self.data is not None:
            source = self.data
        else:
            raise ValueError("Cache not loaded")

        df = source

        # SECURITY: Filter by user's accessible tenants first
        if user_tenants is not None:
            df = df[df["administration"].isin(user_tenants)]

        year_int = int(year)

        # Closure-aware filtering
        if start_year is not None:
            mask = (
                (df["VW"] == "N")
                & (df["jaar"] >= start_year)
                & (df["jaar"] <= year_int)
            ) | ((df["VW"] == "Y") & (df["jaar"] == year_int))
        else:
            mask = ((df["VW"] == "N") & (df["jaar"] <= year_int)) | (
                (df["VW"] == "Y") & (df["jaar"] == year_int)
            )
        df = df[mask]

        # Filter by criteria
        if administration != "all":
            df = df[df["administration"] == administration]

        df = df[(df["Parent"] == parent) & (df["Aangifte"] == aangifte)]

        # Group by account
        details = df.groupby(["Reknum", "AccountName"])["Amount"].sum().reset_index()
        details.columns = ["Reknum", "AccountName", "Amount"]

        return details.to_dict("records")

    def get_available_years(self, db_manager=None, tenant=None):
        """
        Get list of ALL available years from database (not just cached years).

        Args:
            db_manager: DatabaseManager instance
            tenant: Optional tenant filter

        Returns:
            list: Sorted list of years (newest first)
        """
        if db_manager is not None:
            try:
                conn = db_manager.get_connection()
                if tenant:
                    query = """
                        SELECT DISTINCT YEAR(TransactionDate) as year
                        FROM mutaties
                        WHERE administration = %s
                        ORDER BY year DESC
                    """
                    result = pd.read_sql(query, conn, params=[tenant])
                else:
                    query = """
                        SELECT DISTINCT YEAR(TransactionDate) as year
                        FROM mutaties
                        ORDER BY year DESC
                    """
                    result = pd.read_sql(query, conn)
                conn.close()
                return [str(int(y)) for y in result["year"].dropna()]
            except Exception as e:
                logger.warning(
                    f"Could not query database for years: {e}, falling back to cache"
                )

        # Fallback: Use cached data
        if tenant and tenant in self._tenant_data:
            entry = self._tenant_data[tenant]
            if entry.data is not None and not entry.data.empty:
                years = entry.data["jaar"].dropna().unique()
                return sorted([str(int(y)) for y in years], reverse=True)

        # Fallback to combined data
        combined = self.data
        if combined is None:
            raise ValueError("Cache not loaded and no database manager provided")

        years = combined["jaar"].dropna().unique()
        return sorted([str(int(y)) for y in years], reverse=True)

    def get_available_administrations(self, year=None, tenant=None):
        """
        Get list of available administrations from cache.

        Args:
            year: Optional year filter
            tenant: Optional tenant filter (returns just this tenant's admin)

        Returns:
            list: Sorted list of administrations
        """
        if tenant and tenant in self._tenant_data:
            return [tenant]

        combined = self.data
        if combined is None:
            raise ValueError("Cache not loaded")

        df = combined
        if year:
            df = df[df["jaar"] == int(year)]

        admins = df["administration"].dropna().unique()
        return sorted(admins.tolist())


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
