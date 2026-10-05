/**
 * Pure CSV helpers for the Transactions table export (Part a).
 *
 * Co-located with BankingMutatiesTab so the component stays lean and the unit
 * tests import pure functions without touching Chakra/React. All escaping and
 * UTF-8 BOM encoding is delegated to the shared csvExport utility.
 *
 * Reads RAW underlying field values only (no locale formatting).
 *
 * Reference: .kiro/specs/myBacklog/transactions-export/design.md §Components (Part a)
 * Requirements: 2.1, 2.4, 3.1, 3.3, 4.1
 */

import { generateCsvFromObjects } from '../../utils/csvExport';

/** Ordered column config for the transactions table export. */
export interface CsvColumn {
  key: string;
  header: string;
}

/**
 * Build the ordered 8-column config for the transactions table export.
 *
 * Headers are resolved by the caller via i18n and passed in, so the pure
 * builder stays translation-agnostic and testable. Column order and field
 * mapping are the single source of the export contract.
 */
export function transactionsCsvColumns(headers: {
  trxNumber: string;
  date: string;
  description: string;
  amount: string;
  debit: string;
  credit: string;
  reference: string;
  administration: string;
}): CsvColumn[] {
  return [
    { key: 'TransactionNumber', header: headers.trxNumber },
    { key: 'TransactionDate', header: headers.date },
    { key: 'TransactionDescription', header: headers.description },
    { key: 'TransactionAmount', header: headers.amount },
    { key: 'Debet', header: headers.debit },
    { key: 'Credit', header: headers.credit },
    { key: 'ReferenceNumber', header: headers.reference },
    { key: 'Administration', header: headers.administration },
  ];
}

/**
 * Pure CSV builder. Reads RAW field values (no locale formatting) in input
 * order, for EVERY row (no display-limit slice). RFC-4180 escaping is handled
 * by generateCsvFromObjects.
 */
export function buildTransactionsCsv(
  columns: CsvColumn[],
  rows: Record<string, any>[],
): string {
  return generateCsvFromObjects(columns, rows);
}

/** `transactions-YYYY-MM-DD.csv` using the current date. */
export function transactionsCsvFilename(now: Date = new Date()): string {
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  return `transactions-${yyyy}-${mm}-${dd}.csv`;
}
