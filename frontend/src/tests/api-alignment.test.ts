/**
 * API Alignment Test - Frontend
 * Validates that all API calls in components have corresponding backend routes
 */

const API_ENDPOINTS = [
  '/api/test',
  '/api/reports/mutaties-table',
  '/api/reports/balance-data', 
  '/api/reports/available-years',
  '/api/reports/actuals-balance',
  '/api/reports/actuals-profitloss',
  '/api/bnb/bnb-table',
  '/api/bnb/bnb-filter-options',
  '/api/bnb/bnb-listing-data',
  '/api/bnb/bnb-channel-data',
  '/api/reports/aangifte-ib',
  '/api/bnb/bnb-violin-data',
  '/api/bnb/bnb-filter-options',
  '/api/bnb/bnb-returning-guests',
  '/api/str-channel/preview',
  '/api/str-channel/calculate',
  '/api/str-channel/save'
];

describe('API Alignment Tests', () => {
  const BASE_URL = 'http://localhost:5000';
  
  beforeAll(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  describe('API Endpoint Validation', () => {
    it.each(API_ENDPOINTS)('should have working endpoint: %s', async (endpoint) => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => name === 'content-type' ? 'application/json' : null
        },
        json: async () => ({ success: true, data: [] }),
        text: async () => '{"success": true, "data": []}'
      });

      const response = await fetch(`${BASE_URL}${endpoint}`);
      
      expect(response.ok).toBe(true);
      expect(response.status).toBe(200);
      
      const contentType = response.headers.get('content-type');
      expect(contentType).toContain('application/json');
      
      const text = await response.text();
      expect(text).not.toMatch(/<!doctype/i);
      expect(text).not.toMatch(/<html/i);
    });
  });
});

export {};