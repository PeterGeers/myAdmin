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
    
    def _refresh(self, db_manager):
        """
        Refresh cache from database
        
        Args:
            db_manager: DatabaseManager instance
        """
        try:
            self._loading = True
            start_time = datetime.now()
            
            logger.info("Loading vw_mutaties into memory cache...")
            
            conn = db_manager.get_connection()
            
            # Load all data from view
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
    
    def query_aangifte_ib(self, year, administration='all'):
        """
        Query Aangifte IB data from cache
        
        Args:
            year: Year to filter (string or int)
            administration: Administration to filter (default: 'all')
            
        Returns:
            dict: Summary data grouped by Parent and Aangifte
        """
        if self.data is None:
            raise ValueError("Cache not loaded")
        
        df = self.data.copy()
        
        # Apply VW logic: N (Balance) = all up to year end, Y (P&L) = only that year
        year_end = pd.to_datetime(f"{year}-12-31")
        mask = (
            ((df['VW'] == 'N') & (df['TransactionDate'] <= year_end)) |
            ((df['VW'] == 'Y') & (df['jaar'] == int(year)))
        )
        df = df[mask]
        
        # Filter by administration
        if administration != 'all':
            df = df[df['Administration'].str.startswith(administration)]
        
        # Group by Parent and Aangifte
        summary = df.groupby(['Parent', 'Aangifte'])['Amount'].sum().reset_index()
        summary.columns = ['Parent', 'Aangifte', 'Amount']
        
        return summary.to_dict('records')
    
    def query_aangifte_ib_details(self, year, administration, parent, aangifte, user_tenants=None):
        """
        Query detailed accounts for specific Parent and Aangifte
        
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
            df = df[df['Administration'].isin(user_tenants)]
        
        # Apply VW logic
        year_end = pd.to_datetime(f"{year}-12-31")
        mask = (
            ((df['VW'] == 'N') & (df['TransactionDate'] <= year_end)) |
            ((df['VW'] == 'Y') & (df['jaar'] == int(year)))
        )
        df = df[mask]
        
        # Filter by criteria
        if administration != 'all':
            df = df[df['Administration'].str.startswith(administration)]
        
        df = df[(df['Parent'] == parent) & (df['Aangifte'] == aangifte)]
        
        # Group by account
        details = df.groupby(['Reknum', 'AccountName'])['Amount'].sum().reset_index()
        details.columns = ['Reknum', 'AccountName', 'Amount']
        
        return details.to_dict('records')
    
    def get_available_years(self):
        """Get list of available years from cache"""
        if self.data is None:
            raise ValueError("Cache not loaded")
        
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
        
        admins = df['Administration'].dropna().unique()
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
