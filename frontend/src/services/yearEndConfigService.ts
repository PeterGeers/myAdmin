/**
 * Year-End Configuration Service
 * 
 * API service for managing year-end closure account configuration.
 * Uses "purpose" to identify which accounts serve special functions.
 */

import { authenticatedGet, authenticatedPost, authenticatedDelete } from './apiService';

export interface AvailableAccount {
  Account: string;
  AccountName: string;
  VW: string;
  current_purpose: string | null;
}

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
