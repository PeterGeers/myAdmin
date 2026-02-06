# Failing Tests Summary - CI/CD Blockers

**Date**: 2026-02-06 (Updated after mock improvements)
**Total Test Suites**: 51
**Failing Test Suites**: 3
**Total Tests**: 2,136
**Failing Tests**: 16 (reduced from 17)

## Progress Update

✅ **Mock improvements applied** - Reduced failures from 17 to 16 tests

- Enhanced `useDisclosure` to use React.useState (now manages state properly)
- Improved Button/Select to handle `isLoading` → `disabled`
- Fixed 1 test in GenericFilter.test.tsx (38 passing vs 37 before)

## Current Status

### 1. GenericFilter.property.test.tsx

- **Failing**: 6 out of 13 (unchanged)
- **Passing**: 7 out of 13
- **Status**: PBT skipped by design (documented)

### 2. GenericFilter.test.tsx

- **Failing**: 8 out of 46 (improved from 9) ✅
- **Passing**: 38 out of 46 (improved from 37) ✅
- **Status**: Partially fixed, 8 tests still failing

### 3. ReferenceAnalysisReport.test.tsx

- **Failing**: 2 out of 8 (unchanged, pre-existing)
- **Passing**: 6 out of 8

## Next Steps

**Recommendation**: Continue fixing mocks (Option 1)

- We've made progress (17→16 failures)
- Mock improvements are working
- Estimated 1-2 hours to fix remaining 8 unit test failures

**Alternative**: Skip failing tests (Option 2) - 15 minutes to unblock CI/CD

## Test Execution Summary

```
Test Suites: 3 failed, 1 skipped, 47 passed, 50 of 51 total
Tests:       16 failed, 28 skipped, 2092 passed, 2136 total
```

**Success Rate**: 99.2% (2092/2108 non-skipped tests passing)
**Improvement**: 1 test fixed (5.9% reduction in failures)
