/**
 * Tests for useTenantModules.
 *
 * Two concerns:
 *  1. Module-gate booleans (hasMEMBERS et al.) mirror the tenant's
 *     available_modules (task 2.3, R7.2).
 *  2. Tenant-switch freshness (spec: Common/tenant-switch-menu-refresh-fix):
 *     switching currentTenant refetches and flips the flags without a reload,
 *     the request carries the current tenant explicitly (Req 2.1) and is
 *     non-cacheable (Req 3), and a superseded response can't clobber newer state.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { authenticatedGet } from '../services/apiService';
import { useTenant } from '../context/TenantContext';
import { useTenantModules, TenantModules } from './useTenantModules';
import { createMockResponse } from '@/test-utils/mockHelpers';

vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
}));

// Mutable current-tenant so individual tests can drive a switch.
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

const mockModulesResponse = (modules: string[]) => {
  const body: TenantModules = {
    tenant: 'h-dcn',
    available_modules: modules,
    user_module_permissions: modules,
    tenant_enabled_modules: modules,
  };
  mockAuthenticatedGet.mockResolvedValue(createMockResponse({ body }));
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('useTenantModules — hasMEMBERS gate', () => {
  beforeEach(() => {
    mockUseTenant.mockReturnValue(tenantCtx('h-dcn'));
  });

  it('hasMEMBERS is true for a MEMBERS-entitled tenant', async () => {
    mockModulesResponse(['MEMBERS', 'FIN']);
    const { result } = renderHook(() => useTenantModules());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasMEMBERS).toBe(true);
  });

  it('hasMEMBERS is false when the tenant is not MEMBERS-entitled', async () => {
    mockModulesResponse(['FIN', 'ZZP']);
    const { result } = renderHook(() => useTenantModules());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasMEMBERS).toBe(false);
  });

  it('hasMEMBERS is false when the tenant has no modules', async () => {
    mockModulesResponse([]);
    const { result } = renderHook(() => useTenantModules());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasMEMBERS).toBe(false);
  });
});

// Module set per tenant for the switch scenario. HDCN has no MEMBERS / no STR —
// the exact "stale menu could offer Members for a no-MEMBERS tenant" case.
const MODULES_BY_TENANT: Record<string, string[]> = {
  GoodwinSolutions: ['FIN', 'STR', 'MEMBERS'],
  HDCN: ['FIN', 'ZZP'],
};

describe('useTenantModules — tenant-switch freshness', () => {
  beforeEach(() => {
    // apiService derives X-Tenant from the passed tenant option, falling back to
    // localStorage; answer per whichever the request carries so the mock is honest.
    mockAuthenticatedGet.mockImplementation(async (_endpoint, options) => {
      const t = options?.tenant ?? localStorage.getItem('selectedTenant') ?? 'GoodwinSolutions';
      return createMockResponse({ body: { available_modules: MODULES_BY_TENANT[t] ?? [] } });
    });
  });

  it('refetches and flips flags when currentTenant changes (no reload)', async () => {
    localStorage.setItem('selectedTenant', 'GoodwinSolutions');
    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));

    const { result, rerender } = renderHook(() => useTenantModules());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasMEMBERS).toBe(true);
    expect(result.current.hasZZP).toBe(false);

    localStorage.setItem('selectedTenant', 'HDCN');
    mockUseTenant.mockReturnValue(tenantCtx('HDCN'));
    rerender();

    await waitFor(() => {
      expect(result.current.hasZZP).toBe(true);
      expect(result.current.hasMEMBERS).toBe(false);
    });
    expect(mockAuthenticatedGet).toHaveBeenCalledTimes(2);
  });

  it('sends the current tenant explicitly on the request (Req 2.1)', async () => {
    localStorage.setItem('selectedTenant', 'GoodwinSolutions');
    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));

    const { rerender } = renderHook(() => useTenantModules());
    await waitFor(() => expect(mockAuthenticatedGet).toHaveBeenCalledTimes(1));

    localStorage.setItem('selectedTenant', 'HDCN');
    mockUseTenant.mockReturnValue(tenantCtx('HDCN'));
    rerender();
    await waitFor(() => expect(mockAuthenticatedGet).toHaveBeenCalledTimes(2));

    const secondOpts = mockAuthenticatedGet.mock.calls[1][1] as { tenant?: string } | undefined;
    expect(secondOpts?.tenant).toBe('HDCN');
  });

  it('requests the modules endpoint with no-store cache semantics (Req 3)', async () => {
    localStorage.setItem('selectedTenant', 'GoodwinSolutions');
    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));

    renderHook(() => useTenantModules());
    await waitFor(() => expect(mockAuthenticatedGet).toHaveBeenCalledTimes(1));

    const firstOpts = mockAuthenticatedGet.mock.calls[0][1] as { cache?: RequestCache } | undefined;
    expect(firstOpts?.cache).toBe('no-store');
  });

  it('discards a superseded response so it cannot clobber the current tenant (Req 2.3)', async () => {
    // First tenant's response is delayed; second tenant's resolves immediately.
    // The stale (delayed) GoodwinSolutions response must NOT overwrite HDCN state.
    let releaseSlow: (r: Response) => void = () => { };
    const slow = new Promise<Response>((resolve) => { releaseSlow = resolve; });

    mockAuthenticatedGet.mockImplementationOnce(() => slow);
    mockAuthenticatedGet.mockImplementationOnce(async () =>
      createMockResponse({ body: { available_modules: MODULES_BY_TENANT.HDCN } }),
    );

    localStorage.setItem('selectedTenant', 'GoodwinSolutions');
    mockUseTenant.mockReturnValue(tenantCtx('GoodwinSolutions'));
    const { result, rerender } = renderHook(() => useTenantModules());

    // Switch to HDCN before the first (slow) response resolves.
    localStorage.setItem('selectedTenant', 'HDCN');
    mockUseTenant.mockReturnValue(tenantCtx('HDCN'));
    rerender();

    await waitFor(() => expect(result.current.hasZZP).toBe(true)); // HDCN applied
    expect(result.current.hasMEMBERS).toBe(false);

    // Now let the stale GoodwinSolutions response resolve — it must be ignored.
    releaseSlow(createMockResponse({ body: { available_modules: MODULES_BY_TENANT.GoodwinSolutions } }));

    await waitFor(() => expect(mockAuthenticatedGet).toHaveBeenCalledTimes(2));
    // State still reflects HDCN, not the late GoodwinSolutions payload.
    expect(result.current.hasMEMBERS).toBe(false);
    expect(result.current.hasZZP).toBe(true);
  });
});
