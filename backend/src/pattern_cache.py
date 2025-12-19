#!/usr/bin/env python3
"""
Persistent Pattern Cache System

Implements persistent caching for pattern analysis that:
- Survives application restarts
- Shares cache between multiple instances
- Uses multi-level caching (memory + database + file)
- Provides cache warming on startup
- Implements cache invalidation strategies

REQ-PAT-006: Implement pattern caching for performance
- Persistent Pattern Cache: Pattern cache survives application restarts and is shared between instances
"""

import json
import os
import pickle
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PersistentPatternCache:
    """
    Multi-level persistent cache for pattern analysis
    
    Cache Levels:
    1. Memory Cache (L1) - Fastest access, volatile
    2. Database Cache (L2) - Persistent, shared between instances
    3. File Cache (L3) - Backup persistence, local to instance
    
    Features:
    - Automatic cache warming on startup
    - Cache invalidation based on data freshness
    - Thread-safe operations
    - Fallback mechanisms between cache levels
    """
    
    def __init__(self, db_manager, cache_dir: str = "cache", max_memory_entries: int = 1000):
        """
        Initialize persistent pattern cache
        
        Args:
            db_manager: Database manager instance for L2 cache
            cache_dir: Directory for file-based cache (L3)
            max_memory_entries: Maximum entries in memory cache (L1)
        """
        self.db = db_manager
        self.cache_dir = Path(cache_dir)
        self.max_memory_entries = max_memory_entries
        
        # L1 Cache: Memory (fastest, volatile)
        self._memory_cache = {}
        self._memory_access_times = {}
        self._cache_lock = threading.RLock()
        
        # L3 Cache: File system (backup persistence)
        self.cache_dir.mkdir(exist_ok=True)
        self.patterns_file = self.cache_dir / "patterns_cache.json"
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        
        # Cache statistics
        self.stats = {
            'hits': {'memory': 0, 'database': 0, 'file': 0},
            'misses': 0,
            'writes': {'memory': 0, 'database': 0, 'file': 0},
            'evictions': 0,
            'startup_time': None
        }
        
        # Initialize cache
        self._initialize_cache()
    
    def _initialize_cache(self):
        """Initialize cache system and warm up from persistent storage"""
        start_time = time.time()
        logger.info("🔥 Warming up persistent pattern cache...")
        
        try:
            # Try to load from file cache first (L3)
            self._load_from_file_cache()
            
            # Validate cache freshness and load from database if needed (L2)
            self._validate_and_refresh_cache()
            
            self.stats['startup_time'] = time.time() - start_time
            logger.info(f"✅ Cache warmed up in {self.stats['startup_time']:.3f}s with {len(self._memory_cache)} entries")
            
        except Exception as e:
            logger.error(f"❌ Cache initialization failed: {e}")
            self._memory_cache = {}
    
    def get_patterns(self, administration: str, 
                    reference_number: Optional[str] = None,
                    debet_account: Optional[str] = None,
                    credit_account: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get patterns from cache with multi-level fallback
        
        Cache lookup order:
        1. Memory cache (L1) - fastest
        2. Database cache (L2) - persistent, shared
        3. File cache (L3) - backup
        4. Return None if not found (triggers fresh analysis)
        """
        cache_key = self._build_cache_key(administration, reference_number, debet_account, credit_account)
        
        with self._cache_lock:
            # L1: Check memory cache first
            if cache_key in self._memory_cache:
                entry = self._memory_cache[cache_key]
                if self._is_cache_entry_valid(entry):
                    self._memory_access_times[cache_key] = time.time()
                    self.stats['hits']['memory'] += 1
                    logger.debug(f"📋 Cache HIT (Memory): {cache_key}")
                    return entry['data']
                else:
                    # Entry expired, remove from memory
                    del self._memory_cache[cache_key]
                    if cache_key in self._memory_access_times:
                        del self._memory_access_times[cache_key]
            
            # L2: Check database cache
            db_patterns = self._load_from_database_cache(administration)
            if db_patterns and db_patterns.get('patterns_discovered', 0) > 0:
                # Store in memory cache for faster future access
                self._store_in_memory_cache(cache_key, db_patterns)
                self.stats['hits']['database'] += 1
                logger.debug(f"📋 Cache HIT (Database): {cache_key}")
                return db_patterns
            
            # L3: Check file cache as last resort
            file_patterns = self._load_from_file_cache_key(cache_key)
            if file_patterns:
                # Store in memory cache for faster future access
                self._store_in_memory_cache(cache_key, file_patterns)
                self.stats['hits']['file'] += 1
                logger.debug(f"📋 Cache HIT (File): {cache_key}")
                return file_patterns
            
            # Cache miss - no valid data found
            self.stats['misses'] += 1
            logger.debug(f"📋 Cache MISS: {cache_key}")
            return None
    
    def store_patterns(self, administration: str, patterns: Dict[str, Any],
                      reference_number: Optional[str] = None,
                      debet_account: Optional[str] = None,
                      credit_account: Optional[str] = None):
        """
        Store patterns in all cache levels for maximum persistence
        
        Storage order:
        1. Memory cache (L1) - immediate access
        2. Database cache (L2) - persistent, shared (already handled by pattern_analyzer)
        3. File cache (L3) - backup persistence
        """
        cache_key = self._build_cache_key(administration, reference_number, debet_account, credit_account)
        
        with self._cache_lock:
            # L1: Store in memory cache
            self._store_in_memory_cache(cache_key, patterns)
            self.stats['writes']['memory'] += 1
            
            # L3: Store in file cache (L2 is handled by pattern_analyzer)
            self._store_in_file_cache(cache_key, patterns)
            self.stats['writes']['file'] += 1
            
            logger.debug(f"💾 Stored patterns in cache: {cache_key}")
    
    def invalidate_cache(self, administration: str):
        """
        Invalidate all cache entries for a specific administration
        
        This is called when new transactions are processed or patterns are updated
        """
        with self._cache_lock:
            # Remove from memory cache
            keys_to_remove = [key for key in self._memory_cache.keys() if key.startswith(f"{administration}_")]
            for key in keys_to_remove:
                del self._memory_cache[key]
                if key in self._memory_access_times:
                    del self._memory_access_times[key]
            
            # Remove from file cache
            self._remove_from_file_cache(administration)
            
            logger.info(f"🗑️ Invalidated cache for administration: {administration}")
    
    def clear_all_cache(self):
        """Clear all cache levels - useful for testing or maintenance"""
        with self._cache_lock:
            self._memory_cache.clear()
            self._memory_access_times.clear()
            
            # Clear file cache
            if self.patterns_file.exists():
                self.patterns_file.unlink()
            if self.metadata_file.exists():
                self.metadata_file.unlink()
            
            logger.info("🗑️ Cleared all cache levels")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        with self._cache_lock:
            total_hits = sum(self.stats['hits'].values())
            total_requests = total_hits + self.stats['misses']
            hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'cache_levels': {
                    'memory_entries': len(self._memory_cache),
                    'database_active': True,  # L2 is always active via pattern_analyzer
                    'file_cache_exists': self.patterns_file.exists()
                },
                'performance': {
                    'hit_rate_percent': round(hit_rate, 2),
                    'total_requests': total_requests,
                    'startup_time_seconds': self.stats.get('startup_time', 0)
                },
                'hits_by_level': self.stats['hits'],
                'writes_by_level': self.stats['writes'],
                'misses': self.stats['misses'],
                'evictions': self.stats['evictions'],
                'memory_usage': {
                    'max_entries': self.max_memory_entries,
                    'current_entries': len(self._memory_cache),
                    'utilization_percent': round(len(self._memory_cache) / self.max_memory_entries * 100, 2)
                }
            }
    
    def _build_cache_key(self, administration: str, 
                        reference_number: Optional[str] = None,
                        debet_account: Optional[str] = None,
                        credit_account: Optional[str] = None) -> str:
        """Build cache key for filtered patterns"""
        key_parts = [administration]
        if reference_number:
            key_parts.append(f"ref:{reference_number}")
        if debet_account:
            key_parts.append(f"deb:{debet_account}")
        if credit_account:
            key_parts.append(f"cred:{credit_account}")
        return "_".join(key_parts)
    
    def _store_in_memory_cache(self, cache_key: str, patterns: Dict[str, Any]):
        """Store patterns in memory cache with LRU eviction"""
        # Check if we need to evict entries
        if len(self._memory_cache) >= self.max_memory_entries:
            self._evict_lru_entries()
        
        # Store with timestamp
        cache_entry = {
            'data': patterns,
            'timestamp': time.time(),
            'ttl_hours': 24  # Cache valid for 24 hours
        }
        
        self._memory_cache[cache_key] = cache_entry
        self._memory_access_times[cache_key] = time.time()
    
    def _evict_lru_entries(self):
        """Evict least recently used entries from memory cache"""
        if not self._memory_access_times:
            return
        
        # Remove 10% of entries (LRU)
        entries_to_remove = max(1, len(self._memory_cache) // 10)
        
        # Sort by access time (oldest first)
        sorted_entries = sorted(self._memory_access_times.items(), key=lambda x: x[1])
        
        for cache_key, _ in sorted_entries[:entries_to_remove]:
            if cache_key in self._memory_cache:
                del self._memory_cache[cache_key]
            if cache_key in self._memory_access_times:
                del self._memory_access_times[cache_key]
            self.stats['evictions'] += 1
    
    def _is_cache_entry_valid(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid based on TTL"""
        if 'timestamp' not in entry or 'ttl_hours' not in entry:
            return False
        
        age_hours = (time.time() - entry['timestamp']) / 3600
        return age_hours < entry['ttl_hours']
    
    def _load_from_database_cache(self, administration: str) -> Optional[Dict[str, Any]]:
        """Load patterns from database cache (L2)"""
        try:
            # Check if patterns exist in database and are fresh
            metadata = self.db.execute_query("""
                SELECT last_analysis_date, transactions_analyzed, patterns_discovered
                FROM pattern_analysis_metadata 
                WHERE administration = %s
            """, (administration,))
            
            if not metadata or not metadata[0]['last_analysis_date']:
                return None
            
            last_analysis = metadata[0]['last_analysis_date']
            
            # Check if analysis is recent (within 24 hours)
            if datetime.now() - last_analysis > timedelta(hours=24):
                return None
            
            # Load patterns from database
            verb_results = self.db.execute_query("""
                SELECT administration, bank_account, verb, verb_company, verb_reference, 
                       is_compound, reference_number, debet_account, credit_account, 
                       occurrences, confidence, last_seen, sample_description
                FROM pattern_verb_patterns 
                WHERE administration = %s
                ORDER BY last_seen DESC, occurrences DESC
            """, (administration,))
            
            if not verb_results:
                return None
            
            # Convert to pattern format
            reference_patterns = {}
            for row in verb_results:
                pattern_key = f"{row['administration']}_{row['bank_account']}_{row['verb']}"
                reference_patterns[pattern_key] = {
                    'administration': row['administration'],
                    'bank_account': row['bank_account'],
                    'verb': row['verb'],
                    'verb_company': row['verb_company'],
                    'verb_reference': row['verb_reference'],
                    'is_compound': bool(row['is_compound']),
                    'reference_number': row['reference_number'],
                    'debet_account': row['debet_account'],
                    'credit_account': row['credit_account'],
                    'occurrences': row['occurrences'],
                    'confidence': float(row['confidence']) if row['confidence'] else 1.0,
                    'last_seen': row['last_seen'],
                    'sample_description': row['sample_description']
                }
            
            meta = metadata[0]
            return {
                'debet_patterns': {},
                'credit_patterns': {},
                'reference_patterns': reference_patterns,
                'total_transactions': meta['transactions_analyzed'] or 0,
                'patterns_discovered': len(reference_patterns),
                'analysis_date': last_analysis.isoformat(),
                'date_range': {
                    'from': (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d'),
                    'to': datetime.now().strftime('%Y-%m-%d')
                },
                'statistics': {
                    'patterns_by_type': {
                        'debet_patterns': 0,
                        'credit_patterns': 0,
                        'reference_patterns': len(reference_patterns)
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error loading from database cache: {e}")
            return None
    
    def _load_from_file_cache(self):
        """Load cache from file system (L3) during startup"""
        try:
            if not self.patterns_file.exists():
                return
            
            with open(self.patterns_file, 'r', encoding='utf-8') as f:
                file_cache = json.load(f)
            
            # Load into memory cache with validation
            loaded_count = 0
            for cache_key, entry in file_cache.items():
                if self._is_cache_entry_valid(entry):
                    self._memory_cache[cache_key] = entry
                    self._memory_access_times[cache_key] = time.time()
                    loaded_count += 1
            
            logger.info(f"📁 Loaded {loaded_count} entries from file cache")
            
        except Exception as e:
            logger.error(f"Error loading file cache: {e}")
    
    def _load_from_file_cache_key(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Load specific key from file cache"""
        try:
            if not self.patterns_file.exists():
                return None
            
            with open(self.patterns_file, 'r', encoding='utf-8') as f:
                file_cache = json.load(f)
            
            if cache_key in file_cache:
                entry = file_cache[cache_key]
                if self._is_cache_entry_valid(entry):
                    return entry['data']
            
            return None
            
        except Exception as e:
            logger.error(f"Error loading from file cache key {cache_key}: {e}")
            return None
    
    def _store_in_file_cache(self, cache_key: str, patterns: Dict[str, Any]):
        """Store patterns in file cache (L3)"""
        try:
            # Load existing cache
            file_cache = {}
            if self.patterns_file.exists():
                with open(self.patterns_file, 'r', encoding='utf-8') as f:
                    file_cache = json.load(f)
            
            # Add new entry
            cache_entry = {
                'data': patterns,
                'timestamp': time.time(),
                'ttl_hours': 24
            }
            file_cache[cache_key] = cache_entry
            
            # Clean up expired entries
            current_time = time.time()
            file_cache = {
                k: v for k, v in file_cache.items()
                if self._is_cache_entry_valid(v)
            }
            
            # Write back to file
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(file_cache, f, indent=2, default=str)
            
            # Update metadata
            metadata = {
                'last_updated': datetime.now().isoformat(),
                'total_entries': len(file_cache),
                'cache_version': '1.0'
            }
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error storing in file cache: {e}")
    
    def _remove_from_file_cache(self, administration: str):
        """Remove entries for specific administration from file cache"""
        try:
            if not self.patterns_file.exists():
                return
            
            with open(self.patterns_file, 'r', encoding='utf-8') as f:
                file_cache = json.load(f)
            
            # Remove entries for this administration
            keys_to_remove = [key for key in file_cache.keys() if key.startswith(f"{administration}_")]
            for key in keys_to_remove:
                del file_cache[key]
            
            # Write back
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(file_cache, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Error removing from file cache: {e}")
    
    def _validate_and_refresh_cache(self):
        """Validate cache freshness and refresh if needed"""
        try:
            # Check if we have any administrations in memory cache
            administrations = set()
            for cache_key in self._memory_cache.keys():
                admin = cache_key.split('_')[0]
                administrations.add(admin)
            
            # Validate each administration's cache freshness
            for admin in administrations:
                db_patterns = self._load_from_database_cache(admin)
                if db_patterns:
                    # Update memory cache with fresh database data
                    cache_key = self._build_cache_key(admin)
                    self._store_in_memory_cache(cache_key, db_patterns)
                    
        except Exception as e:
            logger.error(f"Error validating cache: {e}")


# Global cache instance (singleton pattern)
_cache_instance = None
_cache_lock = threading.Lock()


def get_pattern_cache(db_manager) -> PersistentPatternCache:
    """
    Get singleton instance of persistent pattern cache
    
    This ensures all parts of the application use the same cache instance
    """
    global _cache_instance
    
    if _cache_instance is None:
        with _cache_lock:
            if _cache_instance is None:
                _cache_instance = PersistentPatternCache(db_manager)
    
    return _cache_instance