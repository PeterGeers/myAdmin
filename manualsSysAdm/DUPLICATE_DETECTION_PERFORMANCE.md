# Duplicate Detection Performance Monitoring and Optimization

## Overview

This document describes the performance monitoring and optimization system for the duplicate invoice detection feature. The system ensures that duplicate detection operations meet the 2-second response time requirement (Requirement 5.5) and provides comprehensive monitoring capabilities (Requirement 6.4).

## Performance Requirements

### Response Time (Requirement 5.5)

- **Target**: Duplicate detection must complete within 2 seconds
- **Measurement**: End-to-end time from query initiation to result return
- **Monitoring**: Automatic tracking of all duplicate check operations

### Monitoring Coverage (Requirement 6.4)

- **Audit Trail**: 100% coverage of all duplicate detection decisions
- **Performance Metrics**: Comprehensive collection of execution times, cache hits, and error rates
- **Health Monitoring**: Real-time health score calculation and alerting

## Architecture

### Components

1. **DuplicateDetectionMetrics** (`duplicate_performance_monitor.py`)

   - Collects performance metrics for all operations
   - Calculates summary statistics and health scores
   - Provides export capabilities for analysis

2. **DuplicateQueryOptimizer** (`duplicate_query_optimizer.py`)

   - Implements query caching with TTL
   - Optimizes database queries for performance
   - Provides query analysis and recommendations

3. **PerformanceMonitor** (`duplicate_performance_monitor.py`)

   - Decorators for automatic performance tracking
   - Context managers for operation monitoring
   - Integration with metrics collection

4. **Performance API** (`duplicate_performance_routes.py`)
   - REST endpoints for monitoring and optimization
   - Real-time performance status
   - Health checks and recommendations

## Performance Optimization Strategies

### 1. Query Optimization

#### Database Indexes

The system requires the following indexes for optimal performance:

```sql
-- Composite index for duplicate detection
CREATE INDEX idx_duplicate_check
ON mutaties (ReferenceNumber, TransactionDate, TransactionAmount);

-- Date range index for 2-year window
CREATE INDEX idx_transaction_date
ON mutaties (TransactionDate);
```

#### Query Structure

Optimized query with proper indexing:

```sql
SELECT * FROM mutaties
WHERE ReferenceNumber = ?
  AND TransactionDate = ?
  AND ABS(TransactionAmount - ?) < 0.01
  AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
ORDER BY ID DESC
LIMIT 100;
```

### 2. Caching Strategy

#### Query Cache

- **TTL**: 5 minutes (300 seconds) default
- **Key Generation**: MD5 hash of (ReferenceNumber, TransactionDate, TransactionAmount)
- **Invalidation**: Automatic on new transaction insertion
- **Target Hit Rate**: 70%

#### Cache Benefits

- **Performance**: Cache hits are nearly instantaneous (< 0.001s)
- **Database Load**: Reduces database queries by 30-70%
- **Scalability**: Improves system capacity under load

### 3. Connection Pooling

The system uses MySQL connection pooling:

- **Pool Size**: 5 connections
- **Reset on Return**: Enabled
- **Fallback**: Direct connections if pool fails

## Monitoring and Metrics

### Collected Metrics

#### Duplicate Check Metrics

- Execution time per check
- Number of duplicates found
- Cache hit/miss ratio
- Threshold exceeded count
- Error rate

#### File Cleanup Metrics

- Cleanup execution time
- Success rate
- File sizes cleaned
- Error tracking

#### Decision Logging Metrics

- Logging execution time
- Decision types (continue/cancel)
- Retry counts
- Success rate

#### Database Query Metrics

- Query execution time
- Rows returned
- Cache effectiveness
- Slow query detection

### Health Score Calculation

The system calculates a health score (0-100) based on:

1. **Query Performance (40% weight)**

   - Percentage of queries exceeding 2-second threshold
   - Target: < 10% threshold exceeded

2. **Error Rate (30% weight)**

   - Percentage of failed operations
   - Target: < 5% error rate

