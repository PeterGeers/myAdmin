/**
 * Authenticated API Service
 * 
 * This service provides utilities for making authenticated API calls
 * with automatic JWT token injection and token refresh handling.
 */

import { getCurrentAuthTokens } from './authService';
import { API_BASE_URL } from '../config/api';

/**
 * Request options for authenticated API calls
 */
export interface AuthenticatedRequestOptions extends RequestInit {
  skipAuth?: boolean; // Skip authentication for public endpoints
  onUploadProgress?: (progressEvent: any) => void; // For file upload progress
  tenant?: string; // Optional tenant override (defaults to current tenant from context)
}

/**
 * Get current tenant from localStorage
 * This is used by API service to include tenant in requests
 * 
 * @returns Current tenant or null if not set
 */
function getCurrentTenant(): string | null {
  try {
    return localStorage.getItem('selectedTenant');
  } catch {
    return null;
  }
}

/**
 * Make an authenticated API request with JWT token
 * 
 * @param endpoint - API endpoint (e.g., '/api/invoices')
 * @param options - Fetch options with optional skipAuth flag
 * @returns Fetch response
 * @throws Error if authentication fails or request fails
 */
export async function authenticatedRequest(
  endpoint: string,
  options: AuthenticatedRequestOptions = {}
): Promise<Response> {
  const { skipAuth = false, tenant, ...fetchOptions } = options;

  // Build full URL
  const url = `${API_BASE_URL}${endpoint}`;

  // Get authentication tokens if not skipping auth
  let headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...fetchOptions.headers,
  };

  if (!skipAuth) {
    try {
      const tokens = await getCurrentAuthTokens();
      
      if (!tokens?.idToken) {
        throw new Error('No authentication token available');
      }

      // Add Authorization header with JWT token
      headers = {
        ...headers,
        Authorization: `Bearer ${tokens.idToken}`,
      };

      // Add X-Tenant header if tenant is available
      const currentTenant = tenant || getCurrentTenant();
      if (currentTenant) {
        headers = {
          ...headers,
          'X-Tenant': currentTenant,
        };
      }
    } catch (error) {
      console.error('Failed to get authentication tokens:', error);
      throw new Error('Authentication required');
    }
  }

  // Make the request
  try {
    const response = await fetch(url, {
      ...fetchOptions,
      headers,
      credentials: 'include', // Include credentials for cross-origin requests
    });

    // Handle 401 Unauthorized - token might be expired
    if (response.status === 401 && !skipAuth) {
      console.warn('Received 401 Unauthorized - token may be expired');
      
      // Try to refresh tokens and retry once
      try {
        const tokens = await getCurrentAuthTokens();
        if (tokens?.idToken) {
          headers = {
            ...headers,
            Authorization: `Bearer ${tokens.idToken}`,
          };

          // Re-add tenant header
          const currentTenant = tenant || getCurrentTenant();
          if (currentTenant) {
            headers = {
              ...headers,
              'X-Tenant': currentTenant,
            };
          }
          
          // Retry the request with refreshed token
          return await fetch(url, {
            ...fetchOptions,
            headers,
            credentials: 'include', // Include credentials for cross-origin requests
          });
        }
      } catch (refreshError) {
        console.error('Failed to refresh token:', refreshError);
        throw new Error('Session expired - please log in again');
      }
    }

    return response;
  } catch (error) {
    console.error('API request failed:', error);
    throw error;
  }
}

/**
 * Make an authenticated GET request
 * 
 * @param endpoint - API endpoint
 * @param options - Request options
 * @returns Fetch response
 */
export async function authenticatedGet(
  endpoint: string,
  options: AuthenticatedRequestOptions = {}
): Promise<Response> {
  return authenticatedRequest(endpoint, {
    ...options,
    method: 'GET',
  });
}

/**
 * Make an authenticated POST request
 * 
 * @param endpoint - API endpoint
 * @param body - Request body (will be JSON stringified)
 * @param options - Request options
 * @returns Fetch response
 */
export async function authenticatedPost(
  endpoint: string,
  body?: any,
  options: AuthenticatedRequestOptions = {}
): Promise<Response> {
  return authenticatedRequest(endpoint, {
    ...options,
    method: 'POST',
    body: body ? JSON.stringify(body) : undefined,
  });
}

/**
 * Make an authenticated PUT request
 * 
 * @param endpoint - API endpoint
 * @param body - Request body (will be JSON stringified)
 * @param options - Request options
 * @returns Fetch response
 */
