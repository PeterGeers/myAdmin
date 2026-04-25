/**
 * PivotResultTablePivoted Component — Column-Pivoted Display Mode
 *
 * Renders pivot query results with column pivoting: distinct values of the
 * pivot column become column headers, with aggregate measures spread across
 * those columns. Supports hierarchical column headers via multi-row <thead>
 * when column nest levels are present. Appends a grand total column group.
 *
 * Requirements: 9.2, 9.4, 9.6, 9.9
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §5 PivotResultTable
 */

import React, { useMemo } from 'react';
import {
  Box,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { formatPivotNumber, resolveLocale } from '../../utils/pivotFormatting';
import type {
  NumberFormat,
  PivotColumnMeta,
  PivotConfig,
} from '../../types/pivot';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PivotResultTablePivotedProps {
  /** Result rows from the pivot query */
  data: Record<string, any>[];
  /** Column metadata describing each column in the result */
  columns: PivotColumnMeta[];
  /** The pivot configuration that produced these results */
  config: PivotConfig;
  /** Active number format for aggregate values */
  numberFormat: NumberFormat;
}

// ---------------------------------------------------------------------------
// Types for header structure
// ---------------------------------------------------------------------------

/** A single header cell in the multi-row thead */
interface HeaderCell {
  label: string;
  colSpan: number;
  rowSpan: number;
  isNumeric: boolean;
  isGroup: boolean;
}

/** Describes one leaf (bottom-level) aggregate column in the pivoted layout */
interface PivotLeafColumn {
  /** Column name in the result data (the alias) */
  name: string;
  /** Column metadata */
  meta: PivotColumnMeta;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Detect whether the result set contains column-pivoted data by checking
 * if any column has a pivotGroup field.
 */
export function isPivotedResult(columns: PivotColumnMeta[]): boolean {
  return columns.some((c) => c.pivotGroup != null);
}

/**
 * Extract the ordered list of distinct pivot values from column metadata.
 */
function extractPivotValues(columns: PivotColumnMeta[]): (string | number)[] {
  const seen = new Set<string>();
  const values: (string | number)[] = [];
  for (const col of columns) {
    if (col.pivotGroup === 'pivot' && col.pivotValue != null) {
      const key = String(col.pivotValue);
      if (!seen.has(key)) {
        seen.add(key);
        values.push(col.pivotValue);
      }
    }
  }
  return values;
}

/**
 * Extract the ordered list of distinct nest-level combinations from column metadata.
 * Returns an array of { label, values } objects for each unique combination.
 */
function extractNestCombinations(
  columns: PivotColumnMeta[],
): { label: string; values: Record<string, string | number> }[] {
  const seen = new Set<string>();
  const combos: { label: string; values: Record<string, string | number> }[] = [];

  for (const col of columns) {
    if (col.pivotGroup === 'pivot' && col.nestValues && Object.keys(col.nestValues).length > 0) {
      const key = Object.values(col.nestValues).map(String).join('|');
      if (!seen.has(key)) {
        seen.add(key);
        combos.push({
          label: Object.values(col.nestValues).map(String).join(' / '),
          values: col.nestValues,
        });
      }
    }
  }
  return combos;
}

/**
 * Get the unique aggregate measure labels (function + column) from the config.
 */
function getMeasureLabels(config: PivotConfig): string[] {
  return config.aggregateMeasures.map((m) => {
    if (m.column === '*') return m.function;
    return `${m.function}(${m.column})`;
  });
}

/**
 * Format a cell value for display using the active number format.
 */
function formatCell(
  value: any,
  col: PivotColumnMeta,
  format: NumberFormat,
  locale: string,
): string {
  if (value == null) return '';
  if (col.type === 'group') return String(value);

  const numValue = typeof value === 'number' ? value : Number(value);
  if (Number.isNaN(numValue)) return String(value);
  return formatPivotNumber(numValue, format, locale);
}

// ---------------------------------------------------------------------------
// Header builder
// ---------------------------------------------------------------------------

/**
 * Build the multi-row header structure for a column-pivoted result.
 *
 * Layout depends on whether nest levels are present:
 *
 * **Without nest levels** (2 header rows):
 * Row 0: [group cols (rowSpan=2)] [pivotValue1 (colSpan=N)] [pivotValue2 (colSpan=N)] ... [Total (colSpan=N)]
 * Row 1:                          [measure1] [measure2] ... [measure1] [measure2] ...     [measure1] [measure2] ...
 *
 * **With nest levels** (3 header rows):
 * Row 0: [group cols (rowSpan=3)] [pivotValue1 (colSpan=N*M)] [pivotValue2 (colSpan=N*M)] ... [Total (colSpan=N)]
 * Row 1:                          [nest1 (colSpan=N)] [nest2 (colSpan=N)] ...                  (empty — total has no nests)
 * Row 2:                          [measure1] [measure2] ... per nest combo                     [measure1] [measure2] ...
 */
function buildHeaderRows(
  groupColumns: PivotColumnMeta[],
  pivotValues: (string | number)[],
  nestCombos: { label: string; values: Record<string, string | number> }[],
  measureLabels: string[],
  t: (key: string, opts?: any) => string,
): HeaderCell[][] {
  const numMeasures = measureLabels.length;
  const hasNests = nestCombos.length > 0;
  const totalHeaderRows = hasNests ? 3 : 2;

  const rows: HeaderCell[][] = Array.from({ length: totalHeaderRows }, () => []);

  // Group column headers — span all header rows
  for (const col of groupColumns) {
    rows[0].push({
      label: col.name,
      colSpan: 1,
      rowSpan: totalHeaderRows,
      isNumeric: false,
      isGroup: true,
    });
  }

  if (hasNests) {
    // Row 0: pivot value headers spanning (nestCombos * measures) columns
    const colsPerPivot = nestCombos.length * numMeasures;
    for (const pv of pivotValues) {
      rows[0].push({
        label: String(pv),
        colSpan: colsPerPivot,
        rowSpan: 1,
        isNumeric: true,
        isGroup: false,
      });
    }
    // Total header in row 0
    rows[0].push({
      label: t('pivot.results.grandTotal'),
      colSpan: numMeasures,
      rowSpan: 1,
      isNumeric: true,
      isGroup: false,
    });

    // Row 1: nest combo headers under each pivot value
    for (let _pvIdx = 0; _pvIdx < pivotValues.length; _pvIdx++) {
      for (const combo of nestCombos) {
        rows[1].push({
          label: combo.label,
          colSpan: numMeasures,
          rowSpan: 1,
          isNumeric: true,
          isGroup: false,
        });
      }
    }
    // Total group in row 1 spans down to row 2 (no nest level for totals)
    // We leave row 1 empty for the total group — the total header in row 0
    // already has rowSpan=1, so we need a placeholder in row 1 for the total
    // that spans the measure columns
    rows[1].push({
      label: '',
      colSpan: numMeasures,
      rowSpan: 1,
      isNumeric: true,
      isGroup: false,
    });

    // Row 2: measure labels under each nest combo under each pivot value + total
    const totalLeafCols = pivotValues.length * nestCombos.length * numMeasures + numMeasures;
    for (let i = 0; i < totalLeafCols; i++) {
      rows[2].push({
        label: measureLabels[i % numMeasures],
        colSpan: 1,
        rowSpan: 1,
        isNumeric: true,
        isGroup: false,
      });
    }
  } else {
    // No nest levels — 2 header rows
    // Row 0: pivot value headers spanning measures columns
    for (const pv of pivotValues) {
      rows[0].push({
        label: String(pv),
        colSpan: numMeasures,
        rowSpan: 1,
        isNumeric: true,
        isGroup: false,
      });
    }
    // Total header
    rows[0].push({
      label: t('pivot.results.grandTotal'),
      colSpan: numMeasures,
      rowSpan: 1,
      isNumeric: true,
      isGroup: false,
    });

    // Row 1: measure labels under each pivot value + total
    const totalLeafCols = (pivotValues.length + 1) * numMeasures;
    for (let i = 0; i < totalLeafCols; i++) {
      rows[1].push({
        label: measureLabels[i % numMeasures],
        colSpan: 1,
        rowSpan: 1,
        isNumeric: true,
        isGroup: false,
      });
    }
  }

  return rows;
}

/**
 * Build the ordered list of leaf (data) columns matching the header layout.
 * This determines which column name to read from each data row cell.
 */
function buildLeafColumns(
  groupColumns: PivotColumnMeta[],
  allColumns: PivotColumnMeta[],
  pivotValues: (string | number)[],
  nestCombos: { label: string; values: Record<string, string | number> }[],
  measureCount: number,
): PivotLeafColumn[] {
  const leaves: PivotLeafColumn[] = [];

  // Group columns first
  for (const col of groupColumns) {
    leaves.push({ name: col.name, meta: col });
  }

  // Pivoted aggregate columns — ordered by pivot value, then nest combo, then measure
  for (const pv of pivotValues) {
    if (nestCombos.length > 0) {
      for (const combo of nestCombos) {
        // Find columns matching this pivot value + nest combo
        const matching = allColumns.filter(
          (c) =>
            c.pivotGroup === 'pivot' &&
            String(c.pivotValue) === String(pv) &&
            c.nestValues != null &&
            Object.entries(combo.values).every(
              ([k, v]) => String(c.nestValues![k]) === String(v),
            ),
        );
        for (const col of matching) {
          leaves.push({ name: col.name, meta: col });
        }
      }
    } else {
      // No nest levels — just pivot value columns
      const matching = allColumns.filter(
        (c) => c.pivotGroup === 'pivot' && String(c.pivotValue) === String(pv),
      );
      for (const col of matching) {
        leaves.push({ name: col.name, meta: col });
      }
    }
  }

  // Grand total columns
  const totals = allColumns.filter((c) => c.pivotGroup === 'total');
  for (const col of totals) {
    leaves.push({ name: col.name, meta: col });
  }

  return leaves;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PivotResultTablePivoted({
  data,
  columns,
  config,
  numberFormat,
}: PivotResultTablePivotedProps): React.ReactElement {
  const { t, i18n } = useTypedTranslation('reports');
  const locale = resolveLocale(i18n.language);

  const groupColumns = useMemo(
    () => columns.filter((c) => c.type === 'group'),
    [columns],
  );

  const pivotValues = useMemo(() => extractPivotValues(columns), [columns]);
  const nestCombos = useMemo(() => extractNestCombinations(columns), [columns]);
  const measureLabels = useMemo(() => getMeasureLabels(config), [config]);

  const headerRows = useMemo(
    () => buildHeaderRows(groupColumns, pivotValues, nestCombos, measureLabels, t),
    [groupColumns, pivotValues, nestCombos, measureLabels, t],
  );

  const leafColumns = useMemo(
    () =>
      buildLeafColumns(
        groupColumns,
        columns,
        pivotValues,
        nestCombos,
        measureLabels.length,
      ),
    [groupColumns, columns, pivotValues, nestCombos, measureLabels.length],
  );

  return (
    <Box>
      <TableContainer overflowX="auto">
        <Table size="sm" variant="simple">
          <Thead>
            {headerRows.map((row, rowIdx) => (
              <Tr key={`header-${rowIdx}`}>
                {row.map((cell, cellIdx) => (
                  <Th
                    key={`h-${rowIdx}-${cellIdx}`}
                    colSpan={cell.colSpan}
                    rowSpan={cell.rowSpan}
                    bg={cell.isGroup ? 'gray.700' : 'gray.650'}
                    isNumeric={cell.isNumeric}
                    textAlign={cell.isNumeric && !cell.isGroup ? 'center' : undefined}
                    borderBottom="1px solid"
                    borderColor="gray.500"
                    whiteSpace="nowrap"
                    px={2}
                    py={1}
                  >
                    <Text
                      fontSize="xs"
                      color={cell.isGroup ? 'gray.300' : 'orange.200'}
                      fontWeight="bold"
                      textTransform={cell.isGroup ? 'uppercase' : 'none'}
                    >
                      {cell.label}
                    </Text>
                  </Th>
                ))}
              </Tr>
            ))}
          </Thead>
          <Tbody>
            {data.map((row, rowIdx) => (
              <Tr key={rowIdx} _hover={{ bg: 'gray.600' }}>
                {leafColumns.map((leaf) => (
                  <Td
                    key={leaf.name}
                    color="white"
                    fontSize="sm"
                    isNumeric={leaf.meta.type === 'aggregate'}
                    whiteSpace="nowrap"
                    px={2}
                  >
                    {formatCell(row[leaf.name], leaf.meta, numberFormat, locale)}
                  </Td>
                ))}
              </Tr>
            ))}
          </Tbody>
        </Table>
      </TableContainer>
    </Box>
  );
}

export default PivotResultTablePivoted;