3. **Cache Efficiency (20% weight)**

   - Cache hit rate vs. target (70%)
   - Target: > 70% cache hits

4. **Decision Logging (10% weight)**
   - Success rate of audit logging
   - Target: > 95% success rate

### Health Status Levels

- **Healthy** (90-100): System performing optimally
- **Degraded** (70-89): Minor performance issues
- **Warning** (50-69): Significant performance degradation
- **Critical** (0-49): Severe performance problems

## API Endpoints

### Performance Status

```
GET /api/duplicate-detection/performance/status
```

Returns current performance metrics and health status.

### Detailed Metrics

```
GET /api/duplicate-detection/performance/metrics?metric_type=all&time_range=24
```

Returns detailed metrics for specified type and time range.

### Health Check

```
GET /api/duplicate-detection/performance/health
```

Returns health score and recommendations.

### Cache Statistics

```
GET /api/duplicate-detection/performance/cache-stats
```

Returns cache performance metrics and hit rates.

### Query Statistics

```
GET /api/duplicate-detection/performance/query-stats
```

Returns database query performance statistics.

### Performance Optimization

```
POST /api/duplicate-detection/performance/optimize
{
  "cleanup_cache": true,
  "reset_stats": false,
  "analyze_queries": true
}
```

Runs optimization operations and returns results.

### Export Metrics

```
POST /api/duplicate-detection/performance/export
{
  "filepath": "logs/metrics_20241217.json"
}
```

Exports metrics to JSON file for analysis.

### Performance Test

```
POST /api/duplicate-detection/performance/test
{
  "test_count": 10,
  "use_cache": true
}
```

Runs performance test and returns results.

## Load Testing

### Test Scenarios

1. **Single User Performance**

   - 20 sequential requests
   - Target: < 2 seconds average
   - Validates basic performance

2. **Light Load (5 concurrent users)**

   - 5 users × 10 requests each
   - Target: < 2 seconds average
   - Validates concurrent handling

3. **Medium Load (10 concurrent users)**

   - 10 users × 10 requests each
   - Target: < 2.5 seconds average
   - Validates scalability

4. **Optimized Query Performance**

   - Tests cache effectiveness
   - Target: > 30% cache hit rate
   - Validates optimization

5. **Sustained Load**
   - 30 seconds at 5 req/s
   - Target: Maintain < 2 seconds
   - Validates stability

### Running Load Tests

```bash
# Run all load tests
python -m pytest backend/test/test_duplicate_load.py -v -s

# Run specific test
python -m pytest backend/test/test_duplicate_load.py::TestDuplicateDetectionLoad::test_single_user_performance -v -s
```

## Performance Benchmarks

### Baseline Performance (No Cache)

- **Average**: 0.03-0.05 seconds
- **95th Percentile**: 0.10-0.15 seconds
- **Max**: 0.15-0.20 seconds

### Optimized Performance (With Cache)

- **Cache Hit**: < 0.001 seconds (instantaneous)
- **Cache Miss**: 0.03-0.05 seconds
- **Overall Average**: 0.01-0.03 seconds (with 50% hit rate)

### Concurrent Performance

- **5 Users**: 0.04-0.06 seconds average
- **10 Users**: 0.05-0.08 seconds average
- **Throughput**: 50-100 requests/second

## Troubleshooting

### Slow Queries

**Symptoms:**

- Average execution time > 2 seconds
- High slow query count
- Low health score

**Solutions:**

1. Verify database indexes exist:

   ```sql
   SHOW INDEX FROM mutaties;
   ```

2. Analyze query performance:

   ```sql
   EXPLAIN SELECT * FROM mutaties WHERE ...;
   ```

3. Check database server load
4. Review connection pool configuration
5. Consider increasing cache TTL

### Low Cache Hit Rate

**Symptoms:**

- Cache hit rate < 50%
- High database load
- Degraded performance

**Solutions:**

1. Increase cache TTL (default: 300s)
2. Review cache invalidation strategy
3. Check for unique transaction patterns
4. Monitor cache size and evictions

