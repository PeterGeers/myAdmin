import {
  Transaction,
  LookupData,
  CreditCardAccount,
} from '../BankingProcessor';

export interface CreditCardProcessorResult {
  transactions: Transaction[];
  warnings: string[];
}

/**
 * Build a transaction description from CSV columns.
 * For EUR transactions: just the description (column 9).
 * For foreign currency: appends [CURRENCY AMOUNT] suffix.
 */
function buildDescription(columns: string[]): string {
  const description = columns[9] || '';
  const originalCurrency = columns[11]?.trim();
  const originalAmount = columns[10]?.trim();

  if (originalCurrency && originalAmount) {
    return `${description} [${originalCurrency} ${originalAmount}]`.trim();
  }
  return description.trim();
}

/**
 * Process a single credit card CSV row into Transaction(s).
 * Returns 1 transaction for EUR payments, 2 for foreign currency (main + exchange rate diff).
 *
 * @param columns - Parsed CSV columns (13 columns for Rabo BusinessCard Visa)
 * @param index - Row index for row_id assignment
 * @param lookupData - Lookup data containing credit_card_accounts and exchange_rate_account
 * @param fileName - Source file name for Ref4 tracking
 * @returns CreditCardProcessorResult with transactions and any warnings
 */
export function processCreditCardTransactions(
  columns: string[],
  index: number,
  lookupData: LookupData,
  fileName: string,
): CreditCardProcessorResult {
  const result: CreditCardProcessorResult = { transactions: [], warnings: [] };

  // 1. Validate: minimum 13 columns
  if (columns.length < 13) return result;

  // 2. Parse amount (comma decimal, round to 2 decimals)
  const amountStr = columns[8] || '0';
  const amount = Math.round(parseFloat(amountStr.replace(',', '.')) * 100) / 100;
  if (amount === 0) return result;

  // 3. Resolve credit card account via IBAN lookup
  const iban = columns[0] || '';
  const ccLookup = lookupData.credit_card_accounts.find(
    (cc: CreditCardAccount) => cc.iban === iban,
  );
  if (!ccLookup) {
    throw new Error(
      `Credit card rekening ${iban} is niet geconfigureerd voor deze tenant. Voeg deze toe in het Rekeningschema met de credit_card vlag.`,
    );
  }

  // 4. Build main transaction
  const isExpense = amount < 0;
  const absAmount = Math.abs(amount);
  const currentDate = new Date().toISOString().split('T')[0];

  const mainTransaction: Transaction = {
    row_id: index,
    TransactionNumber: `Visa ${currentDate}`,
    TransactionDate: columns[7] || '',
    TransactionDescription: buildDescription(columns),
    TransactionAmount: absAmount,
    Debet: isExpense ? '' : ccLookup.Account,
    Credit: isExpense ? ccLookup.Account : '',
    ReferenceNumber: '',
    Ref1: columns[3] || '',
    Ref2: columns[6] || '',
    Ref3: iban,
    Ref4: fileName,
    Administration: ccLookup.administration,
  };
  result.transactions.push(mainTransaction);

  // 5. Check for foreign currency → exchange rate difference
  const originalAmount = columns[10]
    ? parseFloat(columns[10].replace(',', '.'))
    : 0;
  const exchangeRate = columns[12]
    ? parseFloat(columns[12].replace(',', '.'))
    : 0;

  if (originalAmount !== 0 && exchangeRate > 0 && columns[11]?.trim()) {
    const calculatedEurAmount =
      Math.round((originalAmount / exchangeRate) * 100) / 100;
    const exchangeRateDiff =
      Math.round((absAmount - Math.abs(calculatedEurAmount)) * 100) / 100;

    if (Math.abs(exchangeRateDiff) > 0.005) {
      if (!lookupData.exchange_rate_account) {
        result.warnings.push(
          `Koersverschillenrekening niet geconfigureerd. Koersverschil van €${exchangeRateDiff.toFixed(2)} ` +
            `voor transactie ${columns[6]} wordt overgeslagen.`,
        );
      } else {
        const isGain = exchangeRateDiff > 0;
        const absExchangeDiff = Math.abs(exchangeRateDiff);

        const exchangeTransaction: Transaction = {
          row_id: index + 5000,
          TransactionNumber: `Visa Koers ${currentDate}`,
          TransactionDate: columns[7] || '',
          TransactionDescription: `Koersverschil ${columns[11]} ${columns[10]} @ ${columns[12]}`,
          TransactionAmount: absExchangeDiff,
          Debet: isGain ? '' : lookupData.exchange_rate_account,
          Credit: isGain ? lookupData.exchange_rate_account : '',
          ReferenceNumber: '',
          Ref1: columns[3] || '',
          Ref2: `${columns[6]}_FX`,
          Ref3: iban,
          Ref4: fileName,
          Administration: ccLookup.administration,
        };
        result.transactions.push(exchangeTransaction);
      }
    }
  }

  return result;
}
