/**
 * Parameter Service - Unit Tests
 *
 * Tests for all parameterService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getParameters,
  createParameter,
  updateParameter,
  deleteParameter,
  getParameterDefault,
} from './parameterService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('parameterService', () => {
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
        accessToken: {
          toString: () => 'mock-access-token',
        },
      },
    } as any);

    // Mock fetch
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getParameters', () => {
    it('should fetch all parameters without namespace', async () => {
      const mockBody = { success: true, tenant: mockTenant, parameters: {} };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getParameters();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/parameters'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include namespace query param when provided', async () => {
      const mockBody = { success: true, tenant: mockTenant, parameters: { pricing: [] } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getParameters('pricing');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('namespace=pricing');
    });

    it('should encode special characters in namespace', async () => {
      const mockBody = { success: true, tenant: mockTenant, parameters: {} };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getParameters('my namespace');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('namespace=my%20namespace');
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getParameters()).rejects.toThrow();
    });
  });

  describe('createParameter', () => {
    it('should POST parameter data and return response', async () => {
      const mockBody = { success: true, id: 10 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = {
        scope: 'tenant' as const,
        namespace: 'pricing',
        key: 'base_rate',
        value: 100,
        value_type: 'number' as const,
        is_secret: false,
      };
      const result = await createParameter(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/parameters'),
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
        scope: 'tenant' as const,
        namespace: 'pricing',
        key: 'base_rate',
        value: 100,
        value_type: 'number' as const,
        is_secret: false,
      };

      await expect(createParameter(data)).rejects.toThrow();
    });
  });

  describe('updateParameter', () => {
    it('should PUT updated data for a given parameter id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { value: 200, value_type: 'number' as const };
      const result = await updateParameter(5, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/parameters/5'),
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

    it('should handle value-only update', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { value: 'new-value' };
      const result = await updateParameter(3, data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/parameters/3'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('deleteParameter', () => {
    it('should send DELETE request for given parameter id', async () => {
      const mockBody = { success: true };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteParameter(7);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/parameters/7'),
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

      await expect(deleteParameter(7)).rejects.toThrow();
    });
  });

  describe('getParameterDefault', () => {
    it('should fetch parameter default with namespace and key', async () => {
      const mockBody = { success: true, has_default: true, value: 50, value_type: 'number', source: 'code_default' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getParameterDefault('pricing', 'base_rate');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/tenant-admin/parameters/default');
      expect(calledUrl).toContain('namespace=pricing');
      expect(calledUrl).toContain('key=base_rate');
      expect(result).toEqual(mockBody);
    });

    it('should return response when no default exists', async () => {
      const mockBody = { success: true, has_default: false };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getParameterDefault('unknown', 'missing_key');

      expect(result).toEqual(mockBody);
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getParameterDefault('pricing', 'base_rate')).rejects.toThrow();
    });
  });
});
