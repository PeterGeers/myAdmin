/**
 * Hook for managing tenant-specific module access
 * 
 * Fetches which modules (FIN, STR) are available for the current tenant
 * based on both tenant configuration and user permissions.
 */

import { useState, useEffect } from 'react';
import { useTenant } from '../context/TenantContext';
import { authenticatedGet } from '../services/apiService';

export interface TenantModules {
  tenant: string;
  available_modules: string[];
  user_module_permissions: string[];
  tenant_enabled_modules: string[];
}

export interface AllTenantModules {
  tenants: Record<string, string[]>;
  user_module_permissions: string[];
}

/**
 * Hook to get available modules for current tenant
 */
export function useTenantModules() {
  const { currentTenant } = useTenant();
  const [modules, setModules] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentTenant) {
      setModules([]);
      setLoading(false);
      return;
    }

    // Capture the tenant that triggered this effect so the request targets it
    // explicitly and a superseded response can be discarded (see below).
    const tenantAtStart = currentTenant;
    let cancelled = false;

    const fetchModules = async () => {
      try {
        setLoading(true);
        setError(null);

        // Pass the tenant explicitly (so X-Tenant matches the effect's tenant,
        // not a lagging localStorage read) and use no-store so a tenant switch
        // never replays a previous tenant's cached response — the URL is
        // identical across tenants, so an HTTP cache would otherwise serve stale
        // module lists.
        const response = await authenticatedGet('/api/tenant/modules', {
          tenant: tenantAtStart,
          cache: 'no-store',
        });
        const data: TenantModules = await response.json();
        // Ignore results for a tenant we've since switched away from.
        if (cancelled || tenantAtStart !== currentTenant) {
          return;
        }
        setModules(data.available_modules || []);
      } catch (err) {
        if (cancelled) {
          return;
        }
        console.error('Failed to fetch tenant modules:', err);
        setError('Failed to load available modules');
        setModules([]);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchModules();

    return () => {
      cancelled = true;
    };
  }, [currentTenant]);

  return {
    modules,
    loading,
    error,
    hasModule: (moduleName: string) => modules.includes(moduleName),
    hasFIN: modules.includes('FIN'),
    hasSTR: modules.includes('STR'),
    hasZZP: modules.includes('ZZP'),
    hasMEMBERS: modules.includes('MEMBERS'),
  };
}

/**
 * Hook to get modules for all user's tenants
 */
export function useAllTenantModules() {
  const [tenantModules, setTenantModules] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAllModules = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await authenticatedGet('/api/tenant/modules/all');
        const data: AllTenantModules = await response.json();
        setTenantModules(data.tenants || {});
      } catch (err) {
        console.error('Failed to fetch all tenant modules:', err);
        setError('Failed to load tenant modules');
        setTenantModules({});
      } finally {
        setLoading(false);
      }
    };

    fetchAllModules();
  }, []);

  return {
    tenantModules,
    loading,
    error,
    getTenantModules: (tenant: string) => tenantModules[tenant] || [],
  };
}
