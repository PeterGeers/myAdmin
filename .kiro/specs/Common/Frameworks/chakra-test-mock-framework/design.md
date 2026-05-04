# Design Document: Chakra Test Mock Framework

## Overview

This design describes a centralized, project-wide mock framework for Chakra UI v2.8.2 in the Vitest/jsdom test environment. The framework replaces 30+ per-file `vi.mock('@chakra-ui/react', ...)` blocks with a single pair of mock modules loaded automatically via Vite's `resolve.alias` mechanism in the `test` block of `vite.config.ts`.

### Problem

1. **jsdom crash**: Chakra UI v2's dependency `@zag-js/focus-visible` monkey-patches `HTMLElement.prototype.focus`, which is getter-only in jsdom 29+. This crashes every test that loads real Chakra.
2. **Boilerplate duplication**: Each test file that renders Chakra components contains 50–150 lines of inline mock definitions, duplicated across 30+ files with inconsistent coverage.
3. **Transitive import gap**: `vi.mock()` only intercepts direct imports in the file where it's declared. When component A imports component B which imports `@chakra-ui/react`, the `vi.mock()` in A's test file does NOT intercept B's import. This forces developers to understand and work around this limitation.
4. **test-utils.tsx conflict**: The custom render wrapper imports `ChakraProvider` and `extendTheme` from `@chakra-ui/react`. With per-file mocking, test files that mock Chakra must import `render` from `@testing-library/react` directly, bypassing the project's standard test utilities.

### Solution

Use Vite's `resolve.alias` inside the `test` block of `vite.config.ts` to redirect all imports of `@chakra-ui/react` and `@chakra-ui/icons` to centralized mock modules. This approach:

- Intercepts **all** imports (direct and transitive) at the bundler level
- Applies **only** during test runs (production/dev builds are unaffected)
- Makes `test-utils.tsx` work without modification (its `ChakraProvider` import resolves to the mock)
- Requires **zero** mock setup in new test files

### Design Decisions

| Decision                    | Choice                                                                                        | Rationale                                                                                                                                                                                                                                                     |
| --------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mock loading mechanism      | `test.alias` in `test` block                                                                  | Only mechanism that intercepts transitive imports; `vi.mock()` and `__mocks__/` directory convention do not. Note: the correct Vitest key is `test.alias`, not `test.resolve.alias` — the latter does not intercept transitive imports from source components |
| Mock file location          | `frontend/src/__mocks__/chakra-ui-react.tsx` and `frontend/src/__mocks__/chakra-ui-icons.tsx` | Flat file names (not scoped `@chakra-ui/react.tsx`) because `resolve.alias` points to a specific file path, not a directory convention                                                                                                                        |
| Prop filtering approach     | Shared `filterChakraProps` utility function                                                   | Avoids repeating destructuring patterns in every mock component; single source of truth for which props to strip                                                                                                                                              |
| Hook mocking strategy       | Stateful `useDisclosure`, stub `useToast`/`useColorMode`/`useColorModeValue`                  | `useDisclosure` needs real state for open/close testing; others need only stable return values                                                                                                                                                                |
| Per-file override mechanism | `vi.mock('@/__mocks__/chakra-ui-react', ...)` or `vi.hoisted()`                               | Since `@chakra-ui/react` resolves to the mock module, `vi.mock('@chakra-ui/react', ...)` re-mocks the mock itself — which works but is semantically confusing. Using the resolved path is clearer.                                                            |

## Architecture

### File Layout

```
frontend/
├── src/
│   ├── __mocks__/
│   │   ├── chakra-ui-react.tsx          # Main Chakra UI mock module (NEW)
│   │   ├── chakra-ui-icons.tsx          # Icons mock module (REPLACES existing @chakra-ui/icons.tsx)
│   │   ├── chakra-prop-filter.ts        # Shared prop filter utility (NEW)
│   │   └── @chakra-ui/                  # REMOVE after migration (old convention)
│   │       └── icons.tsx                # REMOVE — superseded by chakra-ui-icons.tsx
│   ├── test-utils.tsx                   # UNCHANGED — works automatically via alias
│   ├── theme.js                         # UNCHANGED — extendTheme mock returns its input
│   └── setupTests.ts                    # UNCHANGED
├── vite.config.ts                       # MODIFIED — add resolve.alias in test block
└── ...
```

