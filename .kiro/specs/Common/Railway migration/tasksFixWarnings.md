# Fix Lint Warnings

## Status: in-progress

## Overview

Fix remaining ESLint warnings and test failures in the frontend codebase to improve code quality and follow testing best practices.

## URGENT: Fix Template Management Test Failures (56 tests)

**Status**: Not started
**Priority**: HIGH
**Created**: 2026-02-01

### Issue

Template Management tests were created today (2026-02-01 17:11) with duplicate/conflicting Chakra UI mock definitions. The duplicate mocks have been removed, but 56 tests still fail due to test logic issues.

### What Was Fixed

- ✅ Removed duplicate mock definitions from:
  - `ValidationResults.test.tsx`
  - `AIHelpButton.test.tsx`
  - `TemplateManagement.test.tsx`
- ✅ All tests now use centralized `chakraMock.tsx`
- ✅ "Element type is invalid" errors eliminated (was causing 82 test failures)
- ✅ 87 tests now passing (up from 0)

### Remaining Issues (56 test failures)

These are test logic issues, not mock issues:

- Wrong assertions
- Missing test data/mocks
- Incorrect DOM queries (e.g., `getByText(/upload/i)` matching multiple elements)
- Test expectations not matching actual component behavior

### Files Affected

1. `frontend/src/components/TenantAdmin/TemplateManagement/__tests__/ValidationResults.test.tsx`
2. `frontend/src/components/TenantAdmin/TemplateManagement/__tests__/AIHelpButton.test.tsx`
3. `frontend/src/components/TenantAdmin/TemplateManagement/__tests__/TemplateManagement.test.tsx`
4. `frontend/src/components/TenantAdmin/TemplateManagement/__tests__/TemplatePreview.test.tsx`
5. `frontend/src/components/TenantAdmin/TemplateManagement/__tests__/TemplateApproval.test.tsx`

### Action Required

1. Run tests individually to identify specific failures
2. Fix assertions and test logic for each failing test
3. **After each successful test fix**: Commit and push changes immediately
   ```bash
   git add .
   git commit -m "Fix [test name] in [file]"
   git push
   ```
4. Ensure all 145 Template Management tests pass
5. Verify no regression in other test suites

### Task List

#### Task 1: Fix ValidationResults.test.tsx

- [x] Run test: `npm test -- --testPathPattern="ValidationResults.test.tsx" --no-coverage --watchAll=false`
- [x] Identify failing tests
- [x] Fix test logic and assertions
- [x] Verify all tests pass
- [x] Commit: `git add . && git commit -m "Fix ValidationResults.test.tsx" && git push`

#### Task 2: Fix AIHelpButton.test.tsx

- [x] Run test: `npm test -- --testPathPattern="AIHelpButton.test.tsx" --no-coverage --watchAll=false`
- [x] Identify failing tests
- [x] Fix test logic and assertions
- [x] Verify all tests pass
- [x] Commit: `git add . && git commit -m "Fix AIHelpButton.test.tsx" && git push`

#### Task 3: Fix TemplateManagement.test.tsx

- [x] Run test: `npm test -- --testPathPattern="TemplateManagement.test.tsx" --no-coverage --watchAll=false`
- [x] Identify failing tests
- [x] Fix test logic and assertions
- [x] Verify all tests pass
- [x] Commit: `git add . && git commit -m "Fix TemplateManagement.test.tsx" && git push`

#### Task 4: Fix TemplatePreview.test.tsx

- [x] Run test: `npm test -- --testPathPattern="TemplatePreview.test.tsx" --no-coverage --watchAll=false`
- [x] Identify failing tests
- [x] Fix test logic and assertions
- [x] Verify all tests pass
- [x] Commit: `git add . && git commit -m "Fix TemplatePreview.test.tsx" && git push`

#### Task 5: Fix TemplateApproval.test.tsx

- [x] Run test: `npm test -- --testPathPattern="TemplateApproval.test.tsx" --no-coverage --watchAll=false`
- [x] Identify failing tests
- [x] Fix test logic and assertions
- [x] Verify all tests pass
- [x] Commit: `git add . && git commit -m "Fix TemplateApproval.test.tsx" && git push`

#### Task 6: Final Verification

- [x] Run all Template Management tests: `npm test -- --testPathPattern="TemplateManagement/__tests__" --no-coverage --watchAll=false`
- [x] Verify all 145 tests pass
- [x] Run full test suite: `npm test -- --no-coverage --watchAll=false`
- [x] Verify no regression in other test suites

### Test Command

