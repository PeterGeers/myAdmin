"""
Query Optimization for Duplicate Detection System

This module provides query optimization, caching, and performance tuning
specifically for duplicate detection database operations.

Requirements: 5.5, 6.4
"""

import time
import hashlib
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from functools import lru_cache
import json

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
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float
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
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float
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
            if datetime.now() < entry['expires_at']:
                self.hits += 1
                logger.debug(f"Cache hit for key: {cache_key}")
                return entry['data']
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
        ttl: Optional[int] = None
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
            'data': data,
            'cached_at': datetime.now(),
            'expires_at': expires_at,
            'ttl': ttl
        }
        
        logger.debug(f"Cached result for key: {cache_key} (TTL: {ttl}s)")
    
    def invalidate(
        self,
        reference_number: Optional[str] = None,
        transaction_date: Optional[str] = None,
        transaction_amount: Optional[float] = None
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
            key for key, entry in self.cache.items()
            if now >= entry['expires_at']
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
            'total_entries': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate_percent': round(hit_rate, 2),
            'evictions': self.evictions,
            'total_requests': total_requests
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
            'total_queries': 0,
            'cached_queries': 0,
            'optimized_queries': 0,
            'slow_queries': 0
        }
    
    def check_duplicates_optimized(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float,
        table_name: str = 'mutaties',
        use_cache: bool = True
    ) -> Tuple[List[Dict], Dict]:
        """
        Execute optimized duplicate check with caching and performance tracking.
        
        Args:
            reference_number: Reference number to check
            transaction_date: Transaction date
            transaction_amount: Transaction amount
            table_name: Database table name
            use_cache: Whether to use query cache
            
        Returns:
            Tuple of (results, performance_info)
        """
        start_time = time.time()
        cache_hit = False
        
        # Try cache first if enabled
        if use_cache:
            cached_result = self.cache.get(
                reference_number, transaction_date, transaction_amount
            )
            if cached_result is not None:
                execution_time = time.time() - start_time
                cache_hit = True
                self.query_stats['cached_queries'] += 1
                
                performance_info = {
                    'execution_time': execution_time,
                    'cache_hit': True,
                    'rows_returned': len(cached_result),
                    'query_optimized': False
                }
                
                return cached_result, performance_info
        
        # Execute query with optimization
        try:
            # Use optimized query with proper indexing
            query = f"""
                SELECT 
                    ID, TransactionNumber, TransactionDate, TransactionDescription,
                    TransactionAmount, Debet, Credit, ReferenceNumber,
                    Ref1, Ref2, Ref3, Ref4, Administration
                FROM {table_name}
                WHERE ReferenceNumber = %s
                    AND TransactionDate = %s
                    AND ABS(TransactionAmount - %s) < 0.01
                    AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
                ORDER BY ID DESC
                LIMIT 100
            """
            
            results = self.db.execute_query(
                query,
                (reference_number, transaction_date, transaction_amount),
                fetch=True
            )
            
            execution_time = time.time() - start_time
            
            # Cache the result if caching is enabled
            if use_cache and results is not None:
                self.cache.set(
                    reference_number, transaction_date, transaction_amount,
                    results if results else []
                )
            
            # Track statistics
            self.query_stats['total_queries'] += 1
            self.query_stats['optimized_queries'] += 1
            
            if execution_time > 2.0:
                self.query_stats['slow_queries'] += 1
                logger.warning(
                    f"Slow duplicate check query: {execution_time:.3f}s for "
                    f"{reference_number} on {transaction_date}"
                )
            
            performance_info = {
                'execution_time': execution_time,
                'cache_hit': False,
                'rows_returned': len(results) if results else 0,
                'query_optimized': True,
                'slow_query': execution_time > 2.0
            }
            
            return results if results else [], performance_info
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error in optimized duplicate check: {e}")
            
            performance_info = {
                'execution_time': execution_time,
                'cache_hit': False,
                'rows_returned': 0,
                'query_optimized': False,
                'error': str(e)
            }
            
            raise
    
    def analyze_query_performance(self, query: str, params: Tuple) -> Dict:
        """
        Analyze query performance using EXPLAIN.
        
        Args:
            query: SQL query to analyze
            params: Query parameters
            
        Returns:
            Dictionary with query analysis results
        """
        try:
            # Execute EXPLAIN query
            explain_query = f"EXPLAIN {query}"
            explain_results = self.db.execute_query(explain_query, params, fetch=True)
            
            analysis = {
                'timestamp': datetime.now().isoformat(),
                'query': query,
                'explain_results': explain_results,
                'recommendations': []
            }
            
            # Analyze EXPLAIN results
            if explain_results:
                for row in explain_results:
                    # Check for full table scans
                    if row.get('type') == 'ALL':
                        analysis['recommendations'].append(
                            f"Full table scan detected on table '{row.get('table')}'. "
                            "Consider adding an index."
                        )
                    
                    # Check for large row counts
                    if row.get('rows') and row['rows'] > 10000:
                        analysis['recommendations'].append(
                            f"Query examines {row['rows']} rows. "
                            "Consider adding more selective WHERE clauses or indexes."
                        )
                    
                    # Check for missing indexes
                    if row.get('key') is None:
                        analysis['recommendations'].append(
                            f"No index used for table '{row.get('table')}'. "
                            "Consider creating an appropriate index."
                        )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing query performance: {e}")
            return {
                'error': str(e),
                'query': query
            }
    
    def get_optimization_recommendations(self) -> List[str]:
        """
        Get query optimization recommendations based on collected statistics.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Check cache hit rate
        cache_stats = self.cache.get_stats()
        if cache_stats['hit_rate_percent'] < 50 and cache_stats['total_requests'] > 10:
            recommendations.append(
                f"Cache hit rate is low ({cache_stats['hit_rate_percent']:.1f}%). "
                "Consider increasing cache TTL or reviewing cache invalidation strategy."
            )
        
        # Check slow query rate
        if self.query_stats['total_queries'] > 0:
            slow_query_rate = (
                self.query_stats['slow_queries'] / self.query_stats['total_queries'] * 100
            )
            if slow_query_rate > 10:
                recommendations.append(
                    f"High slow query rate ({slow_query_rate:.1f}%). "
                    "Review database indexes and query optimization."
                )
        
        # Check if indexes exist
        recommendations.append(
            "Ensure composite index exists on (ReferenceNumber, TransactionDate, TransactionAmount) "
            "for optimal duplicate detection performance."
        )
        
        # General recommendations
        if not recommendations:
            recommendations.append(
                "Query performance is good. Continue monitoring for any degradation."
            )
        
        return recommendations
    
    def get_query_statistics(self) -> Dict:
        """
        Get query execution statistics.
        
        Returns:
            Dictionary with query statistics
        """
        cache_stats = self.cache.get_stats()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'query_stats': self.query_stats.copy(),
            'cache_stats': cache_stats,
            'cache_efficiency': {
                'hit_rate_percent': cache_stats['hit_rate_percent'],
                'total_entries': cache_stats['total_entries'],
                'memory_saved_queries': cache_stats['hits']
            },
            'performance_metrics': {
                'slow_query_rate': (
                    self.query_stats['slow_queries'] / self.query_stats['total_queries'] * 100
                    if self.query_stats['total_queries'] > 0 else 0
                ),
                'cache_utilization_rate': (
                    self.query_stats['cached_queries'] / self.query_stats['total_queries'] * 100
                    if self.query_stats['total_queries'] > 0 else 0
                )
            }
        }
    
    def invalidate_cache_for_transaction(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float
    ) -> None:
        """
        Invalidate cache for a specific transaction.
        
        Should be called when a new transaction is inserted to ensure
        cache consistency.
        
        Args:
            reference_number: Reference number
            transaction_date: Transaction date
            transaction_amount: Transaction amount
        """
        self.cache.invalidate(reference_number, transaction_date, transaction_amount)
        logger.info(
            f"Invalidated cache for transaction: {reference_number} "
            f"on {transaction_date} amount {transaction_amount}"
        )
    
    def cleanup_cache(self) -> int:
        """
        Cleanup expired cache entries.
        
        Returns:
            Number of entries removed
        """
        return self.cache.cleanup_expired()
    
    def reset_statistics(self) -> None:
        """Reset query statistics."""
        self.query_stats = {
            'total_queries': 0,
            'cached_queries': 0,
            'optimized_queries': 0,
            'slow_queries': 0
        }
        self.cache.reset_stats()
        logger.info("Query statistics reset")


# Global query optimizer instance
_global_optimizer = None


def get_query_optimizer(db_manager=None, cache_ttl: int = 300) -> DuplicateQueryOptimizer:
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


def reset_query_optimizer() -> None:
    """Reset global query optimizer instance."""
    global _global_optimizer
    _global_optimizer = None