### Import Resolution Flow

```mermaid
graph TD
    A[Test File] -->|import from '@chakra-ui/react'| B{Vite resolve.alias}
    B -->|test environment| C[src/__mocks__/chakra-ui-react.tsx]
    B -->|dev/prod| D[node_modules/@chakra-ui/react]

    E[Component Under Test] -->|transitive import '@chakra-ui/react'| B

    F[test-utils.tsx] -->|import ChakraProvider, extendTheme| B
    F -->|import from '@testing-library/react'| G[Real RTL]

    H[theme.js] -->|import extendTheme| B

    I[Test File] -->|import from '@chakra-ui/icons'| J{Vite resolve.alias}
    J -->|test environment| K[src/__mocks__/chakra-ui-icons.tsx]
    J -->|dev/prod| L[node_modules/@chakra-ui/icons]
```

### How test.alias Works in the Test Block

The `test.alias` configuration in `vite.config.ts` tells Vitest's Vite-based module resolver to substitute import paths **before** any module code executes. Note: the correct key is `test.alias` (not `test.resolve.alias`) — the latter was found during implementation to not intercept transitive imports from source components. This happens at the bundler level, meaning:

1. Every `import { Box } from '@chakra-ui/react'` in any file (test files, source files, even `node_modules` if they import Chakra) resolves to the mock module.
2. The real `@chakra-ui/react` package is never loaded, so `@zag-js/focus-visible` never executes.
3. `test-utils.tsx` imports `ChakraProvider` and gets the mock `ChakraProvider` — no modification needed.
4. `theme.js` imports `extendTheme` and gets the mock `extendTheme` which returns its input — no crash.

## Components and Interfaces

### 1. Prop Filter Utility (`chakra-prop-filter.ts`)

The prop filter is a pure function that separates Chakra-specific style/behavior props from standard HTML/DOM attributes.

