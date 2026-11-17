/**
 * Fetch the Tenant-Admin surfaces derived for the current tenant.
 *
 * The backend owns applicability; the frontend renders the returned contract.
 * Mirrors useTenantModules' tenant-at-start and cancelled-response safeguards so
 * a slow response for a previous tenant can never replace the current tenant's UI.
 */

import { useEffect, useState } from 'react';
import { useTenant } from '../context/TenantContext';
import { authenticatedGet } from '../services/apiService';

export type AdminSurfaceKind = 'always' | 'module' | 'capability' | 'role';

export interface AdminSurface {
  id: string;
  kind: AdminSurfaceKind;
  order: number;
  label_key: string;
}

export interface AdminSurfacesResponse {
  tenant: string;
  admin_surfaces: AdminSurface[];
}

/** Safe baseline when the surface endpoint cannot be reached (Requirement 8.2). */
export const FALLBACK_SURFACE_IDS = ['users', 'tenant-info', 'sender', 'landing'];

export function useTenantAdminSurfaces(): {
  surfaces: AdminSurface[];
  fallbackSurfaceIds: string[];
  loading: boolean;
  error: string | null;
} {
  const { currentTenant } = useTenant();
  const [surfaces, setSurfaces] = useState<AdminSurface[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentTenant) {
      setSurfaces([]);
      setError(null);
      setLoading(false);
      return;
    }

    const tenantAtStart = currentTenant;
    let cancelled = false;

    const fetchSurfaces = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await authenticatedGet('/api/tenant/admin-surfaces', {
          tenant: tenantAtStart,
          cache: 'no-store',
        });
        if (!response.ok) {
          throw new Error(`Surface request failed (${response.status})`);
        }
        const data: AdminSurfacesResponse = await response.json();
        if (cancelled || tenantAtStart !== currentTenant) {
          return;
        }
        setSurfaces(Array.isArray(data.admin_surfaces) ? data.admin_surfaces : []);
      } catch (err) {
        if (cancelled || tenantAtStart !== currentTenant) {
          return;
        }
        console.error('Failed to fetch tenant admin surfaces:', err);
        setSurfaces([]);
        setError('Failed to load tenant admin surfaces');
      } finally {
        if (!cancelled && tenantAtStart === currentTenant) {
          setLoading(false);
        }
      }
    };

    fetchSurfaces();
    return () => {
      cancelled = true;
    };
  }, [currentTenant]);

  return {
    surfaces,
    fallbackSurfaceIds: [...FALLBACK_SURFACE_IDS],
    loading,
    error,
  };
}
