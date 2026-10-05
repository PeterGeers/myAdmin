/**
 * Pure CSV mapping helpers for the FIN report transactions export.
 *
 * Extracted from MutatiesReport.tsx so the row->cells contract can be unit
 * tested without rendering a React tree. These helpers are the single source
 * of the report export's column order and the Debit=Reknum (account code) /
 * Credit=AccountName (account name) contract.
 *
 * RAW values only — no locale formatting (no formatCurrency / formatDate).
 * RFC-4180 escaping and the UTF-8 BOM are handled by the shared csvExport util.
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 6.2, 8.1
 * Reference: .kiro/specs/myBacklog/transactions-export/design.md
 */

/** Shape of a report transaction row consumed by the CSV mapping. */
export interface MutatiesCsvRow {
  TransactionDate: string;
  ReferenceNumber: string;
  TransactionDescription: string;
  Amount: number;
  Reknum: string; // Account code  -> Debit
  AccountName: string; // Account name  -> Credit
  Administration: string;
}

/** Fixed header order: Date, Reference, Description, Amount, Debit, Credit, Administration. */
export function mutatiesCsvHeaders(labels: {
  date: string;
  reference: string;
  description: string;
  amount: string;
  debit: string;
  credit: string;
  administration: string;
}): string[] {
  return [
    labels.date,
    labels.reference,
    labels.description,
    labels.amount,
    labels.debit,
    labels.credit,
    labels.administration,
  ];
}

/**
 * Pure row -> cells mapping. RAW values only. Column order matches the headers.
 * Debit = Reknum (account code); Credit = AccountName (account name).
 */
export function mapMutatiesRow(row: MutatiesCsvRow): (string | number)[] {
  return [
    row.TransactionDate,
    row.ReferenceNumber,
    row.TransactionDescription,
    row.Amount,
    row.Reknum, // Debit  = account code
    row.AccountName, // Credit = account name
    row.Administration,
  ];
}
