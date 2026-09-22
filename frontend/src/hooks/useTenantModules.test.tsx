/**
 * Tests for useTenantModules — MEMBERS module gate (task 2.3, R7.2).
 *
 * Asserts the `hasMEMBERS` boolean mirrors the sibling `hasFIN`/`hasZZP`
 * booleans: true when the tenant's available_modules include 'MEMBERS',
 * false otherwise.
 */

import { renderHook, waitFor } from '@/test-utils';
import { createMockResponse } from '@/test-utils/mockHelpers';
import { useTenantModules, TenantModules } from './useTenantModules';
import { authenticatedGet } from '../services/apiService';

// Mock the API service (hook fetches via authenticatedGet, not raw fetch)
vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
}));

// Mock TenantContext so the hook has a current tenant and fetches modules
vi.mock('../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'h-dcn' }),
}));

const mockModulesResponse = (modules: string[]) => {
  const body: TenantModules = {
    tenant: 'h-dcn',
    available_modules: modules,
    user_module_permissions: modules,
    tenant_enabled_modules: modules,
  };
  vi.mocked(authenticatedGet).mockResolvedValue(createMockResponse({ body }));
};

describe('useTenantModules — hasMEMBERS', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