```typescript
// frontend/src/__mocks__/chakra-prop-filter.ts

/**
 * Set of all Chakra UI style and component-specific props that should be
 * stripped before passing to a DOM element. Using a Set for O(1) lookup.
 */
const CHAKRA_PROPS = new Set([
  // Layout props
  "bg",
  "p",
  "px",
  "py",
  "pt",
  "pb",
  "pl",
  "pr",
  "m",
  "mx",
  "my",
  "mt",
  "mb",
  "ml",
  "mr",
  "w",
  "h",
  "minH",
  "maxH",
  "minW",
  "maxW",
  "display",
  "alignItems",
  "justifyContent",
  "flexDirection",
  "flex",
  "position",
  "top",
  "left",
  "right",
  "bottom",
  "zIndex",
  "overflow",
  "gap",
  "spacing",
  "flexWrap",
  "flexGrow",
  "flexShrink",
  "gridTemplateColumns",
  "gridColumn",
  "gridRow",

  // Styling props
  "colorScheme",
  "variant",
  "size",
  "borderRadius",
  "boxShadow",
  "border",
  "borderColor",
  "borderWidth",
  "borderTop",
  "borderBottom",
  "textAlign",
  "fontSize",
  "fontWeight",
  "fontFamily",
  "color",
  "lineHeight",
  "letterSpacing",
  "textTransform",
  "textDecoration",
  "opacity",
  "cursor",
  "transition",
  "transform",
  "bgColor",
  "background",
  "backgroundImage",

  // Pseudo-style props (Chakra's style props for pseudo-selectors)
  "_hover",
  "_focus",
  "_active",
  "_disabled",
  "_selected",
  "_checked",
  "_expanded",
  "_grabbed",
  "_pressed",
  "_invalid",
  "_loading",
  "_placeholder",

  // Component-specific props
  "isDisabled",
  "isLoading",
  "loadingText",
  "isInvalid",
  "isRequired",
  "isReadOnly",
  "isChecked",
  "isOpen",
  "onClose",
  "onOpen",
  "onToggle",
  "leftIcon",
  "rightIcon",
  "templateColumns",
  "colSpan",
  "rowSpan",
  "animateOpacity",
  "allowMultiple",
  "defaultIndex",
  "scrollBehavior",
  "leastDestructiveRef",
  "isTruncated",
  "noOfLines",
  "isIndeterminate",
  "hasStripe",
  "isAnimated",
  "placement",
  "gutter",
  "arrowSize",
  "arrowShadowColor",
  "motionPreset",
  "preserveScrollBarGap",
  "blockScrollOnMount",
  "closeOnOverlayClick",
  "closeOnEsc",
  "returnFocusOnClose",
  "autoFocus",
  "trapFocus",
  "initialFocusRef",
  "finalFocusRef",
  "isLazy",
  "lazyBehavior",
  "colorMode",
  "useSystemColorMode",
  "cssVarsRoot",
  "direction",
  "environment",
  "disableGlobalStyle",
  "isAttached",
  "labelColor",
  "isNumeric",

  // Shorthand props that conflict with DOM
  "as",
  "sx",
  "__css",
  "boxSize",

  // Additional style props that may leak through
  "minHeight",
  "maxHeight",
  "minWidth",
  "maxWidth",
  "whiteSpace",
  "overflowX",
  "overflowY",
  "resize",
  "fontStyle",
  "wordBreak",
  "textOverflow",

  // Additional layout/grid props
  "columns",
  "minChildWidth",
  "wrap",
  "align",
  "justify",
  "templateRows",
  "autoFlow",
  "autoColumns",
  "autoRows",
]);

/**
 * Filters out Chakra-specific props, returning only valid DOM attributes.
 *
 * @param props - The full props object from a Chakra component mock
 * @returns An object containing only standard HTML/DOM attributes
 */
export function filterChakraProps(
  props: Record<string, any>,
): Record<string, any> {
  const domProps: Record<string, any> = {};
  for (const key in props) {
    if (!CHAKRA_PROPS.has(key)) {
      domProps[key] = props[key];
    }
  }
  return domProps;
}
```

**Interface contract:**

- Input: any props object (from JSX spread)
- Output: a new object with only DOM-safe attributes
- Preserves: `id`, `className`, `style`, `onClick`, `onChange`, `data-*`, `aria-*`, `role`, `ref`, `key`, `children`
- Removes: everything in the `CHAKRA_PROPS` set

### 2. Main Chakra UI Mock Module (`chakra-ui-react.tsx`)

The mock module exports named exports matching `@chakra-ui/react`'s public API. Components are organized by category.

#### Component Mock Patterns

**Pattern A: Simple container** — renders a single HTML element, filters props, passes children.

```typescript
export const Box = ({ children, ...props }: any) => (
  <div {...filterChakraProps(props)}>{children}</div>
);
```

Used for: `Box`, `Flex`, `VStack`, `HStack`, `Stack`, `Grid`, `GridItem`, `SimpleGrid`, `Container`, `Wrap`, `WrapItem`, `Card`, `CardBody`, `CardHeader`, `FormControl`, `ModalBody`, `ModalFooter`, `DrawerBody`, `DrawerFooter`, `PopoverBody`, `AccordionPanel`, `TabPanels`, `TabPanel`, `AlertDescription`, `FormHelperText`, `TableContainer`, `ButtonGroup`, `Tag`, `TagLabel`, `Link`, `InputGroup`, `InputLeftElement`, `InputRightElement`

> **Note on `Box`**: The `Box` mock supports the `as` prop for polymorphic rendering — when `as` is provided, it renders as that HTML element instead of `<div>`.

**Pattern B: Semantic HTML element** — renders a specific HTML tag.

```typescript
export const Heading = ({ children, ...props }: any) => (
  <h2 {...filterChakraProps(props)}>{children}</h2>
);
export const Button = ({ children, onClick, isDisabled, isLoading, loadingText, ...props }: any) => (
  <button onClick={onClick} disabled={isDisabled || isLoading} {...filterChakraProps(props)}>
    {isLoading && loadingText ? loadingText : children}
  </button>
);
```

