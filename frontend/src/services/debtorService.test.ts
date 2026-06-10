/**
 * Debtor Service - Unit Tests
 *
 * Tests for all debtorService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getReceivables,
  getPayables,
  getAging,
  sendReminder,
  markOverdue,
  runPaymentCheck,
  getPaymentCheckStatus,
} from './debtorService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('debtorService', () => {
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

  describe('getReceivables', () => {
    it('should fetch receivables with correct endpoint', async () => {
      const mockBody = { receivables: [{ id: 1, amount: 500 }] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getReceivables();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/debtors/receivables'),
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

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getReceivables()).rejects.toThrow();
    });
  });

  describe('getPayables', () => {
    it('should fetch payables with correct endpoint', async () => {
      const mockBody = { payables: [{ id: 2, amount: 300 }] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getPayables();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/debtors/payables'),
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
  });

  describe('getAging', () => {
    it('should fetch aging report with correct endpoint', async () => {
      const mockBody = { aging: { '0-30': 1000, '31-60': 500 } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getAging();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/debtors/aging'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('sendReminder', () => {
    it('should POST reminder for a specific invoice', async () => {
      const mockBody = { success: true, message: 'Reminder sent' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await sendReminder(42);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/debtors/send-reminder/42'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'Content-Type': 'application/json',
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include the invoice ID in the URL', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await sendReminder(99);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/zzp/debtors/send-reminder/99');
    });
  });

  describe('markOverdue', () => {
    it('should POST to mark-overdue endpoint', async () => {
      const mockBody = { success: true, marked_count: 3 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await markOverdue();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/invoices/mark-overdue'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('runPaymentCheck', () => {
    it('should POST to payment-check/run endpoint', async () => {
      const mockBody = { success: true, checked: 10, matched: 7 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await runPaymentCheck();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/payment-check/run'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('getPaymentCheckStatus', () => {
    it('should GET payment-check/status endpoint', async () => {
      const mockBody = { status: 'completed', last_run: '2024-01-15T10:30:00Z' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getPaymentCheckStatus();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/zzp/payment-check/status'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });
});
