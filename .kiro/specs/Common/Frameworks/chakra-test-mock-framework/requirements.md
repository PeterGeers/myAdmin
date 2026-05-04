# Requirements Document

## Introduction

The Chakra Test Mock Framework provides a centralized, project-wide mock solution for Chakra UI v2.8.2 components in the Vitest/jsdom test environment. Currently, 30+ test files each contain their own 50–150 line `vi.mock('@chakra-ui/react', ...)` blocks to work around the `@zag-js/focus-visible` crash in jsdom. This leads to repeated boilerplate, inconsistent mock coverage, and conflicts between the mocked Chakra module and the `test-utils.tsx` render wrapper that depends on `ChakraProvider` and `extendTheme`. The framework eliminates per-file mock duplication by providing a single, automatically-applied mock via Vite's `resolve.alias` mechanism that all test files inherit — including transitive imports from components that internally depend on `@chakra-ui/react` — while preserving compatibility with the existing custom render wrapper.

## Glossary

- **Mock_Module**: A centralized TypeScript file at `frontend/src/__mocks__/chakra-ui-react.tsx` that provides mock implementations for all `@chakra-ui/react` exports, loaded via a `resolve.alias` entry in the `test` block of `vite.config.ts`
- **Icons_Mock_Module**: A centralized TypeScript file at `frontend/src/__mocks__/chakra-ui-icons.tsx` that provides mock implementations for all `@chakra-ui/icons` exports, loaded via a `resolve.alias` entry in the `test` block of `vite.config.ts`
- **Resolve_Alias**: A Vite configuration mechanism in `vite.config.ts` that remaps module import paths at build/test time; when configured inside the `test` block using `test.alias`, the alias applies only during Vitest test runs and does not affect production builds. Note: the correct Vitest configuration key is `test.alias` (not `test.resolve.alias`), which Vitest merges with the top-level `resolve.alias`
- **Test_Utils**: The custom render wrapper at `frontend/src/test-utils.tsx` that wraps components with providers for testing; with `resolve.alias` active, its `import { ChakraProvider } from '@chakra-ui/react'` resolves to the Mock_Module automatically
- **Setup_File**: The Vitest setup file at `frontend/src/setupTests.ts` that runs before each test file
- **Chakra_Component_Mock**: A lightweight React functional component that renders a standard HTML element, strips Chakra-specific style props (e.g., `bg`, `colorScheme`, `spacing`), and passes remaining valid DOM props through
- **Chakra_Hook_Mock**: A mock implementation of a Chakra UI hook (e.g., `useToast`, `useDisclosure`, `useColorMode`, `useColorModeValue`) that returns stable, predictable values suitable for testing
- **Chakra_Utility_Mock**: A mock implementation of a Chakra UI utility function (e.g., `extendTheme`, `forwardRef`, `keyframes`, `createStandaloneToast`) that returns a predictable value or passthrough suitable for testing; unlike hooks, these are plain functions and not subject to React hook rules
- **Prop_Filter**: A utility function that separates Chakra-specific style props from standard HTML/DOM props to prevent React DOM warnings in test output
- **Inline_Mock**: A per-file `vi.mock('@chakra-ui/react', ...)` block that duplicates Chakra component mocking within an individual test file
- **jsdom_Crash**: The runtime error caused by `@zag-js/focus-visible` (a Chakra UI v2 dependency) attempting to access browser APIs unavailable in the jsdom environment
- **Transitive_Import**: An import that occurs indirectly — e.g., when a component under test imports another component that internally imports `@chakra-ui/react`; `vi.mock()` and `__mocks__` directory convention do NOT intercept transitive imports, but `resolve.alias` does

## Requirements

### Requirement 1: Centralized Chakra UI Component Mock Module

**User Story:** As a frontend developer, I want a single centralized mock for all Chakra UI components, so that I do not need to write per-file mock blocks when creating new tests.

#### Acceptance Criteria

