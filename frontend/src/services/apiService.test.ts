/**
 * Tests for Authenticated API Service
 */

import {
  authenticatedRequest,
  authenticatedGet,
  authenticatedPost,
  authenticatedPut,
  authenticatedDelete,
  authenticatedFormData,
  buildApiUrl
} from './apiService';
import { getCurrentAuthTokens } from './authService';

// Mock the authService
jest.mock('./authService');

// Mock fetch
global.fetch = jest.fn();

describe('apiService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('authenticatedRequest', () => {
    it('should add Authorization header with JWT token', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedRequest('/api/test');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/test',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock-id-token'
          })
        })
      );
    });

    it('should skip authentication when skipAuth is true', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedRequest('/api/status', { skipAuth: true });

      expect(getCurrentAuthTokens).not.toHaveBeenCalled();
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/status',
        expect.objectContaining({
          headers: expect.not.objectContaining({
            'Authorization': expect.anything()
          })
        })
      );
    });

    it('should throw error when no token is available', async () => {
      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(null);

      await expect(authenticatedRequest('/api/test')).rejects.toThrow('Authentication required');
    });

    it('should retry request on 401 with refreshed token', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      const refreshedTokens = {
        idToken: 'refreshed-id-token',
        accessToken: 'refreshed-access-token'
      };

      (getCurrentAuthTokens as jest.Mock)
        .mockResolvedValueOnce(mockTokens)
        .mockResolvedValueOnce(refreshedTokens);

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({ status: 401, ok: false })
        .mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ success: true }) });

      const response = await authenticatedRequest('/api/test');

      expect(global.fetch).toHaveBeenCalledTimes(2);
      expect(response.ok).toBe(true);
    });
  });

  describe('authenticatedGet', () => {
    it('should make GET request', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ data: 'test' })
      });

      await authenticatedGet('/api/data');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/data',
        expect.objectContaining({
          method: 'GET'
        })
      );
    });
  });

  describe('authenticatedPost', () => {
    it('should make POST request with JSON body', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      const body = { name: 'test', value: 123 };

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedPost('/api/data', body);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/data',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(body)
        })
      );
    });
  });

  describe('authenticatedPut', () => {
    it('should make PUT request with JSON body', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      const body = { name: 'updated', value: 456 };

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedPut('/api/data/123', body);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/data/123',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(body)
        })
      );
    });
  });

  describe('authenticatedDelete', () => {
    it('should make DELETE request', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedDelete('/api/data/123');

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/data/123',
        expect.objectContaining({
          method: 'DELETE'
        })
      );
    });
  });

  describe('authenticatedFormData', () => {
    it('should make POST request with FormData', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      const formData = new FormData();
      formData.append('file', new Blob(['test']), 'test.txt');

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedFormData('/api/upload', formData);

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/upload',
        expect.objectContaining({
          method: 'POST',
          body: formData,
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock-id-token'
          })
        })
      );
    });

    it('should not set Content-Type header for FormData', async () => {
      const mockTokens = {
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      };

      const formData = new FormData();
      formData.append('file', new Blob(['test']), 'test.txt');

      (getCurrentAuthTokens as jest.Mock).mockResolvedValue(mockTokens);
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true })
      });

      await authenticatedFormData('/api/upload', formData);

      const callArgs = (global.fetch as jest.Mock).mock.calls[0][1];
      expect(callArgs.headers).not.toHaveProperty('Content-Type');
    });
  });

  describe('buildApiUrl', () => {
    it('should build URL without params', () => {
      const url = buildApiUrl('/api/test');
      expect(url).toBe('/api/test');
    });

    it('should build URL with URLSearchParams', () => {
      const params = new URLSearchParams({ year: '2024', quarter: '1' });
      const url = buildApiUrl('/api/test', params);
      expect(url).toBe('/api/test?year=2024&quarter=1');
    });

    it('should build URL with object params', () => {
      const params = { year: '2024', quarter: '1' };
      const url = buildApiUrl('/api/test', params);
      expect(url).toBe('/api/test?year=2024&quarter=1');
    });
  });
});
