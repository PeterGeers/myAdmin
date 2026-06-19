# Implementation Plan: Budget UI Alignment

## Overview

Refactor four budget module pages to align with the project's established UI patterns (reference: `ZZPInvoices.tsx`). This is purely a frontend effort covering dark theme, i18n, FilterableHeader, table styling, modal patterns (Formik+Yup), responsive design, and button styling. Tasks are organized as: foundation (translations), per-page refactoring, and verification.

## Tasks

- [x] 1. Foundation: Create translation files and register namespace
  - [x] 1.1 Create English translation file `frontend/src/locales/en/budget.json`
    - Include all keys defined in the design's `BudgetTranslations` interface
    - Organize under categories: `titles`, `columns`, `buttons`, `labels`, `messages`
    - _Requirements: 2.1, 2.3, 2.5, 2.6_

  - [x] 1.2 Create Dutch translation file `frontend/src/locales/nl/budget.json`
    - Mirror the exact same key structure as the English file
    - Provide Dutch translations for all values
    - _Requirements: 2.1, 2.4, 2.5, 2.6_

  - [x] 1.3 Register the `budget` namespace in `frontend/src/i18n.ts`
    - Import `budgetNl` from `./locales/nl/budget.json` and `budgetEn` from `./locales/en/budget.json`
    - Add `budget: budgetNl` to the `nl` resources and `budget: budgetEn` to the `en` resources
    - _Requirements: 2.1, 2.3, 2.4_

  - [x] 1.4 Write property tests for translation file parity
    - **Property 1: Translation key completeness (EN/NL parity)**
    - **Property 2: Translation key structure conformance**
    - **Validates: Requirements 2.3, 2.4, 2.6**

- [x] 2. Refactor BudgetVersionsPage
  - [x] 2.1 Apply all seven gap areas to `BudgetVersionsPage.tsx`
    - Add `useTypedTranslation('budget')` and replace all hardcoded strings with `t()` / `tc()` calls
    - Add `useFilterableTable` with `INITIAL_FILTERS` for name, fiscal_year, status, is_active
    - Replace all `<Th>` elements with `<FilterableHeader>` components (sortable)
    - Apply dark theme: `bg="gray.800" color="white"` on Table, `color="white"` on title
    - Change row hover to `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
    - Hide Active column on mobile: `display={{ base: 'none', md: 'table-cell' }}`
    - Wrap table in `<Box overflowX="auto">`
    - Header Flex: add `wrap="wrap"` and `gap={2}`
    - Convert create-version modal to Formik + Yup (`createVersionSchema`), add `closeOnOverlayClick={false}`
    - Modal: `bg="gray.800" color="white"` on ModalContent
    - Buttons: primary actions `colorScheme="orange"`, cancel `variant="ghost"`
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 3.1, 3.5, 3.6, 3.7, 4.1, 4.2, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.6, 7.1, 7.4_

  - [x] 2.2 Write unit tests for BudgetVersionsPage refactoring
    - Test that FilterableHeader renders for each column
    - Test that Formik modal validates required fields
    - Test that dark theme props are applied
    - _Requirements: 3.1, 5.2, 5.3_

- [x] 3. Refactor BudgetTemplatesPage
  - [x] 3.1 Apply all seven gap areas to `BudgetTemplatesPage.tsx`
    - Add `useTypedTranslation('budget')` and replace all hardcoded strings with `t()` / `tc()` calls
    - Add `useFilterableTable` with `INITIAL_FILTERS` for name, line_count, created_at
    - Replace all `<Th>` elements with `<FilterableHeader>` components (sortable)
    - Apply dark theme: `bg="gray.800" color="white"` on Table, `color="white"` on title
    - Replace all light-theme backgrounds (`gray.50`, `purple.50`, `white`, `red.50`, `green.50`) with dark equivalents (`gray.700`, `whiteAlpha.100`)
    - Replace row hover `_hover={{ bg: 'gray.50' }}` with `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
    - Hide Created column on mobile: `display={{ base: 'none', md: 'table-cell' }}`
    - Wrap table in `<Box overflowX="auto">`
    - Header Flex: add `wrap="wrap"` and `gap={2}`
    - Convert template modal to Formik + Yup (`templateSchema`), add `closeOnOverlayClick={false}`
    - Modal: `bg="gray.800" color="white"` on ModalContent
    - Replace `colorScheme="blue"` and `colorScheme="green"` on Create Template buttons with `colorScheme="orange"`
    - Modal footer: Save `colorScheme="orange"`, Cancel `variant="ghost"`, Delete `colorScheme="red" variant="outline"`
    - Apply `color="white"` on all user-facing text within the page body
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.1, 2.2, 3.2, 3.5, 3.6, 3.7, 4.1, 4.3, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.5, 6.6, 7.1, 7.2, 7.4, 7.5_

  - [x] 3.2 Write unit tests for BudgetTemplatesPage refactoring
    - Test that FilterableHeader renders for each column
    - Test that Formik modal validates required fields (name, at least 1 line)
    - Test that no light-theme backgrounds remain
    - _Requirements: 3.2, 5.2, 5.3_

