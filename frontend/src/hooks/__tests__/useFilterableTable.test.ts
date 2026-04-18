/**
 * Unit tests for useFilterableTable hook
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md §3
 * Requirements: 12.3
 */

import { renderHook, act } from '@testing-library/react';
import { useFilterableTable } from '../useFilterableTable';

interface TestRow {
  name: string;
  age: number;
  city: string;
}

const sampleData: TestRow[] = [
  { name: 'Charlie', age: 30, city: 'Amsterdam' },
  { name: 'Alice', age: 25, city: 'Berlin' },
  { name: 'Bob', age: 35, city: 'Amsterdam' },
  { name: 'Dave', age: 28, city: 'Copenhagen' },
];

const defaultConfig = {
  initialFilters: { name: '', city: '' },
  defaultSort: { field: 'name' as const, direction: 'asc' as const },
};

describe('useFilterableTable', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('combined filter + sort produces correct output', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, defaultConfig),
    );

    // Initial: all data sorted by name ascending (case-insensitive)
    expect(result.current.processedData.map((r) => r.name)).toEqual([
      'Alice', 'Bob', 'Charlie', 'Dave',
    ]);

    // Filter by city = 'amsterdam'
    act(() => {
      result.current.setFilter('city', 'amsterdam');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });

    // Only Amsterdam rows, still sorted by name asc
    expect(result.current.processedData).toEqual([
      { name: 'Bob', age: 35, city: 'Amsterdam' },
      { name: 'Charlie', age: 30, city: 'Amsterdam' },
    ]);
  });

  it('all delegated properties from sub-hooks are accessible', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, defaultConfig),
    );

    // From useColumnFilters
    expect(result.current.filters).toEqual({ name: '', city: '' });
    expect(typeof result.current.setFilter).toBe('function');
    expect(typeof result.current.resetFilters).toBe('function');
    expect(result.current.hasActiveFilters).toBe(false);

    // From useTableSort
    expect(result.current.sortField).toBe('name');
    expect(result.current.sortDirection).toBe('asc');
    expect(typeof result.current.handleSort).toBe('function');
    expect(typeof result.current.getSortIndicator).toBe('function');

    // Combined
    expect(Array.isArray(result.current.processedData)).toBe(true);
  });

  it('filter applied before sort (verified with specific example)', () => {
    // Data where filter + sort order matters:
    // If we sort first then filter, we'd get a different intermediate state.
    // The key invariant: sort operates on the filtered subset only.
    const data: TestRow[] = [
      { name: 'Zara', age: 20, city: 'Amsterdam' },
      { name: 'Alice', age: 30, city: 'Berlin' },
      { name: 'Mike', age: 25, city: 'Amsterdam' },
    ];

    const { result } = renderHook(() =>
      useFilterableTable(data, {
        initialFilters: { city: '' },
        defaultSort: { field: 'name', direction: 'asc' },
      }),
    );

    // Filter to Amsterdam only
    act(() => {
      result.current.setFilter('city', 'amsterdam');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });

    // Should be: Mike, Zara (filtered to Amsterdam, then sorted by name asc)
    // NOT: Alice, Mike, Zara (sorted first, then filtered)
    const names = result.current.processedData.map((r) => r.name);
    expect(names).toEqual(['Mike', 'Zara']);

    // Verify Alice (Berlin) is excluded
    expect(result.current.processedData).toHaveLength(2);
    expect(result.current.processedData.every((r) => r.city === 'Amsterdam')).toBe(true);
  });

  it('config with only filters (no sort) works', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, {
        initialFilters: { name: '', city: '' },
        // No defaultSort
      }),
    );

    // No sort → original order preserved
    expect(result.current.sortField).toBeNull();
    expect(result.current.processedData).toEqual(sampleData);

    // Filter still works
    act(() => {
      result.current.setFilter('name', 'alice');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(result.current.processedData).toEqual([sampleData[1]]);
  });

  it('config with only sort (no filters) works', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, {
        initialFilters: {},
        defaultSort: { field: 'age', direction: 'desc' },
      }),
    );

    // No filters → all data, sorted by age descending
    expect(result.current.hasActiveFilters).toBe(false);
    expect(result.current.processedData.map((r) => r.age)).toEqual([35, 30, 28, 25]);
  });

  it('handleSort toggles direction and re-sorts processedData', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, defaultConfig),
    );

    // Initial: sorted by name asc
    expect(result.current.processedData.map((r) => r.name)).toEqual([
      'Alice', 'Bob', 'Charlie', 'Dave',
    ]);

    // Toggle to desc
    act(() => {
      result.current.handleSort('name');
    });

    expect(result.current.sortDirection).toBe('desc');
    expect(result.current.processedData.map((r) => r.name)).toEqual([
      'Dave', 'Charlie', 'Bob', 'Alice',
    ]);
  });

  it('resetFilters restores full data while preserving sort', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, defaultConfig),
    );

    // Apply filter
    act(() => {
      result.current.setFilter('city', 'amsterdam');
    });
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.processedData).toHaveLength(2);

    // Reset filters
    act(() => {
      result.current.resetFilters();
    });

    // All data back, still sorted by name asc
    expect(result.current.processedData).toHaveLength(4);
    expect(result.current.processedData.map((r) => r.name)).toEqual([
      'Alice', 'Bob', 'Charlie', 'Dave',
    ]);
  });

  it('getSortIndicator returns correct symbols', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, defaultConfig),
    );

    expect(result.current.getSortIndicator('name')).toBe('↑');
    expect(result.current.getSortIndicator('age')).toBe('');

    act(() => {
      result.current.handleSort('name');
    });

    expect(result.current.getSortIndicator('name')).toBe('↓');
  });

  it('debounceMs config is passed through to useColumnFilters', () => {
    const { result } = renderHook(() =>
      useFilterableTable(sampleData, {
        initialFilters: { name: '' },
        debounceMs: 300,
      }),
    );

    act(() => {
      result.current.setFilter('name', 'alice');
    });

    // At 150ms: not yet applied (custom 300ms debounce)
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.processedData).toEqual(sampleData);

    // At 300ms: applied
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.processedData).toHaveLength(1);
    expect(result.current.processedData[0].name).toBe('Alice');
  });
});