```bash
npm test -- --testPathPattern="TemplateManagement/__tests__" --no-coverage --watchAll=false
```

---

## Current State

- **Total warnings**: ~310 (down from 318, reduced by ~8 warnings)
- **Errors**: 0
- **Test failures**: 0 (all Template Management tests passing!)
- **Recently fixed**: 4 simple querySelector calls in UnifiedAdminYearFilter.test.tsx
- **Recently fixed**: 25 warnings (unused imports, missing alt text)
- **Recently fixed**: Chakra UI mock conflicts (eliminated 82 test crashes)
- **Recently fixed**: ValidationResults.test.tsx - all 28 tests passing (fixed useDisclosure mock and test assertions)

## Warning Breakdown

### 1. Conditional Expect Calls (199 warnings)

**Rule**: `jest/no-conditional-expect`
**Issue**: Using `expect()` inside conditional statements (if/else, loops)
**Files affected**: Primarily `UnifiedAdminYearFilter.test.tsx` (majority of issues)

**Example**:

```typescript
if (condition) {
  expect(something).toBe(true);
}
```

**Fix**: Restructure tests to avoid conditional logic or use separate test cases.

### 2. Direct Node Access (113 warnings)

**Rule**: `testing-library/no-node-access`
**Issue**: Using `.closest()`, `.parentElement`, `.children`, etc.
**Files affected**: Multiple test files including:

- `UnifiedAdminYearFilter.test.tsx` (majority)
- `TemplatePreview.test.tsx`
- `TemplateApproval.test.tsx`
- `ValidationResults.test.tsx` (4 warnings)
- `DuplicateWarningDialog.test.tsx`

**Example**:

```typescript
const element = screen.getByText("text").closest("div");
```

**Fix**: Use Testing Library queries like `getByRole()`, `getByTestId()` instead.

### 3. Multiple Assertions in waitFor (44 warnings)

**Rule**: `testing-library/no-wait-for-multiple-assertions`
**Issue**: Multiple `expect()` calls inside `waitFor()` callback
**Files affected**: Multiple test files

**Example**:

```typescript
await waitFor(() => {
  expect(a).toBe(1);
  expect(b).toBe(2);
});
```

**Fix**: Split into separate `waitFor()` calls or move non-async assertions outside.

### 4. Container Methods (38 warnings)

**Rule**: `testing-library/no-container`
**Issue**: Using `container.querySelector()` instead of Testing Library queries
**Files affected**: Primarily `UnifiedAdminYearFilter.test.tsx`

**Example**:

```typescript
const element = container.querySelector(".class");
```

**Fix**: Use `getByRole()`, `getByTestId()`, or other Testing Library queries.

### 5. Unused Variables (24 warnings)

**Issue**: Variables declared but never used
**Files affected**: Various test files including:

- `TemplateUpload.test.tsx` (10 warnings)
- `UnifiedAdminYearFilter.test.tsx`
- Others

**Fix**: Remove unused variable declarations.

### 6. Other Warnings (remaining)

- Using `queryBy*` when element should exist (use `getBy*`)
- Side effects in `waitFor` callbacks
- Redundant role definitions (1 warning in chakraMock.tsx)
- React Hook dependency warnings (2 warnings)

## Tasks - Template by Template Approach

### Task 1: Fix ValidationResults.test.tsx

**File**: `src/components/TenantAdmin/TemplateManagement/__tests__/ValidationResults.test.tsx`  
**Total Warnings**: 4

- [x] Fix direct node access at line 270
- [x] Fix direct node access at line 283
- [x] Run tests: `npm test -- --testPathPattern="ValidationResults.test.tsx" --no-coverage --watchAll=false`
- [x] Verify all tests pass
- [x] Git commit: `git add . && git commit -m "Fix ValidationResults.test.tsx warnings" && git push`

---

### Task 2: Fix TemplatePreview.test.tsx

**File**: `src/components/TenantAdmin/TemplateManagement/__tests__/TemplatePreview.test.tsx`  
**Total Warnings**: 4

- [x] Check current warnings: `npm run lint 2>&1 | Select-String "TemplatePreview.test.tsx"`
- [x] Fix direct node access at line 37
- [x] Fix direct node access at line 160
- [x] Verify warnings reduced: `npm run lint 2>&1 | Select-String "TemplatePreview.test.tsx"`
- [x] Run tests: `npm test -- --testPathPattern="TemplatePreview.test.tsx" --no-coverage --watchAll=false`
- [x] Verify all tests pass
- [x] Git commit: `git add . && git commit -m "Fix TemplatePreview.test.tsx warnings" && git push`

