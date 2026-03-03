/**
 * Integration Tests for Year-End Closure Service
 * 
 * Tests the year-end closure service layer including:
 * - Year status retrieval
 * - Year validation
 * - Close year functionality
 * - Reopen year functionality with sequential validation
 * - Error handling
 * - API integration
 * 
 * Note: Component-level tests are skipped due to Chakra UI mocking complexity.
 * These service-level tests provide coverage of the core business logic.
 */

import {
  getYearStatus,
  validateYear,
  closeYear,
  reopenYear,
  getClosedYears,
} from '../services/yearEndClosureService';
import { authenticatedGet, authenticatedPost } from '../services/apiService';

// Mock the API service
jest.mock('../services/apiService', () => ({
  authenticatedGet: jest.fn(),
  authenticatedPost: jest.fn(),
  tenantAwareGet: jest.fn(),
  tenantAwarePost: jest.fn(),
}));

// Mock tenantApiService to use our mocked functions
jest.mock('../services/tenantApiService', () => {
  const actualApiService = jest.requireActual('../services/apiService');
  return {
    tenantAwareGet: actualApiService.tenantAwareGet || jest.fn(),
    tenantAwarePost: actualApiService.tenantAwarePost || jest.fn(),
  };
});

// Mock the config
jest.mock('../config', () => ({
  buildApiUrl: jest.fn((endpoint) => `http://localhost:5000${endpoint}`),
}));

// Helper to create mock Response
const createMockResponse = (data: any, ok = true) => ({
  ok,
  json: async () => data,
  status: ok ? 200 : 400,
  statusText: ok ? 'OK' : 'Bad Request',
});

