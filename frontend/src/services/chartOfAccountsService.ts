/**
 * Chart of Accounts API Service
 * 
 * Service layer for interacting with the Chart of Accounts backend API.
 * All methods handle authentication and tenant context automatically.
 */

import {
  Account,
  AccountsResponse,
  AccountResponse,
  AccountFormData,
  AccountsQueryParams,
  ImportResponse,
  ImportErrorResponse
} from '../types/chartOfAccounts';
import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete } from './apiService';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

/**
 * List all accounts with optional search, sorting, and pagination
 */
export const listAccounts = async (
  params?: AccountsQueryParams
): Promise<AccountsResponse> => {
  const queryParams = new URLSearchParams();
  
  if (params?.search) queryParams.append('search', params.search);
  if (params?.sort_by) queryParams.append('sort_by', params.sort_by);
  if (params?.sort_order) queryParams.append('sort_order', params.sort_order);
  if (params?.page) queryParams.append('page', params.page.toString());
  if (params?.limit) queryParams.append('limit', params.limit.toString());
  
  const endpoint = `/api/tenant-admin/chart-of-accounts${
    queryParams.toString() ? `?${queryParams.toString()}` : ''
  }`;
  
  const response = await authenticatedGet(endpoint);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to list accounts');
  }
  
  return response.json();
};

/**
 * Get a single account by account number
 */
export const getAccount = async (accountNumber: string): Promise<Account> => {
  const response = await authenticatedGet(
    `/api/tenant-admin/chart-of-accounts/${encodeURIComponent(accountNumber)}`
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to get account');
  }
  
  const data: AccountResponse = await response.json();
  return data.account;
};

/**
 * Create a new account
 */
export const createAccount = async (account: AccountFormData): Promise<Account> => {
  const response = await authenticatedPost(
    `/api/tenant-admin/chart-of-accounts`,
    account
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to create account');
  }
  
  const data: AccountResponse = await response.json();
  return data.account;
};

/**
 * Update an existing account
 */
export const updateAccount = async (
  accountNumber: string,
  account: Partial<AccountFormData>
): Promise<Account> => {
  const response = await authenticatedPut(
    `/api/tenant-admin/chart-of-accounts/${encodeURIComponent(accountNumber)}`,
    account
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to update account');
  }
  
  const data: AccountResponse = await response.json();
  return data.account;
};

/**
 * Delete an account
 */
export const deleteAccount = async (accountNumber: string): Promise<void> => {
  const response = await authenticatedDelete(
    `/api/tenant-admin/chart-of-accounts/${encodeURIComponent(accountNumber)}`
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || error.message || 'Failed to delete account');
  }
};

/**
 * Export all accounts to Excel
 */
export const exportAccounts = async (): Promise<Blob> => {
  const response = await authenticatedGet(
    `/api/tenant-admin/chart-of-accounts/export`
  );
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to export accounts');
  }
  
  return response.blob();
};

/**
 * Import accounts from Excel file
 */
export const importAccounts = async (
  file: File
): Promise<ImportResponse | ImportErrorResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  
  // Use authenticatedRequest directly for FormData (don't JSON stringify)
  const { getCurrentAuthTokens } = await import('./authService');
  const tokens = await getCurrentAuthTokens();
  
  if (!tokens?.idToken) {
    throw new Error('Authentication required');
  }
  
  const tenant = localStorage.getItem('selectedTenant');
  
  const response = await fetch(`${API_BASE_URL}/api/tenant-admin/chart-of-accounts/import`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${tokens.idToken}`,
      'X-Tenant': tenant || '',
      // Don't set Content-Type - let browser set it with boundary for multipart/form-data
    },
    body: formData
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.error || 'Failed to import accounts');
  }
  
  return data;
};
