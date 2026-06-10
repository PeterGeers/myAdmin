/**
 * SysAdmin Service - Unit Tests
 *
 * Tests for all sysadminService API functions with mocked fetch calls.
 */

import { vi } from 'vitest';
import { fetchAuthSession } from 'aws-amplify/auth';
import { createMockResponse } from '@/test-utils/mockHelpers';
import {
  getTenants,
  getTenant,
  createTenant,
  updateTenant,
  deleteTenant,
  reprovisionTenant,
  resendInvitation,
  getPendingSignups,
  provisionSignup,
  getRoles,
  createRole,
  updateRole,
  deleteRole,
  getTenantModules,
  updateTenantModules,
  getSystemHealth,
} from './sysadminService';

// Mock AWS Amplify
vi.mock('aws-amplify/auth');

// Mock config
vi.mock('../config', () => ({
  buildApiUrl: vi.fn((endpoint: string) => `http://localhost:5000${endpoint}`),
}));

const mockFetchAuthSession = vi.mocked(fetchAuthSession);

describe('sysadminService', () => {
  const mockToken = 'mock-jwt-token';

  beforeEach(() => {
    vi.clearAllMocks();

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

  // ==========================================================================
  // Tenant Management
  // ==========================================================================

  describe('getTenants', () => {
    it('should fetch tenants with default params', async () => {
      const mockBody = { tenants: [], total: 0, page: 1, per_page: 20, total_pages: 0 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getTenants();

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': `Bearer ${mockToken}`,
          }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should include query params when provided', async () => {
      const mockBody = { tenants: [], total: 0, page: 2, per_page: 10, total_pages: 1 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await getTenants({ page: 2, per_page: 10, status: 'active', search: 'test' });

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('page=2');
      expect(calledUrl).toContain('per_page=10');
      expect(calledUrl).toContain('status=active');
      expect(calledUrl).toContain('search=test');
    });

    it('should throw on authentication failure', async () => {
      mockFetchAuthSession.mockResolvedValueOnce({ tokens: undefined } as any);

      await expect(getTenants()).rejects.toThrow('No authentication token available');
    });

    it('should throw on HTTP error response', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 500, body: { error: 'Server error' } })
      );

      await expect(getTenants()).rejects.toThrow('Server error');
    });
  });

  describe('getTenant', () => {
    it('should fetch a single tenant by administration', async () => {
      const mockBody = { administration: 'acme', display_name: 'ACME Corp', status: 'active' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getTenant('acme');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/sysadmin/tenants/acme');
      expect(result).toEqual(mockBody);
    });

    it('should throw on 404', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 404, body: { error: 'Tenant not found' } })
      );

      await expect(getTenant('nonexistent')).rejects.toThrow('Tenant not found');
    });
  });

  describe('createTenant', () => {
    it('should POST tenant data', async () => {
      const mockBody = { success: true, message: 'Tenant created' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = {
        administration: 'new-tenant',
        display_name: 'New Tenant',
        contact_email: 'admin@newtenant.com',
        enabled_modules: ['finance'],
      };
      const result = await createTenant(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants'),
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

      await expect(createTenant({
        administration: '',
        display_name: '',
        contact_email: '',
        enabled_modules: [],
      })).rejects.toThrow('Missing required fields');
    });
  });

  describe('updateTenant', () => {
    it('should PUT updated data for a given tenant', async () => {
      const mockBody = { success: true, message: 'Tenant updated' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { display_name: 'Updated Name', status: 'suspended' as const };
      const result = await updateTenant('acme', data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants/acme'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('deleteTenant', () => {
    it('should send DELETE request for given tenant', async () => {
      const mockBody = { success: true, message: 'Tenant deleted' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteTenant('old-tenant');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants/old-tenant'),
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

  describe('reprovisionTenant', () => {
    it('should POST reprovision request', async () => {
      const mockBody = { success: true, provisioning: { database: 'ok' } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await reprovisionTenant('acme', { locale: 'nl', modules: ['finance'] });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants/acme/reprovision'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ locale: 'nl', modules: ['finance'] }),
        })
      );
      expect(result).toEqual(mockBody);
    });

    it('should send empty body when no options provided', async () => {
      const mockBody = { success: true, provisioning: {} };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      await reprovisionTenant('acme');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants/acme/reprovision'),
        expect.objectContaining({
          body: JSON.stringify({}),
        })
      );
    });
  });

  describe('resendInvitation', () => {
    it('should POST resend invitation request', async () => {
      const mockBody = { success: true, message: 'Invitation sent' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await resendInvitation('acme', 'user@acme.com');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants/acme/resend-invitation'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'user@acme.com' }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  // ==========================================================================
  // Provisioning
  // ==========================================================================

  describe('getPendingSignups', () => {
    it('should fetch pending signups', async () => {
      const mockBody = { signups: [{ id: 1, email: 'new@user.com' }], count: 1 };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getPendingSignups();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/sysadmin/provisioning/pending');
      expect(result).toEqual(mockBody);
    });
  });

  describe('provisionSignup', () => {
    it('should POST provisioning request', async () => {
      const mockBody = { success: true, administration: 'new-co', provisioning: { database: 'created' } };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { email: 'admin@newco.com', modules: ['finance', 'str'] };
      const result = await provisionSignup(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/provisioning/provision'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  // ==========================================================================
  // Role Management
  // ==========================================================================

  describe('getRoles', () => {
    it('should fetch all roles', async () => {
      const mockBody = { roles: [{ name: 'admin', description: 'Administrator', precedence: 1 }] };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getRoles();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/sysadmin/roles');
      expect(result).toEqual(mockBody);
    });
  });

  describe('createRole', () => {
    it('should POST new role data', async () => {
      const mockBody = { success: true, message: 'Role created' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { name: 'editor', description: 'Content editor', precedence: 5 };
      const result = await createRole(data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/roles'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('updateRole', () => {
    it('should PUT updated role data', async () => {
      const mockBody = { success: true, message: 'Role updated' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const data = { description: 'Updated description', precedence: 3 };
      const result = await updateRole('editor', data);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/roles/editor'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(data),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  describe('deleteRole', () => {
    it('should send DELETE request for given role', async () => {
      const mockBody = { success: true, message: 'Role deleted' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await deleteRole('editor');

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/roles/editor'),
        expect.objectContaining({
          method: 'DELETE',
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  // ==========================================================================
  // Module Management
  // ==========================================================================

  describe('getTenantModules', () => {
    it('should fetch modules for a tenant', async () => {
      const mockBody = {
        modules: [{ administration: 'acme', module_name: 'finance', is_active: true, created_at: '2024-01-01' }],
        registered_modules: [{ name: 'finance', description: 'Finance module', depends_on: [], readonly: false }],
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getTenantModules('acme');

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/sysadmin/tenants/acme/modules');
      expect(result).toEqual(mockBody);
    });
  });

  describe('updateTenantModules', () => {
    it('should PUT updated module list', async () => {
      const mockBody = { success: true, message: 'Modules updated' };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const modules = [{ name: 'finance', is_active: true }, { name: 'str', is_active: false }];
      const result = await updateTenantModules('acme', modules);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/sysadmin/tenants/acme/modules'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ modules }),
        })
      );
      expect(result).toEqual(mockBody);
    });
  });

  // ==========================================================================
  // Health Check
  // ==========================================================================

  describe('getSystemHealth', () => {
    it('should fetch system health status', async () => {
      const mockBody = {
        overall: 'healthy',
        services: [
          { service: 'database', status: 'healthy', responseTime: 12, lastChecked: '2024-01-01T00:00:00Z' },
        ],
        timestamp: '2024-01-01T00:00:00Z',
      };
      vi.mocked(global.fetch).mockResolvedValueOnce(createMockResponse({ body: mockBody }));

      const result = await getSystemHealth();

      const calledUrl = vi.mocked(global.fetch).mock.calls[0]![0] as string;
      expect(calledUrl).toContain('/api/sysadmin/health');
      expect(result).toEqual(mockBody);
    });

    it('should throw on HTTP error', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        createMockResponse({ ok: false, status: 503, body: { error: 'Service unavailable' } })
      );

      await expect(getSystemHealth()).rejects.toThrow('Service unavailable');
    });
  });
});
