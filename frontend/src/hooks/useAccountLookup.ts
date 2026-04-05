/**
 * Hook for fetching and caching chart of accounts for the current tenant.
 * Used by AccountSelect to populate the searchable dropdown.
 */

import { useState, useEffect, useCallback } from 'react';
import { useTenant } from '../context/TenantContext';
import { authenticatedGet } from '../services/apiService';

export interface AccountOption {
  Account: string;
  AccountName: string;
}

/**
 * Fetches accounts from /api/accounts/lookup once per tenant change
 * and caches them in state. Returns a flat list for dropdowns.
 */
export function useAccountLookup() {
  const { currentTenant } = useTenant();
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAccounts = useCallback(async () => {
    if (!currentTenant) {
      setAccounts([]);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await authenticatedGet('/api/accounts/lookup');
      const data = await response.json();
      if (data.success) {
        setAccounts(data.accounts || []);
      } else {
        setError('Failed to load accounts');
      }
    } catch (err) {
      console.error('Failed to fetch account lookup:', err);
      setError('Failed to load accounts');
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [currentTenant]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  return { accounts, loading, error, refetch: fetchAccounts };
}