Used for: `Heading` (h2), `Text` (p/span via `as`), `Button` (button), `IconButton` (button with `aria-label`), `Input` (input, with `isDisabled` → `disabled`), `Textarea` (textarea, with `isDisabled` → `disabled`), `Select` (select, with `isDisabled` → `disabled`), `Code` (code), `Divider` (hr), `Image` (img), `Table` (table), `Thead` (thead), `Tbody` (tbody), `Tr` (tr), `Th` (th), `Td` (td), `List` (ul), `ListItem` (li), `ModalHeader` (h2), `AlertDialogHeader` (h2), `DrawerHeader` (h2)

**Pattern C: Conditional render** — renders children only when a condition prop is true.

```typescript
export const Modal = ({ children, isOpen, ...props }: any) =>
  isOpen ? <div role="dialog" {...filterChakraProps(props)}>{children}</div> : null;
```

Used for: `Modal` (role="dialog"), `AlertDialog` (role="alertdialog"), `Drawer` (role="dialog"), `Collapse` (uses `in` prop)

**Pattern D: Passthrough/no-op** — renders nothing, a minimal placeholder, or passes children through.

```typescript
export const ModalOverlay = ({ children }: any) => <div data-testid="modal-overlay">{children}</div>;
export const Tooltip = ({ children }: any) => <>{children}</>;
```

Used for: `ModalOverlay` (passes children through), `DrawerOverlay` (passes children through), `AlertDialogOverlay` (passes children through), `Tooltip`, `PopoverTrigger`, `AccordionIcon`, `AlertIcon`, `ListIcon`, `Skeleton`

> **Note on Overlay components**: `ModalOverlay`, `DrawerOverlay`, and `AlertDialogOverlay` pass through children rather than rendering empty `<div />`s. This was changed during migration because the empty-div approach broke nested content in some test scenarios.

#### Hook Mocks

```typescript
// Stateful — needs real React state for open/close testing
export const useDisclosure = (options?: { defaultIsOpen?: boolean }) => {
  const [isOpen, setIsOpen] = React.useState(options?.defaultIsOpen ?? false);
  return {
    isOpen,
    onOpen: vi.fn(() => setIsOpen(true)),
    onClose: vi.fn(() => setIsOpen(false)),
    onToggle: vi.fn(() => setIsOpen((prev) => !prev)),
  };
};

// Stub — returns a callable mock
export const useToast = () => vi.fn();

// Stub — returns fixed light mode
export const useColorMode = () => ({
  colorMode: "light" as const,
  toggleColorMode: vi.fn(),
  setColorMode: vi.fn(),
});

// Stub — always returns the light-mode value
export const useColorModeValue = (light: any, _dark: any) => light;
```

#### Utility Mocks

```typescript
// Returns input — theme.js calls extendTheme({...}) and gets the config back
export const extendTheme = (config: any) => config ?? {};

// Passthrough — preserves ref forwarding semantics
export const forwardRef = (renderFn: any) => React.forwardRef(renderFn);

// Returns a string — used in CSS-in-JS (not relevant in tests)
export const keyframes = () => "";

// Returns an object with a toast mock function
export const createStandaloneToast = () => ({ toast: vi.fn() });
```

### 3. Icons Mock Module (`chakra-ui-icons.tsx`)

Uses a factory function to create icon mocks consistently:

```typescript
const createMockIcon = (name: string) => {
  const Icon = (props: any) => <span data-testid={name} {...filterChakraProps(props)} />;
  Icon.displayName = name;
  return Icon;
};

export const CheckIcon = createMockIcon('CheckIcon');
export const CloseIcon = createMockIcon('CloseIcon');
// ... all icons listed in Requirement 2
```

The existing `frontend/src/__mocks__/@chakra-ui/icons.tsx` already follows this pattern with `<svg>` elements. The new `chakra-ui-icons.tsx` will use `<span>` elements instead (lighter, and consistent with the requirements) and will be placed at the flat path `frontend/src/__mocks__/chakra-ui-icons.tsx` for the `resolve.alias` to point to.

