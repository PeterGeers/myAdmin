/**
 * Property-Based Tests for Chakra Mock Framework
 *
 * Uses @fast-check/vitest to verify universal correctness properties
 * of the mock modules across many randomized inputs.
 */
import React from 'react';
import { describe, expect } from 'vitest';
import { test as fcTest } from '@fast-check/vitest';
import fc from 'fast-check';
import { render } from '@testing-library/react';
import { renderHook, act } from '@testing-library/react';
import { filterChakraProps } from '../chakra-prop-filter';
import {
  extendTheme,
  useDisclosure,
  Modal,
  AlertDialog,
  Drawer,
  Collapse,
  Button,
} from '../chakra-ui-react';
import * as IconsModule from '../chakra-ui-icons';

// ---------------------------------------------------------------------------
// Shared constants
// ---------------------------------------------------------------------------

/** Chakra props that filterChakraProps must remove */
const CHAKRA_PROP_NAMES = [
  'bg', 'p', 'px', 'py', 'pt', 'pb', 'pl', 'pr',
  'm', 'mx', 'my', 'mt', 'mb', 'ml', 'mr',
  'w', 'h', 'minH', 'maxH', 'minW', 'maxW',
  'display', 'alignItems', 'justifyContent', 'flexDirection', 'flex',
  'position', 'zIndex', 'overflow', 'gap', 'spacing',
  'colorScheme', 'variant', 'size', 'borderRadius', 'boxShadow',
  'fontSize', 'fontWeight', 'color',
  '_hover', '_focus', '_active', '_disabled',
  'isDisabled', 'isLoading', 'isChecked', 'isOpen',
  'as', 'sx', '__css',
];

/** DOM attributes that filterChakraProps must preserve */
const DOM_ATTR_NAMES = [
  'id', 'className', 'onClick', 'onChange', 'data-testid',
  'role', 'aria-label', 'aria-describedby', 'title', 'tabIndex',
  'htmlFor', 'name', 'disabled', 'checked', 'href',
];

