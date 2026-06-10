/**
 * Asset Service - Unit Tests
 *
 * Tests for all assetService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getAssets,
  getAsset,
  createAsset,
  updateAsset,
  deleteAsset,
  disposeAsset,
  generateDepreciation,
  getAssetRegisterReport,
  getDepreciationScheduleReport,
} from './assetService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('assetService', () => {
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

  describe('getAssets', () => {
    it('should fetch assets with default params', async () => {
      const mockBody = { assets: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getAssets();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/assets'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include query params when provided', async () => {
      const mockBody = { assets: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getAssets({ status: 'active', category: 'machinery' });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('status=active');
      expect(calledUrl).toContain('category=machinery');
    });

    it('should include ledger_account param', async () => {
      const mockBody = { assets: [], count: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getAssets({ ledger_account: '0100' });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('ledger_account=0100');
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getAssets()).rejects.toThrow('Not authenticated');
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: { error: 'Server error' } })
      );

      await expect(getAssets()).rejects.toThrow('Server error');
    });
  });

  describe('getAsset', () => {
    it('should fetch a single asset by id', async () => {
      const mockBody = { asset: { id: 1, description: 'Laptop', transactions: [] } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getAsset(1);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/assets/1');
      expect(result).toEqual(mockBody);
    });

    it('should throw on 404 not found', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 404, body: { error: 'Asset not found' } })
      );

      await expect(getAsset(999)).rejects.toThrow('Asset not found');
    });
  });

  describe('createAsset', () => {
    it('should POST asset data and return new asset id', async () => {
      const mockBody = { success: true, asset_id: 42 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { description: 'Server', purchase_amount: 5000 };
      const result = await createAsset(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/assets'),
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

    it('should throw on validation error', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 400, body: { error: 'Missing required fields' } })
      );

      await expect(createAsset({})).rejects.toThrow('Missing required fields');
    });
  });

  describe('updateAsset', () => {
    it('should PUT updated data for a given asset id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { description: 'Updated Server' };
      const result = await updateAsset(5, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/assets/5'),
        expect.objectContaining({
          method: 'PUT',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('deleteAsset', () => {
    it('should send DELETE request for given asset id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteAsset(3);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/assets/3'),
        expect.objectContaining({
          method: 'DELETE',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('disposeAsset', () => {
    it('should POST disposal data and return write-off amount', async () => {
      const mockBody = { success: true, write_off: 1500 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { disposal_date: '2024-06-15', disposal_amount: 500, credit_account: '8000' };
      const result = await disposeAsset(7, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/assets/7/dispose'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('generateDepreciation', () => {
    it('should POST depreciation generation request', async () => {
      const mockBody = { success: true, entries_created: 5, entries_skipped: 1, details: [] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { year: 2024, period: 'Q1' };
      const result = await generateDepreciation(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/assets/generate-depreciation'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('getAssetRegisterReport', () => {
    it('should fetch asset register report', async () => {
      const mockBody = {
        assets: [],
        summary: {
          total_assets: 10,
          total_purchase: 50000,
          total_book_value: 30000,
          total_depreciation: 20000,
          by_category: {},
        },
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getAssetRegisterReport();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/assets/reports/register');
      expect(result).toEqual(mockBody);
    });
  });

  describe('getDepreciationScheduleReport', () => {
    it('should fetch depreciation schedule without year', async () => {
      const mockBody = { year: '2024', schedule: [], total_annual_depreciation: 12000 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getDepreciationScheduleReport();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/assets/reports/depreciation-schedule');
      expect(calledUrl).not.toContain('year=');
      expect(result).toEqual(mockBody);
    });

    it('should include year parameter when provided', async () => {
      const mockBody = { year: '2023', schedule: [], total_annual_depreciation: 10000 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getDepreciationScheduleReport(2023);

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('year=2023');
    });
  });
});
