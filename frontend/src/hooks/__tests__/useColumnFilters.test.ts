/**
 * Unit tests for useColumnFilters hook
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md §1
 * Requirements: 12.1
 */

import { vi } from 'vitest';
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
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
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
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
    });
    expect(result.current.filteredData).toEqual(sampleData);

    // At 300ms: applied
    act(() => {
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
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
      vi.advanceTimersByTime(150);
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

  // Findings F-007: when the SAME hook instance is reused with a DIFFERENT set of
  // columns (the Member Analytics PivotResultTable stays mounted while the user
  // Executes a set with different columns), the filter key set must re-sync — a
  // column absent from `filters` gets filterValue === undefined and renders no
  // filter input ("only one column has a filter"). The reconcile adds new keys,
  // drops removed keys, and preserves surviving values.
  describe('re-syncs the filter key set when initialFilters keys change (F-007)', () => {
    it('adds filter keys for newly-introduced columns', () => {
      const { result, rerender } = renderHook<
        ReturnType<typeof useColumnFilters<TestRow>>,
        { init: Record<string, string> }
      >(({ init }) => useColumnFilters(sampleData, init), {
        initialProps: { init: { membership_type: '' } },
      });
      // Only the first set's column is tracked initially.
      expect(Object.keys(result.current.filters)).toEqual(['membership_type']);

      // Execute a different set → different columns.
      rerender({ init: { name: '', email: '', birthday: '', country: '' } });

      // Every new column is now a tracked (defined) filter key.
      expect(Object.keys(result.current.filters).sort()).toEqual(
        ['birthday', 'country', 'email', 'name'].sort(),
      );
      for (const key of ['name', 'email', 'birthday', 'country']) {
        expect(result.current.filters[key]).toBe('');
      }
      // The removed column is no longer tracked.
      expect(result.current.filters).not.toHaveProperty('membership_type');
    });

    it('preserves an active filter value for a column that survives the change', () => {
      const { result, rerender } = renderHook<
        ReturnType<typeof useColumnFilters<TestRow>>,
        { init: Record<string, string> }
      >(({ init }) => useColumnFilters(sampleData, init), {
        initialProps: { init: { name: '', email: '' } },
      });

      act(() => {
        result.current.setFilter('name', 'alice');
      });
      act(() => {
        vi.advanceTimersByTime(150);
      });
      expect(result.current.filters.name).toBe('alice');

      // Rerender with a changed key set that still includes `name`.
      rerender({ init: { name: '', email: '', region: '' } });

      // `name`'s active value survives; the new `region` key is added empty.
      expect(result.current.filters.name).toBe('alice');
      expect(result.current.filters.region).toBe('');
    });

    it('does not disturb state when the key set is unchanged (stable columns)', () => {
      const { result, rerender } = renderHook(
        ({ init }: { init: Record<string, string> }) => useColumnFilters(sampleData, init),
        { initialProps: { init: { name: '', email: '', status: '' } } },
      );

      act(() => {
        result.current.setFilter('email', 'example');
      });
      act(() => {
        vi.advanceTimersByTime(150);
      });

      // A fresh initialFilters object with the SAME keys (new identity each
      // render) must not reset the active filter.
      rerender({ init: { name: '', email: '', status: '' } });
      expect(result.current.filters.email).toBe('example');
      expect(result.current.filteredData).toEqual([sampleData[0], sampleData[2]]);
    });
  });
});
