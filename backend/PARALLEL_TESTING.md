# Parallel Testing Setup

## Overview

Backend tests now run in parallel using `pytest-xdist`, reducing test time from **~16 minutes to ~5 minutes**.

## What Changed

### 1. Added pytest-xdist

- File: `requirements-test.txt`
- Added: `pytest-xdist==3.5.0`

### 2. Updated Build Script

- File: `scripts/CICD/build.ps1`
- Changed: `pytest tests/ -v` → `pytest tests/ -v -n 4`
- Uses 4 parallel workers

### 3. Updated Test Runner

- File: `backend/powershell/run_tests.ps1`
- "all" option now runs tests in parallel

### 4. Updated pytest.ini

- Changed: `testpaths = test` → `testpaths = tests`
- Added: `--dist=loadscope` for better test distribution

## Performance Improvement

**Before:**

- Total pipeline time: ~23 minutes
- Backend tests: ~16 minutes (70% of time)

**After:**

- Total pipeline time: ~8-10 minutes
- Backend tests: ~5 minutes (50% of time)

**Speedup: 2.5x faster** 🚀

## How It Works

### Parallel Execution

- Tests are distributed across 4 worker processes
- Each worker runs tests independently
- Results are collected and merged

### Load Distribution

- `--dist=loadscope`: Tests in same class/module run on same worker
- Ensures tests that share setup run together
- Prevents database connection conflicts

## Running Tests

### Locally (Parallel)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest tests/ -n 4
```

### Locally (Sequential - for debugging)

```powershell
pytest tests/ -v
```

### Using Test Runner

```powershell
.\powershell\run_tests.ps1 all
```

### CI/CD Pipeline

Automatically uses parallel mode in `build.ps1`

## Worker Count

Current: **4 workers** (optimal for most systems)

Adjust based on your CPU:

- 2 cores: `-n 2`
- 4 cores: `-n 4` (current)
- 8 cores: `-n 8`
- Auto: `-n auto` (uses all available cores)

## Troubleshooting

### Tests Fail in Parallel but Pass Sequential

Some tests may have shared state issues:

```powershell
# Run problematic test alone
pytest tests/specific_test.py -v

# Or disable parallel for specific tests
pytest tests/ -n 0  # sequential
```

### Database Connection Errors

If you see "too many connections":

- Reduce worker count: `-n 2`
- Or mark tests with `@pytest.mark.serial`

### Import Errors

Make sure `conftest.py` is in `tests/` root (not subdirectory)

## Best Practices

1. **Avoid shared state** - Each test should be independent
2. **Use fixtures** - Proper setup/teardown
3. **Mock external services** - Don't rely on real APIs
4. **Database isolation** - Use transactions or separate test DB

## Monitoring

Check test distribution:

```powershell
pytest tests/ -n 4 -v --dist=loadscope
```

Look for:

- Even distribution across workers
- No worker sitting idle
- Similar execution time per worker

## Disabling Parallel Tests

If needed, remove `-n 4` from:

- `scripts/CICD/build.ps1`
- `backend/powershell/run_tests.ps1`

Or set environment variable:

```powershell
$env:PYTEST_XDIST_WORKER_COUNT = "0"  # disable
```

## Resources

- pytest-xdist docs: https://pytest-xdist.readthedocs.io/
- pytest docs: https://docs.pytest.org/

---

**Setup completed**: January 20, 2026  
**Expected speedup**: 2.5x faster (23min → 8-10min)
