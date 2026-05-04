# Implementation Plan: Chakra Test Mock Framework

## Overview

Migrate from 30+ per-file `vi.mock('@chakra-ui/react', ...)` blocks to a centralized mock framework loaded via Vite's `resolve.alias` in the `test` block of `vite.config.ts`. The implementation follows a 4-phase approach: create mock modules, configure resolve.alias, migrate existing test files, and clean up legacy files. All code is TypeScript/TSX targeting the existing Vitest + React Testing Library stack with `fast-check` for property-based tests.

## Tasks

- [x] 1. Create prop filter utility and mock modules
  - [x] 1.1 Create the prop filter utility at `frontend/src/__mocks__/chakra-prop-filter.ts`
    - Implement the `filterChakraProps` function with a `Set<string>` of all Chakra-specific prop names
    - Include layout props (`bg`, `p`, `px`, `py`, `pt`, `pb`, `pl`, `pr`, `m`, `mx`, `my`, `mt`, `mb`, `ml`, `mr`, `w`, `h`, `minH`, `maxH`, `minW`, `maxW`, `display`, `alignItems`, `justifyContent`, `flexDirection`, `flex`, `position`, `top`, `left`, `right`, `bottom`, `zIndex`, `overflow`, `gap`, `spacing`)
    - Include styling props (`colorScheme`, `variant`, `size`, `borderRadius`, `boxShadow`, `border`, `borderColor`, `borderWidth`, `textAlign`, `fontSize`, `fontWeight`, `color`, `_hover`, `_focus`, `_active`, `_disabled`, `isTruncated`, `noOfLines`)
    - Include component-specific props (`isDisabled`, `isLoading`, `loadingText`, `isInvalid`, `isRequired`, `isChecked`, `isOpen`, `onClose`, `leftIcon`, `rightIcon`, `templateColumns`, `colSpan`, `animateOpacity`, `allowMultiple`, `defaultIndex`, `scrollBehavior`, `leastDestructiveRef`)
    - Include shorthand/internal props (`as`, `sx`, `__css`)
    - Export as a named export for use by both mock modules
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 1.3_

  - [x] 1.2 Create the main Chakra UI mock module at `frontend/src/__mocks__/chakra-ui-react.tsx`
    - Import `filterChakraProps` from `./chakra-prop-filter`
    - Import React and `vi` from vitest
    - Implement Pattern A (simple container) mocks: `Box`, `Flex`, `VStack`, `HStack`, `Grid`, `GridItem`, `Container`, `Card`, `CardBody`, `CardHeader`, `FormControl`, `ModalBody`, `ModalFooter`, `DrawerBody`, `DrawerFooter`, `PopoverBody`, `AccordionPanel`, `TabPanels`, `TabPanel`, `AlertDescription`, `FormHelperText`, `TableContainer`
    - Implement Pattern B (semantic HTML) mocks: `Heading` (h2), `Text` (p), `Button` (button with `isDisabled`/`isLoading` → `disabled`), `Input` (input), `Textarea` (textarea), `Select` (select with `value`/`onChange` forwarding), `Checkbox` (input[type=checkbox] with `isChecked`/`onChange`), `Code` (code), `Divider` (hr), `Image` (img), `Table` (table), `Thead` (thead), `Tbody` (tbody), `Tr` (tr), `Th` (th), `Td` (td), `List` (ul), `ListItem` (li)
    - Implement Pattern C (conditional render) mocks: `Modal` (role="dialog", `isOpen`), `AlertDialog` (role="alertdialog", `isOpen`), `Drawer` (role="dialog", `isOpen`), `Collapse` (`in` prop)
    - Implement Pattern D (passthrough/no-op) mocks: `ModalOverlay`, `DrawerOverlay`, `AlertDialogOverlay`, `Tooltip`, `PopoverTrigger`, `AccordionIcon`, `AlertIcon`, `ListIcon`, `Skeleton`, `ModalCloseButton`, `DrawerCloseButton`, `PopoverCloseButton`
    - Implement remaining component mocks: `Alert`, `AlertTitle`, `ModalHeader`, `ModalContent`, `DrawerHeader`, `DrawerContent`, `AlertDialogContent`, `AlertDialogHeader`, `AlertDialogBody`, `AlertDialogFooter`, `Popover`, `PopoverContent`, `PopoverHeader`, `Accordion`, `AccordionItem`, `AccordionButton`, `Tabs`, `TabList`, `Tab`, `Badge`, `Spinner`, `Progress`, `CloseButton`, `Icon`, `Switch`, `FormLabel`, `FormErrorMessage`, `Menu`, `MenuButton`, `MenuList`, `MenuItem`
    - Implement hook mocks: `useDisclosure` (stateful with `React.useState`), `useToast` (returns `vi.fn()`), `useColorMode` (returns static light mode), `useColorModeValue` (returns light value)
    - Implement utility mocks: `extendTheme` (identity/passthrough), `forwardRef` (delegates to `React.forwardRef`), `keyframes` (returns empty string), `createStandaloneToast` (returns `{ toast: vi.fn() }`)
    - Ensure the module contains zero imports from `@chakra-ui/react`, `@zag-js/focus-visible`, or any Chakra internal package
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 3.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x] 1.3 Create the icons mock module at `frontend/src/__mocks__/chakra-ui-icons.tsx`
    - Import `filterChakraProps` from `./chakra-prop-filter`
    - Create a `createMockIcon` factory that returns a component rendering `<span data-testid={name} {...filterChakraProps(props)} />`
    - Export all required icons: `CheckIcon`, `CloseIcon`, `WarningIcon`, `InfoIcon`, `CheckCircleIcon`, `SearchIcon`, `ChevronDownIcon`, `ChevronUpIcon`, `ViewIcon`, `ViewOffIcon`, `ArrowUpIcon`, `ArrowDownIcon`, `AddIcon`, `DeleteIcon`, `EditIcon`, `ExternalLinkIcon`, `DownloadIcon`, `HamburgerIcon`
    - Set `displayName` on each icon component
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 1.4 Write property tests for prop filter and mock modules
    - Create test file at `frontend/src/__mocks__/__tests__/chakra-mock.property.test.tsx`
    - Use `@fast-check/vitest` with `{ numRuns: 100 }` per property
    - **Property 1: Prop filter correctly partitions Chakra and DOM props** — generate random props objects with keys from both the CHAKRA_PROPS set and a set of known DOM attributes; verify `filterChakraProps` output contains zero Chakra props and all DOM props with original values
      - **Validates: Requirements 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 5.4**
    - **Property 2: extendTheme is an identity function** — generate arbitrary JS objects via `fc.anything()` filtered to objects; verify `extendTheme(input)` deeply equals `input`
      - **Validates: Requirements 1.10, 4.3**
    - **Property 3: useDisclosure state reflects operation sequence** — generate sequences of `'open'`/`'close'`/`'toggle'` operations via `fc.array(fc.constantFrom('open', 'close', 'toggle'))`; verify final `isOpen` state matches expected state computed by applying operations in order
      - **Validates: Requirements 1.8**
    - **Property 4: Conditional-render components respect their visibility prop** — for each of `Modal`, `AlertDialog`, `Drawer`, `Collapse`, generate boolean visibility and string children; verify children are in DOM when visible and absent when not
      - **Validates: Requirements 6.1, 6.6, 6.7, 6.9**
    - **Property 5: Button maps disabled state from isDisabled and isLoading** — generate boolean `isDisabled` × boolean `isLoading`; verify `disabled` attribute is set iff `isDisabled || isLoading`
      - **Validates: Requirements 6.2, 6.3**
    - **Property 6: All icon mocks render as span elements with identifying data-testid** — for each icon name from the export list, render the component and verify it produces a `<span>` with `data-testid` equal to the icon name
      - **Validates: Requirements 2.3**

  - [x] 1.5 Write unit tests for mock module exports and behavior
    - Create test file at `frontend/src/__mocks__/__tests__/chakra-mock.test.tsx`
    - Test that the mock module exports all required components from Requirement 1.1 (verify each is a defined function)
    - Test that the mock module exports all required hooks: `useToast`, `useDisclosure`, `useColorMode`, `useColorModeValue` (Requirement 1.6)
    - Test that the mock module exports all required utilities: `extendTheme`, `forwardRef`, `keyframes`, `createStandaloneToast` (Requirement 1.7)
    - Test `useToast` returns a callable function (Requirement 1.9)
    - Test `forwardRef` preserves ref forwarding — render a component via `forwardRef`, attach a ref, verify ref is set (Requirement 1.11)
    - Test `createStandaloneToast` returns `{ toast: fn }` where `toast` is callable (Requirement 1.12)
    - Test icons module exports all required icons from Requirement 2.1
    - Test `Select` forwards `value` and `onChange` to native `<select>` (Requirement 6.4)
    - Test `Checkbox` forwards `isChecked`/`onChange` to native `<input type="checkbox">` (Requirement 6.5)
    - Test `Tabs` renders children queryable via RTL (Requirement 6.8)
    - Test `Popover` renders `PopoverTrigger` and `PopoverContent` children queryable via RTL (Requirement 6.10)
    - _Requirements: 1.1, 1.6, 1.7, 1.9, 1.11, 1.12, 2.1, 6.4, 6.5, 6.8, 6.10_

