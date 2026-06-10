/**
 * Tests for tenantApiService
 */

import { vi } from 'vitest';
import {
  tenantAwareGet,
  tenantAwarePost,
  getCurrentTenant,
  requireTenant,
} from './tenantApiService';

import { authenticatedGet, authenticatedPost } from './apiService';

// Mock the base API service
vi.mock('./apiService', () => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
}));

const mockAuthenticatedGet = vi.mocked(authenticatedGet);
const mockAuthenticatedPost = vi.mocked(authenticatedPost);

describe('tenantApiService', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  describe('tenantAwareGet', () => {
    it('should include current tenant in query parameters', async () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockAuthenticatedGet.mockResolvedValue(new Response());

      await tenantAwareGet('/api/test');

      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        '/api/test?administration=GoodwinSolutions',
        undefined
      );
    });

    it('should include additional parameters', async () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockAuthenticatedGet.mockResolvedValue(new Response());

      await tenantAwareGet('/api/test', { year: '2024', month: '01' });

      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        '/api/test?administration=GoodwinSolutions&year=2024&month=01',
        undefined
      );
    });

    it('should use "all" when no tenant is selected', async () => {
      mockAuthenticatedGet.mockResolvedValue(new Response());

      await tenantAwareGet('/api/test');

      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        '/api/test?administration=all',
        undefined
      );
    });
  });

  describe('tenantAwarePost', () => {
    it('should include current tenant in request body', async () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockAuthenticatedPost.mockResolvedValue(new Response());

      const data = { name: 'test' };
      await tenantAwarePost('/api/test', data);

      expect(mockAuthenticatedPost).toHaveBeenCalledWith(
        '/api/test',
        { name: 'test', administration: 'GoodwinSolutions' },
        undefined
      );
    });

    it('should not override existing administration in data', async () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockAuthenticatedPost.mockResolvedValue(new Response());

      const data = { name: 'test', administration: 'PeterPrive' };
      await tenantAwarePost('/api/test', data);

      expect(mockAuthenticatedPost).toHaveBeenCalledWith(
        '/api/test',
        { name: 'test', administration: 'PeterPrive' },
        undefined
      );
    });
  });

  describe('getCurrentTenant', () => {
    it('should return current tenant from localStorage', () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      
      const tenant = getCurrentTenant();
      
      expect(tenant).toBe('GoodwinSolutions');
    });

    it('should return null when no tenant is selected', () => {
      const tenant = getCurrentTenant();
      
      expect(tenant).toBeNull();
    });
  });

  describe('requireTenant', () => {
    it('should return current tenant when selected', () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      
      const tenant = requireTenant();
      
      expect(tenant).toBe('GoodwinSolutions');
    });

    it('should throw error when no tenant is selected', () => {
      expect(() => requireTenant()).toThrow(
        'No tenant selected. Please select a tenant first.'
      );
    });
  });
});