1. THE Mock_Module SHALL export mock implementations for all Chakra UI components currently used across the project, including at minimum: `Box`, `Flex`, `VStack`, `HStack`, `Stack`, `Grid`, `GridItem`, `SimpleGrid`, `Container`, `Wrap`, `WrapItem`, `Heading`, `Text`, `Button`, `IconButton`, `ButtonGroup`, `Input`, `InputGroup`, `InputLeftElement`, `InputRightElement`, `Textarea`, `Select`, `Checkbox`, `Switch`, `FormControl`, `FormLabel`, `FormHelperText`, `FormErrorMessage`, `Alert`, `AlertIcon`, `AlertTitle`, `AlertDescription`, `Modal`, `ModalOverlay`, `ModalContent`, `ModalHeader`, `ModalBody`, `ModalFooter`, `ModalCloseButton`, `Drawer`, `DrawerOverlay`, `DrawerContent`, `DrawerHeader`, `DrawerBody`, `DrawerFooter`, `DrawerCloseButton`, `AlertDialog`, `AlertDialogOverlay`, `AlertDialogContent`, `AlertDialogHeader`, `AlertDialogBody`, `AlertDialogFooter`, `Popover`, `PopoverTrigger`, `PopoverContent`, `PopoverBody`, `PopoverHeader`, `PopoverCloseButton`, `Accordion`, `AccordionItem`, `AccordionButton`, `AccordionPanel`, `AccordionIcon`, `Tabs`, `TabList`, `Tab`, `TabPanels`, `TabPanel`, `Badge`, `Tag`, `TagLabel`, `Code`, `Divider`, `Spinner`, `Progress`, `Skeleton`, `Collapse`, `CloseButton`, `List`, `ListItem`, `ListIcon`, `Icon`, `Card`, `CardBody`, `CardHeader`, `ChakraProvider`, `Tooltip`, `Link`, `Menu`, `MenuButton`, `MenuList`, `MenuItem`, `Table`, `Thead`, `Tbody`, `Tr`, `Th`, `Td`, `TableContainer`, and `Image`
2. WHEN Vitest resolves an import of `@chakra-ui/react` during a test run, THE Resolve_Alias SHALL redirect the import to the Mock_Module so that the mock is loaded automatically without requiring any `vi.mock()` call in the test file
3. WHEN a Chakra_Component_Mock receives Chakra-specific style props, THE Prop_Filter SHALL remove those props before passing the remaining props to the underlying HTML element
4. WHEN a Chakra_Component_Mock receives standard HTML attributes and event handlers, THE Chakra_Component_Mock SHALL forward those attributes to the rendered HTML element
5. WHEN a Chakra_Component_Mock receives a `data-testid` attribute, THE Chakra_Component_Mock SHALL forward the `data-testid` to the rendered HTML element
6. THE Mock_Module SHALL export mock implementations for Chakra hooks: `useToast`, `useDisclosure`, `useColorMode`, and `useColorModeValue`
7. THE Mock_Module SHALL export mock implementations for Chakra utility functions: `extendTheme`, `forwardRef`, `keyframes`, and `createStandaloneToast`
8. WHEN `useDisclosure` is called, THE Chakra_Hook_Mock SHALL return an object with `isOpen`, `onOpen`, `onClose`, and `onToggle` properties where `onOpen`, `onClose`, and `onToggle` are callable mock functions that update `isOpen` state
9. WHEN `useToast` is called, THE Chakra_Hook_Mock SHALL return a callable mock function
10. WHEN `extendTheme` is called, THE Chakra_Utility_Mock SHALL return the theme configuration object passed to it
11. WHEN `forwardRef` is called, THE Chakra_Utility_Mock SHALL behave as a passthrough that returns the render function as a React component, preserving ref forwarding semantics
12. WHEN `createStandaloneToast` is called, THE Chakra_Utility_Mock SHALL return an object with a `toast` property that is a callable mock function, enabling toast usage outside React component context

### Requirement 2: Centralized Chakra UI Icons Mock Module

**User Story:** As a frontend developer, I want a single centralized mock for all Chakra UI icon components, so that icon imports do not require per-file mocking.

#### Acceptance Criteria

1. THE Icons_Mock_Module SHALL export mock implementations for all Chakra UI icons currently used across the project, including at minimum: `CheckIcon`, `CloseIcon`, `WarningIcon`, `InfoIcon`, `CheckCircleIcon`, `SearchIcon`, `ChevronDownIcon`, `ChevronUpIcon`, `ViewIcon`, `ViewOffIcon`, `ArrowUpIcon`, `ArrowDownIcon`, `AddIcon`, `DeleteIcon`, `EditIcon`, `ExternalLinkIcon`, `DownloadIcon`, and `HamburgerIcon`
2. WHEN Vitest resolves an import of `@chakra-ui/icons` during a test run, THE Resolve_Alias SHALL redirect the import to the Icons_Mock_Module so that the mock is loaded automatically without requiring any `vi.mock()` call in the test file
3. WHEN an icon mock component is rendered, THE Icons_Mock_Module SHALL render a `<span>` element containing a recognizable text symbol for the icon

### Requirement 3: jsdom Crash Prevention via Resolve Alias