- [x] 2. Checkpoint — Verify mock modules in isolation
  - Ensure all property tests and unit tests from task 1 pass, ask the user if questions arise.

- [x] 3. Configure resolve.alias in vite.config.ts
  - [x] 3.1 Add test-only resolve.alias entries to `frontend/vite.config.ts`
    - Add `resolve.alias` inside the existing `test` block (not at the top level)
    - Map `'@chakra-ui/react'` to `path.resolve(__dirname, './src/__mocks__/chakra-ui-react.tsx')`
    - Map `'@chakra-ui/icons'` to `path.resolve(__dirname, './src/__mocks__/chakra-ui-icons.tsx')`
    - Verify the existing top-level `@` alias is unaffected
    - Verify the alias entries are exclusively inside the `test` block so production builds and dev server are unaffected
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 8.1, 8.2, 8.3, 8.4_

  - [x] 3.2 Write integration tests for alias configuration and test-utils compatibility
    - Create test file at `frontend/src/__mocks__/__tests__/chakra-mock.integration.test.tsx`
    - Test that `import { render } from '@/test-utils'` works correctly with the alias active — render a simple component and verify it's queryable via RTL (Requirements 4.1, 4.4)
    - Test that mock `ChakraProvider` renders children without applying styles (Requirement 4.2)
    - Test that mock `extendTheme` returns a valid object so `theme.js` doesn't throw (Requirement 4.3)
    - Test that `test-utils.tsx` requires zero modifications (Requirement 4.5)
    - Test that a component with a transitive `@chakra-ui/react` import renders without crash (Requirements 3.1, 3.2, 7.4)
    - Test that rendering mock components produces zero React DOM warnings about unknown props — spy on `console.error` (Requirement 5.5)
    - Test per-file override mechanism: use `vi.mock` with the resolved mock module path to override a specific export and verify it works (Requirement 7.6)
    - _Requirements: 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5, 5.5, 7.4, 7.6_

