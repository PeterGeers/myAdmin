/**
 * Property-based tests for FilterableHeader component
 *
 * Uses fast-check 4.4.0 with minimum 100 iterations per property.
 *
 * Feature: table-filter-framework-v2, Property 6: Accessibility Label Propagation
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md — Property 6
 * Validates: Requirements 4.8
 */

import React from 'react';
import { render } from '@testing-library/react';
import fc from 'fast-check';

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => {
  const React = require('react');

  return {
    Th: ({
      children,
      bg,
      isNumeric,
      'aria-sort': ariaSort,
      ...props
    }: any) => (
      <th
        data-bg={bg}
        data-is-numeric={isNumeric || undefined}
        aria-sort={ariaSort}
        {...props}
      >
        {children}
      </th>
    ),
    VStack: ({ children, spacing, align }: any) => (
      <div data-testid="vstack" data-spacing={spacing} data-align={align}>
        {children}
      </div>
    ),
    HStack: ({
      children,
      spacing,
      cursor,
      onClick,
      role,
      'aria-label': ariaLabel,
    }: any) => (
      <div
        data-testid="label-row"
        data-spacing={spacing}
        data-cursor={cursor}
        onClick={onClick}
        role={role}
        aria-label={ariaLabel}
      >
        {children}
      </div>
    ),
    Text: ({
      children,
      fontSize,
      color,
      fontWeight,
      textTransform,
    }: any) => (
      <span
        data-font-size={fontSize}
        data-color={color}
        data-font-weight={fontWeight}
        data-text-transform={textTransform}
      >
        {children}
      </span>
    ),
    Input: ({
      size,
      value,
      onChange,
      placeholder,
      bg,
      color,
      'aria-label': ariaLabel,
      autoComplete,
      autoCorrect,
      autoCapitalize,
      spellCheck,
      ...props
    }: any) => (
      <input
        data-size={size}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        data-bg={bg}
        data-color={color}
        aria-label={ariaLabel}
        autoComplete={autoComplete}
        data-auto-correct={autoCorrect}
        data-auto-capitalize={autoCapitalize}
        data-spell-check={spellCheck}
        {...props}
      />
    ),
  };
});

// Import component after mocks
// eslint-disable-next-line import/first
import { FilterableHeader } from '../FilterableHeader';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/**
 * Generate non-empty label strings.
 * Uses printable ASCII characters to avoid rendering issues in tests.
 */
const nonEmptyLabelArbitrary = fc
  .stringMatching(/^[a-zA-Z0-9 _-]{1,30}$/)
  .filter((s) => s.trim().length > 0);

/** Generate a sort direction or null (inactive). */
const sortDirectionArbitrary = fc.oneof(
  fc.constant('asc' as const),
  fc.constant('desc' as const),
  fc.constant(null),
);

// ---------------------------------------------------------------------------
// Property 6: Accessibility Label Propagation
// ---------------------------------------------------------------------------

describe('Property 6: Accessibility Label Propagation', () => {
  /**
   * **Validates: Requirements 4.8**
   *
   * For any non-empty label string, FilterableHeader renders `aria-label`
   * on the filter input containing the label text.
   */
  it('filter input aria-label contains the label text for any non-empty label', () => {
    fc.assert(
      fc.property(nonEmptyLabelArbitrary, (label) => {
        const { container, unmount } = render(
          <table>
            <thead>
              <tr>
                <FilterableHeader
                  label={label}
                  filterValue=""
                  onFilterChange={() => {}}
                />
              </tr>
            </thead>
          </table>,
        );

        const input = container.querySelector('input');
        expect(input).not.toBeNull();

        const ariaLabel = input!.getAttribute('aria-label');
        expect(ariaLabel).not.toBeNull();
        expect(ariaLabel).toContain(label);
        expect(ariaLabel).toBe(`Filter by ${label}`);

        unmount();
      }),
      { numRuns: 100 },
    );
  });

  /**
   * **Validates: Requirements 4.8**
   *
   * For any non-empty label string and any sort direction, when sorting is
   * enabled, FilterableHeader renders a valid `aria-sort` attribute on the
   * `<Th>` element matching the current sort direction.
   */
  it('aria-sort on <Th> matches the current sort direction for any label and direction', () => {
    fc.assert(
      fc.property(
        nonEmptyLabelArbitrary,
        sortDirectionArbitrary,
        (label, direction) => {
          const { container, unmount } = render(
            <table>
              <thead>
                <tr>
                  <FilterableHeader
                    label={label}
                    sortable
                    sortDirection={direction}
                    onSort={() => {}}
                  />
                </tr>
              </thead>
            </table>,
          );

          const th = container.querySelector('th');
          expect(th).not.toBeNull();

          const ariaSort = th!.getAttribute('aria-sort');
          expect(ariaSort).not.toBeNull();

          if (direction === 'asc') {
            expect(ariaSort).toBe('ascending');
          } else if (direction === 'desc') {
            expect(ariaSort).toBe('descending');
          } else {
            expect(ariaSort).toBe('none');
          }

          unmount();
        },
      ),
      { numRuns: 100 },
    );
  });

  /**
   * Combined property: for any non-empty label, when both filter and sort
   * are enabled, both aria-label on input and aria-sort on Th are correct.
   */
  it('both aria-label and aria-sort are correct when filter and sort are enabled together', () => {
    fc.assert(
      fc.property(
        nonEmptyLabelArbitrary,
        sortDirectionArbitrary,
        (label, direction) => {
          const { container, unmount } = render(
            <table>
              <thead>
                <tr>
                  <FilterableHeader
                    label={label}
                    filterValue=""
                    onFilterChange={() => {}}
                    sortable
                    sortDirection={direction}
                    onSort={() => {}}
                  />
                </tr>
              </thead>
            </table>,
          );

          // Check filter input aria-label
          const input = container.querySelector('input');
          expect(input).not.toBeNull();
          expect(input!.getAttribute('aria-label')).toBe(`Filter by ${label}`);

          // Check Th aria-sort
          const th = container.querySelector('th');
          expect(th).not.toBeNull();
          const expectedSort =
            direction === 'asc'
              ? 'ascending'
              : direction === 'desc'
                ? 'descending'
                : 'none';
          expect(th!.getAttribute('aria-sort')).toBe(expectedSort);

          unmount();
        },
      ),
      { numRuns: 100 },
    );
  });
});
