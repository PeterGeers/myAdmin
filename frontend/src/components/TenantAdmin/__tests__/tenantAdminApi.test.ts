/**
 * Tenant Admin API Service - Unit Tests
 * 
 * Tests for all API service functions with mocked fetch calls.
 * Target: 15+ tests
 */

import { fetchAuthSession } from 'aws-amplify/auth';
import * as api from '../../../services/tenantAdminApi';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

const mockFetchAuthSession = fetchAuthSession as jest.MockedFunction<typeof fetchAuthSession>;

describe('Tenant Admin API Service', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();
    
    // Mock localStorage
    Storage.prototype.getItem = jest.fn((key) => {
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
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // ============================================================================
  // User Management API Tests
  // ============================================================================

  describe('User Management API', () => {
    test('createUser sends POST request with correct data', async () => {
      const mockResponse = { success: true, username: 'test@example.com' };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const userData = {
        email: 'test@example.com',
        given_name: 'Test',
        family_name: 'User',
      };

      const result = await api.createUser(userData);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/users'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
          body: JSON.stringify(userData),
        })
      );
      expect(result).toEqual(mockResponse);
    });

    test('listUsers sends GET request with filters', async () => {
      const mockResponse = { users: [] };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.listUsers({ role: 'Tenant_Admin', search: 'test' });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('role=Tenant_Admin'),
        expect.any(Object)
      );
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('search=test'),
        expect.any(Object)
      );
    });

    test('assignRole sends POST request to correct endpoint', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.assignRole('testuser', 'Tenant_Admin');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/users/testuser/groups'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ group_name: 'Tenant_Admin' }),
        })
      );
    });

    test('removeRole sends DELETE request to correct endpoint', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.removeRole('testuser', 'Tenant_Admin');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/users/testuser/groups/Tenant_Admin'),
        expect.objectContaining({
          method: 'DELETE',
        })
      );
    });

    test('removeUser sends DELETE request', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.removeUser('testuser');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/users/testuser'),
        expect.objectContaining({
          method: 'DELETE',
        })
      );
    });
  });

  // ============================================================================
  // Credentials Management API Tests
  // ============================================================================

  describe('Credentials Management API', () => {
    test('uploadCredentials sends FormData with file', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const mockFile = new File(['{}'], 'credentials.json', { type: 'application/json' });
      await api.uploadCredentials(mockFile, 'google_drive');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/credentials'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
            'X-Tenant': mockTenant,
          }),
        })
      );

      const callArgs = (global.fetch as jest.Mock).mock.calls[0];
      expect(callArgs[1].body).toBeInstanceOf(FormData);
    });

    test('listCredentials sends GET request', async () => {
      const mockResponse = { credentials: [] };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.listCredentials();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/credentials'),
        expect.any(Object)
      );
      expect(result).toEqual(mockResponse);
    });

    test('testCredentials sends POST request with credential type', async () => {
      const mockResponse = { success: true, accessible: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.testCredentials('google_drive');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/credentials/test'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ credential_type: 'google_drive' }),
        })
      );
    });

    test('startOAuth sends POST request with service', async () => {
      const mockResponse = { auth_url: 'https://oauth.example.com', state: 'abc123' };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.startOAuth('google_drive');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/credentials/oauth/start'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ service: 'google_drive' }),
        })
      );
      expect(result).toEqual(mockResponse);
    });

    test('completeOAuth sends POST request with code and state', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.completeOAuth('auth-code', 'state-token');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/credentials/oauth/complete'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ code: 'auth-code', state: 'state-token', service: 'google_drive' }),
        })
      );
    });
  });

  // ============================================================================
  // Storage Configuration API Tests
  // ============================================================================

  describe('Storage Configuration API', () => {
    test('browseFolders sends GET request', async () => {
      const mockResponse = { folders: [] };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.browseFolders();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/storage/folders'),
        expect.any(Object)
      );
      expect(result).toEqual(mockResponse);
    });

    test('getStorageConfig sends GET request', async () => {
      const mockResponse = { config: {} };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.getStorageConfig();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/storage/config'),
        expect.any(Object)
      );
      expect(result).toEqual(mockResponse);
    });

    test('updateStorageConfig sends PUT request with config', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const config = { google_drive_invoices_folder_id: 'folder123' };
      await api.updateStorageConfig(config, true);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/storage/config'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ ...config, validate: true }),
        })
      );
    });

    test('testFolder sends POST request with folder ID', async () => {
      const mockResponse = { accessible: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.testFolder('folder123');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/storage/test'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ folder_id: 'folder123' }),
        })
      );
    });

    test('getStorageUsage sends GET request', async () => {
      const mockResponse = { usage: {} };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.getStorageUsage();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/storage/usage'),
        expect.any(Object)
      );
      expect(result).toEqual(mockResponse);
    });
  });

  // ============================================================================
  // Tenant Details API Tests
  // ============================================================================

  describe('Tenant Details API', () => {
    test('getTenantDetails sends GET request', async () => {
      const mockResponse = { tenant: { administration: 'TestTenant' } };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.getTenantDetails();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/details'),
        expect.any(Object)
      );
      expect(result).toEqual(mockResponse);
    });

    test('updateTenantDetails sends PUT request with details', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const details = { display_name: 'New Name', contact_email: 'test@example.com' };
      await api.updateTenantDetails(details);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/details'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(details),
        })
      );
    });
  });

  // ============================================================================
  // Error Handling Tests
  // ============================================================================

  describe('Error Handling', () => {
    test('handles HTTP error responses', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        json: async () => ({ error: 'Access denied' }),
      });

      await expect(api.listUsers()).rejects.toThrow('Access denied');
    });

    test('handles network errors', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

      await expect(api.listUsers()).rejects.toThrow('Network error');
    });

    test('handles authentication failure', async () => {
      mockFetchAuthSession.mockRejectedValueOnce(new Error('Auth failed'));

      await expect(api.listUsers()).rejects.toThrow('Authentication failed');
    });
  });

  // ============================================================================
  // Settings API Tests
  // ============================================================================

  describe('Settings API', () => {
    test('getSettings sends GET request', async () => {
      const mockResponse = { settings: {} };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await api.getSettings();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/settings'),
        expect.any(Object)
      );
      expect(result).toEqual(mockResponse);
    });

    test('updateSettings sends PUT request', async () => {
      const mockResponse = { success: true };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const settings = { notifications: { email_enabled: true } };
      await api.updateSettings(settings);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tenant-admin/settings'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(settings),
        })
      );
    });

    test('getActivity sends GET request with date range', async () => {
      const mockResponse = { activity: { total_actions: 0 } };
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await api.getActivity({ start_date: '2026-01-01', end_date: '2026-01-31' });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('start_date=2026-01-01'),
        expect.any(Object)
      );
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('end_date=2026-01-31'),
        expect.any(Object)
      );
    });
  });
});