**User Story:** As a frontend developer, I want the jsdom crash caused by `@zag-js/focus-visible` to be prevented automatically, so that I do not need to understand or work around this Chakra UI v2 limitation.

#### Acceptance Criteria

1. WHEN a test file imports any component from `@chakra-ui/react`, THE Resolve_Alias SHALL redirect the import to the Mock_Module so that the real `@chakra-ui/react` package and its dependency `@zag-js/focus-visible` are never loaded in the jsdom environment
2. WHEN a component under test contains a Transitive_Import of `@chakra-ui/react`, THE Resolve_Alias SHALL redirect that transitive import to the Mock_Module, preventing the `@zag-js/focus-visible` crash without requiring any mock setup in the test file
3. WHEN the Mock_Module is loaded via Resolve_Alias, THE Mock_Module SHALL contain zero imports from `@chakra-ui/react`, `@zag-js/focus-visible`, or any other Chakra UI internal package

### Requirement 4: Test Utils Compatibility

**User Story:** As a frontend developer, I want the centralized mock to work alongside the existing `test-utils.tsx` custom render wrapper, so that I can use the project's standard test render function without modification.

#### Acceptance Criteria

1. WHEN a test file imports `render` from `@/test-utils`, THE Test_Utils SHALL function correctly because the Resolve_Alias redirects its `import { ChakraProvider } from '@chakra-ui/react'` to the Mock_Module automatically
2. WHEN the Mock_Module provides a mock `ChakraProvider`, THE mock `ChakraProvider` SHALL render its children without applying Chakra theme styles
3. WHEN the Mock_Module provides a mock `extendTheme`, THE mock `extendTheme` SHALL return a valid object so that `test-utils.tsx` and `theme.js` do not throw during theme initialization
4. WHEN a test file uses the custom render from Test_Utils, THE rendered output SHALL be queryable using React Testing Library queries
5. WHEN the Resolve_Alias is active, THE Test_Utils file SHALL require zero modifications to work with the Mock_Module

### Requirement 5: Prop Filtering Utility

**User Story:** As a frontend developer, I want Chakra-specific style props to be stripped from mock components automatically, so that React does not emit DOM attribute warnings in test output.

#### Acceptance Criteria

1. THE Prop_Filter SHALL remove Chakra layout props including at minimum: `bg`, `p`, `px`, `py`, `pt`, `pb`, `pl`, `pr`, `m`, `mx`, `my`, `mt`, `mb`, `ml`, `mr`, `w`, `h`, `minH`, `maxH`, `minW`, `maxW`, `display`, `alignItems`, `justifyContent`, `flexDirection`, `flex`, `position`, `top`, `left`, `right`, `bottom`, `zIndex`, `overflow`, `gap`, `spacing`, `flexWrap`, `flexGrow`, `flexShrink`, `gridTemplateColumns`, `gridColumn`, `gridRow`, `columns`, `minChildWidth`, `wrap`, `align`, `justify`, `templateRows`, `autoFlow`, `autoColumns`, and `autoRows`
2. THE Prop_Filter SHALL remove Chakra styling props including at minimum: `colorScheme`, `variant`, `size`, `borderRadius`, `boxShadow`, `border`, `borderColor`, `borderWidth`, `borderTop`, `borderBottom`, `textAlign`, `fontSize`, `fontWeight`, `fontFamily`, `color`, `lineHeight`, `letterSpacing`, `textTransform`, `textDecoration`, `opacity`, `cursor`, `transition`, `transform`, `bgColor`, `background`, `backgroundImage`, `minHeight`, `maxHeight`, `minWidth`, `maxWidth`, `whiteSpace`, `overflowX`, `overflowY`, `resize`, `fontStyle`, `wordBreak`, `textOverflow`, `boxSize`, `_hover`, `_focus`, `_active`, `_disabled`, `isTruncated`, and `noOfLines`
3. THE Prop_Filter SHALL remove Chakra component-specific props including at minimum: `isDisabled`, `isLoading`, `loadingText`, `isInvalid`, `isRequired`, `isReadOnly`, `isChecked`, `isOpen`, `onClose`, `leftIcon`, `rightIcon`, `templateColumns`, `colSpan`, `animateOpacity`, `allowMultiple`, `defaultIndex`, `scrollBehavior`, `leastDestructiveRef`, `isAttached`, `labelColor`, and `isNumeric`

   > **Note:** Props listed here (e.g., `isDisabled`, `isLoading`, `isChecked`) are consumed by the Chakra_Component_Mock's behavioral logic FIRST — for example, `isDisabled` is used to set the `disabled` HTML attribute on a `Button` — and THEN the Prop_Filter removes them from the final DOM output. This means Requirement 6 (behavioral fidelity) and this requirement are complementary, not contradictory: the mock reads the prop for behavior, then strips it to avoid React DOM warnings.