// ---------------------------------------------------------------------------
// Property 1: Prop filter correctly partitions Chakra and DOM props
// ---------------------------------------------------------------------------
// Feature: chakra-test-mock-framework, Property 1: Prop filter correctly partitions Chakra and DOM props
describe('Property 1: Prop filter correctly partitions Chakra and DOM props', () => {
  /** Validates: Requirements 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 5.4 */
  fcTest.prop(
    [
      fc.record(
        Object.fromEntries([
          ...CHAKRA_PROP_NAMES.map((k) => [k, fc.option(fc.anything(), { nil: undefined })]),
          ...DOM_ATTR_NAMES.map((k) => [k, fc.option(fc.anything(), { nil: undefined })]),
        ]),
        { requiredKeys: [] },
      ),
    ],
    { numRuns: 100 },
  )('filterChakraProps removes all Chakra props and preserves all DOM props', (props) => {
    const result = filterChakraProps(props) as Record<string, any>;
    const propsRecord = props as Record<string, any>;

    // No Chakra props in output
    for (const key of CHAKRA_PROP_NAMES) {
      expect(result).not.toHaveProperty(key);
    }

    // All DOM props with defined values are preserved
    for (const key of DOM_ATTR_NAMES) {
      if (key in propsRecord && propsRecord[key] !== undefined) {
        expect(result[key]).toEqual(propsRecord[key]);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Property 2: extendTheme is an identity function
// ---------------------------------------------------------------------------
// Feature: chakra-test-mock-framework, Property 2: extendTheme is an identity function
describe('Property 2: extendTheme is an identity function', () => {
  /** Validates: Requirements 1.10, 4.3 */
  fcTest.prop(
    [fc.anything().filter((v) => v !== null && v !== undefined && typeof v === 'object' && !Array.isArray(v))],
    { numRuns: 100 },
  )('extendTheme(input) deeply equals input', (input) => {
    expect(extendTheme(input)).toEqual(input);
  });
});

// ---------------------------------------------------------------------------
// Property 3: useDisclosure state reflects operation sequence
// ---------------------------------------------------------------------------
// Feature: chakra-test-mock-framework, Property 3: useDisclosure state reflects operation sequence
describe('Property 3: useDisclosure state reflects operation sequence', () => {
  /** Validates: Requirements 1.8 */
  fcTest.prop(
    [fc.array(fc.constantFrom('open', 'close', 'toggle'), { minLength: 0, maxLength: 20 })],
    { numRuns: 100 },
  )('final isOpen matches expected state after operations', (ops) => {
    const { result } = renderHook(() => useDisclosure());

    // Compute expected state
    let expected = false;
    for (const op of ops) {
      if (op === 'open') expected = true;
      else if (op === 'close') expected = false;
      else expected = !expected;
    }

    // Apply operations
    for (const op of ops) {
      act(() => {
        if (op === 'open') result.current.onOpen();
        else if (op === 'close') result.current.onClose();
        else result.current.onToggle();
      });
    }

    expect(result.current.isOpen).toBe(expected);
  });
});

// ---------------------------------------------------------------------------
// Property 4: Conditional-render components respect their visibility prop
// ---------------------------------------------------------------------------
// Feature: chakra-test-mock-framework, Property 4: Conditional-render components respect their visibility prop
describe('Property 4: Conditional-render components respect their visibility prop', () => {
  /** Validates: Requirements 6.1, 6.6, 6.7, 6.9 */

  const isOpenComponents = [
    { name: 'Modal', Component: Modal },
    { name: 'AlertDialog', Component: AlertDialog },
    { name: 'Drawer', Component: Drawer },
  ];

  for (const { name, Component } of isOpenComponents) {
    fcTest.prop(
      [fc.boolean(), fc.string({ minLength: 1 })],
      { numRuns: 100 },
    )(`${name} renders children iff isOpen is true`, (visible, text) => {
      const { container } = render(
        <Component isOpen={visible} onClose={() => {}}>
          <span data-testid="child">{text}</span>
        </Component>,
      );
      if (visible) {
        expect(container.textContent).toContain(text);
      } else {
        expect(container.textContent).not.toContain(text);
      }
    });
  }

  fcTest.prop(
    [fc.boolean(), fc.string({ minLength: 1 })],
    { numRuns: 100 },
  )('Collapse renders children iff in is true', (visible, text) => {
    const { container } = render(
      <Collapse in={visible}>
        <span>{text}</span>
      </Collapse>,
    );
    if (visible) {
      expect(container.textContent).toContain(text);
    } else {
      expect(container.textContent).not.toContain(text);
    }
  });
});

// ---------------------------------------------------------------------------
// Property 5: Button maps disabled state from isDisabled and isLoading
// ---------------------------------------------------------------------------
// Feature: chakra-test-mock-framework, Property 5: Button maps disabled state from isDisabled and isLoading
describe('Property 5: Button maps disabled state from isDisabled and isLoading', () => {
  /** Validates: Requirements 6.2, 6.3 */
  fcTest.prop(
    [fc.boolean(), fc.boolean()],
    { numRuns: 100 },
  )('disabled attribute is set iff isDisabled || isLoading', (isDisabled, isLoading) => {
    const { container } = render(
      <Button isDisabled={isDisabled} isLoading={isLoading}>
        Click
      </Button>,
    );
    const btn = container.querySelector('button')!;
    const shouldBeDisabled = isDisabled || isLoading;
    expect(btn.disabled).toBe(shouldBeDisabled);
  });
});

// ---------------------------------------------------------------------------
// Property 6: All icon mocks render as span elements with identifying data-testid
// ---------------------------------------------------------------------------
// Feature: chakra-test-mock-framework, Property 6: All icon mocks render as span elements with identifying data-testid
describe('Property 6: All icon mocks render as span elements with identifying data-testid', () => {
  /** Validates: Requirements 2.3 */

  const iconEntries: Array<[string, React.FC<any>]> = [
    ['CheckIcon', IconsModule.CheckIcon],
    ['CloseIcon', IconsModule.CloseIcon],
    ['WarningIcon', IconsModule.WarningIcon],
    ['InfoIcon', IconsModule.InfoIcon],
    ['CheckCircleIcon', IconsModule.CheckCircleIcon],
    ['SearchIcon', IconsModule.SearchIcon],
    ['ChevronDownIcon', IconsModule.ChevronDownIcon],
    ['ChevronUpIcon', IconsModule.ChevronUpIcon],
    ['ViewIcon', IconsModule.ViewIcon],
    ['ViewOffIcon', IconsModule.ViewOffIcon],
    ['ArrowUpIcon', IconsModule.ArrowUpIcon],
    ['ArrowDownIcon', IconsModule.ArrowDownIcon],
    ['AddIcon', IconsModule.AddIcon],
    ['DeleteIcon', IconsModule.DeleteIcon],
    ['EditIcon', IconsModule.EditIcon],
    ['ExternalLinkIcon', IconsModule.ExternalLinkIcon],
    ['DownloadIcon', IconsModule.DownloadIcon],
    ['HamburgerIcon', IconsModule.HamburgerIcon],
    ['ArrowBackIcon', IconsModule.ArrowBackIcon],
    ['ArrowForwardIcon', IconsModule.ArrowForwardIcon],
    ['ChevronLeftIcon', IconsModule.ChevronLeftIcon],
    ['ChevronRightIcon', IconsModule.ChevronRightIcon],
    ['CopyIcon', IconsModule.CopyIcon],
    ['InfoOutlineIcon', IconsModule.InfoOutlineIcon],
    ['LockIcon', IconsModule.LockIcon],
    ['MinusIcon', IconsModule.MinusIcon],
    ['MoonIcon', IconsModule.MoonIcon],
    ['RepeatIcon', IconsModule.RepeatIcon],
    ['Search2Icon', IconsModule.Search2Icon],
    ['SettingsIcon', IconsModule.SettingsIcon],
    ['SmallAddIcon', IconsModule.SmallAddIcon],
    ['SmallCloseIcon', IconsModule.SmallCloseIcon],
    ['SpinnerIcon', IconsModule.SpinnerIcon],
    ['StarIcon', IconsModule.StarIcon],
    ['SunIcon', IconsModule.SunIcon],
    ['TimeIcon', IconsModule.TimeIcon],
    ['TriangleDownIcon', IconsModule.TriangleDownIcon],
    ['TriangleUpIcon', IconsModule.TriangleUpIcon],
    ['UnlockIcon', IconsModule.UnlockIcon],
    ['WarningTwoIcon', IconsModule.WarningTwoIcon],
  ];

  fcTest.prop(
    [fc.constantFrom(...iconEntries)],
    { numRuns: 100 },
  )('icon renders as span with correct data-testid', ([iconName, IconComponent]) => {
    expect(IconComponent).toBeDefined();

    const { container } = render(<IconComponent />);
    const span = container.querySelector('span');
    expect(span).not.toBeNull();
    expect(span!.getAttribute('data-testid')).toBe(iconName);
  });
});
