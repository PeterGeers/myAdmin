/**
 * Hook for managing tenant-specific optional function access
 *
 * Fetches which optional functions are enabled for the current tenant,
 * respecting both function-level toggles and parent module activation state.
 */

import { useState, useEffect } from 'react';
import { useTenant } from '../context/TenantContext';
import { authenticatedGet } from '../services/apiService';

export interface FunctionState {
  function_name: string;
  parent_module: string;
  label: string;
  is_active: boolean;
  module_active: boolean;
  effective: boolean; // is_active AND module_active
}

/**
 * Hook to get available optional functions for the current tenant.
 *
 * Re-fetches when the active tenant changes.
 * Returns false from hasFunction() while loading or on error (safe default).
 */
export function useTenantFunctions() {
  const { currentTenant } = useTenant();
  const [functions, setFunctions] = useState<FunctionState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentTenant) {
      setFunctions([]);
      setLoading(false);
      return;
    }

    const fetchFunctions = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await authenticatedGet('/api/tenant/functions');
        const result = await response.json();
        setFunctions(result.data || []);
      } catch (err) {
        console.error('Failed to fetch tenant functions:', err);
        setError('Failed to load tenant functions');
        setFunctions([]);
      } finally {
        setLoading(false);
      }
    };

    fetchFunctions();
  }, [currentTenant]);

  const hasFunction = (functionName: string): boolean => {
    if (loading || error) {
      return false;
    }
    const fn = functions.find((f) => f.function_name === functionName);
    return fn ? fn.effective : false;
  };

  return {
    functions,
    loading,
    error,
    hasFunction,
  };
}
