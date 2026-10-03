// API Configuration
declare global {
  interface Window {
    API_BASE_URL?: string;
  }
}

// Determine the correct API base URL
const getApiBaseUrl = (): string => {
  // If window.API_BASE_URL is explicitly set (even if empty string), use it
  if (window.API_BASE_URL !== undefined) {
    return window.API_BASE_URL;
  }
  
  // If running from file:// protocol, use localhost
  if (window.location.protocol === 'file:') {
    return 'http://localhost:5000';
  }
  
  // If running from http/https, use relative URLs
  return '';
};

export const API_BASE_URL = getApiBaseUrl();

// Helper function to build API URLs
export const buildApiUrl = (endpoint: string, params?: URLSearchParams): string => {
  const url = `${API_BASE_URL}${endpoint}`;
  return params ? `${url}?${params.toString()}` : url;
};