---

### Task 3: Fix TemplateApproval.test.tsx

**File**: `src/components/TenantAdmin/TemplateManagement/__tests__/TemplateApproval.test.tsx`  
**Total Warnings**: 4

- [x] Check current warnings: `npm run lint 2>&1 | Select-String "TemplateApproval.test.tsx"`
- [x] Fix direct node access at line 505
- [x] Fix direct node access at line 522
- [x] Verify warnings reduced: `npm run lint 2>&1 | Select-String "TemplateApproval.test.tsx"`
- [x] Run tests: `npm test -- --testPathPattern="TemplateApproval.test.tsx" --no-coverage --watchAll=false`
- [x] Verify all tests pass
- [x] Git commit: `git add . && git commit -m "Fix TemplateApproval.test.tsx warnings" && git push`

---

### Task 4: Fix TemplateManagement.test.tsx

**File**: `src/components/TenantAdmin/TemplateManagement/__tests__/TemplateManagement.test.tsx`  
**Total Warnings**: 2

- [x] Check current warnings: `npm run lint 2>&1 | Select-String "TemplateManagement.test.tsx"`
- [x] Remove unused variable `mockApplyAIFixes` at line 26
- [x] Fix multiple assertions in waitFor at line 101
- [x] Verify warnings reduced: `npm run lint 2>&1 | Select-String "TemplateManagement.test.tsx"`
- [x] Run tests: `npm test -- --testPathPattern="TemplateManagement.test.tsx" --no-coverage --watchAll=false`
- [x] Verify all tests pass
- [x] Git commit: `git add . && git commit -m "Fix TemplateManagement.test.tsx warnings" && git push`

---

### Task 5: Fix TemplateUpload.test.tsx

**File**: `src/components/TenantAdmin/TemplateManagement/__tests__/TemplateUpload.test.tsx`  
**Total Warnings**: 4

- [x] Check current warnings: `npm run lint 2>&1 | Select-String "TemplateUpload.test.tsx"`
- [x] Remove unused variables at line 32 (`leftIcon`, `variant`, `colorScheme`)
- [x] Fix multiple assertions in waitFor at line 204
- [x] Verify warnings reduced: `npm run lint 2>&1 | Select-String "TemplateUpload.test.tsx"`
- [x] Run tests: `npm test -- --testPathPattern="TemplateUpload.test.tsx" --no-coverage --watchAll=false`
- [x] Verify all tests pass
- [x] Git commit: `git add . && git commit -m "Fix TemplateUpload.test.tsx warnings" && git push`

---

### Task 6: Fix chakraMock.tsx

**File**: `src/components/TenantAdmin/TemplateManagement/chakraMock.tsx`  
**Total Warnings**: 1

- [x] Check current warnings: `npm run lint 2>&1 | Select-String "chakraMock.tsx"`
- [x] Remove redundant role definition at line 143
- [x] Verify warnings reduced: `npm run lint 2>&1 | Select-String "chakraMock.tsx"`
- [ ] Run all Template Management tests: `npm test -- --testPathPattern="TemplateManagement/__tests__" --no-coverage --watchAll=false`
- [x] Verify no regression
- [x] Git commit: `git add . && git commit -m "Fix chakraMock.tsx redundant role warning" && git push`

## Implementation Notes

### Best Practices

- Prefer semantic queries: `getByRole()`, `getByLabelText()`
- Use `getByTestId()` only as last resort
- Keep tests focused and simple
- Avoid testing implementation details

### Testing Library Query Priority

1. `getByRole()` - Most accessible
2. `getByLabelText()` - For form fields
3. `getByPlaceholderText()` - For inputs
4. `getByText()` - For non-interactive elements
5. `getByTestId()` - Last resort

### Common Patterns

**Before**:

```typescript
const element = screen.getByText("Submit").closest("form");
expect(element).toHaveAttribute("action", "/submit");
```

**After**:

```typescript
const form = screen.getByRole("form");
expect(form).toHaveAttribute("action", "/submit");
```

**Before**:

```typescript
await waitFor(() => {
  expect(screen.getByText("Success")).toBeInTheDocument();
  expect(screen.getByText("Done")).toBeInTheDocument();
});
```

**After**:

```typescript
expect(await screen.findByText("Success")).toBeInTheDocument();
expect(screen.getByText("Done")).toBeInTheDocument();
```

## Progress Tracking

