"""
MutatiesCache data loading and refresh logic.

Extracted from mutaties_cache.py for maintainability.
Contains all database interaction for cache population:
- Year determination strategy
- Per-tenant refresh
- Legacy (all-tenant) refresh
- On-demand year loading
"""

import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


class MutatisCacheLoaderMixin:
    """Mixin providing data loading and refresh methods for MutatiesCache."""

    def _get_years_to_load(self, db_manager, tenant=None) -> set[int]:
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
            current_year = datetime.now().year  # noqa: DTZ005

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

        except Exception as e:  # noqa: BLE001
            logger.error(f"Error determining years to load: {e}")
            return set()

    def _refresh(self, db_manager, tenant):
        """
        Refresh cache from database for a specific tenant.

        Args:
            db_manager: DatabaseManager instance
            tenant: Tenant identifier (administration)
        """
        from mutaties_cache_models import TenantCacheEntry

        try:
            self._loading = True
            start_time = datetime.now()  # noqa: DTZ005

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

            now = datetime.now()  # noqa: DTZ005
            self._tenant_data[tenant] = TenantCacheEntry(
                data=data,
                last_accessed=now,
                last_loaded=now,
                years_loaded=years_to_load if years_to_load else set(),
            )

            load_time = (datetime.now() - start_time).total_seconds()  # noqa: DTZ005
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
        from mutaties_cache_models import TenantCacheEntry

        try:
            self._loading = True
            start_time = datetime.now()  # noqa: DTZ005
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
            now = datetime.now()  # noqa: DTZ005
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

            load_time = (datetime.now() - start_time).total_seconds()  # noqa: DTZ005
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
                    entry.data = pd.concat([entry.data, new_data], ignore_index=True)
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

            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Error loading years {missing_years} for tenant '{tenant}': {e}"
                )

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
        from mutaties_cache_models import TenantCacheEntry

        if tenant:
            entry = self._tenant_data.get(tenant)
            if entry and entry.data is not None and year in entry.data["jaar"].unique():
                return False
            self._ensure_years_loaded(db_manager, tenant, [year])
            return True

        # Legacy: check if year exists in any tenant's data
        for entry in self._tenant_data.values():
            if entry.data is not None and "jaar" in entry.data.columns:  # noqa: SIM102
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
                now = datetime.now()  # noqa: DTZ005
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
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error loading additional year {year}: {e}")
                return False
