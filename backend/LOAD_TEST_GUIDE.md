# Load Testing Guide

## Overview

The duplicate detection system includes comprehensive load tests in `tests/unit/test_duplicate_load.py`.

## Test Categories

### Fast Tests (< 10 seconds)

- `test_single_user_performance` - Sequential requests from single user
- `test_concurrent_users_light_load` - 5 concurrent users, 10 requests each
- `test_concurrent_users_medium_load` - 10 concurrent users, 10 requests each
- `test_optimized_query_performance` - Cache effectiveness testing
- `test_performance_metrics_collection` - Metrics collection verification

### Slow Tests (> 10 seconds)

- `test_sustained_load` - **30 second sustained load test** (marked with `@pytest.mark.slow`)

## Running Tests

### Run All Load Tests (Including Slow)

```powershell
cd backend
pytest tests/unit/test_duplicate_load.py -v -s
```

### Run Only Fast Tests (Skip Slow)

```powershell
pytest tests/unit/test_duplicate_load.py -v -s -m "not slow"
```

### Run Only Slow Tests

```powershell
pytest tests/unit/test_duplicate_load.py -v -s -m slow
```

### Run All Tests Except Slow Tests

```powershell
pytest -v -m "not slow"
```

## Test Details

### test_sustained_load

- **Duration**: 30 seconds
- **Purpose**: Verify system maintains performance over time
- **Checks**: Memory leaks, connection pool exhaustion, cache degradation
- **Target**: 5 requests/second sustained
- **Requirements**:
  - Average response time < 2 seconds
  - Throughput ≥ 90% of target (4.5 req/s)

## Performance Requirements

All tests verify the **2-second response time requirement** (Requirement 5.5):

- Single user: avg < 2s, max < 3s, p95 < 2s
- Light load (5 users): avg < 2s
- Medium load (10 users): avg < 2.5s (slightly relaxed)
- Sustained load: avg < 2s over 30 seconds
- Cache hits: < 0.1s

## CI/CD Integration

For CI pipelines, exclude slow tests:

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: pytest -v -m "not slow"
```

Run slow tests separately (nightly or weekly):

```yaml
# .github/workflows/nightly.yml
- name: Run load tests
  run: pytest -v -m slow
```

## Interpreting Results

Each test prints detailed performance metrics:

```
Sustained Load Performance:
  Duration: 30.1s
  Total requests: 150
  Successful: 150
  Average time: 0.234s
  Max time: 1.456s
  Target throughput: 5 req/s
  Actual throughput: 4.98 req/s
```

### Key Metrics

- **Average time**: Should be well under 2 seconds
- **Max time**: Outliers indicate potential issues
- **Throughput**: Should meet or exceed target
- **Success rate**: Should be > 95% (light) or > 90% (medium)
- **Cache hit rate**: Should be > 30% for optimized queries

## Troubleshooting

### Test Takes Too Long

- Use `-m "not slow"` to skip sustained load test
- Sustained load test is **intentionally 30 seconds** - this is correct behavior

### Performance Degradation

- Check database connection pool settings
- Verify indexes exist on `mutaties` table
- Review cache configuration (TTL, size limits)
- Check for memory leaks in long-running tests

### Intermittent Failures

- Database contention (run tests serially: `pytest --dist=no`)
- Network latency (check database connection)
- Resource constraints (CPU/memory on test machine)

## Related Documentation

- `manualsSysAdm/DUPLICATE_DETECTION_PERFORMANCE.md` - Performance tuning guide
- `manualsSysAdm/DUPLICATE_DETECTION_MONITORING.md` - Production monitoring
- `backend/src/duplicate_performance_monitor.py` - Metrics collection implementation
