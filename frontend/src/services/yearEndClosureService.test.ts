/**
 * Year-End Closure Service - Unit Tests
 *
 * Tests for all yearEndClosureService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  validateYear,
  closeYear,
  getClosedYears,
  getYearStatus,
  reopenYear,
} from './yearEndClosureService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('yearEndClosureService', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  beforeEach(() => {
    vi.clearAllMocks();

    // Mock localStorage
    Storage.prototype.getItem = vi.fn((key) => {
      if (key === 'selectedTenant') return mockTenant;
      if (key === 'i18nextLng') return 'nl';
      return null;
    });

    // Mock fetchAuthSession
    mockFetchAuthSession.mockResolvedValue({
      tokens: {
        idToken: {
          toString: () => mockToken,
        },
      },
    } as any);

    // Mock fetch
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('validateYear', () => {
    it('should POST year validation request and return validation result', async () => {
      const mockBody = {
        can_close: true,
        errors: [],
        warnings: ['Some transactions are unreconciled'],
        info: {
          net_result: 15000.50,
          net_result_formatted: '€ 15.000,50',
          balance_sheet_accounts: 12,
        },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await validateYear(2024);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/year-end/validate'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
          body: JSON.stringify({ year: 2024 }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 400, body: { error: 'Year 2025 has no transactions' } })
      );

      await expect(validateYear(2025)).rejects.toThrow('Year 2025 has no transactions');
    });

    it('should throw generic message when no error field in response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: {} })
      );

      await expect(validateYear(2024)).rejects.toThrow('Failed to validate year');
    });
  });

  describe('closeYear', () => {
    it('should POST close year request with notes and return closure result', async () => {
      const mockBody = {
        success: true,
        year: 2024,
        closure_transaction_number: 'CLO-2024-001',
        opening_transaction_number: 'OPN-2025-001',
        net_result: 15000.50,
        net_result_formatted: '€ 15.000,50',
        balance_sheet_accounts: 12,
        message: 'Year 2024 closed successfully',
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await closeYear(2024, 'Annual closure');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/year-end/close'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ year: 2024, notes: 'Annual closure' }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should send empty notes when not provided', async () => {
      const mockBody = { success: true, year: 2024, closure_transaction_number: 'CLO-2024-001', opening_transaction_number: 'OPN-2025-001', net_result: 0, net_result_formatted: '€ 0,00', balance_sheet_accounts: 5, message: 'Done' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await closeYear(2024);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/year-end/close'),
        expect.objectContaining({
          body: JSON.stringify({ year: 2024, notes: '' }),
        })
      );
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 409, body: { error: 'Year already closed' } })
      );

      await expect(closeYear(2024)).rejects.toThrow('Year already closed');
    });
  });

  describe('getClosedYears', () => {
    it('should GET closed years list', async () => {
      const mockBody: any[] = [
        {
          year: 2023,
          closed_date: '2024-01-15T10:00:00Z',
          closed_by: 'admin@test.com',
          closure_transaction_number: 'CLO-2023-001',
          opening_balance_transaction_number: 'OPN-2024-001',
          notes: 'Annual closure',
        },
        {
          year: 2022,
          closed_date: '2023-01-10T09:00:00Z',
          closed_by: 'admin@test.com',
          closure_transaction_number: 'CLO-2022-001',
          opening_balance_transaction_number: 'OPN-2023-001',
          notes: '',
        },
      ];
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getClosedYears();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/year-end/closed-years'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: { error: 'Database error' } })
      );

      await expect(getClosedYears()).rejects.toThrow('Database error');
    });
  });

  describe('getYearStatus', () => {
    it('should GET status for a specific year', async () => {
      const mockBody = {
        year: 2024,
        closed: false,
        can_close: true,
        errors: [],
        warnings: [],
        info: {
          net_result: 8000,
          net_result_formatted: '€ 8.000,00',
          balance_sheet_accounts: 10,
          previous_year_closed: true,
        },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getYearStatus(2024);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/year-end/status/2024');
      expect(result).toEqual(mockBody);
    });

    it('should return closed year status', async () => {
      const mockBody = {
        year: 2023,
        closed: true,
        closed_date: '2024-01-15T10:00:00Z',
        closed_by: 'admin@test.com',
        closure_transaction_number: 'CLO-2023-001',
        opening_balance_transaction_number: 'OPN-2024-001',
        notes: 'Year-end closure',
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getYearStatus(2023);

      expect(result.closed).toBe(true);
      expect(result.closed_by).toBe('admin@test.com');
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 404, body: { error: 'Year not found' } })
      );

      await expect(getYearStatus(1999)).rejects.toThrow('Year not found');
    });
  });

  describe('reopenYear', () => {
    it('should POST reopen request and return success', async () => {
      const mockBody = {
        success: true,
        year: 2023,
        message: 'Year 2023 has been reopened',
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await reopenYear(2023);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/year-end/reopen'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ year: 2023 }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 400, body: { error: 'Cannot reopen year with dependent closures' } })
      );

      await expect(reopenYear(2022)).rejects.toThrow('Cannot reopen year with dependent closures');
    });

    it('should throw generic message when no error field', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: {} })
      );

      await expect(reopenYear(2023)).rejects.toThrow('Failed to reopen year');
    });
  });
});
