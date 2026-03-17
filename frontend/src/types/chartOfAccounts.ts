/**
 * Chart of Accounts Type Definitions
 * 
 * Types for managing the chart of accounts (rekeningschema) in the FIN module.
 */

/**
 * Account record from the rekeningschema table
 */
export interface Account {
  AccountID?: number;         // Internal ID (auto-increment, not editable)
  Account: string;            // Account number (e.g., "1000", "NL12RABO...")
  AccountName: string;        // Human-readable account description
  AccountLookup: string;      // Category/lookup code for grouping
  SubParent?: string;         // Sub-parent account reference
  Parent?: string;            // Parent account reference
  VW?: string;                // VW flag (single character)
  Belastingaangifte: string;  // Tax declaration category
  administration?: string;    // Tenant name (set automatically, not editable)
  Pattern?: number;           // Legacy - kept for backward compatibility, use bank_account instead
  purpose?: string;           // Year-end closure purpose (equity_result, pl_closing, interim_opening_balance)
  bank_account?: boolean;     // Whether this is a bank account (replaces Pattern)
  iban?: string;              // IBAN for bank accounts (replaces AccountLookup for bank accounts)
  parameters?: string;        // Raw JSON parameters string
}

/**
 * Response from list accounts endpoint with pagination
 */
export interface AccountsResponse {
  success: boolean;
  accounts: Account[];
  total: number;      // Total number of accounts matching filter
  page: number;       // Current page number
  limit: number;      // Items per page
  pages: number;      // Total number of pages
}

/**
 * Response from single account endpoint
 */
export interface AccountResponse {
  success: boolean;
  account: Account;
}

/**
 * Request body for creating/updating an account
 */
export interface AccountFormData {
  account: string;
  accountName: string;
  accountLookup?: string;
  subParent?: string;
  parent?: string;
  vw?: string;
  belastingaangifte?: string;
  pattern?: boolean;
  purpose?: string;
  bank_account?: boolean;
  iban?: string;
  parameters?: string | null;
}

/**
 * Response from import endpoint
 */
export interface ImportResponse {
  success: boolean;
  imported: number;   // Number of new accounts created
  updated: number;    // Number of existing accounts updated
  total: number;      // Total accounts processed
}

/**
 * Error response from import with validation errors
 */
export interface ImportErrorResponse {
  success: false;
  errors: string[];   // Array of error messages with row numbers
  parsed: number;     // Number of rows successfully parsed
}

/**
 * Props for AccountModal component
 */
export interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  account: Account | null;    // null for create mode, Account for edit mode
  mode: 'create' | 'edit';
  onSave: (account: AccountFormData) => Promise<void>;
  onDelete?: (accountNumber: string) => Promise<void>;
}

/**
 * Query parameters for list accounts endpoint
 */
export interface AccountsQueryParams {
  search?: string;
  sort_by?: 'Account' | 'AccountName' | 'AccountLookup' | 'Belastingaangifte' | 'SubParent' | 'Parent' | 'VW';
  sort_order?: 'asc' | 'desc';
  page?: number;
  limit?: number;
}
