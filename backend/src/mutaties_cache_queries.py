"""
MutatiesCache query and read operations.

Extracted from mutaties_cache.py for maintainability.
Contains all data query/filter methods that operate on cached DataFrames:
- Aangifte IB summary and detail queries
- Available years and administrations lookups
"""

import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MutatisCacheQueriesMixin:
    """Mixin providing query/read methods for MutatiesCache."""

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
