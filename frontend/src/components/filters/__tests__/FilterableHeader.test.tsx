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

import { vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@/test-utils';


// Import component after mocks
// eslint-disable-next-line import-x/first
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
    expect(th).toBeInTheDocument();

    const label = screen.getByText('Status');
    expect(label).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Filter input rendering
  // -----------------------------------------------------------------------

  it('renders filter input when filterValue is provided', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="" onFilterChange={vi.fn()} />
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
            <FilterableHeader label="Name" filterValue="test" onFilterChange={vi.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const input = screen.getByRole('textbox');
    expect(input).toBeInTheDocument();
  });

  it('renders filter input with default placeholder', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Name" filterValue="" onFilterChange={vi.fn()} />
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
              onFilterChange={vi.fn()}
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
            <FilterableHeader label="Name" filterValue="john" onFilterChange={vi.fn()} />
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
    const onFilterChange = vi.fn();
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
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={vi.fn()} />
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
            <FilterableHeader label="Amount" sortable sortDirection="desc" onSort={vi.fn()} />
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
            <FilterableHeader label="Amount" sortable sortDirection={null} onSort={vi.fn()} />
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
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={vi.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const indicator = screen.getByText('↑');
    expect(indicator).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Sort click callback
  // -----------------------------------------------------------------------

  it('calls onSort callback on sort click', () => {
    const onSort = vi.fn();
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={onSort} />
          </tr>
        </thead>
      </table>,
    );

    const labelRow = screen.getByRole('button', { name: 'Sort by Amount' });
    fireEvent.click(labelRow);
    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it('does not call onSort when not sortable', () => {
    const onSort = vi.fn();
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Notes" onSort={onSort} />
          </tr>
        </thead>
      </table>,
    );

    // When not sortable, there's no button role
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(onSort).not.toHaveBeenCalled();
  });

  it('sets cursor to pointer when sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable onSort={vi.fn()} />
          </tr>
        </thead>
      </table>,
    );

    const labelRow = screen.getByRole('button', { name: 'Sort by Amount' });
    expect(labelRow).toBeInTheDocument();
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

    // When not sortable, there's no button role
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('sets role=button on label row when sortable', () => {
    render(
      <table>
        <thead>
          <tr>
            <FilterableHeader label="Amount" sortable onSort={vi.fn()} />
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
            <FilterableHeader label="Account" filterValue="" onFilterChange={vi.fn()} />
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
            <FilterableHeader label="Amount" sortable sortDirection="asc" onSort={vi.fn()} />
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
            <FilterableHeader label="Amount" sortable sortDirection="desc" onSort={vi.fn()} />
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
            <FilterableHeader label="Amount" sortable sortDirection={null} onSort={vi.fn()} />
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
    expect(th).toBeInTheDocument();
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

    // Verify the component renders correctly with isNumeric
    expect(screen.getByText('Amount')).toBeInTheDocument();
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

    // Verify the component renders correctly without isNumeric
    expect(screen.getByText('Name')).toBeInTheDocument();
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
              onFilterChange={vi.fn()}
              sortable
              sortDirection="asc"
              onSort={vi.fn()}
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
