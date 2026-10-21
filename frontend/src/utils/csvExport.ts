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

/**
 * A single CSV cell value. CSV source rows carry arbitrary serializable
 * values (strings, numbers, booleans, null/undefined, …), so this is `unknown`
 * rather than `any`: callers must format/coerce (via a {@link CellFormatter}
 * or the built-in default) before the value is written.
 */
export type CellValue = unknown;

/** Optional formatter applied to each cell value before CSV encoding. */
export type CellFormatter = (value: CellValue, columnIndex: number) => string;

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
  rows: CellValue[][],
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
  data: Record<string, CellValue>[],
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

/**
 * Sanitize a single export-name part (a tenant or pivot display name) so it is
 * safe to embed in a download/attachment filename.
 *
 * Strips filesystem-hostile characters — path separators (`/`, `\`) and ASCII
 * control characters — and collapses any run of whitespace to a single space,
 * trimming the edges. The result never contains a path separator, a control
 * char, or leading/trailing whitespace, so it cannot escape a directory or
 * produce a malformed filename.
 *
 * @param part - A raw tenant or pivot display name (may be empty).
 * @returns The sanitized part (possibly an empty string).
 */
export function sanitize(part: string): string {
  return (part ?? '')
    // Drop path separators and ASCII control chars, but KEEP tab (\u0009),
    // newline (\u000a) and CR (\u000d) so the whitespace-collapse step below
    // can turn them into a single space rather than deleting them outright.
    // eslint-disable-next-line no-control-regex
    .replace(/[/\\\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '')
    // Collapse any whitespace run (spaces, tabs, newlines, unicode spaces) to one space.
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Build the shared pivot-export filename from a tenant name and pivot name.
 *
 * This is the single frontend naming rule mirrored on the SAM worker plane so a
 * downloaded CSV and an emailed attachment for the same tenant+pivot carry the
 * identical name:
 *
 *   exportFileName(tenantName, pivotName)
 *     = sanitize(tenantName) + "-" + sanitize(pivotName) + ".csv"
 *
 * The result is deterministic and always ends in `.csv` — it never falls back
 * to the old fixed `members.csv`.
 *
 * @param tenantName - The active tenant's display name.
 * @param pivotName  - The selected pivot's display name.
 * @returns The `{Tenant_Name}-{Pivot_Name}.csv` filename.
 */
export function exportFileName(tenantName: string, pivotName: string): string {
  return `${sanitize(tenantName)}-${sanitize(pivotName)}.csv`;
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
function defaultFormat(value: CellValue): string {
  if (value == null) return '';
  if (typeof value === 'number') return String(value);
  return String(value);
}