describe('Year-End Closure Service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Get Year Status', () => {
    it('should fetch open year status', async () => {
      const mockData = {
        closed: false,
        year: 2025,
        message: 'Year 2025 is not closed',
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await getYearStatus(2025);

      expect(result).toEqual(mockData);
      expect(result.closed).toBe(false);
    });

    it('should fetch closed year status with details', async () => {
      const mockData = {
        closed: true,
        year: 2024,
        closed_date: 'Tue, 03 Mar 2026 15:03:49 GMT',
        closed_by: 'peter@pgeers.nl',
        closure_transaction_number: 'YearClose 2024',
        opening_balance_transaction_number: 'OpeningBalance 2025',
        notes: 'Year-end closure completed',
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await getYearStatus(2024);

      expect(result.closed).toBe(true);
      expect(result.closed_by).toBe('peter@pgeers.nl');
      expect(result.notes).toBe('Year-end closure completed');
    });

    it('should handle API errors', async () => {
      (tenantAwareGet as jest.Mock).mockResolvedValue(
        createMockResponse({ error: 'API Error' }, false)
      );

      await expect(getYearStatus(2025)).rejects.toThrow();
    });
  });

  describe('Validate Year', () => {
    it('should validate year that can be closed', async () => {
      const mockData = {
        can_close: true,
        errors: [],
        warnings: [],
        info: {
          net_result: -5000,
          net_result_formatted: '€-5,000.00',
          balance_sheet_accounts: 10,
          previous_year_closed: true,
        },
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await validateYear(2025);

      expect(result.can_close).toBe(true);
      expect(result.errors).toHaveLength(0);
      expect(result.info.net_result).toBe(-5000);
    });

    it('should validate year that cannot be closed', async () => {
      const mockData = {
        can_close: false,
        errors: [
          'Previous year 2024 must be closed first',
          'Required accounts not configured',
        ],
        warnings: [],
        info: {
          net_result: 0,
          net_result_formatted: '€0.00',
          balance_sheet_accounts: 0,
        },
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await validateYear(2025);

      expect(result.can_close).toBe(false);
      expect(result.errors).toHaveLength(2);
      expect(result.errors[0]).toContain('Previous year 2024 must be closed first');
    });

    it('should include warnings in validation', async () => {
      const mockData = {
        can_close: true,
        errors: [],
        warnings: ['Net P&L result is zero'],
        info: {
          net_result: 0,
          net_result_formatted: '€0.00',
          balance_sheet_accounts: 5,
        },
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await validateYear(2025);

      expect(result.can_close).toBe(true);
      expect(result.warnings).toHaveLength(1);
      expect(result.warnings[0]).toBe('Net P&L result is zero');
    });
  });

  describe('Close Year', () => {
    it('should close year successfully', async () => {
      const mockData = {
        success: true,
        year: 2025,
        closure_transaction_number: 'YearClose 2025',
        opening_transaction_number: 'OpeningBalance 2026',
        net_result: -5000,
        net_result_formatted: '€-5,000.00',
        balance_sheet_accounts: 10,
        message: 'Year 2025 closed successfully',
      };

      (tenantAwarePost as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await closeYear(2025, 'Closing year 2025');

      expect(result.success).toBe(true);
      expect(result.year).toBe(2025);
      expect(result.closure_transaction_number).toBe('YearClose 2025');
    });

    it('should handle close year errors', async () => {
      (tenantAwarePost as jest.Mock).mockResolvedValue(
        createMockResponse(
          { error: 'Cannot close year 2025: Previous year must be closed first' },
          false
        )
      );

      await expect(closeYear(2025, '')).rejects.toThrow();
    });
  });

  describe('Reopen Year', () => {
    it('should reopen year successfully', async () => {
      const mockData = {
        success: true,
        year: 2024,
        message: 'Year 2024 reopened successfully',
      };

      (tenantAwarePost as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await reopenYear(2024);

      expect(result.success).toBe(true);
      expect(result.year).toBe(2024);
    });

    it('should handle sequential reopening validation error', async () => {
      (tenantAwarePost as jest.Mock).mockResolvedValue(
        createMockResponse(
          { error: 'Cannot reopen year 2024 because year 2025 is already closed' },
          false
        )
      );

      await expect(reopenYear(2024)).rejects.toThrow();
    });
  });

  describe('Get Closed Years', () => {
    it('should fetch list of closed years', async () => {
      const mockData = [
        {
          year: 2024,
          closed_date: 'Tue, 03 Mar 2026 15:03:49 GMT',
          closed_by: 'peter@pgeers.nl',
          closure_transaction_number: 'YearClose 2024',
          opening_balance_transaction_number: 'OpeningBalance 2025',
          notes: 'Year-end closure completed',
        },
        {
          year: 2023,
          closed_date: 'Mon, 02 Mar 2025 14:30:00 GMT',
          closed_by: 'admin@example.com',
          closure_transaction_number: 'YearClose 2023',
          opening_balance_transaction_number: 'OpeningBalance 2024',
          notes: 'Bulk closure',
        },
      ];

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await getClosedYears();

      expect(result).toHaveLength(2);
      expect(result[0].year).toBe(2024);
      expect(result[1].year).toBe(2023);
    });

    it('should return empty array when no years are closed', async () => {
      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse([]));

      const result = await getClosedYears();

      expect(result).toHaveLength(0);
    });
  });

  describe('Sequential Reopening Logic', () => {
    it('should check year status for sequential validation', async () => {
      // Check year 2024 status (closed)
      const mockData2024 = {
        closed: true,
        year: 2024,
        closed_date: 'Tue, 03 Mar 2026 15:03:49 GMT',
        closed_by: 'peter@pgeers.nl',
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData2024));

      const year2024Status = await getYearStatus(2024);
      expect(year2024Status.closed).toBe(true);

      // Check year 2025 status (also closed)
      const mockData2025 = {
        closed: true,
        year: 2025,
        closed_date: 'Tue, 03 Mar 2026 16:00:00 GMT',
        closed_by: 'peter@pgeers.nl',
      };

      (tenantAwareGet as jest.Mock).mockResolvedValue(createMockResponse(mockData2025));

      const year2025Status = await getYearStatus(2025);
      expect(year2025Status.closed).toBe(true);

      // Attempting to reopen 2024 should fail
      (tenantAwarePost as jest.Mock).mockResolvedValue(
        createMockResponse(
          { error: 'Cannot reopen year 2024 because year 2025 is already closed' },
          false
        )
      );

      await expect(reopenYear(2024)).rejects.toThrow();
    });
  });

  describe('Data Integrity', () => {
    it('should include transaction numbers in close response', async () => {
      const mockData = {
        success: true,
        year: 2025,
        closure_transaction_number: 'YearClose 2025',
        opening_transaction_number: 'OpeningBalance 2026',
        net_result: -5000,
        net_result_formatted: '€-5,000.00',
        balance_sheet_accounts: 10,
        message: 'Year 2025 closed successfully',
      };

      (tenantAwarePost as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await closeYear(2025, '');

      expect(result.closure_transaction_number).toBe('YearClose 2025');
      expect(result.opening_transaction_number).toBe('OpeningBalance 2026');
    });

    it('should include financial summary in close response', async () => {
      const mockData = {
        success: true,
        year: 2025,
        closure_transaction_number: 'YearClose 2025',
        opening_transaction_number: 'OpeningBalance 2026',
        net_result: -5000,
        net_result_formatted: '€-5,000.00',
        balance_sheet_accounts: 10,
        message: 'Year 2025 closed successfully',
      };

      (tenantAwarePost as jest.Mock).mockResolvedValue(createMockResponse(mockData));

      const result = await closeYear(2025, '');

      expect(result.net_result).toBe(-5000);
      expect(result.net_result_formatted).toBe('€-5,000.00');
      expect(result.balance_sheet_accounts).toBe(10);
    });
  });
});