4. WHEN the Prop_Filter encounters a standard HTML attribute (e.g., `id`, `className`, `onClick`, `onChange`, `data-testid`, `role`, `aria-label`), THE Prop_Filter SHALL preserve that attribute in the output
5. WHEN a Chakra_Component_Mock renders with filtered props, THE test output SHALL contain zero React warnings about unknown DOM props

### Requirement 6: Behavioral Fidelity for Interactive Components

**User Story:** As a frontend developer, I want mock components for interactive Chakra elements (Modal, Select, Button, etc.) to preserve essential interactive behavior, so that I can test user interactions without the real Chakra runtime.

#### Acceptance Criteria

1. WHEN a mock `Modal` component receives `isOpen` as `true`, THE mock `Modal` SHALL render its children; WHEN `isOpen` is `false`, THE mock `Modal` SHALL render nothing
2. WHEN a mock `Button` component receives an `onClick` handler, THE mock `Button` SHALL invoke the handler when clicked
3. WHEN a mock `Button` component receives `isDisabled` or `isLoading` as `true`, THE mock `Button` SHALL render with the `disabled` HTML attribute
4. WHEN a mock `Select` component receives `value` and `onChange` props, THE mock `Select` SHALL render a native `<select>` element with those props forwarded; WHEN a mock `Select` receives `isDisabled` as `true`, THE mock `Select` SHALL render with the `disabled` HTML attribute
5. WHEN a mock `Checkbox` component receives `isChecked` and `onChange` props, THE mock `Checkbox` SHALL render a native `<input type="checkbox">` with `checked` and `onChange` forwarded
6. WHEN a mock `Collapse` component receives `in` as `true`, THE mock `Collapse` SHALL render its children; WHEN `in` is `false`, THE mock `Collapse` SHALL render nothing
7. WHEN a mock `AlertDialog` component receives `isOpen` as `true`, THE mock `AlertDialog` SHALL render its children with `role="alertdialog"`; WHEN `isOpen` is `false`, THE mock `AlertDialog` SHALL render nothing
8. WHEN a mock `Tabs` component renders, THE mock `Tabs` SHALL render its children so that `Tab` and `TabPanel` elements are accessible to React Testing Library queries
9. WHEN a mock `Drawer` component receives `isOpen` as `true`, THE mock `Drawer` SHALL render its children; WHEN `isOpen` is `false`, THE mock `Drawer` SHALL render nothing
10. WHEN a mock `Popover` component renders, THE mock `Popover` SHALL render its children (including `PopoverTrigger` and `PopoverContent`) so that they are accessible to React Testing Library queries

### Requirement 7: Vite Resolve Alias Configuration for Test-Only Mock Loading

**User Story:** As a frontend developer, I want the mock to be applied automatically via Vite's resolve.alias in the test configuration, so that all imports of `@chakra-ui/react` and `@chakra-ui/icons` — including transitive imports from components in `node_modules` or other source files — resolve to the mock modules during test runs.

#### Acceptance Criteria

1. THE `vite.config.ts` file SHALL contain a `resolve.alias` entry inside the `test` block that maps `@chakra-ui/react` to the Mock_Module file path
2. THE `vite.config.ts` file SHALL contain a `resolve.alias` entry inside the `test` block that maps `@chakra-ui/icons` to the Icons_Mock_Module file path
3. WHEN a new test file is created that imports from `@chakra-ui/react`, THE Resolve_Alias SHALL cause the Mock_Module to be used automatically without the developer adding any mock setup code
4. WHEN a component under test internally imports `@chakra-ui/react` as a Transitive_Import, THE Resolve_Alias SHALL redirect that transitive import to the Mock_Module
5. THE Resolve_Alias entries for `@chakra-ui/react` and `@chakra-ui/icons` SHALL be configured exclusively inside the `test` block of `vite.config.ts`, so that production builds and the development server are unaffected
6. IF a test file needs to override a specific mock component for a specialized test scenario, THEN THE test file SHALL be able to use `vi.mock()` with the resolved Mock_Module path (e.g., `vi.mock('@/__mocks__/chakra-ui-react', ...)`) or use `vi.hoisted()` to replace individual exports, since `vi.mock('@chakra-ui/react', ...)` would target the alias and effectively re-mock the Mock_Module itself

