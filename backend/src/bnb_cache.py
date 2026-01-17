"""
BNB Data Cache Module

Provides in-memory caching of BNB booking data using pandas DataFrame
for fast querying and filtering operations.
"""

import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class BnbCache:
    """In-memory cache for BNB booking data"""
    
    def __init__(self, ttl_minutes=30):
        self.data = None
        self.last_refresh = None
        self.ttl = timedelta(minutes=ttl_minutes)
        logger.info(f"BnbCache initialized with TTL={ttl_minutes} minutes")
    
    def is_valid(self):
        """Check if cache is still valid"""
        if self.data is None or self.last_refresh is None:
            return False
        return datetime.now() - self.last_refresh < self.ttl
    
    def get_data(self, db):
        """Get cached data, refresh if needed"""
        if not self.is_valid():
            self.refresh(db)
        return self.data
    
    def refresh(self, db):
        """Refresh cache from database"""
        start_time = datetime.now()
        logger.info("Loading BNB data into memory cache...")
        
        try:
            # Use vw_bnb_total view to get both actual and planned bookings
            query = """
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
                YEAR(checkinDate) as year,
                QUARTER(checkinDate) as quarter,
                MONTH(checkinDate) as month
            FROM vw_bnb_total
            ORDER BY checkinDate DESC
            """
            
            # Get connection from database manager
            with db.get_cursor() as (cursor, conn):
                self.data = pd.read_sql(query, conn)
            
            # Convert date columns to datetime
            self.data['checkinDate'] = pd.to_datetime(self.data['checkinDate'])
            self.data['checkoutDate'] = pd.to_datetime(self.data['checkoutDate'])
            
            # Ensure numeric columns are float
            numeric_cols = ['nights', 'amountGross', 'amountNett', 'amountChannelFee', 
                          'amountTouristTax', 'amountVat', 'guests']
            for col in numeric_cols:
                self.data[col] = pd.to_numeric(self.data[col], errors='coerce').fillna(0)
            
            # Fill NaN values in string columns
            string_cols = ['channel', 'listing', 'guestName', 'reservationCode', 'status', 'source_type']
            for col in string_cols:
                self.data[col] = self.data[col].fillna('')
            
            self.last_refresh = datetime.now()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            memory_mb = self.data.memory_usage(deep=True).sum() / 1024 / 1024
            
            # Count actual vs planned
            actual_count = len(self.data[self.data['source_type'] == 'actual'])
            planned_count = len(self.data[self.data['source_type'] == 'planned'])
            
            logger.info(f"Cache loaded: {len(self.data):,} rows ({actual_count:,} actual, {planned_count:,} planned) in {elapsed:.2f}s")
            logger.info(f"Memory usage: ~{memory_mb:.1f} MB")
            
        except Exception as e:
            logger.error(f"Failed to refresh BNB cache: {e}")
            raise
    
    def invalidate(self):
        """Invalidate cache"""
        self.data = None
        self.last_refresh = None
        logger.info("BNB cache invalidated")
    
    def get_status(self):
        """Get cache status information"""
        if self.data is None:
            return {
                'loaded': False,
                'row_count': 0,
                'memory_mb': 0,
                'last_refresh': None,
                'ttl_minutes': self.ttl.total_seconds() / 60,
                'is_valid': False
            }
        
        memory_mb = self.data.memory_usage(deep=True).sum() / 1024 / 1024
        
        return {
            'loaded': True,
            'row_count': len(self.data),
            'memory_mb': round(memory_mb, 1),
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'ttl_minutes': self.ttl.total_seconds() / 60,
            'is_valid': self.is_valid()
        }
    
    def query_by_year(self, db, year, status=None):
        """Query bookings by year and optional status"""
        df = self.get_data(db)
        df = df[df['year'] == int(year)].copy()
        
        if status:
            df = df[df['status'] == status]
        
        return df.to_dict('records')
    
    def query_cancelled_by_year(self, db, year):
        """Get cancelled bookings for a specific year"""
        return self.query_by_year(db, year, status='cancelled')
    
    def query_realised_by_year(self, db, year):
        """Get realised (non-cancelled) bookings for a specific year"""
        df = self.get_data(db)
        df = df[(df['year'] == int(year)) & (df['status'] != 'cancelled')].copy()
        return df.to_dict('records')


# Global cache instance
_bnb_cache = None

def get_bnb_cache():
    """Get or create global BNB cache instance"""
    global _bnb_cache
    if _bnb_cache is None:
        _bnb_cache = BnbCache(ttl_minutes=30)
    return _bnb_cache