export async function authenticatedPut(
  endpoint: string,
  body?: any,
  options: AuthenticatedRequestOptions = {}
): Promise<Response> {
  return authenticatedRequest(endpoint, {
    ...options,
    method: 'PUT',
    body: body ? JSON.stringify(body) : undefined,
  });
}

/**
 * Make an authenticated DELETE request
 * 
 * @param endpoint - API endpoint
 * @param options - Request options
 * @returns Fetch response
 */
export async function authenticatedDelete(
  endpoint: string,
  options: AuthenticatedRequestOptions = {}
): Promise<Response> {
  return authenticatedRequest(endpoint, {
    ...options,
    method: 'DELETE',
  });
}

/**
 * Make an authenticated request with FormData (for file uploads)
 * 
 * @param endpoint - API endpoint
 * @param formData - FormData object
 * @param options - Request options with optional onUploadProgress
 * @returns Fetch response
 */
export async function authenticatedFormData(
  endpoint: string,
  formData: FormData,
  options: AuthenticatedRequestOptions = {}
): Promise<Response> {
  const { skipAuth = false, onUploadProgress, tenant, ...fetchOptions } = options;

  // Build full URL
  const url = `${API_BASE_URL}${endpoint}`;

  // Get authentication tokens if not skipping auth
  let headers: HeadersInit = {
    ...fetchOptions.headers,
  };

  // Don't set Content-Type for FormData - browser will set it with boundary
  if (headers && 'Content-Type' in headers) {
    delete (headers as any)['Content-Type'];
  }

  if (!skipAuth) {
    try {
      const tokens = await getCurrentAuthTokens();
      
      if (!tokens?.idToken) {
        throw new Error('No authentication token available');
      }

      headers = {
        ...headers,
        Authorization: `Bearer ${tokens.idToken}`,
      };

      // Add X-Tenant header if tenant is available
      const currentTenant = tenant || getCurrentTenant();
      if (currentTenant) {
        headers = {
          ...headers,
          'X-Tenant': currentTenant,
        };
      }
    } catch (error) {
      console.error('Failed to get authentication tokens:', error);
      throw new Error('Authentication required');
    }
  }

  // If onUploadProgress is provided, use axios for upload progress tracking
  if (onUploadProgress) {
    const axios = (await import('axios')).default;
    
    try {
      const axiosResponse = await axios.post(url, formData, {
        headers: headers as Record<string, string>,
        onUploadProgress,
      });
      
      // Convert axios response to fetch Response format
      return new Response(JSON.stringify(axiosResponse.data), {
        status: axiosResponse.status,
        statusText: axiosResponse.statusText,
        headers: new Headers(axiosResponse.headers as Record<string, string>),
      });
    } catch (error: any) {
      // Convert axios error to fetch error
      if (error.response) {
        return new Response(JSON.stringify(error.response.data), {
          status: error.response.status,
          statusText: error.response.statusText,
          headers: new Headers(error.response.headers as Record<string, string>),
        });
      }
      throw error;
    }
  }

  // Make the request using fetch (no progress tracking)
  return fetch(url, {
    ...fetchOptions,
    method: fetchOptions.method || 'POST',
    headers,
    body: formData,
    credentials: 'include', // Include credentials for cross-origin requests
  });
}

/**
 * Helper to build endpoint with query parameters (without base URL)
 * Use this with authenticatedGet/Post/etc which will add the base URL
 * 
 * @param endpoint - API endpoint
 * @param params - URLSearchParams or object with query parameters
 * @returns Endpoint with query string (no base URL)
 */
export function buildEndpoint(endpoint: string, params?: URLSearchParams | Record<string, string>): string {
  if (!params) {
    return endpoint;
  }

  const searchParams = params instanceof URLSearchParams 
    ? params 
    : new URLSearchParams(params);

  return `${endpoint}?${searchParams.toString()}`;
}

/**
 * Helper to build full API URL with query parameters
 * Only use this if you need the full URL (not for authenticatedGet/Post/etc)
 * 
 * @param endpoint - API endpoint
 * @param params - URLSearchParams or object with query parameters
 * @returns Full URL with query string
 */
export function buildApiUrl(endpoint: string, params?: URLSearchParams | Record<string, string>): string {
  const url = `${API_BASE_URL}${endpoint}`;
  
  if (!params) {
    return url;
  }

  const searchParams = params instanceof URLSearchParams 
    ? params 
    : new URLSearchParams(params);

  return `${url}?${searchParams.toString()}`;
}