### 4. Vite Configuration Changes

```typescript
// vite.config.ts — inside the returned config object
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/setupTests.ts',
  css: true,
  include: ['src/**/*.{test,spec}.{ts,tsx}', 'tests/**/*.{test,spec}.{ts,tsx}'],
  exclude: ['tests/e2e/**', 'node_modules/**', 'build/**'],
  alias: {
    '@chakra-ui/react': path.resolve(__dirname, './src/__mocks__/chakra-ui-react.tsx'),
    '@chakra-ui/icons': path.resolve(__dirname, './src/__mocks__/chakra-ui-icons.tsx'),
  },
},
```

> **Important**: The correct key is `test.alias`, NOT `test.resolve.alias`. During implementation it was discovered that `test.resolve.alias` does not intercept transitive imports from source components. The `test.alias` key is merged with the top-level `resolve.alias` by Vitest, so the existing `@` → `./src/` alias continues to work in all environments.

### 5. Per-File Override Mechanism

When a test needs custom behavior for a specific mock component:

```typescript
// Option 1: Re-mock the resolved module path
vi.mock("@/__mocks__/chakra-ui-react", async () => {
  const original = await vi.importActual("@/__mocks__/chakra-ui-react");
  return {
    ...original,
    useToast: () => mockToast, // custom toast mock for this test
  };
});

// Option 2: Use vi.hoisted() to replace individual exports
const { mockToast } = vi.hoisted(() => ({
  mockToast: vi.fn(),
}));

vi.mock("@chakra-ui/react", async () => {
  const mocks = await vi.importActual("@/__mocks__/chakra-ui-react");
  return { ...mocks, useToast: () => mockToast };
});
```

Both approaches work because `@chakra-ui/react` resolves to the mock module via the alias. Option 2 is more intuitive for developers already familiar with `vi.mock('@chakra-ui/react', ...)`.

## Data Models

This feature does not introduce persistent data models. The key data structures are:

### CHAKRA_PROPS Set

A `Set<string>` containing all Chakra-specific prop names to filter. This is the single source of truth for prop filtering across all mock components.

**Maintenance**: When Chakra UI adds new style props (unlikely for v2.8.2 which is locked), add them to this set. When a new component uses a prop that triggers React DOM warnings, add that prop name here.

### Mock Component Props Interface

