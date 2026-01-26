/**
 * Tests for tenantApiService
 */

import {
  tenantAwareGet,
  tenantAwarePost,
  tenantAwarePut,
  tenantAwareDelete,
  getCurrentTenant,
  requireTenant,
  createTenantParams
} from './tenantApiService';

// Mock the base API service
jest.mock('./apiService', () => ({
  authenticatedGet: jest.fn(),
  authenticatedPost: jest.fn(),
  authenticatedPut: jest.fn(),
  authenticatedDelete: jest.fn()
}));

import { authenticatedGet, authenticatedPost, authenticatedPut, authenticatedDelete } from './apiService';

const mockAuthenticatedGet = authenticatedGet as jest.MockedFunction<typeof authenticatedGet>;
const mockAuthenticatedPost = authenticatedPost as jest.MockedFunction<typeof authenticatedPost>;
const mockAuthenticatedPut = authenticatedPut as jest.MockedFunction<typeof authenticatedPut>;
const mockAuthenticatedDelete = authenticatedDelete as jest.MockedFunction<typeof authenticatedDelete>;

describe('tenantApiService', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
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

  describe('tenantAwarePut', () => {
    it('should include current tenant in request body', async () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockAuthenticatedPut.mockResolvedValue(new Response());

      const data = { id: 1, name: 'test' };
      await tenantAwarePut('/api/test/1', data);

      expect(mockAuthenticatedPut).toHaveBeenCalledWith(
        '/api/test/1',
        { id: 1, name: 'test', administration: 'GoodwinSolutions' },
        undefined
      );
    });
  });

  describe('tenantAwareDelete', () => {
    it('should include current tenant in query parameters', async () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      mockAuthenticatedDelete.mockResolvedValue(new Response());

      await tenantAwareDelete('/api/test/1');

      expect(mockAuthenticatedDelete).toHaveBeenCalledWith(
        '/api/test/1?administration=GoodwinSolutions',
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

  describe('createTenantParams', () => {
    it('should create URLSearchParams with current tenant', () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      
      const params = createTenantParams();
      
      expect(params.get('administration')).toBe('GoodwinSolutions');
    });

    it('should include additional parameters', () => {
      localStorage.setItem('selectedTenant', 'GoodwinSolutions');
      
      const params = createTenantParams({ year: '2024', month: '01' });
      
      expect(params.get('administration')).toBe('GoodwinSolutions');
      expect(params.get('year')).toBe('2024');
      expect(params.get('month')).toBe('01');
    });

    it('should use "all" when no tenant is selected', () => {
      const params = createTenantParams();
      
      expect(params.get('administration')).toBe('all');
    });
  });
});