- [x] 4. Refactor BudgetLinesPage
  - [x] 4.1 Apply all seven gap areas to `BudgetLinesPage.tsx`
    - Add `useTypedTranslation('budget')` and replace all hardcoded strings with `t()` / `tc()` calls
    - Add `useFilterableTable` with `INITIAL_FILTERS` for account_code, period_mode, dimension, total
    - Replace all `<Th>` elements with `<FilterableHeader>` components (sortable)
    - Apply dark theme: `bg="gray.800" color="white"` on Table, `color="white"` on title
    - Change row hover from `_hover={{ bg: 'whiteAlpha.100' }}` to `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
    - Hide Dimension column on mobile: `display={{ base: 'none', md: 'table-cell' }}`
    - Wrap table in `<Box overflowX="auto">`
    - Header Flex: add `wrap="wrap"` and `gap={2}`
    - Convert line edit modal to Formik + Yup (`lineSchema`), add `closeOnOverlayClick={false}`
    - Convert Generate Draft modal to Formik + Yup (`generateDraftSchema`), add `closeOnOverlayClick={false}`
    - Convert Copy Budget modal to Formik + Yup (`copyBudgetSchema`), add `closeOnOverlayClick={false}`
    - All modals: `bg="gray.800" color="white"` on ModalContent
    - Change Generate button from teal to `colorScheme="orange"`, Copy button from purple to `colorScheme="orange"`
    - Modal footers: Save `colorScheme="orange"`, Cancel `variant="ghost"`, Delete `colorScheme="red" variant="outline"`
    - _Requirements: 1.1, 1.5, 2.1, 2.2, 3.3, 3.5, 3.6, 3.7, 4.1, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.3, 6.6, 7.1, 7.3, 7.4, 7.5_

  - [x] 4.2 Write unit tests for BudgetLinesPage refactoring
    - Test that FilterableHeader renders for each column
    - Test that Formik modals validate required fields (lineSchema, generateDraftSchema, copyBudgetSchema)
    - Test that dark theme props are applied
    - _Requirements: 3.3, 5.2, 5.3_

- [x] 5. Refactor BudgetDashboard
  - [x] 5.1 Apply all seven gap areas to `BudgetDashboard.tsx`
    - Add `useTypedTranslation('budget')` and replace all hardcoded strings with `t()` / `tc()` calls
    - Add `useFilterableTable` with `INITIAL_FILTERS` for code, name, budget, actual, variance
    - Replace all `<Th>` elements with `<FilterableHeader>` components (sortable)
    - Apply dark theme: `bg="gray.800" color="white"` on Table, `color="white"` on title
    - Change row hover from `_hover={{ bg: 'whiteAlpha.100' }}` to `_hover={{ bg: 'gray.700', cursor: 'pointer' }}`
    - Hide Name column on mobile: `display={{ base: 'none', md: 'table-cell' }}`
    - Wrap table in `<Box overflowX="auto">`
    - Verify header Flex has `wrap="wrap"` — add `gap={2}` if missing
    - No Formik needed (dashboard has no CRUD modals)
    - Buttons: primary actions `colorScheme="orange"`, secondary `colorScheme="orange" variant="outline"`
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.4, 3.5, 3.6, 3.7, 4.1, 4.4, 4.5, 6.1, 6.4, 6.6, 7.1_

  - [x] 5.2 Write unit tests for BudgetDashboard refactoring
    - Test that FilterableHeader renders for each column
    - Test that dark theme props are applied
    - _Requirements: 3.4, 4.1_

- [x] 6. Verification checkpoint
  - [x] 6.1 Run existing frontend tests and confirm no regressions
    - Run `npx vitest --run` from the frontend directory
    - Fix any type errors or broken imports introduced by the refactoring
    - Ensure all existing tests still pass
    - _Requirements: 1.1–1.5, 2.1–2.6, 3.1–3.7, 4.1–4.5, 5.1–5.6, 6.1–6.6, 7.1–7.5_

  - [x] 6.2 Write property tests for filtering and sorting
    - **Property 3: Column filtering produces matching rows**
    - **Property 4: Column sorting produces ordered output**
    - **Validates: Requirements 3.6, 3.7**

- [x] 7. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster delivery
- Reference implementation: `frontend/src/pages/ZZPInvoices.tsx`
- Existing hooks to reuse: `useFilterableTable`, `FilterableHeader`, `useTypedTranslation`
- Packages already installed: `formik`, `yup`
- Translation files follow the pattern established in `frontend/src/locales/{en,nl}/{namespace}.json`
- The `budget` namespace must be registered in `frontend/src/i18n.ts` (same pattern as `zzp`, `banking`, etc.)
- No backend changes required — purely frontend refactoring
- Properties 3 and 4 likely already have coverage via `useFilterableTable` property tests (`usefilterabletable.property.test.ts`)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1", "3.1", "4.1", "5.1"] },
    { "id": 3, "tasks": ["2.2", "3.2", "4.2", "5.2", "6.1"] },
    { "id": 4, "tasks": ["6.2"] }
  ]
}
```