- [x] 4. Checkpoint — Verify alias configuration
  - Run the full test suite after adding resolve.alias. Some tests may fail due to conflicts between inline mocks and the alias. Document any failures. Ask the user if questions arise.

- [x] 5. Migrate Group A test files — chakraMock.tsx users
  - [x] 5.1 Migrate TemplateManagement test files under `frontend/src/components/TenantAdmin/TemplateManagement/__tests__/`
    - Remove `vi.mock('@chakra-ui/react', ...)` blocks from: `AIHelpButton.test.tsx`, `TemplateManagement.test.tsx`, `TemplatePreview.test.tsx`, `TemplateUpload.test.tsx`, `ValidationResults.test.tsx`, `TemplateApproval.test.tsx`
    - Remove `vi.mock('@chakra-ui/icons', ...)` blocks from the same files
    - Update `render` imports: change `@testing-library/react` to `@/test-utils` where applicable
    - Run each test file individually to verify it passes
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [x] 5.2 Migrate TemplateManagement test files under `frontend/tests/unit/TemplateManagement/`
    - Remove `vi.mock('@chakra-ui/react', ...)` blocks from: `AIHelpButton.test.tsx`, `TemplateManagement.test.tsx`, `TemplatePreview.test.tsx`, `TemplateUpload.test.tsx`, `ValidationResults.test.tsx`, `TemplateApproval.test.tsx`
    - Remove `vi.mock('@chakra-ui/icons', ...)` blocks from the same files
    - Update `render` imports: change `@testing-library/react` to `@/test-utils` where applicable
    - Run each test file individually to verify it passes
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [x] 6. Migrate Group B test files — inline Chakra mock users
  - [x] 6.1 Migrate report test files
    - Remove `vi.mock('@chakra-ui/react', ...)` and `vi.mock('@chakra-ui/icons', ...)` blocks from:
      - `frontend/src/components/reports/AangifteIbReport.test.tsx`
      - `frontend/src/components/reports/BnbReportsGroup.test.tsx`
      - `frontend/src/components/reports/FinancialReportsGroup.test.tsx`
      - `frontend/src/components/reports/MutatiesReport.test.tsx`
      - `frontend/src/components/reports/ReportsIntegration.test.tsx`
      - `frontend/src/components/reports/BtwReport.test.tsx`
      - `frontend/src/components/reports/BnbActualsReport.test.tsx`
      - `frontend/src/components/reports/__tests__/BalanceReport.test.tsx`
      - `frontend/src/components/reports/__tests__/ProfitLossReport.test.tsx`
      - `frontend/tests/unit/reports/BnbReturningGuestsReport.test.tsx`
    - Update `render` imports to `@/test-utils` where applicable
    - Run each test file individually to verify it passes
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [x] 6.2 Migrate filter and component test files
    - Remove `vi.mock('@chakra-ui/react', ...)` and `vi.mock('@chakra-ui/icons', ...)` blocks from:
      - `frontend/src/components/filters/FilterPanel.test.tsx`
      - `frontend/src/components/filters/GenericFilter.test.tsx`
      - `frontend/src/components/filters/YearFilter.test.tsx`
      - `frontend/src/components/filters/__tests__/FilterableHeader.test.tsx`
      - `frontend/src/components/filters/__tests__/FilterableHeader.property.test.tsx`
      - `frontend/src/components/LanguageSelector.test.tsx`
      - `frontend/src/components/TenantSelector.test.tsx`
      - `frontend/src/components/FINReports.test.tsx`
      - `frontend/src/components/pivot/__tests__/PivotBuilder.test.tsx`
    - Update `render` imports to `@/test-utils` where applicable
    - Run each test file individually to verify it passes
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [x] 6.3 Migrate integration and standalone test files
    - Remove `vi.mock('@chakra-ui/react', ...)` and `vi.mock('@chakra-ui/icons', ...)` blocks from:
      - `frontend/src/__tests__/authentication.integration.test.tsx`
      - `frontend/src/__tests__/ReferenceAnalysisReport.test.tsx`
      - `frontend/tests/unit/shared/EmailLogPanel.test.tsx`
      - `frontend/src/tests/template-management-integration.test.tsx`
      - `frontend/src/tests/authentication-flow.test.tsx`
    - Update `render` imports to `@/test-utils` where applicable
    - Run each test file individually to verify it passes
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [x] 7. Migrate Group C test files — partial mock users (vi.importActual)
  - [x] 7.1 Convert ParameterManagement test files to per-file override pattern
    - Migrate `frontend/src/components/TenantAdmin/__tests__/ParameterManagement.test.tsx`:
      - Replace the `vi.mock('@chakra-ui/react', async () => { const actual = await vi.importActual(...) ... })` block with the per-file override pattern: spread the centralized mock and override only `useToast` (or whichever exports need custom behavior)
      - Use `vi.mock('@chakra-ui/react', async () => { const mocks = await vi.importActual('@/__mocks__/chakra-ui-react'); return { ...mocks, useToast: () => mockToast }; })` or equivalent `vi.hoisted()` pattern
    - Migrate `frontend/src/components/TenantAdmin/__tests__/ParameterManagement.property.test.tsx` with the same approach
    - Update `render` imports to `@/test-utils` where applicable
    - Run each test file individually to verify it passes
    - _Requirements: 7.6, 9.1, 9.3_

