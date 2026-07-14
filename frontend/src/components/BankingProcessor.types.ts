/**
 * Shared types for the Banking Processor feature.
 *
 * These types are used across BankingProcessor, its sub-components,
 * and the useBankingProcessor hook.
 */

export interface Transaction {
  ID?: number;
  row_id: number;
  TransactionNumber: string;
  TransactionDate: string;
  TransactionDescription: string;
  TransactionAmount: number;
  Debet: string;
  Credit: string;
  ReferenceNumber: string;
  Ref1: string;
  Ref2: string;
  Ref3: string;
  Ref4: string;
  Administration: string;
  pattern_filled?: boolean;
}

export interface CreditCardAccount {
  iban: string;
  Account: string;
  card_number: string;
  administration: string;
}

export interface LookupData {
  accounts: string[];
  descriptions: string[];
  bank_accounts: Array<{ rekeningNummer: string; Account: string; administration: string }>;
  credit_card_accounts: CreditCardAccount[];
  exchange_rate_account: string | null;
}

export interface BankingBalance {
  Reknum: string;
  Administration: string;
  calculated_balance: number;
  account_name: string;
  last_transaction_date: string;
  last_transaction_description: string;
  last_transaction_amount: number;
  last_transactions: Array<{
    TransactionDate: string;
    TransactionDescription: string;
    TransactionAmount: number;
    Debet: string;
    Credit: string;
    Ref2: string;
    Ref3: string;
  }>;
}