### High Error Rate

**Symptoms:**

- Error rate > 5%
- Failed duplicate checks
- Critical health status

**Solutions:**

1. Check database connectivity
2. Review error logs for patterns
3. Verify table schema and indexes
4. Check for database locks or deadlocks
5. Review application error handling

### Memory Issues

**Symptoms:**

- Increasing memory usage
- Cache growing unbounded
- System slowdown

**Solutions:**

1. Run cache cleanup:

   ```
   POST /api/duplicate-detection/performance/optimize
   {"cleanup_cache": true}
   ```

2. Reduce cache TTL
3. Implement cache size limits
4. Monitor memory usage trends

## Best Practices

### Development

1. Always use the optimized query methods
2. Enable caching for production
3. Monitor performance during development
4. Run load tests before deployment

### Production

1. Monitor health score regularly
2. Set up alerts for degraded status
3. Export metrics daily for analysis
4. Review recommendations weekly
5. Perform cache cleanup during low-traffic periods

### Optimization

1. Keep database indexes up to date
2. Tune cache TTL based on usage patterns
3. Monitor and adjust connection pool size
4. Review slow query logs regularly
5. Implement query result pagination if needed

## Integration Example

### Using Performance Monitoring

```python
from duplicate_performance_monitor import get_performance_monitor
from duplicate_checker import DuplicateChecker
from database import DatabaseManager

# Initialize components
db = DatabaseManager()
checker = DuplicateChecker(db)
monitor = get_performance_monitor()

# Decorate duplicate check method
@monitor.monitor_duplicate_check
def check_duplicates(ref, date, amount):
    return checker.check_for_duplicates(ref, date, amount)

# Use the monitored function
results = check_duplicates('TestRef', '2024-01-01', 100.00)

# Get performance summary
from duplicate_performance_monitor import get_performance_summary
summary = get_performance_summary()
print(f"Health Score: {summary['performance_health']['score']}")
```

### Using Query Optimizer

```python
from duplicate_query_optimizer import get_query_optimizer
from database import DatabaseManager

# Initialize optimizer
db = DatabaseManager()
optimizer = get_query_optimizer(db, cache_ttl=300)

# Execute optimized query
results, perf_info = optimizer.check_duplicates_optimized(
    reference_number='TestRef',
    transaction_date='2024-01-01',
    transaction_amount=100.00,
    use_cache=True
)

print(f"Execution time: {perf_info['execution_time']:.3f}s")
print(f"Cache hit: {perf_info['cache_hit']}")
print(f"Rows returned: {perf_info['rows_returned']}")
```

## Maintenance

### Daily Tasks

- Review health status
- Check for performance degradation
- Monitor error rates

### Weekly Tasks

- Export and analyze metrics
- Review optimization recommendations
- Check cache effectiveness
- Analyze slow query patterns

### Monthly Tasks

- Review and optimize database indexes
- Analyze long-term performance trends
- Update performance baselines
- Review and adjust thresholds

## Future Enhancements

### Planned Improvements

1. **Advanced Caching**: Implement distributed caching (Redis)
2. **Query Optimization**: Machine learning-based query optimization
3. **Predictive Monitoring**: Predict performance issues before they occur
4. **Auto-Scaling**: Automatic cache and connection pool scaling
5. **Real-time Dashboards**: Grafana/Prometheus integration

### Performance Goals

- Target: < 1 second average response time
- Target: > 90% cache hit rate
- Target: 100+ requests/second throughput
- Target: 99.9% uptime

## References

- Requirements Document: `.kiro/specs/duplicate-invoice-detection/requirements.md`
- Design Document: `.kiro/specs/duplicate-invoice-detection/design.md`
- Database Indexes: `backend/src/migrations/20251217120000_duplicate_detection_indexes.json`
- Load Tests: `backend/test/test_duplicate_load.py`

## Support

For performance issues or questions:

1. Check health status endpoint
2. Review error logs in `backend/logs/`
3. Export metrics for analysis
4. Review this documentation
5. Contact system administrator
