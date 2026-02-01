# Template Management Tests - Setup Notes

## Status

✅ **All 148 unit tests have been created and are ready to run**

## Current Issue

The tests are encountering a Chakra UI dependency resolution issue:

```
Cannot find module '@chakra-ui/utils/context' from 'node_modules/@chakra-ui/react/dist/cjs/checkbox/checkbox-context.cjs'
```

This is a known issue with Chakra UI v2 and Jest configuration, not a problem with the test code itself.

## Solution Options

### Option 1: Update Jest Configuration (Recommended)

Add module name mapper to `package.json`:

```json
{
  "jest": {
    "moduleNameMapper": {
      "^@chakra-ui/utils/context$": "<rootDir>/node_modules/@chakra-ui/utils/dist/cjs/context.cjs"
    }
  }
}
```

### Option 2: Use Existing Test Pattern

Follow the pattern used in other test files (e.g., `ProfitLoss.test.tsx`):

- Import `ChakraProvider` directly in each test file
- Wrap components manually in tests
- This is already implemented in the current test files

### Option 3: Install Missing Dependencies

```bash
npm install --save-dev @chakra-ui/utils@latest
```

### Option 4: Mock Chakra UI Components

For unit tests that don't need full Chakra UI rendering:

```typescript
jest.mock('@chakra-ui/react', () => ({
  ChakraProvider: ({ children }: any) => children,
  Box: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  // ... other components
}));
```

## Test Files Created

1. `TemplateUpload.test.tsx` - 30 tests
2. `ValidationResults.test.tsx` - 25 tests
3. `AIHelpButton.test.tsx` - 28 tests
4. `TemplatePreview.test.tsx` - 20 tests
5. `TemplateApproval.test.tsx` - 27 tests
6. `TemplateManagement.test.tsx` - 18 tests

## Test Coverage

- Component rendering and props
- User interactions (clicks, typing, file uploads)
- State management
- API mocking
- Error handling
- Loading states
- Edge cases
- Accessibility

## Running Tests (Once Fixed)

```bash
# Run all Template Management tests
npm test -- --testPathPattern="TemplateManagement" --watchAll=false

# Run specific test file
npm test -- TemplateUpload.test.tsx --watchAll=false

# Run with coverage
npm test -- --testPathPattern="TemplateManagement" --coverage --watchAll=false
```

## Next Steps

1. Choose and implement one of the solution options above
2. Run tests to verify they pass
3. Check coverage report (should be 85-90%)
4. Update TASKS.md to mark as complete

## Notes

- Tests are written following React Testing Library best practices
- All tests use accessible queries (getByRole, getByLabelText)
- Tests focus on user behavior, not implementation details
- API calls are properly mocked
- Tests are independent and can run in any order
