/**
 * Year-End Configuration Service
 * 
 * API service for managing year-end closure account configuration.
 * Uses "purpose" to identify which accounts serve special functions.
 */

import { authenticatedGet, authenticatedPost, authenticatedDelete } from './apiService';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

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
  const response = await authenticatedGet(`${API_BASE_URL}/api/tenant-admin/year-end-config/validate`);
  
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
  const response = await authenticatedGet(`${API_BASE_URL}/api/tenant-admin/year-end-config/purposes`);
  
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
  const response = await authenticatedPost(`${API_BASE_URL}/api/tenant-admin/year-end-config/accounts`, {
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
    ? `${API_BASE_URL}/api/tenant-admin/year-end-config/available-accounts?vw=${vwFilter}`
    : `${API_BASE_URL}/api/tenant-admin/year-end-config/available-accounts`;
  
  const response = await authenticatedGet(url);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get available accounts');
  }
  
  const data = await response.json();
  return data.accounts;
};
