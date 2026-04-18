/**
 * Unit tests for useTableSort hook
 *
 * @see .kiro/specs/table-filter-framework-v2/design.md §2
 * Requirements: 12.2
 */

import { renderHook, act } from '@testing-library/react';
import { useTableSort } from '../useTableSort';

interface TestRow {
  name: string;
  age: number;
  score?: number | null;
}

const sampleData: TestRow[] = [
  { name: 'Charlie', age: 30, score: 85 },
  { name: 'alice', age: 25, score: 92 },
  { name: 'Bob', age: 35, score: 78 },
];

describe('useTableSort', () => {
  it('initial sort state matches defaults when provided', () => {
    const { result } = renderHook(() =>
      useTableSort(sampleData, 'name', 'desc'),
    );

    expect(result.current.sortField).toBe('name');
    expect(result.current.sortDirection).toBe('desc');
  });

  it('initial sort state is null/asc when no defaults provided', () => {
    const { result } = renderHook(() => useTableSort(sampleData));

    expect(result.current.sortField).toBeNull();
    expect(result.current.sortDirection).toBe('asc');
  });

  it('toggles direction on same field (asc→desc→asc)', () => {
    const { result } = renderHook(() =>
      useTableSort(sampleData, 'name', 'asc'),
    );

    expect(result.current.sortDirection).toBe('asc');

    // Toggle to desc
    act(() => {
      result.current.handleSort('name');
    });
    expect(result.current.sortField).toBe('name');
    expect(result.current.sortDirection).toBe('desc');

    // Toggle back to asc
    act(() => {
      result.current.handleSort('name');
    });
    expect(result.current.sortField).toBe('name');
    expect(result.current.sortDirection).toBe('asc');
  });

  it('new field resets direction to ascending', () => {
    const { result } = renderHook(() =>
      useTableSort(sampleData, 'name', 'desc'),
    );

    expect(result.current.sortField).toBe('name');
    expect(result.current.sortDirection).toBe('desc');

    act(() => {
      result.current.handleSort('age');
    });

    expect(result.current.sortField).toBe('age');
    expect(result.current.sortDirection).toBe('asc');
  });

  it('sorts strings case-insensitively', () => {
    const { result } = renderHook(() =>
      useTableSort(sampleData, 'name', 'asc'),
    );

    const names = result.current.sortedData.map((r) => r.name);
    // Case-insensitive: alice, Bob, Charlie
    expect(names).toEqual(['alice', 'Bob', 'Charlie']);
  });

  it('sorts strings case-insensitively in descending order', () => {
    const { result } = renderHook(() =>
      useTableSort(sampleData, 'name', 'desc'),
    );

    const names = result.current.sortedData.map((r) => r.name);
    expect(names).toEqual(['Charlie', 'Bob', 'alice']);
  });

  it('sorts numbers numerically (not lexicographic)', () => {
    const numericData = [
      { value: 100 },
      { value: 20 },
      { value: 3 },
      { value: 1000 },
    ];

    const { result } = renderHook(() =>
      useTableSort(numericData, 'value', 'asc'),
    );

    const values = result.current.sortedData.map((r) => r.value);
    // Numeric: 3, 20, 100, 1000 (not lexicographic: 100, 1000, 20, 3)
    expect(values).toEqual([3, 20, 100, 1000]);
  });

  it('sorts numbers numerically in descending order', () => {
    const numericData = [
      { value: 100 },
      { value: 20 },
      { value: 3 },
      { value: 1000 },
    ];

    const { result } = renderHook(() =>
      useTableSort(numericData, 'value', 'desc'),
    );

    const values = result.current.sortedData.map((r) => r.value);
    expect(values).toEqual([1000, 100, 20, 3]);
  });

  it('sorts null values to end regardless of direction', () => {
    const dataWithNulls: { name: string; score: number | null | undefined }[] = [
      { name: 'Alice', score: 85 },
      { name: 'Bob', score: null },
      { name: 'Charlie', score: 92 },
      { name: 'Dave', score: undefined },
      { name: 'Eve', score: 50 },
    ];

    // Ascending: nulls at end
    const { result: ascResult } = renderHook(() =>
      useTableSort(dataWithNulls, 'score', 'asc'),
    );

    const ascScores = ascResult.current.sortedData.map((r) => r.score);
    // Non-null values sorted ascending, then nulls at end
    expect(ascScores.slice(0, 3)).toEqual([50, 85, 92]);
    expect(ascScores[3]).toBeNull();
    expect(ascScores[4]).toBeUndefined();

    // Descending: nulls still at end
    const { result: descResult } = renderHook(() =>
      useTableSort(dataWithNulls, 'score', 'desc'),
    );

    const descScores = descResult.current.sortedData.map((r) => r.score);
    expect(descScores.slice(0, 3)).toEqual([92, 85, 50]);
    expect(descScores[3]).toBeFalsy(); // null or undefined
    expect(descScores[4]).toBeFalsy(); // null or undefined
  });

  it('getSortIndicator returns correct symbols', () => {
    const { result } = renderHook(() =>
      useTableSort(sampleData, 'name', 'asc'),
    );

    // Active field, ascending
    expect(result.current.getSortIndicator('name')).toBe('↑');

    // Toggle to descending
    act(() => {
      result.current.handleSort('name');
    });
    expect(result.current.getSortIndicator('name')).toBe('↓');

    // Inactive field
    expect(result.current.getSortIndicator('age')).toBe('');
    expect(result.current.getSortIndicator('nonexistent')).toBe('');
  });

  it('returns original order when no sort field is set', () => {
    const { result } = renderHook(() => useTableSort(sampleData));

    expect(result.current.sortField).toBeNull();
    expect(result.current.sortedData).toEqual(sampleData);
  });

  it('does not mutate the original data array', () => {
    const original = [...sampleData];

    renderHook(() => useTableSort(sampleData, 'name', 'asc'));

    expect(sampleData).toEqual(original);
  });

  it('handles empty data array', () => {
    const { result } = renderHook(() =>
      useTableSort([] as TestRow[], 'name', 'asc'),
    );

    expect(result.current.sortedData).toEqual([]);
  });

  it('re-sorts when data changes', () => {
    let data = [{ value: 3 }, { value: 1 }, { value: 2 }];

    const { result, rerender } = renderHook(() =>
      useTableSort(data, 'value', 'asc'),
    );

    expect(result.current.sortedData.map((r) => r.value)).toEqual([1, 2, 3]);

    // Update data
    data = [{ value: 30 }, { value: 10 }, { value: 20 }];
    rerender();

    expect(result.current.sortedData.map((r) => r.value)).toEqual([10, 20, 30]);
  });
});
