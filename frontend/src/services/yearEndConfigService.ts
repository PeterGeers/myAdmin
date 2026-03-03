/**
 * Year-End Configuration Service
 * 
 * API service for managing year-end closure account configuration.
 * Uses "purpose" to identify which accounts serve special functions.
 */

import { authenticatedGet, authenticatedPost, authenticatedDelete } from './apiService';

export interface YearEndPurpose {
  account_code: string;
  account_name: string;
  vw: string;
}

export interface RequiredPurpose {
  description: string;
  expected_vw: string;
  example: string;
}

export interface ConfigurationValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  configured_purposes: Record<string, YearEndPurpose>;
}

export interface ConfiguredPurposesResponse {
  purposes: Record<string, YearEndPurpose>;
  required_purposes: Record<string, RequiredPurpose>;
}

export interface AvailableAccount {
  Account: string;
  AccountName: string;
  VW: string;
  current_purpose: string | null;
}

/**
 * Validate year-end closure configuration
 */
export const validateConfiguration = async (): Promise<ConfigurationValidation> => {
  const response = await authenticatedGet('/api/tenant-admin/year-end-config/validate');
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to validate configuration');
  }
  
  return response.json();
};

/**
 * Get all configured account purposes
 */
export const getConfiguredPurposes = async (): Promise<ConfiguredPurposesResponse> => {
  const response = await authenticatedGet('/api/tenant-admin/year-end-config/purposes');
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get configured purposes');
  }
  
  return response.json();
};

/**
 * Set purpose for an account
 */
export const setAccountPurpose = async (accountCode: string, purpose: string | null): Promise<void> => {
  const response = await authenticatedPost('/api/tenant-admin/year-end-config/accounts', {
    account_code: accountCode,
    purpose: purpose
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to set account purpose');
  }
};

/**
 * Get available accounts for purpose assignment
 */
export const getAvailableAccounts = async (vwFilter?: 'Y' | 'N'): Promise<AvailableAccount[]> => {
  const url = vwFilter 
    ? `/api/tenant-admin/year-end-config/available-accounts?vw=${vwFilter}`
    : '/api/tenant-admin/year-end-config/available-accounts';
  
  const response = await authenticatedGet(url);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get available accounts');
  }
  
  const data = await response.json();
  return data.accounts;
};


// VAT Netting Types
export interface VATAccount {
  Account: string;
  AccountName: string;
  VW: string;
  vat_netting: boolean;
  vat_primary: string | null;
}

export interface VATNettingConfig {
  vat_accounts: VATAccount[];
  primary_account: string | null;
}

export interface VATNettingRequest {
  vat_accounts: string[];
  primary_account: string;
}

/**
 * Get VAT netting configuration
 */
export const getVATNettingConfig = async (): Promise<VATNettingConfig> => {
  const response = await authenticatedGet('/api/year-end-config/vat-netting');
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get VAT netting configuration');
  }
  
  return await response.json();
};

/**
 * Configure VAT netting
 */
export const configureVATNetting = async (config: VATNettingRequest): Promise<void> => {
  const response = await authenticatedPost(
    '/api/year-end-config/vat-netting',
    config
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to configure VAT netting');
  }
};

/**
 * Remove VAT netting configuration
 */
export const removeVATNetting = async (): Promise<void> => {
  const response = await authenticatedDelete('/api/year-end-config/vat-netting');
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to remove VAT netting configuration');
  }
};

/**
 * Get balance sheet accounts (for VAT netting selection)
 */
export const getBalanceSheetAccounts = async (): Promise<AvailableAccount[]> => {
  const response = await authenticatedGet('/api/year-end-config/balance-sheet-accounts');
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get balance sheet accounts');
  }
  
  const data = await response.json();
  return data.accounts || [];
};
