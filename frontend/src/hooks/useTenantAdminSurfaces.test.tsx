/**
 * Tests for useTenantAdminSurfaces.
 *
 * Feature: admin-surface-registry
 * Property 8 — tenant-switch isolation: a superseded response for a tenant the
 *   user has switched away from can never replace the current tenant's surfaces.
 * Property 9 — safe degradation: a failed/non-OK fetch yields no surfaces, an
 *   error, and the baseline fallback id set (never module/capability surfaces).
 *
 * Validates: Requirements 5.5, 8.2, 4.7
 */

import { renderHook, waitFor } from '@testing-library/react';
import { authenticatedGet } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import { useTenantAdminSurfaces, FALLBACK_SURFACE_IDS } from './useTenantAdminSurfaces';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
}));

vi.mock('../context/TenantContext', () => ({
  useTenant: vi.fn(),
}));

const mockAuthenticatedGet = vi.mocked(authenticatedGet);
const mockUseTenant = vi.mocked(useTenant);

function tenantCtx(currentTenant: string | null) {
  return {
    currentTenant,
    availableTenants: ['GoodwinSolutions', 'HDCN'],
    setCurrentTenant: vi.fn(),
    hasMultipleTenants: true,
  };
}

const SURFACES_BY_TENANT: Record<string, string[]> = {
  GoodwinSolutions: ['users', 'financial', 'storage'],
  HDCN: ['users', 'members'],
};

function surfacesBody(ids: string[]) {
  return {
    tenant: 'ignored',
    admin_surfaces: ids.map((id, index) => ({
      id,
      kind: 'module',
      order: index,
      label_key: `tenantAdmin.tabs.${id}`,
    })),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('useTenantAdminSurfaces — surface fetch', () => {
  beforeEach(() => {
    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));
  });

  it('returns the derived surfaces for the current tenant', async () => {
    mockAuthenticatedGet.mockResolvedValue(
      createMockResponse({ body: surfacesBody(['users', 'financial']) }),
    );
    const { result } = renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.surfaces.map((s) => s.id)).toEqual(['users', 'financial']);
    expect(result.current.error).toBeNull();
  });

  it('requests the surface endpoint with the current tenant and no-store', async () => {
    mockAuthenticatedGet.mockResolvedValue(
      createMockResponse({ body: surfacesBody(['users']) }),
    );
    renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(mockAuthenticatedGet).toHaveBeenCalledTimes(1));
    const [endpoint, options] = mockAuthenticatedGet.mock.calls[0];
    expect(endpoint).toBe('/api/tenant/admin-surfaces');
    expect(options?.tenant).toBe('GoodwinSolutions');
    expect(options?.cache).toBe('no-store');
  });

  it('does not fetch when there is no current tenant', async () => {
    mockUseTenant.mockReturnValue(tenantCtx(null));
    const { result } = renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockAuthenticatedGet).not.toHaveBeenCalled();
    expect(result.current.surfaces).toEqual([]);
  });
});

describe('useTenantAdminSurfaces — Property 9: safe degradation', () => {
  beforeEach(() => {
    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));
  });

  it('reports an error and no surfaces on a non-OK response', async () => {
    mockAuthenticatedGet.mockResolvedValue(
      createMockResponse({ ok: false, status: 500, statusText: 'Server Error' }),
    );
    const { result } = renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeTruthy();
    expect(result.current.surfaces).toEqual([]);
  });

  it('reports an error and no surfaces on a thrown fetch', async () => {
    mockAuthenticatedGet.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeTruthy();
    expect(result.current.surfaces).toEqual([]);
  });

  it('always exposes the baseline fallback ids (never module/capability ones)', async () => {
    mockAuthenticatedGet.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fallbackSurfaceIds).toEqual(FALLBACK_SURFACE_IDS);
    expect(FALLBACK_SURFACE_IDS).not.toContain('financial');
    expect(FALLBACK_SURFACE_IDS).not.toContain('members');
    expect(FALLBACK_SURFACE_IDS).not.toContain('storage');
  });
});

describe('useTenantAdminSurfaces — Property 8: tenant-switch isolation', () => {
  it('switching tenant refetches and replaces the surface set', async () => {
    mockAuthenticatedGet.mockImplementation(async (_endpoint, options) => {
      const tenant = options?.tenant ?? 'GoodwinSolutions';
      return createMockResponse({ body: surfacesBody(SURFACES_BY_TENANT[tenant] ?? []) });
    });

    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));
    const { result, rerender } = renderHook(() => useTenantAdminSurfaces());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.surfaces.map((s) => s.id)).toContain('financial');

    mockUseTenant.mockReturnValue(tenantCtx('HDCN'));
    rerender();

    await waitFor(() => {
      expect(result.current.surfaces.map((s) => s.id)).toContain('members');
    });
    expect(result.current.surfaces.map((s) => s.id)).not.toContain('financial');
    expect(mockAuthenticatedGet).toHaveBeenCalledTimes(2);
  });

  it('discards a superseded response so it cannot clobber the current tenant', async () => {
    let releaseSlow: (r: Response) => void = () => {};
    const slow = new Promise<Response>((resolve) => {
      releaseSlow = resolve;
    });

    mockAuthenticatedGet.mockImplementationOnce(() => slow);
    mockAuthenticatedGet.mockImplementationOnce(async () =>
      createMockResponse({ body: surfacesBody(SURFACES_BY_TENANT.HDCN) }),
    );

    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));
    const { result, rerender } = renderHook(() => useTenantAdminSurfaces());

    mockUseTenant.mockReturnValue(tenantCtx('HDCN'));
    rerender();

    await waitFor(() =>
      expect(result.current.surfaces.map((s) => s.id)).toContain('members'),
    );

    // Let the stale GoodwinSolutions response resolve — it must be ignored.
    releaseSlow(
      createMockResponse({ body: surfacesBody(SURFACES_BY_TENANT.GoodwinSolutions) }),
    );

    await waitFor(() => expect(mockAuthenticatedGet).toHaveBeenCalledTimes(2));
    expect(result.current.surfaces.map((s) => s.id)).toContain('members');
    expect(result.current.surfaces.map((s) => s.id)).not.toContain('financial');
  });
});