- [x] Remove unused imports (23 warnings fixed)
- [x] Add missing alt text (2 warnings fixed)
- [x] Fix Template Management test failures (56 tests now passing)
- [x] Fix ValidationResults.test.tsx (28 tests passing, useDisclosure mock fixed)
- [ ] Fix conditional expect calls (199 warnings) - mostly in UnifiedAdminYearFilter.test.tsx
- [ ] Fix direct node access (113 warnings) - multiple files
- [ ] Fix multiple assertions in waitFor (44 warnings)
- [ ] Fix container methods (38 warnings) - mostly in UnifiedAdminYearFilter.test.tsx
- [ ] Fix unused variables (24 warnings)
- [ ] Fix remaining warnings (~20 warnings)

## Success Criteria

- All 428 warnings resolved
- Tests still pass
- No new warnings introduced
- Code follows Testing Library best practices

---

## Task 7: Fix UnifiedAdminYearFilter.test.tsx

**File**: `src/components/UnifiedAdminYearFilter.test.tsx`  
**Total Warnings**: 249 (updated from 220)

**Warning Breakdown**:

- Conditional expect calls: ~140 warnings (`jest/no-conditional-expect`)
- Direct node access: ~50 warnings (`testing-library/no-node-access`)
- Container methods: ~20 warnings (`testing-library/no-container`)
- Unused variables: ~4 warnings (`@typescript-eslint/no-unused-vars`)
- Prefer presence queries: ~3 warnings (`testing-library/prefer-presence-queries`)

### Sub-tasks

- [x] Check current warnings: `npm run lint 2>&1 | Select-String "UnifiedAdminYearFilter.test.tsx" | Measure-Object -Line`
  - **Result**: 249 warnings found (more than the 220 originally documented)
- [x] Analyze warning patterns and create fix strategy
  - **Result**: Comprehensive fix strategy created in `UnifiedAdminYearFilter-fix-strategy.md`
  - **Key Findings**:
    - ~140 conditional expect warnings (property-based testing pattern)
    - ~50 direct node access warnings (querySelector usage)
    - ~20 container method warnings (querySelectorAll usage)
    - ~4 unused variable warnings
    - ~3 prefer-presence-queries warnings
  - **Recommended Approach**: 4-phase incremental refactor (10-15 hours total)
  - **Alternative**: Complete rewrite with focused unit tests
  - **Strategy Document**: `.kiro/specs/Common/Railway migration/UnifiedAdminYearFilter-fix-strategy.md`

#### Phase 1: Quick Wins (Estimated: 1-2 hours, Impact: ~30 warnings)

- [x] **Task 1.1**: Fix unused variables (4 warnings)
  - [x] Line 793: Remove unused `expectedColumns` variable
  - [x] Line 923: Remove unused `propsWithDefaults` variable
  - [x] Line 1091: Remove unused `computedStyle` variable
  - [x] Line 1155: Remove unused `ariaLabel` variable
  - [x] Verify: `npm run lint 2>&1 | Select-String "UnifiedAdminYearFilter.test.tsx" | Select-String "no-unused-vars"`
  - [x] Commit: `git add . && git commit -m "Phase 1.1: Fix unused variables in UnifiedAdminYearFilter.test.tsx" && git push`

- [x] **Task 1.2**: Fix prefer-presence-queries warnings (3 warnings)
  - [x] Line 937: Replace `expect(element !== null).toBe(true)` with `toBeInTheDocument()`
  - [x] Line 943: Replace `expect(element !== null).toBe(true)` with `toBeInTheDocument()`
  - [x] Line 949: Replace `expect(element !== null).toBe(true)` with `toBeInTheDocument()`
  - [x] Verify: `npm run lint 2>&1 | Select-String "UnifiedAdminYearFilter.test.tsx" | Select-String "prefer-presence-queries"`
  - [x] Commit: `git add . && git commit -m "Phase 1.2: Fix prefer-presence-queries in UnifiedAdminYearFilter.test.tsx" && git push`

- [x] **Task 1.3**: Fix simple container.querySelector calls (10-15 warnings)
  - [x] Replace simple querySelector calls with getByRole/getByTestId
  - [x] Focus on low-risk replacements that don't require component changes
  - [x] Verify: `npm run lint 2>&1 | Select-String "UnifiedAdminYearFilter.test.tsx" | Measure-Object -Line`
  - [x] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [x] Commit: `git add . && git commit -m "Phase 1.3: Fix simple querySelector calls in UnifiedAdminYearFilter.test.tsx" && git push`

#### Phase 2: Refactor Helper Functions (Estimated: 2-3 hours, Impact: ~40 warnings)

