/**
 * Unit tests for useColumnFilters hook
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md §1
 * Requirements: 12.1
 */

import { renderHook, act } from '@testing-library/react';
import { useColumnFilters } from '../useColumnFilters';

interface TestRow {
  name: string;
  email: string;
  status?: string;
}

const sampleData: TestRow[] = [
  { name: 'Alice', email: 'alice@example.com', status: 'active' },
  { name: 'Bob', email: 'bob@test.com', status: 'inactive' },
  { name: 'Charlie', email: 'charlie@example.com', status: 'active' },
];

const initialFilters = { name: '', email: '', status: '' };

describe('useColumnFilters', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns full data when no filters are active', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    expect(result.current.filteredData).toEqual(sampleData);
    expect(result.current.hasActiveFilters).toBe(false);
  });

  it('filters by a single field and returns matching rows', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    act(() => {
      result.current.setFilter('name', 'alice');
    });

    // Advance past debounce
    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(result.current.filteredData).toEqual([sampleData[0]]);
  });

  it('filters by multiple fields simultaneously (AND logic)', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    act(() => {
      result.current.setFilter('email', 'example');
    });
    act(() => {
      result.current.setFilter('status', 'active');
    });

    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(result.current.filteredData).toEqual([sampleData[0], sampleData[2]]);
  });

  it('performs case-insensitive matching', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    act(() => {
      result.current.setFilter('name', 'ALICE');
    });

    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(result.current.filteredData).toEqual([sampleData[0]]);
  });

  it('debounces filtering with default 150ms delay', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    act(() => {
      result.current.setFilter('name', 'alice');
    });

    // Before debounce: filteredData still has all rows
    expect(result.current.filteredData).toEqual(sampleData);

    // After debounce: filteredData is updated
    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(result.current.filteredData).toEqual([sampleData[0]]);
  });

  it('debounces filtering with custom delay', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters, { debounceMs: 300 }),
    );

    act(() => {
      result.current.setFilter('name', 'bob');
    });

    // At 150ms: not yet applied
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.filteredData).toEqual(sampleData);

    // At 300ms: applied
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.filteredData).toEqual([sampleData[1]]);
  });

  it('resetFilters clears all filters and returns full data', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    // Apply a filter
    act(() => {
      result.current.setFilter('name', 'alice');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.filteredData).toHaveLength(1);

    // Reset
    act(() => {
      result.current.resetFilters();
    });

    expect(result.current.filteredData).toEqual(sampleData);
    expect(result.current.filters).toEqual({ name: '', email: '', status: '' });
    expect(result.current.hasActiveFilters).toBe(false);
  });

  it('does not exclude rows when filter key is missing from a row', () => {
    const dataWithMissingField = [
      { name: 'Alice', email: 'alice@example.com' },
      { name: 'Bob', email: 'bob@test.com', extra: 'value' },
    ];

    const { result } = renderHook(() =>
      useColumnFilters(dataWithMissingField, { name: '', extra: '' }),
    );

    act(() => {
      result.current.setFilter('extra', 'val');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });

    // Alice's row doesn't have 'extra' field → filter passes → included
    // Bob's row has 'extra' = 'value' which contains 'val' → included
    expect(result.current.filteredData).toEqual(dataWithMissingField);
  });

  it('returns empty result for empty data array', () => {
    const { result } = renderHook(() =>
      useColumnFilters([] as TestRow[], initialFilters),
    );

    act(() => {
      result.current.setFilter('name', 'test');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(result.current.filteredData).toEqual([]);
  });

  it('hasActiveFilters reflects filter state immediately', () => {
    const { result } = renderHook(() =>
      useColumnFilters(sampleData, initialFilters),
    );

    expect(result.current.hasActiveFilters).toBe(false);

    act(() => {
      result.current.setFilter('name', 'a');
    });

    // hasActiveFilters updates immediately (not debounced)
    expect(result.current.hasActiveFilters).toBe(true);

    act(() => {
      result.current.setFilter('name', '');
    });

    expect(result.current.hasActiveFilters).toBe(false);
  });
});
