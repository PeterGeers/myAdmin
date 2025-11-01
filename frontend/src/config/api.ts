// API Configuration - DO NOT use hardcoded localhost URLs
// Always use relative URLs for production compatibility

export const API_BASE_URL = ''; // Empty string for relative URLs

export const API_ENDPOINTS = {
  // Reports
  MUTATIES_TABLE: '/api/reports/mutaties-table',
  BNB_FILTER_OPTIONS: '/api/reports/bnb-filter-options',
  BNB_LISTING_DATA: '/api/reports/bnb-listing-data',
  BNB_CHANNEL_DATA: '/api/reports/bnb-channel-data',
  AVAILABLE_YEARS: '/api/reports/available-years',
  ACTUALS_PROFITLOSS: '/api/reports/actuals-profitloss',
  ACTUALS_BALANCE: '/api/reports/actuals-balance',
  BALANCE_DATA: '/api/reports/balance-data',
  REFERENCE_ANALYSIS: '/api/reports/reference-analysis',
  AANGIFTE_IB: '/api/reports/aangifte-ib',
  AANGIFTE_IB_EXPORT: '/api/reports/aangifte-ib-export',
  AANGIFTE_IB_XLSX_EXPORT: '/api/reports/aangifte-ib-xlsx-export',
  
  // BNB
  BNB_VIOLIN_DATA: '/api/bnb/bnb-violin-data',
  BNB_RETURNING_GUESTS: '/api/bnb/bnb-returning-guests',
  BNB_GUEST_BOOKINGS: '/api/bnb/bnb-guest-bookings',
  BNB_FILTER_OPTIONS_BNB: '/api/bnb/bnb-filter-options',
  
  // Status
  STATUS: '/api/status',
  TEST: '/api/test'
} as const;

// Helper function to build API URLs
export const buildApiUrl = (endpoint: string, params?: URLSearchParams): string => {
  const url = `${API_BASE_URL}${endpoint}`;
  return params ? `${url}?${params.toString()}` : url;
};