- [x] 8. Checkpoint — Verify all migrations
  - Run the full test suite. All tests that passed before migration must continue to pass. Ask the user if questions arise.

- [ ] 9. Cleanup legacy files and update documentation
  - [ ] 9.1 Remove legacy mock files
    - Delete `frontend/src/components/TenantAdmin/TemplateManagement/chakraMock.tsx` (superseded by centralized mock module)
    - Delete `frontend/src/__mocks__/@chakra-ui/icons.tsx` (superseded by flat-path `chakra-ui-icons.tsx`)
    - Delete `frontend/src/__mocks__/@zag-js/focus-visible.ts` (no longer needed — real `@zag-js` is never loaded via alias)
    - Remove the empty `frontend/src/__mocks__/@chakra-ui/` and `frontend/src/__mocks__/@zag-js/` directories if empty
    - Run the full test suite to confirm zero regressions
    - _Requirements: 9.4_

  - [ ] 9.2 Update vitest-guide documentation
    - Update `.kiro/specs/Common/Frameworks/test-maintenance-framework/frontend/vitest-guide.md`:
      - Replace the "Approach 2: Mocked Chakra" section (or equivalent) with documentation about the automatic mock via `resolve.alias`
      - Remove references to `chakraMock.tsx`
      - Document the location and purpose of `frontend/src/__mocks__/chakra-ui-react.tsx` and `frontend/src/__mocks__/chakra-ui-icons.tsx`
      - Explain that mocks are loaded via `resolve.alias` in the `test` block and why this approach was chosen over `__mocks__` directory convention or `vi.mock()` (transitive import coverage)
      - Document how to write a new test file that renders Chakra UI components without any manual mock setup
      - Document how to override a specific mock component per-file (correct path with `vi.mock()` given alias redirection)
      - Document how to add a new Chakra component mock when a previously unmocked component is needed
      - Document the relationship between the mock module and `test-utils.tsx`
      - Document known limitations: no style assertions, fixed color mode values, instant animations, no internal state management, recommend Playwright for real Chakra rendering
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 10. Final checkpoint — Full suite verification and smoke tests
  - Run the full test suite (`vitest --run`) to confirm zero regressions
  - Verify zero inline `vi.mock('@chakra-ui/react', ...)` blocks remain in test files (except Group C per-file overrides)
  - Verify zero inline `vi.mock('@chakra-ui/icons', ...)` blocks remain in test files
  - Verify `chakraMock.tsx` no longer exists
  - Verify resolve.alias entries are exclusively inside the `test` block of `vite.config.ts`
  - Ask the user if questions arise.

## Notes

- All tasks are required
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each phase
- Property tests validate the 6 universal correctness properties from the design document using `fast-check`
- Unit tests validate specific examples and edge cases
- The design uses TypeScript — all mock modules and tests use `.tsx`/`.ts` extensions
- The migration is batched by mock pattern (Group A/B/C) to minimize risk
- `test-utils.tsx` requires zero modifications — the alias handles everything automatically
