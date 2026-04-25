/**
 * CSV generation and download utilities.
 *
 * Reusable CSV export extracted from MutatiesReport and other report components.
 * Handles proper escaping of commas, quotes, and newlines in cell values.
 *
 * Requirements: 7.2, 7.3
 * Reference: .kiro/specs/dynamic-pivot-views/design.md §7 CSV Export
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Optional formatter applied to each cell value before CSV encoding. */
export type CellFormatter = (value: any, columnIndex: number) => string;

/** Options for CSV generation. */
export interface GenerateCsvOptions {
  /** Delimiter between fields. Defaults to ','. */
  delimiter?: string;
  /** Line separator. Defaults to '\n'. */
  lineSeparator?: string;
  /** Optional formatter applied to each data cell (not headers). */
  formatter?: CellFormatter;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Generate a CSV string from column headers and data rows.
 *
 * @param headers - Array of column header strings.
 * @param rows    - Array of data rows. Each row is an array of cell values.
 * @param options - Optional configuration (delimiter, line separator, formatter).
 * @returns CSV string ready for download.
 *
 * @example
 * const csv = generateCsv(
 *   ['Name', 'Amount'],
 *   [['Airbnb', 12345.67], ['Booking.com', 8901.23]],
 * );
 */
export function generateCsv(
  headers: string[],
  rows: any[][],
  options?: GenerateCsvOptions,
): string {
  const delimiter = options?.delimiter ?? ',';
  const lineSeparator = options?.lineSeparator ?? '\n';
  const formatter = options?.formatter;

  const lines: string[] = [];

  // Header row
  lines.push(headers.map((h) => escapeCsvField(h, delimiter)).join(delimiter));

  // Data rows
  for (const row of rows) {
    const cells = row.map((cell, colIndex) => {
      const value = formatter ? formatter(cell, colIndex) : defaultFormat(cell);
      return escapeCsvField(value, delimiter);
    });
    lines.push(cells.join(delimiter));
  }

  return lines.join(lineSeparator);
}

/**
 * Generate a CSV string from an array of objects using column metadata.
 *
 * Convenience wrapper that extracts values from objects by column key.
 *
 * @param columns   - Array of { key, header } describing each column.
 * @param data      - Array of row objects.
 * @param options   - Optional configuration.
 * @returns CSV string.
 *
 * @example
 * const csv = generateCsvFromObjects(
 *   [{ key: 'channel', header: 'Channel' }, { key: 'SUM_Amount', header: 'Total' }],
 *   [{ channel: 'Airbnb', SUM_Amount: 12345.67 }],
 * );
 */
export function generateCsvFromObjects(
  columns: { key: string; header: string }[],
  data: Record<string, any>[],
  options?: GenerateCsvOptions,
): string {
  const headers = columns.map((c) => c.header);
  const rows = data.map((row) => columns.map((c) => row[c.key]));
  return generateCsv(headers, rows, options);
}

/**
 * Trigger a CSV file download in the browser.
 *
 * Uses the Blob + URL.createObjectURL + anchor click pattern
 * consistent with MutatiesReport.tsx.
 *
 * @param csvContent - The CSV string to download.
 * @param filename   - Download filename (should end with .csv).
 */
export function downloadCsv(csvContent: string, filename: string): void {
  // Add BOM for Excel UTF-8 compatibility
  const bom = '\uFEFF';
  const blob = new Blob([bom + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();

  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Escape a single CSV field value.
 *
 * RFC 4180 rules:
 * - If the field contains the delimiter, a double quote, or a newline,
 *   wrap it in double quotes and escape internal double quotes by doubling them.
 */
function escapeCsvField(value: string, delimiter: string): string {
  if (
    value.includes(delimiter) ||
    value.includes('"') ||
    value.includes('\n') ||
    value.includes('\r')
  ) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/**
 * Default formatting for cell values.
 * Converts null/undefined to empty string, everything else to string.
 */
function defaultFormat(value: any): string {
  if (value == null) return '';
  if (typeof value === 'number') return String(value);
  return String(value);
}
