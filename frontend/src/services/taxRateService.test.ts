/**
 * Tax Rate Service - Unit Tests
 *
 * Tests for all taxRateService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getTaxRates,
  createTaxRate,
  updateTaxRate,
  deleteTaxRate,
} from './taxRateService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('taxRateService', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  beforeEach(() => {
    vi.clearAllMocks();

    // Mock localStorage
    Storage.prototype.getItem = vi.fn((key) => {
      if (key === 'selectedTenant') return mockTenant;
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

  describe('getTaxRates', () => {
    it('should fetch all tax rates', async () => {
      const mockBody = {
        success: true,
        tenant: mockTenant,
        tax_rates: [
          {
            id: 1,
            tax_type: 'BTW',
            tax_code: 'BTW21',
            rate: 21,
            ledger_account: '1500',
            effective_from: '2024-01-01',
            effective_to: null,
            scope_origin: 'system',
            description: 'Standard VAT rate',
            calc_method: 'percentage',
          },
        ],
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getTaxRates();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/tax-rates'),
        expect.objectContaining({
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

      await expect(getTaxRates()).rejects.toThrow();
    });
  });

  describe('createTaxRate', () => {
    it('should POST new tax rate data', async () => {
      const mockBody = { success: true, id: 5 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = {
        tax_type: 'BTW',
        tax_code: 'BTW9',
        rate: 9,
        effective_from: '2024-01-01',
        description: 'Reduced VAT rate',
      };
      const result = await createTaxRate(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/tax-rates'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${mockToken}`,
          }),
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      const data = {
        tax_type: 'BTW',
        tax_code: 'BTW21',
        rate: 21,
        effective_from: '2024-01-01',
      };
      await expect(createTaxRate(data)).rejects.toThrow();
    });
  });

  describe('updateTaxRate', () => {
    it('should PUT updated data for a given tax rate id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { rate: 21, description: 'Updated standard rate' };
      const result = await updateTaxRate(3, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/tax-rates/3'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${mockToken}`,
          }),
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(updateTaxRate(1, { rate: 15 })).rejects.toThrow();
    });
  });

  describe('deleteTaxRate', () => {
    it('should send DELETE request for given tax rate id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteTaxRate(7);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/tax-rates/7'),
        expect.objectContaining({
          method: 'DELETE',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(deleteTaxRate(1)).rejects.toThrow();
    });
  });
});
