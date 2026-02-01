# Fix Lint Warnings

## Status: in-progress

## Overview

Fix remaining 428 ESLint warnings in the frontend codebase to improve code quality and follow testing best practices.

## Current State

- **Total warnings**: 428
- **Errors**: 0
- **Recently fixed**: 25 warnings (unused imports, missing alt text)

## Warning Breakdown

### 1. Conditional Expect Calls (199 warnings)

**Rule**: `jest/no-conditional-expect`
**Issue**: Using `expect()` inside conditional statements (if/else, loops)
**Files affected**: Primarily `DuplicateWarningDialog.test.tsx`, `PDFUploadForm.test.tsx`

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
**Files affected**: Multiple test files

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
**Files affected**: Multiple test files

**Example**:

```typescript
const element = container.querySelector(".class");
```

**Fix**: Use `getByRole()`, `getByTestId()`, or other Testing Library queries.

### 5. Other Warnings (34 warnings)

- Using `queryBy*` when element should exist (use `getBy*`)
- Side effects in `waitFor` callbacks
- Redundant role definitions
- Unused variables

## Tasks

### Task 1: Fix Conditional Expect Calls

**Priority**: High
**Effort**: Medium
**Files**:

- `src/components/DuplicateWarningDialog.test.tsx` (majority of issues)
- `src/components/PDFUploadForm.test.tsx`

**Approach**:

1. Identify conditional logic in tests
2. Restructure into separate test cases
3. Use test.each() for parameterized tests where appropriate

### Task 2: Fix Direct Node Access

**Priority**: High
**Effort**: High
**Files**: Multiple test files across codebase

**Approach**:

1. Add `data-testid` attributes to components where needed
2. Replace `.closest()` with proper queries
3. Use `within()` for scoped queries

### Task 3: Fix Multiple Assertions in waitFor

**Priority**: Medium
**Effort**: Low
**Files**: Multiple test files

**Approach**:

1. Move non-async assertions outside `waitFor()`
2. Split into multiple `waitFor()` calls if needed
3. Use `findBy*` queries instead of `waitFor(() => getBy*())`

### Task 4: Fix Container Methods

**Priority**: Medium
**Effort**: Medium
**Files**: Multiple test files

**Approach**:

1. Replace `container.querySelector()` with Testing Library queries
2. Add test IDs where semantic queries aren't possible
3. Use `screen` instead of destructuring `container`

### Task 5: Fix Remaining Warnings

**Priority**: Low
**Effort**: Low

**Approach**:

1. Replace `queryBy*` with `getBy*` where appropriate
2. Remove side effects from `waitFor` callbacks
3. Clean up redundant role definitions
4. Remove any remaining unused variables

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
- [ ] Fix conditional expect calls (199 warnings)
- [ ] Fix direct node access (113 warnings)
- [ ] Fix multiple assertions in waitFor (44 warnings)
- [ ] Fix container methods (38 warnings)
- [ ] Fix remaining warnings (34 warnings)

## Success Criteria

- All 428 warnings resolved
- Tests still pass
- No new warnings introduced
- Code follows Testing Library best practices
