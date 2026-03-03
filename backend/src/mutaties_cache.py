"""
In-Memory Cache for vw_mutaties View
Provides fast access to mutation data for reporting
"""

import pandas as pd
from datetime import datetime, timedelta
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class MutatiesCache:
    """
    Thread-safe in-memory cache for vw_mutaties data
    Automatically refreshes data based on TTL (Time To Live)
    """
    
    def __init__(self, ttl_minutes=30):
        """
        Initialize the cache
        
        Args:
            ttl_minutes: Time to live in minutes before auto-refresh (default: 30)
        """
        self.data = None
        self.last_loaded = None
        self.ttl = timedelta(minutes=ttl_minutes)
        self.lock = Lock()
        self._loading = False
        
    def get_data(self, db_manager):
        """
        Get cached data, refreshing if necessary
        
        Args:
            db_manager: DatabaseManager instance for loading data
            
        Returns:
            pandas.DataFrame: Cached mutation data
        """
        # Check if refresh is needed
        if self._needs_refresh():
            with self.lock:
                # Double-check after acquiring lock
                if self._needs_refresh():
                    self._refresh(db_manager)
        
        return self.data
    
    def _needs_refresh(self):
        """Check if cache needs to be refreshed"""
        if self.data is None:
            return True
        if self.last_loaded is None:
            return True
        if (datetime.now() - self.last_loaded) > self.ttl:
            return True
        return False
    
    def _get_years_to_load(self, db_manager):
        """
        Determine which years to load into cache.
        
        Strategy (Option 3 - Hybrid Approach):
        1. Get all years that are NOT closed (open years)
        2. Get the most recent closed year (for comparisons)
        3. Return set of years to load
        
        Args:
            db_manager: DatabaseManager instance
            
        Returns:
            set: Set of years (integers) to load
        """
        try:
            # Get current year as fallback
            current_year = datetime.now().year
            
            # Query to get closed years from year_closure_status
            # NOTE: If a year is in this table, it IS closed
            query = """
                SELECT DISTINCT year
                FROM year_closure_status
                ORDER BY year DESC
            """
            
            closed_years_result = db_manager.execute_query(query, fetch=True)
            closed_years = [row['year'] for row in closed_years_result] if closed_years_result else []
            
            # Get all years that have transactions
            query_all_years = """
                SELECT DISTINCT jaar as year
                FROM vw_mutaties
                WHERE jaar IS NOT NULL
                ORDER BY jaar DESC
            """
            
            all_years_result = db_manager.execute_query(query_all_years, fetch=True)
            all_years = [row['year'] for row in all_years_result] if all_years_result else []
            
            if not all_years:
                # No data yet, load current year
                logger.info("No transaction years found, loading current year")
                return {current_year}
            
            # Determine open years (years with transactions that are not closed)
            open_years = [year for year in all_years if year not in closed_years]
            
            # If no open years, assume current year is open
            if not open_years:
                open_years = [current_year]
            
            # Get last closed year (most recent)
            last_closed_year = closed_years[0] if closed_years else None
            
            # Build set of years to load
            years_to_load = set(open_years)
            
            # Add last closed year for comparisons
            if last_closed_year:
                years_to_load.add(last_closed_year)
            
            logger.info(f"Years analysis: All={len(all_years)}, Closed={len(closed_years)}, Open={len(open_years)}, Loading={len(years_to_load)}")
            
            return years_to_load
            
        except Exception as e:
            logger.error(f"Error determining years to load: {e}")
            # Fallback: return empty set to load all data
            return set()
    
    def _refresh(self, db_manager):
        """
        Refresh cache from database.
        
        OPTIMIZATION (Option 3 - Hybrid Approach):
        - Load all open years (not yet closed)
        - Load last closed year (for year-end comparisons)
        - Skip older closed years (load on-demand if needed)
        
        This significantly improves performance for tenants with many years of data.
        
        Args:
            db_manager: DatabaseManager instance
        """
        try:
            self._loading = True
            start_time = datetime.now()
            
            logger.info("Loading vw_mutaties into memory cache (optimized)...")
            
            conn = db_manager.get_connection()
            
            # Get years to load (open years + last closed year)
            years_to_load = self._get_years_to_load(db_manager)
            
            if years_to_load:
                # Build year filter for query
                year_filter = " OR ".join([f"jaar = {year}" for year in years_to_load])
                
                query = f"""
                    SELECT 
                        Aangifte,
                        TransactionNumber,
                        TransactionDate,
                        TransactionDescription,
                        Amount,
                        Reknum,
                        AccountName,
                        Parent,
                        VW,
                        jaar,
                        kwartaal,
                        maand,
                        week,
                        ReferenceNumber,
                        administration,
                        Ref3,
                        Ref4
                    FROM vw_mutaties
                    WHERE {year_filter}
                """
                
                logger.info(f"Loading years: {sorted(years_to_load)}")
            else:
                # Fallback: Load all data if year detection fails
                logger.warning("Could not determine years to load, loading all data")
                query = """
                    SELECT 
                        Aangifte,
                        TransactionNumber,
                        TransactionDate,
                        TransactionDescription,
                        Amount,
                        Reknum,
                        AccountName,
                        Parent,
                        VW,
                        jaar,
                        kwartaal,
                        maand,
                        week,
                        ReferenceNumber,
                        administration,
                        Ref3,
                        Ref4
                    FROM vw_mutaties
                """
            
            self.data = pd.read_sql(query, conn)
            conn.close()
            conn.close()
            
            # Convert date column to datetime for faster filtering
            if 'TransactionDate' in self.data.columns:
                self.data['TransactionDate'] = pd.to_datetime(self.data['TransactionDate'])
            
            self.last_loaded = datetime.now()
            load_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Cache loaded: {len(self.data):,} rows in {load_time:.2f}s")
            logger.info(f"Memory usage: ~{self.data.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")
            
        except Exception as e:
            logger.error(f"Error refreshing cache: {e}")
            # Keep old data if refresh fails
            if self.data is None:
                raise
        finally:
            self._loading = False
    
    def invalidate(self):
        """Force cache refresh on next request"""
        with self.lock:
            logger.info("Cache invalidated - will refresh on next request")
            self.data = None
            self.last_loaded = None
    
    def load_additional_year(self, db_manager, year):
        """
        Load an additional year into the cache on-demand.
        
        This is used when a user requests data from a closed year that
        wasn't loaded initially (older than last closed year).
        
        Args:
            db_manager: DatabaseManager instance
            year: Year to load (integer)
            
        Returns:
            bool: True if year was loaded, False if already in cache or error
        """
        with self.lock:
            try:
                # Check if year is already in cache
                if self.data is not None and year in self.data['jaar'].unique():
                    logger.info(f"Year {year} already in cache")
                    return False
                
                logger.info(f"Loading additional year {year} into cache...")
                start_time = datetime.now()
                
                conn = db_manager.get_connection()
                
                query = f"""
                    SELECT 
                        Aangifte,
                        TransactionNumber,
                        TransactionDate,
                        TransactionDescription,
                        Amount,
                        Reknum,
                        AccountName,
                        Parent,
                        VW,
                        jaar,
                        kwartaal,
                        maand,
                        week,
                        ReferenceNumber,
                        administration,
                        Ref3,
                        Ref4
                    FROM vw_mutaties
                    WHERE jaar = {year}
                """
                
                year_data = pd.read_sql(query, conn)
                conn.close()
                
                # Convert date column
                if 'TransactionDate' in year_data.columns:
                    year_data['TransactionDate'] = pd.to_datetime(year_data['TransactionDate'])
                
                # Append to existing cache
                if self.data is not None:
                    self.data = pd.concat([self.data, year_data], ignore_index=True)
                else:
                    self.data = year_data
                
                load_time = (datetime.now() - start_time).total_seconds()
                logger.info(f"Loaded year {year}: {len(year_data):,} rows in {load_time:.2f}s")
                
                return True
                
            except Exception as e:
                logger.error(f"Error loading additional year {year}: {e}")
                return False
    
    def get_stats(self):
        """Get cache statistics"""
        if self.data is None:
            return {
                'loaded': False,
                'rows': 0,
                'last_loaded': None,
                'age_seconds': None
            }
        
        age = (datetime.now() - self.last_loaded).total_seconds() if self.last_loaded else None
        
        return {
            'loaded': True,
            'rows': len(self.data),
            'columns': len(self.data.columns),
            'memory_mb': round(self.data.memory_usage(deep=True).sum() / 1024 / 1024, 2),
            'last_loaded': self.last_loaded.isoformat() if self.last_loaded else None,
            'age_seconds': round(age, 1) if age else None,
            'ttl_seconds': self.ttl.total_seconds(),
            'needs_refresh': self._needs_refresh()
        }
    
    def query_aangifte_ib(self, year, administration='all', db_manager=None):
        """
        Query Aangifte IB data from cache
        
        Uses NEW MODEL (year-end closure):
        - Balance sheet accounts (VW='N'): Current year only (includes OpeningBalance)
        - P&L accounts (VW='Y'): Current year only
        
        Args:
            year: Year to filter (string or int)
            administration: Administration to filter (default: 'all')
            db_manager: DatabaseManager instance (for on-demand loading)
            
        Returns:
            dict: Summary data grouped by Parent and Aangifte
        """
        if self.data is None:
            raise ValueError("Cache not loaded")
        
        year_int = int(year)
        
        # Check if year is in cache, load if needed
        if year_int not in self.data['jaar'].unique():
            if db_manager:
                logger.info(f"Year {year_int} not in cache, loading on-demand...")
                self.load_additional_year(db_manager, year_int)
            else:
                logger.warning(f"Year {year_int} not in cache and no db_manager provided")
        
        df = self.data.copy()
        
        # NEW MODEL: Use current year only for ALL accounts
        # Balance sheet accounts include OpeningBalance which brings forward history
        mask = (
            ((df['VW'] == 'N') & (df['jaar'] == year_int)) |
            ((df['VW'] == 'Y') & (df['jaar'] == year_int))
        )
        df = df[mask]
        
        # Filter by administration
        if administration != 'all':
            df = df[df['administration'].str.startswith(administration)]
        
        # Group by Parent and Aangifte
        summary = df.groupby(['Parent', 'Aangifte'])['Amount'].sum().reset_index()
        summary.columns = ['Parent', 'Aangifte', 'Amount']
        
        # Sort by Parent (ascending) and Aangifte (alphabetically) to match database order
        # The Aangifte field comes from rekeningschema.Belastingaangifte which has a natural order
        summary = summary.sort_values(['Parent', 'Aangifte'], ascending=[True, True])
        
        return summary.to_dict('records')
    
    def query_aangifte_ib_details(self, year, administration, parent, aangifte, user_tenants=None):
        """
        Query detailed accounts for specific Parent and Aangifte
        
        Uses NEW MODEL (year-end closure):
        - Balance sheet accounts (VW='N'): Current year only (includes OpeningBalance)
        - P&L accounts (VW='Y'): Current year only
        
        Args:
            year: Year to filter
            administration: Administration to filter
            parent: Parent category
            aangifte: Aangifte category
            user_tenants: List of tenants user has access to (for security filtering)
            
        Returns:
            list: Account details with amounts
        """
        if self.data is None:
            raise ValueError("Cache not loaded")
        
        df = self.data.copy()
        
        # SECURITY: Filter by user's accessible tenants first
        if user_tenants is not None:
            df = df[df['administration'].isin(user_tenants)]
        
        # NEW MODEL: Use current year only for ALL accounts
        mask = (
            ((df['VW'] == 'N') & (df['jaar'] == int(year))) |
            ((df['VW'] == 'Y') & (df['jaar'] == int(year)))
        )
        df = df[mask]
        
        # Filter by criteria
        if administration != 'all':
            df = df[df['administration'].str.startswith(administration)]
        
        df = df[(df['Parent'] == parent) & (df['Aangifte'] == aangifte)]
        
        # Group by account
        details = df.groupby(['Reknum', 'AccountName'])['Amount'].sum().reset_index()
        details.columns = ['Reknum', 'AccountName', 'Amount']
        
        return details.to_dict('records')
    
    def get_available_years(self, db_manager=None):
        """
        Get list of ALL available years from database (not just cached years).
        
        This ensures year selectors show all years, even if they're not loaded in cache.
        
        Args:
            db_manager: DatabaseManager instance (optional, will use cache if not provided)
            
        Returns:
            list: Sorted list of years (newest first)
        """
        # If db_manager provided, query database directly for ALL years
        if db_manager is not None:
            try:
                conn = db_manager.get_connection()
                query = "SELECT DISTINCT YEAR(TransactionDate) as year FROM mutaties ORDER BY year DESC"
                result = pd.read_sql(query, conn)
                conn.close()
                return [str(int(y)) for y in result['year'].dropna()]
            except Exception as e:
                logger.warning(f"Could not query database for years: {e}, falling back to cache")
        
        # Fallback: Use cached data
        if self.data is None:
            raise ValueError("Cache not loaded and no database manager provided")
        
        years = self.data['jaar'].dropna().unique()
        return sorted([str(int(y)) for y in years], reverse=True)
    
    def get_available_administrations(self, year=None):
        """
        Get list of available administrations from cache
        
        Args:
            year: Optional year filter
            
        Returns:
            list: Sorted list of administrations
        """
        if self.data is None:
            raise ValueError("Cache not loaded")
        
        df = self.data
        
        if year:
            df = df[df['jaar'] == int(year)]
        
        admins = df['administration'].dropna().unique()
        return sorted(admins.tolist())


# Global cache instance
_cache = None


def get_cache(ttl_minutes=30):
    """
    Get or create the global cache instance
    
    Args:
        ttl_minutes: Time to live in minutes (default: 30)
        
    Returns:
        MutatiesCache: Global cache instance
    """
    global _cache
    if _cache is None:
        _cache = MutatiesCache(ttl_minutes=ttl_minutes)
    return _cache


def invalidate_cache():
    """Invalidate the global cache"""
    global _cache
    if _cache:
        _cache.invalidate()
