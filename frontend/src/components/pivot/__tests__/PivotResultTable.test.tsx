/**
 * PivotResultTable — Unit Tests
 *
 * Covers flat mode rendering, loading state, empty state, number formatting,
 * the three-way number format toggle (decimal / whole / k-notation),
 * hierarchical mode with expand/collapse, and export button states.
 *
 * Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 7.6, 8.1
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@/test-utils';
import '@testing-library/jest-dom';
import { PivotResultTable } from '../PivotResultTable';
import type { PivotColumnMeta, PivotConfig } from '../../../types/pivot';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock PivotExportMenu to avoid API dependencies and test its presence/absence
vi.mock('../PivotExportMenu', () => ({
  PivotExportMenu: ({ data, columns }: any) => {
    const hasData = data.length > 0 && columns.length > 0;
    return (
      <button
        data-testid="pivot-export-menu"
        disabled={!hasData}
      >
        Export
      </button>
    );
  },
}));

// Mock PivotResultTablePivoted to avoid complex rendering in non-pivoted tests
vi.mock('../PivotResultTablePivoted', () => ({
  PivotResultTablePivoted: () => <div data-testid="pivoted-table">Pivoted</div>,
  isPivotedResult: (columns: any[]) => columns.some((c: any) => c.pivotValue !== undefined),
}));

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, opts?: any) => {
      const map: Record<string, string> = {
        'pivot.results.loading': 'Executing pivot query...',
        'pivot.results.noData': 'No data matches the current configuration.',
        'pivot.results.rowCount': `${opts?.count ?? 0} rows`,
        'pivot.numberFormat.label': 'Number Format',
        'pivot.numberFormat.decimal': 'Decimal (2dp)',
        'pivot.numberFormat.whole': 'Whole numbers',
        'pivot.numberFormat.kNotation': 'Abbreviated (K/M)',
      };
      return map[key] ?? key;
    },
    i18n: { language: 'en' },
  }),
}));

// Mock FilterableHeader to render a simple <th> with optional filter input
vi.mock('../../filters/FilterableHeader', () => ({
  FilterableHeader: ({ label, filterValue, onFilterChange, onSort, sortable, sortDirection, isNumeric, ...props }: any) => (
    <th data-testid={`th-${label}`} onClick={sortable ? onSort : undefined}>
      <span>{label}</span>
      {sortDirection && <span data-testid={`sort-${label}`}>{sortDirection === 'asc' ? '↑' : '↓'}</span>}
      {filterValue !== undefined && (
        <input
          data-testid={`filter-${label}`}
          value={filterValue}
          onChange={(e) => onFilterChange?.(e.target.value)}
        />
      )}
    </th>
  ),
}));

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const baseConfig: PivotConfig = {
  dataSource: 'vw_mutaties',
  groupColumns: ['Aangifte', 'jaar'],
  aggregateMeasures: [
    { function: 'SUM', column: 'Amount' },
    { function: 'COUNT', column: '*' },
  ],
  filters: {},
  columnPivot: null,
  columnNestLevels: [],
  displayMode: 'flat',
};

const sampleColumns: PivotColumnMeta[] = [
  { name: 'Aangifte', type: 'group', dataType: 'varchar' },
  { name: 'jaar', type: 'group', dataType: 'int' },
  { name: 'SUM_Amount', type: 'aggregate', dataType: 'decimal', function: 'SUM', sourceColumn: 'Amount' },
  { name: 'COUNT', type: 'aggregate', dataType: 'int', function: 'COUNT', sourceColumn: '*' },
];

const sampleData = [
  { Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67, COUNT: 42 },
  { Aangifte: 'BTW', jaar: 2025, SUM_Amount: 15678.90, COUNT: 55 },
  { Aangifte: 'IB', jaar: 2024, SUM_Amount: 8000.00, COUNT: 20 },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PivotResultTable', () => {
  it('renders loading state', () => {
    render(
      <table>
        <tbody>
          <tr>
            <td>
              <PivotResultTable
                data={[]}
                columns={[]}
                config={baseConfig}
                isLoading={true}
              />
            </td>
          </tr>
        </tbody>
      </table>,
    );
    expect(screen.getByText('Executing pivot query...')).toBeInTheDocument();
  });

  it('renders nothing when no columns (no query executed)', () => {
    const { container } = render(
      <PivotResultTable
        data={[]}
        columns={[]}
        config={baseConfig}
        isLoading={false}
      />,
    );
    // Should render a minimal empty element (stable root to avoid React removeChild errors)
    expect(container.querySelector('table')).toBeNull();
    expect(container.textContent).toBe('');
  });

  it('renders empty state when columns exist but no data', () => {
    render(
      <PivotResultTable
        data={[]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );
    expect(screen.getByText('No data matches the current configuration.')).toBeInTheDocument();
  });

  it('renders flat table with correct columns', () => {
    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // All column headers should be present
    expect(screen.getByTestId('th-Aangifte')).toBeInTheDocument();
    expect(screen.getByTestId('th-jaar')).toBeInTheDocument();
    expect(screen.getByTestId('th-SUM_Amount')).toBeInTheDocument();
    expect(screen.getByTestId('th-COUNT')).toBeInTheDocument();
  });

  it('renders data rows with group and aggregate values', () => {
    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Group column values
    expect(screen.getAllByText('BTW')).toHaveLength(2);
    expect(screen.getByText('IB')).toBeInTheDocument();

    // Row count
    expect(screen.getByText('3 rows')).toBeInTheDocument();
  });

  it('renders filter inputs for all columns', () => {
    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    expect(screen.getByTestId('filter-Aangifte')).toBeInTheDocument();
    expect(screen.getByTestId('filter-jaar')).toBeInTheDocument();
    expect(screen.getByTestId('filter-SUM_Amount')).toBeInTheDocument();
    expect(screen.getByTestId('filter-COUNT')).toBeInTheDocument();
  });

  it('formats COUNT values as whole numbers when whole format is selected', () => {
    render(
      <PivotResultTable
        data={[{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 100.50, COUNT: 42 }]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Default is decimal — COUNT shows 42.00
    expect(screen.getByText('42.00')).toBeInTheDocument();

    // Switch to whole numbers — COUNT shows 42
    fireEvent.click(screen.getByTestId('number-format-whole'));
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('handles null values gracefully', () => {
    const dataWithNulls = [
      { Aangifte: null, jaar: 2024, SUM_Amount: null, COUNT: 0 },
    ];

    render(
      <PivotResultTable
        data={dataWithNulls}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Should not crash — null values render as empty strings
    expect(screen.getByText('1 rows')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Number format toggle (Requirement 3.7)
  // -------------------------------------------------------------------------

  it('renders number format toggle when aggregate columns exist', () => {
    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    expect(screen.getByText('Number Format')).toBeInTheDocument();
    expect(screen.getByTestId('number-format-decimal')).toBeInTheDocument();
    expect(screen.getByTestId('number-format-whole')).toBeInTheDocument();
    expect(screen.getByTestId('number-format-k-notation')).toBeInTheDocument();
  });

  it('does not render number format toggle when no aggregate columns', () => {
    const groupOnlyColumns: PivotColumnMeta[] = [
      { name: 'Aangifte', type: 'group', dataType: 'varchar' },
      { name: 'jaar', type: 'group', dataType: 'int' },
    ];
    const groupOnlyData = [{ Aangifte: 'BTW', jaar: 2024 }];

    render(
      <PivotResultTable
        data={groupOnlyData}
        columns={groupOnlyColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    expect(screen.queryByText('Number Format')).not.toBeInTheDocument();
    expect(screen.queryByTestId('number-format-decimal')).not.toBeInTheDocument();
  });

  it('defaults to decimal format', () => {
    render(
      <PivotResultTable
        data={[{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67, COUNT: 42 }]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Decimal format: 12,345.67 (en-US locale)
    expect(screen.getByText('12,345.67')).toBeInTheDocument();
  });

  it('switches to whole number format on toggle click', () => {
    render(
      <PivotResultTable
        data={[{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67, COUNT: 42 }]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Click "Whole numbers" toggle
    fireEvent.click(screen.getByTestId('number-format-whole'));

    // Whole format: 12,346 (rounded, en-US locale)
    expect(screen.getByText('12,346')).toBeInTheDocument();
  });

  it('switches to k-notation format on toggle click', () => {
    render(
      <PivotResultTable
        data={[{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67, COUNT: 42 }]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Click "Abbreviated (K/M)" toggle
    fireEvent.click(screen.getByTestId('number-format-k-notation'));

    // K-notation: 12.3K (en-US locale)
    expect(screen.getByText('12.3K')).toBeInTheDocument();
  });

  it('applies number format to all aggregate columns', () => {
    render(
      <PivotResultTable
        data={[{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 5000.50, COUNT: 1234 }]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Switch to k-notation
    fireEvent.click(screen.getByTestId('number-format-k-notation'));

    // Both aggregate columns should use k-notation
    expect(screen.getByText('5.0K')).toBeInTheDocument();   // SUM_Amount
    expect(screen.getByText('1.2K')).toBeInTheDocument();   // COUNT
  });

  it('calls onNumberFormatChange callback when toggle is clicked', () => {
    const onFormatChange = vi.fn();

    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
        onNumberFormatChange={onFormatChange}
      />,
    );

    fireEvent.click(screen.getByTestId('number-format-whole'));
    expect(onFormatChange).toHaveBeenCalledWith('whole');

    fireEvent.click(screen.getByTestId('number-format-k-notation'));
    expect(onFormatChange).toHaveBeenCalledWith('k-notation');

    fireEvent.click(screen.getByTestId('number-format-decimal'));
    expect(onFormatChange).toHaveBeenCalledWith('decimal');
  });

  it('respects externally controlled numberFormat prop', () => {
    render(
      <PivotResultTable
        data={[{ Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12345.67, COUNT: 42 }]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
        numberFormat="whole"
      />,
    );

    // Should use whole format from prop: 12,346
    expect(screen.getByText('12,346')).toBeInTheDocument();
  });

  it('does not render number format toggle in empty state', () => {
    render(
      <PivotResultTable
        data={[]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Empty state shows info message, no toggle
    expect(screen.queryByTestId('number-format-decimal')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Hierarchical mode tests (Requirements: 8.1–8.7)
// ---------------------------------------------------------------------------

describe('PivotResultTable — Hierarchical Mode', () => {
  const hierarchicalConfig: PivotConfig = {
    dataSource: 'vw_mutaties',
    groupColumns: ['Aangifte', 'jaar'],
    aggregateMeasures: [
      { function: 'SUM', column: 'Amount' },
      { function: 'COUNT', column: '*' },
    ],
    filters: {},
    columnPivot: null,
    columnNestLevels: [],
    includeRollup: true,
    displayMode: 'hierarchical',
  };

  const hierarchicalData = [
    { Aangifte: 'BTW', jaar: 2024, SUM_Amount: 12000, COUNT: 42 },
    { Aangifte: 'BTW', jaar: 2025, SUM_Amount: 15000, COUNT: 55 },
    { Aangifte: 'IB', jaar: 2024, SUM_Amount: 8000, COUNT: 20 },
    { Aangifte: 'IB', jaar: 2025, SUM_Amount: 9000, COUNT: 25 },
  ];

  it('renders hierarchical tree when displayMode is hierarchical and 2+ group columns', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Top-level nodes should be visible (BTW, IB)
    expect(screen.getByTestId('tree-row-0-BTW')).toBeInTheDocument();
    expect(screen.getByTestId('tree-row-0-IB')).toBeInTheDocument();

    // Child nodes should be visible (expanded by default for branch nodes)
    // 2024 and 2025 appear under both BTW and IB, so use getAllByTestId
    expect(screen.getAllByTestId('tree-row-1-2024')).toHaveLength(2);
    expect(screen.getAllByTestId('tree-row-1-2025')).toHaveLength(2);
  });

  it('shows expand/collapse icons on parent rows', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Parent rows should have toggle icons
    expect(screen.getByTestId('tree-toggle-BTW')).toBeInTheDocument();
    expect(screen.getByTestId('tree-toggle-IB')).toBeInTheDocument();
  });

  it('collapses children when parent row is clicked', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Children should be visible initially (branch nodes default to expanded)
    const btw2024Rows = screen.getAllByTestId('tree-row-1-2024');
    expect(btw2024Rows.length).toBeGreaterThan(0);

    // Click BTW parent to collapse
    fireEvent.click(screen.getByTestId('tree-row-0-BTW'));

    // After collapse, BTW's children (2024, 2025 under BTW) should be hidden
    // But IB's children should still be visible
    // We check that the total number of tree-row-1-* elements decreased
    const allDepth1Rows = screen.getAllByTestId(/^tree-row-1-/);
    // IB still has 2 children visible, BTW's 2 are hidden → 2 remaining
    expect(allDepth1Rows.length).toBe(2);
  });

  it('expands children when collapsed parent row is clicked again', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Collapse BTW
    fireEvent.click(screen.getByTestId('tree-row-0-BTW'));
    // Re-expand BTW
    fireEvent.click(screen.getByTestId('tree-row-0-BTW'));

    // All 4 child rows should be visible again
    const allDepth1Rows = screen.getAllByTestId(/^tree-row-1-/);
    expect(allDepth1Rows.length).toBe(4);
  });

  it('shows expand all / collapse all buttons in hierarchical mode', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    expect(screen.getByTestId('expand-all')).toBeInTheDocument();
    expect(screen.getByTestId('collapse-all')).toBeInTheDocument();
  });

  it('does not show expand/collapse buttons in flat mode', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    expect(screen.queryByTestId('expand-all')).not.toBeInTheDocument();
    expect(screen.queryByTestId('collapse-all')).not.toBeInTheDocument();
  });

  it('collapse all hides all children', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Click collapse all
    fireEvent.click(screen.getByTestId('collapse-all'));

    // Only top-level rows should be visible
    expect(screen.getByTestId('tree-row-0-BTW')).toBeInTheDocument();
    expect(screen.getByTestId('tree-row-0-IB')).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^tree-row-1-/)).toHaveLength(0);
  });

  it('expand all shows all children after collapse', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Collapse all, then expand all
    fireEvent.click(screen.getByTestId('collapse-all'));
    fireEvent.click(screen.getByTestId('expand-all'));

    // All child rows should be visible again
    const allDepth1Rows = screen.getAllByTestId(/^tree-row-1-/);
    expect(allDepth1Rows.length).toBe(4);
  });

  it('displays rolled-up aggregate values on parent rows', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // BTW parent should show SUM of 12000 + 15000 = 27000 and COUNT 42 + 55 = 97
    // In decimal format: 27,000.00 and 97.00
    const btwRow = screen.getByTestId('tree-row-0-BTW');
    expect(btwRow).toHaveTextContent('27,000.00');
    expect(btwRow).toHaveTextContent('97.00');

    // IB parent should show SUM of 8000 + 9000 = 17000 and COUNT 20 + 25 = 45
    const ibRow = screen.getByTestId('tree-row-0-IB');
    expect(ibRow).toHaveTextContent('17,000.00');
    expect(ibRow).toHaveTextContent('45.00');
  });

  it('falls back to flat mode when only 1 group column even if displayMode is hierarchical', () => {
    const singleGroupConfig: PivotConfig = {
      ...hierarchicalConfig,
      groupColumns: ['Aangifte'],
    };

    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={singleGroupConfig}
        isLoading={false}
      />,
    );

    // Should render flat mode — no tree rows, no expand/collapse buttons
    expect(screen.queryByTestId('expand-all')).not.toBeInTheDocument();
    expect(screen.queryByTestId('collapse-all')).not.toBeInTheDocument();
    expect(screen.queryByTestId(/^tree-row-/)).not.toBeInTheDocument();
  });

  it('applies number format toggle in hierarchical mode', () => {
    render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Switch to k-notation
    fireEvent.click(screen.getByTestId('number-format-k-notation'));

    // BTW parent: 27000 → 27.0K
    const btwRow = screen.getByTestId('tree-row-0-BTW');
    expect(btwRow).toHaveTextContent('27.0K');
  });

  it('toggles between flat and hierarchical without re-executing query', () => {
    const { rerender } = render(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    // Hierarchical mode: tree rows visible
    expect(screen.getByTestId('tree-row-0-BTW')).toBeInTheDocument();

    // Switch to flat mode (simulating parent config change)
    rerender(
      <PivotResultTable
        data={hierarchicalData}
        columns={sampleColumns}
        config={{ ...hierarchicalConfig, displayMode: 'flat' }}
        isLoading={false}
      />,
    );

    // Flat mode: no tree rows, regular table headers
    expect(screen.queryByTestId(/^tree-row-/)).not.toBeInTheDocument();
    expect(screen.getByTestId('th-Aangifte')).toBeInTheDocument();
    expect(screen.getByTestId('th-jaar')).toBeInTheDocument();
  });
});


// ---------------------------------------------------------------------------
// Export button tests (Requirement 7.6)
// ---------------------------------------------------------------------------

describe('PivotResultTable — Export Buttons', () => {
  it('renders export menu when data is present', () => {
    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    const exportMenu = screen.getByTestId('pivot-export-menu');
    expect(exportMenu).toBeInTheDocument();
    expect(exportMenu).not.toBeDisabled();
  });

  it('does not render export menu when no data (empty state)', () => {
    render(
      <PivotResultTable
        data={[]}
        columns={sampleColumns}
        config={baseConfig}
        isLoading={false}
      />,
    );

    // Export menu should not be in the DOM — toolbar is not rendered in empty state
    expect(screen.queryByTestId('pivot-export-menu')).not.toBeInTheDocument();
  });

  it('does not render export menu when no columns (no query executed)', () => {
    render(
      <PivotResultTable
        data={[]}
        columns={[]}
        config={baseConfig}
        isLoading={false}
      />,
    );

    expect(screen.queryByTestId('pivot-export-menu')).not.toBeInTheDocument();
  });

  it('does not render export menu during loading state', () => {
    render(
      <table>
        <tbody>
          <tr>
            <td>
              <PivotResultTable
                data={[]}
                columns={[]}
                config={baseConfig}
                isLoading={true}
              />
            </td>
          </tr>
        </tbody>
      </table>,
    );

    expect(screen.queryByTestId('pivot-export-menu')).not.toBeInTheDocument();
  });

  it('renders export menu in hierarchical mode when data is present', () => {
    const hierarchicalConfig: PivotConfig = {
      ...baseConfig,
      displayMode: 'hierarchical',
      includeRollup: true,
    };

    render(
      <PivotResultTable
        data={sampleData}
        columns={sampleColumns}
        config={hierarchicalConfig}
        isLoading={false}
      />,
    );

    const exportMenu = screen.getByTestId('pivot-export-menu');
    expect(exportMenu).toBeInTheDocument();
    expect(exportMenu).not.toBeDisabled();
  });
});
