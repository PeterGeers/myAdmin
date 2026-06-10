/**
 * BankingProcessor Utility Functions
 *
 * Stateless utility functions for CSV parsing and transaction processing.
 * These do not depend on React state/hooks and are exported for use by
 * BankingFileUpload and other components.
 */

import type { Transaction, LookupData } from './BankingProcessor.types';

// ---------------------------------------------------------------------------
// CSV Parsing
// ---------------------------------------------------------------------------

export const parseCSVRow = (row: string): string[] => {
  const columns: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < row.length; i++) {
    const char = row[i];
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      columns.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  columns.push(current.trim());
  return columns;
};

// ---------------------------------------------------------------------------
// Revolut Transaction Processing
// ---------------------------------------------------------------------------

export const processRevolutTransaction = (columns: string[], index: number, bankLookup: any, fileName: string, header?: string[]): Transaction[] => {
  if (!bankLookup) {
    throw new Error('Bank account not configured for Revolut. Please add it in Chart of Accounts with the bank_account flag.');
  }

  const transactions: Transaction[] = [];

  // Helper to find column index by name (supports Dutch and English)
  const getColIdx = (names: string[], fallback: number): number => {
    if (!header) return fallback;
    const idx = header.findIndex(h => names.some(n => h.toLowerCase().includes(n.toLowerCase())));
    return idx >= 0 ? idx : fallback;
  };

  // Map columns by name with fallback to position
  const startdatumIdx = getColIdx(['startdatum', 'started date', 'started'], 2);
  const datumVoltooidIdx = getColIdx(['datum voltooid', 'completed date', 'completed'], 3);
  const beschrijvingIdx = getColIdx(['beschrijving', 'description'], 4);
  const bedragIdx = getColIdx(['bedrag', 'amount'], 5);
  const kostenIdx = getColIdx(['kosten', 'fee'], 6);
  const statusIdx = getColIdx(['status', 'state'], 8);
  const saldoIdx = getColIdx(['saldo', 'balance'], 9);

  const startdatum = columns[startdatumIdx] || '';
  const datumVoltooidRaw = columns[datumVoltooidIdx] || '';
  const beschrijving = columns[beschrijvingIdx] || '';
  const bedrag = columns[bedragIdx] || '0';
  const kosten = columns[kostenIdx] || '0';
  const status = columns[statusIdx] || '';
  const saldoRawValue = columns[saldoIdx] || '';
  const saldoRaw = columns[saldoIdx] || '0';
  const saldo = parseFloat(saldoRaw.replace(',', '.')).toFixed(2);

  // Language-independent filter: skip non-completed transactions
  if (!datumVoltooidRaw.trim() || !saldoRawValue.trim()) return transactions;

  if (status.includes('REVERTED') || status.includes('PENDING')) return transactions;

  const amount = parseFloat(bedrag.replace(',', '.'));
  const fee = parseFloat(kosten.replace(',', '.'));
  const balance = parseFloat(saldo.replace(',', '.'));

  if (amount === 0 && fee === 0) return transactions;

  const currentDate = new Date().toISOString().split('T')[0];

  // Main transaction
  if (amount !== 0) {
    const isNegative = amount < 0;
    const absAmount = Math.abs(amount);
    const ref2 = [beschrijving, saldo, datumVoltooidRaw].join('_');

    transactions.push({
      row_id: index,
      TransactionNumber: `Revolut ${currentDate}`,
      TransactionDate: startdatum.split(' ')[0] || '',
      TransactionDescription: beschrijving,
      TransactionAmount: absAmount,
      Debet: isNegative ? '' : bankLookup.Account,
      Credit: isNegative ? bankLookup.Account : '',
      ReferenceNumber: '',
      Ref1: bankLookup.rekeningNummer,
      Ref2: ref2,
      Ref3: balance.toString(),
      Ref4: fileName,
      Administration: bankLookup.administration,
    });
  }

  // Fee transaction
  if (fee > 0) {
    const feeRef2 = ['Revo Charges', saldo, datumVoltooidRaw].join('_');

    transactions.push({
      row_id: index + 1000,
      TransactionNumber: `Revolut ${currentDate}`,
      TransactionDate: startdatum.split(' ')[0] || '',
      TransactionDescription: 'Revo Charges',
      TransactionAmount: fee,
      Debet: '',
      Credit: bankLookup.Account,
      ReferenceNumber: '',
      Ref1: bankLookup.rekeningNummer,
      Ref2: feeRef2,
      Ref3: balance.toString(),
      Ref4: fileName,
      Administration: bankLookup.administration,
    });
  }

  return transactions;
};

// ---------------------------------------------------------------------------
// Rabobank Transaction Processing
// ---------------------------------------------------------------------------

export const processRabobankTransaction = (columns: string[], index: number, lookupData: LookupData, fileName: string): Transaction | null => {
  if (columns.length < 20) return null;

  const amountStr = columns[6] || '0';
  const isNegative = amountStr.startsWith('-');
  const amount = parseFloat(amountStr.replace(/[+-]/g, '').replace(',', '.'));

  if (amount === 0) return null;

  const iban = columns[0] || '';
  const bankLookup = lookupData.bank_accounts.find(ba => ba.rekeningNummer === iban);
  if (!bankLookup) {
    throw new Error(`Bank account ${iban} is not configured for this tenant. Please add it in Chart of Accounts with the bank_account flag.`);
  }
  const bankCode = iban.includes('RABO') ? 'RABO' : 'BANK';
  const currentDate = new Date().toISOString().split('T')[0];

  const description = [columns[9], columns[19], columns[20], columns[21]]
    .filter(field => field?.trim() && field.trim() !== 'NA' && field.trim() !== '' && field.trim() !== 'nan')
    .join(' ')
    .replace(/\s+/g, ' ')
    .replace(/Google Pay/g, 'GPay')
    .trim();

  return {
    row_id: index,
    TransactionNumber: `${bankCode} ${currentDate}`,
    TransactionDate: columns[4] || '',
    TransactionDescription: description,
    TransactionAmount: amount,
    Debet: isNegative ? '' : bankLookup.Account,
    Credit: isNegative ? bankLookup.Account : '',
    ReferenceNumber: '',
    Ref1: columns[0] || '',
    Ref2: parseInt(columns[3] || '0').toString(),
    Ref3: columns[7] || '',
    Ref4: fileName,
    Administration: bankLookup.administration,
  };
};
