/**
 * FilterableHeader Unit Tests
 *
 * Test suite for the FilterableHeader component covering:
 * - Label rendering
 * - Filter input rendering and callbacks
 * - Sort indicator rendering and callbacks
 * - Accessibility attributes (aria-label, aria-sort)
 * - isNumeric right-alignment
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md §4
 * Requirements: 12.4
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock Chakra UI components to simplify testing
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

describe('FilterableHeader', () => {
  // -----------------------------------------------------------------------
  // Label rendering
  // -----------------------------------------------------------------------

  it('renders label text in <Th>', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Account Name" />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByText('Account Name')).toBeInTheDocument();
  });

  it('renders label with dark theme styling', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Status" />
          </tr>
        </thead>
      </table>,
    );

    const th = screen.getByRole('columnheader');
    expect(th).toHaveAttribute('data-bg', 'gray.700');

    const label = screen.getByText('Status');
    expect(label).toHaveAttribute('data-color', 'gray.300');
    expect(label).toHaveAttribute('data-font-weight', 'bold');
    expect(label).toHaveAttribute('data-text-transform', 'uppercase');
  });

  // -----------------------------------------------------------------------
  // Filter input rendering
  // -----------------------------------------------------------------------

  it('renders filter input when filterValue is provided', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="" onFilterChange={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('does not render filter input when filterValue is omitted', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('renders filter input with dark theme styling', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="test" onFilterChange={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('data-bg', 'gray.600');
    expect(input).toHaveAttribute('data-color', 'white');
  });

  it('renders filter input with default placeholder', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="" onFilterChange={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByPlaceholderText('Filter...')).toBeInTheDocument();
  });

  it('renders filter input with custom placeholder', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader
              label="Name"
              filterValue=""
              onFilterChange={jest.fn()}
              placeholder="Search names..."
            />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByPlaceholderText('Search names...')).toBeInTheDocument();
  });

  it('displays current filter value in input', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="john" onFilterChange={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByRole('textbox')).toHaveValue('john');
  });

  // -----------------------------------------------------------------------
  // Filter change callback
  // -----------------------------------------------------------------------

  it('calls onFilterChange on input change', () => {
    const onFilterChange = jest.fn();
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="" onFilterChange={onFilterChange} />
          </tr>
        </thead>
      </table>,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'abc' } });
    expect(onFilterChange).toHaveBeenCalledWith('abc');
  });

  // -----------------------------------------------------------------------
  // Sort indicator rendering
  // -----------------------------------------------------------------------

  it('renders ascending sort indicator when sortable and sortDirection is asc', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByText('↑')).toBeInTheDocument();
  });

  it('renders descending sort indicator when sortable and sortDirection is desc', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="desc" onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByText('↓')).toBeInTheDocument();
  });

  it('does not render sort indicator when sortable but sortDirection is null', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection={null} onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.queryByText('↑')).not.toBeInTheDocument();
    expect(screen.queryByText('↓')).not.toBeInTheDocument();
  });

  it('does not render sort indicator when not sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Notes" />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.queryByText('↑')).not.toBeInTheDocument();
    expect(screen.queryByText('↓')).not.toBeInTheDocument();
  });

  it('renders sort indicator with orange.300 color', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const indicator = screen.getByText('↑');
    expect(indicator).toHaveAttribute('data-color', 'orange.300');
  });

  // -----------------------------------------------------------------------
  // Sort click callback
  // -----------------------------------------------------------------------

  it('calls onSort callback on sort click', () => {
    const onSort = jest.fn();
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={onSort} />
          </tr>
        </thead>
      </table>,
    );

    const labelRow = screen.getByTestId('label-row');
    fireEvent.click(labelRow);
    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it('does not call onSort when not sortable', () => {
    const onSort = jest.fn();
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Notes" onSort={onSort} />
          </tr>
        </thead>
      </table>,
    );

    const labelRow = screen.getByTestId('label-row');
    fireEvent.click(labelRow);
    expect(onSort).not.toHaveBeenCalled();
  });

  it('sets cursor to pointer when sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const labelRow = screen.getByTestId('label-row');
    expect(labelRow).toHaveAttribute('data-cursor', 'pointer');
  });

  it('sets cursor to default when not sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Notes" />
          </tr>
        </thead>
      </table>,
    );

    const labelRow = screen.getByTestId('label-row');
    expect(labelRow).toHaveAttribute('data-cursor', 'default');
  });

  it('sets role=button on label row when sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByRole('button', { name: 'Sort by Amount' })).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Accessibility: aria-label on filter input
  // -----------------------------------------------------------------------

  it('sets aria-label on filter input', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Account" filterValue="" onFilterChange={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('aria-label', 'Filter by Account');
  });

  // -----------------------------------------------------------------------
  // Accessibility: aria-sort on <Th>
  // -----------------------------------------------------------------------

  it('sets aria-sort="ascending" on <Th> when sortable and direction is asc', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const th = screen.getByRole('columnheader');
    expect(th).toHaveAttribute('aria-sort', 'ascending');
  });

  it('sets aria-sort="descending" on <Th> when sortable and direction is desc', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="desc" onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const th = screen.getByRole('columnheader');
    expect(th).toHaveAttribute('aria-sort', 'descending');
  });

  it('sets aria-sort="none" on <Th> when sortable but no active direction', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection={null} onSort={jest.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const th = screen.getByRole('columnheader');
    expect(th).toHaveAttribute('aria-sort', 'none');
  });

  it('does not set aria-sort on <Th> when not sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Notes" />
          </tr>
        </thead>
      </table>,
    );

    const th = screen.getByRole('columnheader');
    expect(th).not.toHaveAttribute('aria-sort');
  });

  // -----------------------------------------------------------------------
  // isNumeric prop
  // -----------------------------------------------------------------------

  it('passes isNumeric prop to <Th> for right-alignment', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" isNumeric />
          </tr>
        </thead>
      </table>,
    );

    const th = screen.getByRole('columnheader');
    expect(th).toHaveAttribute('data-is-numeric', 'true');
  });

  it('aligns VStack to flex-end when isNumeric', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" isNumeric />
          </tr>
        </thead>
      </table>,
    );

    const vstack = screen.getByTestId('vstack');
    expect(vstack).toHaveAttribute('data-align', 'flex-end');
  });

  it('aligns VStack to flex-start when not isNumeric', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" />
          </tr>
        </thead>
      </table>,
    );

    const vstack = screen.getByTestId('vstack');
    expect(vstack).toHaveAttribute('data-align', 'flex-start');
  });

  // -----------------------------------------------------------------------
  // Combined: filter + sort
  // -----------------------------------------------------------------------

  it('renders both filter input and sort indicator together', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader
              label="Account"
              filterValue="test"
              onFilterChange={jest.fn()}
              sortable
              sortDirection="asc"
              onSort={jest.fn()}
            />
          </tr>
        </thead>
      </table>,
    );

    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('Account')).toBeInTheDocument();
  });
});
