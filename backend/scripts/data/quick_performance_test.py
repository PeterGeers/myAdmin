#!/usr/bin/env python3
import sys
import os
import time

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pattern_analyzer import PatternAnalyzer

# Quick performance validation
analyzer = PatternAnalyzer()
start = time.perf_counter()
patterns = analyzer.get_filtered_patterns('GoodwinSolutions')
elapsed = time.perf_counter() - start

print(f'✅ Pattern retrieval: {elapsed:.6f}s ({patterns["patterns_discovered"]} patterns)')
print(f'✅ Performance target: {"EXCEEDED" if elapsed < 0.001 else "MET" if elapsed < 0.08 else "NOT MET"}')

# Get cache stats
stats = analyzer.persistent_cache.get_cache_stats()
print(f'✅ Cache hit rate: {stats["performance"]["hit_rate_percent"]:.1f}%')
print(f'✅ Memory cache entries: {stats["cache_levels"]["memory_entries"]}')