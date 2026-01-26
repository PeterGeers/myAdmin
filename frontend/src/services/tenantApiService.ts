/**
 * Tenant-Aware API Service
 * 
 * Extends the base API service to automatically include tenant context
 * in API calls, providing a standardized way to make tenant-scoped requests.
 */

import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete } from './apiService';

/**
 * Makes a GET request with automatic tenant context
 * @param endpoint - API endpoint (without query parameters)
 * @param additionalParams - Additional query parameters
 * @param options - Additional options for the request
 * @returns Promise resolving to the response
 */
export const tenantAwareGet = async (
  endpoint: string, 
  additionalParams?: Record<string, string>,
  options?: RequestInit
): Promise<Response> => {
  const currentTenant = localStorage.getItem('selectedTenant');
  const params = new URLSearchParams({
    administration: currentTenant || 'all',
    ...additionalParams
  });
  
  const url = `${endpoint}?${params}`;
  return authenticatedGet(url, options);
};

/**
 * Makes a POST request with automatic tenant context in body
 * @param endpoint - API endpoint
 * @param data - Request body data
 * @param options - Additional options for the request
 * @returns Promise resolving to the response
 */
export const tenantAwarePost = async (
  endpoint: string,
  data: any,
  options?: RequestInit
): Promise<Response> => {
  const currentTenant = localStorage.getItem('selectedTenant');
  
  const tenantAwareData = {
    ...data,
    administration: data.administration || currentTenant
  };
  
  return authenticatedPost(endpoint, tenantAwareData, options);
};

/**
 * Makes a PUT request with automatic tenant context in body
 * @param endpoint - API endpoint
 * @param data - Request body data
 * @param options - Additional options for the request
 * @returns Promise resolving to the response
 */
export const tenantAwarePut = async (
  endpoint: string,
  data: any,
  options?: RequestInit
): Promise<Response> => {
  const currentTenant = localStorage.getItem('selectedTenant');
  
  const tenantAwareData = {
    ...data,
    administration: data.administration || currentTenant
  };
  
  return authenticatedPut(endpoint, tenantAwareData, options);
};

/**
 * Makes a DELETE request with automatic tenant context
 * @param endpoint - API endpoint
 * @param additionalParams - Additional query parameters
 * @param options - Additional options for the request
 * @returns Promise resolving to the response
 */
export const tenantAwareDelete = async (
  endpoint: string,
  additionalParams?: Record<string, string>,
  options?: RequestInit
): Promise<Response> => {
  const currentTenant = localStorage.getItem('selectedTenant');
  const params = new URLSearchParams({
    administration: currentTenant || 'all',
    ...additionalParams
  });
  
  const url = `${endpoint}?${params}`;
  return authenticatedDelete(url, options);
};

/**
 * Utility function to get current tenant
 * @returns Current tenant or null
 */
export const getCurrentTenant = (): string | null => {
  return localStorage.getItem('selectedTenant');
};

/**
 * Utility function to validate tenant is selected
 * @throws Error if no tenant is selected
 * @returns Current tenant
 */
export const requireTenant = (): string => {
  const tenant = getCurrentTenant();
  if (!tenant) {
    throw new Error('No tenant selected. Please select a tenant first.');
  }
  return tenant;
};

/**
 * Creates tenant-scoped URL parameters
 * @param additionalParams - Additional parameters to include
 * @returns URLSearchParams with tenant context
 */
export const createTenantParams = (additionalParams?: Record<string, string>): URLSearchParams => {
  const currentTenant = getCurrentTenant();
  return new URLSearchParams({
    administration: currentTenant || 'all',
    ...additionalParams
  });
};