### Requirement 8: Production Build Isolation

**User Story:** As a frontend developer, I want the mock configuration to have zero impact on production builds and the development server, so that the real Chakra UI library is used in all non-test environments.

#### Acceptance Criteria

1. WHEN a production build is executed via `vite build`, THE build output SHALL use the real `@chakra-ui/react` and `@chakra-ui/icons` packages from `node_modules`
2. WHEN the development server is started via `vite dev`, THE application SHALL use the real `@chakra-ui/react` and `@chakra-ui/icons` packages from `node_modules`
3. THE Resolve_Alias entries for Chakra mock modules SHALL exist only inside the `test` block of `vite.config.ts` and SHALL NOT appear in the top-level `resolve.alias` configuration
4. WHEN the top-level `resolve.alias` contains the existing `@` path alias, THE test-only Chakra aliases SHALL not interfere with the `@` alias in any environment

### Requirement 9: Migration of Existing Test Files

**User Story:** As a frontend developer, I want existing test files to be migrated to use the centralized mock, so that the codebase has a single consistent approach.

#### Acceptance Criteria

1. WHEN the migration is complete, THE codebase SHALL contain zero Inline_Mock blocks for `@chakra-ui/react` in test files (except for test files that intentionally override specific mock behavior per Requirement 7 acceptance criterion 6)
2. WHEN the migration is complete, THE codebase SHALL contain zero Inline_Mock blocks for `@chakra-ui/icons` in test files (except for test files that intentionally override specific mock behavior)
3. WHEN the migration is complete, all tests that passed in the test run immediately before migration begins SHALL continue to pass with the centralized Mock_Module loaded via Resolve_Alias
4. WHEN the migration is complete, THE existing `chakraMock.tsx` file at `frontend/src/components/TenantAdmin/TemplateManagement/chakraMock.tsx` SHALL be removed since its functionality is superseded by the Mock_Module
5. WHEN the migration is complete, test files that previously imported `render` from `@testing-library/react` (to avoid the real ChakraProvider) SHALL be updated to import `render` from `@/test-utils` since the mock `ChakraProvider` is now safe to use

### Requirement 10: Developer Documentation

**User Story:** As a frontend developer, I want clear documentation on how the mock framework works, so that I can write new tests confidently and troubleshoot mock-related issues.

#### Acceptance Criteria

1. THE documentation SHALL describe the location and purpose of the Mock_Module and Icons_Mock_Module files
2. THE documentation SHALL explain that the mocks are loaded via `resolve.alias` in the `test` block of `vite.config.ts` and why this approach was chosen over `__mocks__` directory convention or `vi.mock()` (transitive import coverage)
3. THE documentation SHALL describe how to write a new test file that renders Chakra UI components without any manual mock setup
4. THE documentation SHALL describe how to override a specific mock component when a test requires custom behavior, including the correct path to use with `vi.mock()` given the alias redirection
5. THE documentation SHALL describe how to add a new Chakra component mock when a previously unmocked component is needed
6. THE documentation SHALL describe the relationship between the Mock_Module and Test_Utils, explaining that `test-utils.tsx` requires no modifications because its `@chakra-ui/react` import is automatically redirected to the Mock_Module by the Resolve_Alias

### Requirement 11: Known Limitations Documentation

**User Story:** As a frontend developer, I want the mock framework to clearly document its known limitations, so that I understand what cannot be tested with mocked components and know when to use alternative testing strategies.

#### Acceptance Criteria

1. THE documentation SHALL state that style-based assertions (e.g., `toHaveStyle`) do not work with mocked components because the Chakra_Component_Mock renders plain HTML elements without Chakra's CSS-in-JS styling
2. THE documentation SHALL state that responsive features and color mode features return fixed values (e.g., `useColorMode` returns a static `"light"` mode, `useColorModeValue` returns the light-mode value) and do not simulate responsive breakpoints or mode switching
3. THE documentation SHALL state that animations are instant — the Chakra_Component_Mock does not replicate CSS transitions, Framer Motion animations, or Chakra's transition props
4. THE documentation SHALL state that Chakra's internal state management (e.g., `Tabs` active tab tracking, `Accordion` expand/collapse state, `Menu` open/close state) is not replicated in the mocks; mock components render their children statically
5. THE documentation SHALL recommend that tests requiring real Chakra UI rendering behavior — such as visual regression tests, animation tests, responsive layout tests, or complex stateful component interactions — use Playwright end-to-end tests instead of Vitest unit tests with mocked components