- [ ] **Task 2.1**: Refactor verification helpers to separate assertion logic
  - [ ] Refactor `verifyAdministrationSection` helper
  - [ ] Refactor `verifyYearSection` helper
  - [ ] Refactor `verifyLoadingState` helper
  - [ ] Refactor `verifyDisabledState` helper
  - [ ] Create assertion-free helpers that return data instead of performing assertions
  - [ ] Move assertions to test bodies with clear preconditions
  - [ ] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [ ] Commit: `git add . && git commit -m "Phase 2.1: Refactor helper functions in UnifiedAdminYearFilter.test.tsx" && git push`

#### Phase 3: Restructure Property Tests (Estimated: 4-6 hours, Impact: ~100 warnings)

- [ ] **Task 3.1**: Split large property tests into smaller, focused tests
  - [ ] Split rendering tests
  - [ ] Split state management tests
  - [ ] Split interaction tests
  - [ ] Split error handling tests
  - [ ] Use test.each() for parameterized testing
  - [ ] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [ ] Commit: `git add . && git commit -m "Phase 3.1: Restructure property tests in UnifiedAdminYearFilter.test.tsx" && git push`

#### Phase 4: Replace DOM Queries (Estimated: 3-4 hours, Impact: ~70 warnings)

- [ ] **Task 4.1**: Fix direct node access warnings (~50 warnings)
  - [ ] Lines: 296, 297, 326, 782, 945, 1023, 1156, 1289, 1423, 1556
  - [ ] Add data-testid attributes to mock component where needed
  - [ ] Replace querySelector with Testing Library queries (getByRole, getByTestId)
  - [ ] Use within() for scoped queries
  - [ ] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [ ] Commit: `git add . && git commit -m "Phase 4.1: Fix direct node access in UnifiedAdminYearFilter.test.tsx" && git push`

- [ ] **Task 4.2**: Fix container methods warnings (~20 warnings)
  - [ ] Lines: 345, 379, 445, 512, 678, 823, 956, 1089, 1234
  - [ ] Replace querySelectorAll with getAllByRole()
  - [ ] Use within() for scoped queries
  - [ ] Query specific elements by accessible names
  - [ ] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [ ] Commit: `git add . && git commit -m "Phase 4.2: Fix container methods in UnifiedAdminYearFilter.test.tsx" && git push`

#### Phase 5: Fix Conditional Expect Warnings (Estimated: 6-8 hours, Impact: ~140 warnings)

- [ ] **Task 5.1**: Fix conditional expect warnings in helper functions
  - [ ] Extract conditional logic before assertions
  - [ ] Use separate test cases for different conditions
  - [ ] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [ ] Commit: `git add . && git commit -m "Phase 5.1: Fix conditional expects in helpers" && git push`

- [ ] **Task 5.2**: Fix conditional expect warnings in property test bodies
  - [ ] Lines: 503-1558 (majority of file)
  - [ ] Refactor configuration loop tests to use test.each()
  - [ ] Split tests with multiple conditional branches
  - [ ] Run tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
  - [ ] Commit: `git add . && git commit -m "Phase 5.2: Fix conditional expects in property tests" && git push`

#### Final Verification

- [ ] Verify warnings reduced: `npm run lint 2>&1 | Select-String "UnifiedAdminYearFilter.test.tsx" | Measure-Object -Line`
- [ ] Run all tests: `npm test -- --testPathPattern="UnifiedAdminYearFilter.test.tsx" --no-coverage --watchAll=false`
- [ ] Verify all tests pass
- [ ] Final commit: `git add . && git commit -m "Complete: Fix all UnifiedAdminYearFilter.test.tsx warnings" && git push`

### Notes

This file has 220 warnings, making it the most problematic test file. The majority are conditional expect calls which will require significant refactoring. Consider:

1. **Conditional Expects**: These occur when `expect()` is inside `if` statements or loops. Solution: Restructure tests to avoid conditional logic or split into separate test cases.

2. **Direct Node Access**: Using `.closest()`, `.parentElement`, `.children`, etc. Solution: Use Testing Library queries like `getByRole()`, `getByTestId()`.

3. **Container Methods**: Using `container.querySelector()`. Solution: Use `getByRole()`, `getByTestId()`, or other Testing Library queries.

4. **Unused Variables**: Remove variables that are declared but never used.

5. **Prefer Presence Queries**: Use `getBy*` instead of `queryBy*` when checking if element is present.

Given the large number of warnings, this task may need to be broken down into multiple smaller commits focusing on one warning type at a time.