Each mock component accepts `any` props (matching Chakra's permissive typing) and returns a `React.ReactElement | null`. The implicit interface is:

```typescript
interface MockComponentContract {
  // Input: any props object (Chakra components accept arbitrary style props)
  (props: Record<string, any>): React.ReactElement | null;
  // Output DOM element has:
  //   - Only valid HTML attributes (after filterChakraProps)
  //   - Behavioral props mapped to HTML equivalents (isDisabled → disabled)
  //   - data-testid preserved
  //   - children rendered
}
```

### useDisclosure Return Type

```typescript
interface UseDisclosureReturn {
  isOpen: boolean;
  onOpen: Mock<() => void>; // vi.fn() that sets isOpen = true
  onClose: Mock<() => void>; // vi.fn() that sets isOpen = false
  onToggle: Mock<() => void>; // vi.fn() that toggles isOpen
}
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property 1: Prop filter correctly partitions Chakra and DOM props

_For any_ props object containing an arbitrary mix of Chakra-specific prop names and standard HTML/DOM attribute names, `filterChakraProps` SHALL return an object that contains none of the Chakra-specific props and all of the DOM-valid props with their original values preserved.

**Validates: Requirements 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 5.4**

### Property 2: extendTheme is an identity function

_For any_ JavaScript object passed to `extendTheme`, the return value SHALL be deeply equal to the input object.

**Validates: Requirements 1.10, 4.3**

### Property 3: useDisclosure state reflects operation sequence

_For any_ sequence of `onOpen`, `onClose`, and `onToggle` calls on a `useDisclosure` instance, the `isOpen` state SHALL always equal the expected state computed by applying the operations in order (open → true, close → false, toggle → !current).

**Validates: Requirements 1.8**

### Property 4: Conditional-render components respect their visibility prop

_For any_ children content and _for each_ conditional-render component (`Modal`, `AlertDialog`, `Drawer`, `Collapse`), when the visibility prop (`isOpen` or `in`) is `true` the component SHALL render its children into the DOM, and when the visibility prop is `false` the component SHALL render nothing.

**Validates: Requirements 6.1, 6.6, 6.7, 6.9**

### Property 5: Button maps disabled state from isDisabled and isLoading

_For any_ combination of `isDisabled` (boolean) and `isLoading` (boolean) props, the mock `Button` SHALL render with the HTML `disabled` attribute set to `true` if and only if `isDisabled || isLoading` is `true`. Additionally, _for any_ `onClick` handler, clicking a non-disabled Button SHALL invoke the handler exactly once.

**Validates: Requirements 6.2, 6.3**

### Property 6: All icon mocks render as span elements with identifying data-testid

_For any_ icon component exported from the Icons_Mock_Module, rendering it SHALL produce a `<span>` element with a `data-testid` attribute equal to the icon's export name.

**Validates: Requirements 2.3**

## Error Handling

### Mock Module Load Errors

If the mock module files contain syntax errors or missing exports, Vitest will fail at module resolution time with a clear error pointing to the mock file path. This is preferable to the current situation where the `@zag-js/focus-visible` crash produces an opaque error.

### Missing Component Mocks

If a test renders a Chakra component that is not exported from the mock module, the import will be `undefined`. React will throw a clear error: "Element type is invalid: expected a string or a class/function but got: undefined." The fix is to add the missing component to the mock module.

**Mitigation**: The mock module exports a comprehensive list of all Chakra components currently used in the project (per Requirement 1.1). New components should be added to the mock module when they're first used.

### Prop Filter False Positives

If a custom component uses a prop name that collides with a Chakra prop name (e.g., a custom `size` prop on a non-Chakra component), the prop filter will strip it. This is unlikely in practice because:

1. The mock components only wrap Chakra components, which use Chakra prop names by design.
2. Custom props on Chakra components should use `data-*` attributes or unique names.

**Mitigation**: If a collision occurs, the specific mock component can handle the prop before calling `filterChakraProps`.

### Per-File Override Conflicts

If a test file uses `vi.mock('@chakra-ui/react', ...)` to override the mock, the entire mock module is replaced — not merged. Developers must spread the original mock and override only the specific exports they need.

**Mitigation**: Document the correct override pattern (spread original + override specific exports) in the vitest-guide.

## Testing Strategy

### Property-Based Tests (fast-check)

Property-based testing is well-suited for this feature because the core logic (prop filtering, state management, conditional rendering) involves pure functions and universal behavioral contracts.

**Library**: `fast-check` 4.x via `@fast-check/vitest`
**Iterations**: Minimum 100 per property test
**Timeout**: 30000ms per property test (to accommodate 100+ iterations)

Each property test MUST:

- Reference its design document property number in a comment tag
- Use the format: `// Feature: chakra-test-mock-framework, Property {N}: {title}`
- Run at least 100 iterations via `{ numRuns: 100 }`

**Property test file**: `frontend/src/__mocks__/__tests__/chakra-mock.property.test.tsx`

| Property                  | What varies                                | Generator strategy                                                  |
| ------------------------- | ------------------------------------------ | ------------------------------------------------------------------- |
| 1: Prop filter partitions | Prop objects with random Chakra + DOM keys | `fc.record()` with keys drawn from Chakra set and DOM attribute set |
| 2: extendTheme identity   | Arbitrary JS objects                       | `fc.anything()` filtered to objects                                 |
| 3: useDisclosure state    | Sequences of open/close/toggle operations  | `fc.array(fc.constantFrom('open', 'close', 'toggle'))`              |
| 4: Conditional render     | Boolean visibility + string children       | `fc.boolean()` × `fc.string()`                                      |
| 5: Button disabled state  | Boolean isDisabled × boolean isLoading     | `fc.boolean()` × `fc.boolean()`                                     |
| 6: Icon mock rendering    | Icon component names from export list      | `fc.constantFrom(...iconNames)`                                     |

### Unit Tests (example-based)

**Test file**: `frontend/src/__mocks__/__tests__/chakra-mock.test.tsx`

| Test                                         | What it verifies                                                      | Requirement |
| -------------------------------------------- | --------------------------------------------------------------------- | ----------- |
| Mock module exports all required components  | Every component name is a defined export                              | 1.1         |
| Mock module exports all required hooks       | useToast, useDisclosure, useColorMode, useColorModeValue are defined  | 1.6         |
| Mock module exports all required utilities   | extendTheme, forwardRef, keyframes, createStandaloneToast are defined | 1.7         |
| useToast returns callable function           | Return value is a function                                            | 1.9         |
| forwardRef preserves ref forwarding          | Ref is attached to rendered element                                   | 1.11        |
| createStandaloneToast returns toast function | Return has callable toast property                                    | 1.12        |
| Icons module exports all required icons      | Every icon name is a defined export                                   | 2.1         |
| Select forwards value and onChange           | Native select has value and onChange                                  | 6.4         |
| Checkbox forwards isChecked and onChange     | Native input[type=checkbox] has checked and onChange                  | 6.5         |
| Tabs renders children queryable              | Tab and TabPanel are queryable via RTL                                | 6.8         |
| Popover renders children queryable           | PopoverTrigger and PopoverContent are queryable                       | 6.10        |
| Per-file override works                      | vi.mock override replaces specific export                             | 7.6         |

### Integration Tests

| Test                                      | What it verifies                                            | Requirement |
| ----------------------------------------- | ----------------------------------------------------------- | ----------- |
| test-utils render works with alias        | Custom render produces queryable output                     | 4.1, 4.4    |
| Transitive imports are intercepted        | Component with internal Chakra import renders without crash | 3.2, 7.4    |
| No React DOM warnings with filtered props | console.error spy catches zero unknown-prop warnings        | 5.5         |

### Smoke Tests (post-migration)

| Check                              | Method                                                      | Requirement |
| ---------------------------------- | ----------------------------------------------------------- | ----------- |
| Zero inline @chakra-ui/react mocks | `grep -r "vi.mock('@chakra-ui/react'" --include="*.test.*"` | 9.1         |
| Zero inline @chakra-ui/icons mocks | `grep -r "vi.mock('@chakra-ui/icons'" --include="*.test.*"` | 9.2         |
| chakraMock.tsx removed             | File does not exist                                         | 9.4         |
| All tests pass                     | `npm run test:run`                                          | 9.3         |
| Alias only in test block           | Manual review of vite.config.ts                             | 7.5, 8.3    |

### Migration Strategy

The migration proceeds in phases to minimize risk:

**Phase 1: Create mock modules**

1. Create `frontend/src/__mocks__/chakra-prop-filter.ts`
2. Create `frontend/src/__mocks__/chakra-ui-react.tsx`
3. Create `frontend/src/__mocks__/chakra-ui-icons.tsx` (flat path, replacing the scoped `@chakra-ui/icons.tsx`)
4. Write property tests and unit tests for the mock modules
5. Verify all tests pass with mock modules in isolation

**Phase 2: Configure resolve.alias**

1. Add `test.alias` entries to `vite.config.ts` (note: `test.alias` not `test.resolve.alias` — the latter does not intercept transitive imports)
2. Run the full test suite — some tests may fail because they have inline mocks that conflict with the alias
3. Fix any immediate conflicts

**Phase 3: Migrate test files (batch by pattern)**

Group test files by their current mock pattern:

- **Group A** (12 files): Files using `chakraMock.tsx` import — remove `vi.mock` blocks, switch `render` import to `@/test-utils`
- **Group B** (20+ files): Files with inline Chakra mocks (including `template-upload-integration.test.tsx` discovered during checkpoint 8) — remove `vi.mock` blocks, switch `render` import to `@/test-utils`, verify tests pass
- **Group C** (2 files): Files with partial mocks (`vi.importActual`) — convert to per-file overrides using the new override pattern

For each file:

1. Remove the `vi.mock('@chakra-ui/react', ...)` block
2. Remove the `vi.mock('@chakra-ui/icons', ...)` block
3. Change `import { render, screen, ... } from '@testing-library/react'` to `import { render, screen, ... } from '@/test-utils'`
4. Run the individual test file to verify it passes
5. If a test needs custom mock behavior, use the per-file override pattern

**Phase 4: Cleanup**

1. Delete `frontend/src/components/TenantAdmin/TemplateManagement/chakraMock.tsx`
2. Delete `frontend/src/__mocks__/@chakra-ui/icons.tsx` (old scoped path)
3. Delete `frontend/src/__mocks__/@zag-js/focus-visible.ts` (no longer needed — the real `@zag-js` is never loaded)
4. Update the vitest-guide documentation
5. Run full test suite to confirm zero regressions

### Documentation Updates

The vitest-guide at `.kiro/specs/Common/Frameworks/test-maintenance-framework/frontend/vitest-guide.md` must be updated to:

1. Replace the "Approach 2: Mocked Chakra" section with documentation about the automatic mock via `resolve.alias`
2. Remove references to `chakraMock.tsx`
3. Add a section on how to override specific mocks per-file
4. Add a section on how to add new component mocks
5. Document known limitations (no style assertions, no responsive features, no animations, no internal state management)
6. Update the "Writing New Tests — Checklist" to remove the Chakra mock setup step

### Implementation Notes (Post-Migration)

The following issues were discovered and resolved during implementation:

1. **`test.alias` vs `test.resolve.alias`**: The original design specified `test.resolve.alias`, but this was found to NOT intercept transitive imports from source components. The correct Vitest configuration key is `test.alias`, which is merged with the top-level `resolve.alias` and correctly intercepts all imports including transitive ones.

2. **Overlay components need children passthrough**: `ModalOverlay`, `DrawerOverlay`, and `AlertDialogOverlay` were initially implemented as empty `<div />`s (Pattern D). This broke nested content in some test scenarios. They were updated to pass through children.

3. **Header components render as `<h2>`**: `ModalHeader`, `AlertDialogHeader`, and `DrawerHeader` were updated to render as `<h2>` elements to match real Chakra's heading semantics, which some tests relied on for accessible queries.

4. **`isDisabled` handling on form inputs**: `Select`, `Input`, and `Textarea` mocks needed explicit `isDisabled` → `disabled` mapping, similar to `Button`.

5. **Missing components discovered during migration**: `Stack`, `SimpleGrid`, `Wrap`, `WrapItem`, `ButtonGroup`, `IconButton`, `Tag`, `TagLabel`, `Link`, `InputGroup`, `InputLeftElement`, `InputRightElement` were not in the original component list but were found to be used by source components during migration.

6. **`Box` polymorphic rendering**: The `Box` mock was updated to support the `as` prop, rendering as the specified HTML element instead of always rendering as `<div>`.

7. **Additional prop filter entries**: Several props were discovered during migration that triggered React DOM warnings: `minHeight`, `maxHeight`, `minWidth`, `maxWidth`, `whiteSpace`, `overflowX`, `overflowY`, `resize`, `boxSize`, `isReadOnly`, `isAttached`, `labelColor`, `isNumeric`, and various grid/layout props.

8. **`.chakra-spinner` CSS class queries**: Three test files (`CredentialsManagement`, `TaxRateManagement`, `UserManagement`) queried `document.querySelector('.chakra-spinner')` which relies on real Chakra CSS classes. These were updated to use `screen.getByRole('status')` which works with the mock `Spinner`.

9. **`Collapse` behavioral fidelity**: The `template-upload-integration.test.tsx` file had tests that accessed a textarea inside a `Collapse` component. The old inline mock rendered `Collapse` children unconditionally, but the centralized mock correctly respects the `in` prop. Tests were updated to click the expand button before accessing collapsed content.
