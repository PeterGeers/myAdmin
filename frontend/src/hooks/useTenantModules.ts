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

    const fetchModules = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const response = await authenticatedGet('/api/tenant/modules');
        const data: TenantModules = await response.json();
        setModules(data.available_modules || []);
      } catch (err) {
        console.error('Failed to fetch tenant modules:', err);
        setError('Failed to load available modules');
        setModules([]);
      } finally {
        setLoading(false);
      }
    };

    fetchModules();
  }, [currentTenant]);

  return {
    modules,
    loading,
    error,
    hasModule: (moduleName: string) => modules.includes(moduleName),
    hasFIN: modules.includes('FIN'),
    hasSTR: modules.includes('STR'),
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
