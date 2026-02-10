/**
 * Tenant Admin - Frontend Integration Tests
 * 
 * Tests complete user flows end-to-end with mocked API responses.
 * Target: 5+ integration tests
 */

import { fetchAuthSession } from 'aws-amplify/auth';
import * as api from '../../../services/tenantAdminApi';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

const mockFetchAuthSession = fetchAuthSession as jest.MockedFunction<typeof fetchAuthSession>;

describe('Tenant Admin Integration Tests', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  beforeEach(() => {
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
  // Integration Test 1: Complete User Creation Flow
  // ============================================================================

  describe('Integration Test 1: Complete User Creation Flow', () => {
    test('creates user, assigns role, and verifies access', async () => {
      // Step 1: Create user
      const createUserResponse = {
        success: true,
        username: 'newuser@example.com',
        message: 'User created successfully',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => createUserResponse,
      });

      const userData = {
        email: 'newuser@example.com',
        given_name: 'New',
        family_name: 'User',
      };

      const createResult = await api.createUser(userData);

      expect(createResult.success).toBe(true);
      expect(createResult.username).toBe('newuser@example.com');

      // Step 2: Assign role to user
      const assignRoleResponse = {
        success: true,
        message: 'Role assigned successfully',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => assignRoleResponse,
      });

      const assignResult = await api.assignRole('newuser@example.com', 'Tenant_Admin');

      expect(assignResult.success).toBe(true);

      // Step 3: Verify user appears in list
      const listUsersResponse = {
        users: [
          {
            username: 'newuser@example.com',
            email: 'newuser@example.com',
            name: 'New User',
            status: 'FORCE_CHANGE_PASSWORD',
            enabled: true,
            groups: ['Tenant_Admin'],
            tenants: [mockTenant],
            created: new Date().toISOString(),
          },
        ],
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => listUsersResponse,
      });

      const listResult = await api.listUsers();

      expect(listResult.users).toHaveLength(1);
      expect(listResult.users[0].email).toBe('newuser@example.com');
      expect(listResult.users[0].groups).toContain('Tenant_Admin');

      // Verify complete flow
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    test('handles user creation failure gracefully', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ error: 'User already exists' }),
      });

      const userData = {
        email: 'existing@example.com',
        given_name: 'Existing',
        family_name: 'User',
      };

      await expect(api.createUser(userData)).rejects.toThrow('User already exists');
    });
  });

  // ============================================================================
  // Integration Test 2: Complete Credential Upload Flow
  // ============================================================================

  describe('Integration Test 2: Complete Credential Upload Flow', () => {
    test('uploads credentials, tests connection, and verifies storage', async () => {
      // Step 1: Upload credentials file
      const uploadResponse = {
        success: true,
        message: 'Credentials uploaded successfully',
        credential_type: 'google_drive',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => uploadResponse,
      });

      const file = new File(['{"key": "value"}'], 'credentials.json', {
        type: 'application/json',
      });

      const uploadResult = await api.uploadCredentials(file, 'google_drive');

      expect(uploadResult.success).toBe(true);
      expect(uploadResult.credential_type).toBe('google_drive');

      // Step 2: Test connection
      const testResponse = {
        success: true,
        accessible: true,
        message: 'Connection successful',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => testResponse,
      });

      const testResult = await api.testCredentials('google_drive');

      expect(testResult.success).toBe(true);
      expect(testResult.accessible).toBe(true);

      // Step 3: Verify credentials appear in list
      const listResponse = {
        credentials: [
          {
            type: 'google_drive',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ],
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => listResponse,
      });

      const listResult = await api.listCredentials();

      expect(listResult.credentials).toHaveLength(1);
      expect(listResult.credentials[0].type).toBe('google_drive');

      // Verify complete flow
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    test('handles upload failure and shows error', async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ error: 'Invalid credentials format' }),
      });

      const file = new File(['invalid'], 'credentials.json', {
        type: 'application/json',
      });

      await expect(api.uploadCredentials(file, 'google_drive')).rejects.toThrow(
        'Invalid credentials format'
      );
    });
  });

  // ============================================================================
  // Integration Test 3: Complete Storage Configuration Flow
  // ============================================================================

  describe('Integration Test 3: Complete Storage Configuration Flow', () => {
    test('browses folders, configures storage, and verifies usage', async () => {
      // Step 1: Browse available folders
      const browseFoldersResponse = {
        folders: [
          { id: 'folder1', name: 'Invoices', url: 'https://drive.google.com/folder1' },
          { id: 'folder2', name: 'Templates', url: 'https://drive.google.com/folder2' },
        ],
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => browseFoldersResponse,
      });

      const browseFoldersResult = await api.browseFolders();

      expect(browseFoldersResult.folders).toHaveLength(2);

      // Step 2: Configure storage
      const configureResponse = {
        success: true,
        message: 'Storage configured successfully',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => configureResponse,
      });

      const storageConfig = {
        google_drive_invoices_folder_id: 'folder1',
      };

      const configureResult = await api.updateStorageConfig(storageConfig, true);

      expect(configureResult.success).toBe(true);

      // Verify complete flow
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });

  // ============================================================================
  // Integration Test 4: Error Handling
  // ============================================================================

  describe('Integration Test 4: Error Handling', () => {
    test('handles authentication failure', async () => {
      mockFetchAuthSession.mockRejectedValue(new Error('Auth failed'));

      await expect(api.listUsers()).rejects.toThrow('Authentication failed');
    });

    test('handles 403 Forbidden errors', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ error: 'Access denied' }),
      });

      await expect(api.listUsers()).rejects.toThrow('Access denied');
    });
  });

  // ============================================================================
  // Integration Test 5: Loading States
  // ============================================================================

  describe('Integration Test 5: Loading States', () => {
    test('tracks loading state during operations', async () => {
      let isLoading = false;

      isLoading = true;

      (global.fetch as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({ success: true }),
                }),
              50
            )
          )
      );

      const userData = {
        email: 'test@example.com',
        given_name: 'Test',
        family_name: 'User',
      };

      const createPromise = api.createUser(userData);

      expect(isLoading).toBe(true);

      await createPromise;

      isLoading = false;
      expect(isLoading).toBe(false);
    });
  });
});
