/**
 * PivotExportMenu Component
 *
 * Provides CSV export for pivot results with two modes:
 * - Pivot result export: aggregated data as displayed, formatted per current number format
 * - Underlying dataset export: raw rows before aggregation, full-precision numbers
 *
 * Uses generateCsvFromObjects() and downloadCsv() from csvExport.ts.
 * Follows the Blob + URL.createObjectURL + anchor click pattern from MutatiesReport.tsx.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §7 CSV Export
 */

import React, { useCallback, useState } from 'react';
import {
  Button,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Spinner,
  useToast,
} from '@chakra-ui/react';
import { ChevronDownIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { generateCsv, downloadCsv } from '../../utils/csvExport';
import { formatPivotNumber, resolveLocale } from '../../utils/pivotFormatting';
import { exportUnderlying } from '../../services/pivotService';
import type { NumberFormat, PivotColumnMeta, PivotConfig } from '../../types/pivot';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PivotExportMenuProps {
  /** Result rows from the pivot query */
  data: Record<string, any>[];
  /** Column metadata describing each column in the result */
  columns: PivotColumnMeta[];
  /** The pivot configuration that produced these results */
  config: PivotConfig;
  /** Current number format for pivot result export */
  numberFormat: NumberFormat;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a filename for the CSV download.
 * Pattern: pivot-{dataSource}-{type}-{timestamp}.csv
 */
function buildFilename(dataSource: string, type: 'result' | 'underlying'): string {
  const timestamp = new Date().toISOString().slice(0, 10);
  const safeName = dataSource.replace(/[^a-zA-Z0-9_-]/g, '_');
  return `pivot-${safeName}-${type}-${timestamp}.csv`;
}

/**
 * Create a cell formatter that applies pivot number formatting to aggregate
 * columns and leaves group columns as-is.
 */
function createPivotFormatter(
  columns: PivotColumnMeta[],
  numberFormat: NumberFormat,
  locale: string,
) {
  return (value: any, columnIndex: number): string => {
    if (value == null) return '';

    const col = columns[columnIndex];
    if (!col || col.type === 'group') {
      return String(value);
    }

    // Aggregate column: apply number formatting
    const numValue = typeof value === 'number' ? value : Number(value);
    if (Number.isNaN(numValue)) return String(value);

    return formatPivotNumber(numValue, numberFormat, locale);
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PivotExportMenu({
  data,
  columns,
  config,
  numberFormat,
}: PivotExportMenuProps): React.ReactElement {
  const { t, i18n } = useTypedTranslation('reports');
  const locale = resolveLocale(i18n.language);
  const toast = useToast();

  const [isExportingUnderlying, setIsExportingUnderlying] = useState(false);

  const hasData = data.length > 0 && columns.length > 0;

  // -----------------------------------------------------------------------
  // Pivot result export
  // -----------------------------------------------------------------------
  const handleExportPivotResult = useCallback(() => {
    if (!hasData) return;

    try {
      const headers = columns.map((col) => col.name);
      const formatter = createPivotFormatter(columns, numberFormat, locale);

      const rows = data.map((row) =>
        columns.map((col) => row[col.name]),
      );

      const csv = generateCsv(headers, rows, { formatter });
      downloadCsv(csv, buildFilename(config.dataSource, 'result'));
    } catch {
      toast({
        title: t('pivot.errors.exportFailed'),
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
    }
  }, [hasData, columns, data, numberFormat, locale, config.dataSource, toast, t]);

  // -----------------------------------------------------------------------
  // Underlying dataset export
  // -----------------------------------------------------------------------
  const handleExportUnderlying = useCallback(async () => {
    if (!hasData) return;

    setIsExportingUnderlying(true);
    try {
      const response = await exportUnderlying(config);

      if (!response.success || !response.data || response.data.length === 0) {
        toast({
          title: t('pivot.results.noData'),
          status: 'info',
          duration: 3000,
          isClosable: true,
        });
        return;
      }

      // Use all keys from the first row as column headers
      const underlyingColumns = Object.keys(response.data[0]);
      const headers = underlyingColumns;
      const rows = response.data.map((row) =>
        underlyingColumns.map((key) => row[key]),
      );

      // Underlying export uses full-precision numbers (no formatting)
      const csv = generateCsv(headers, rows);
      downloadCsv(csv, buildFilename(config.dataSource, 'underlying'));
    } catch {
      toast({
        title: t('pivot.errors.exportFailed'),
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
    } finally {
      setIsExportingUnderlying(false);
    }
  }, [hasData, config, toast, t]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <Menu>
      <MenuButton
        as={Button}
        size="xs"
        rightIcon={isExportingUnderlying ? <Spinner size="xs" /> : <ChevronDownIcon />}
        variant="outline"
        color="white"
        isDisabled={!hasData || isExportingUnderlying}
        data-testid="pivot-export-menu"
      >
        {t('pivot.actions.export')}
      </MenuButton>
      <MenuList bg="gray.700" borderColor="gray.600">
        <MenuItem
          bg="gray.700"
          _hover={{ bg: 'gray.600' }}
          color="white"
          fontSize="sm"
          onClick={handleExportPivotResult}
          data-testid="export-pivot-result"
        >
          {t('pivot.actions.exportPivot')}
        </MenuItem>
        <MenuItem
          bg="gray.700"
          _hover={{ bg: 'gray.600' }}
          color="white"
          fontSize="sm"
          onClick={handleExportUnderlying}
          isDisabled={isExportingUnderlying}
          data-testid="export-underlying-data"
        >
          {isExportingUnderlying
            ? t('export.exporting')
            : t('pivot.actions.exportUnderlying')}
        </MenuItem>
      </MenuList>
    </Menu>
  );
}

export default PivotExportMenu;
