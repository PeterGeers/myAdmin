/**
 * Hook for fetching field configuration (visibility/required) per entity.
 * Used by forms and tables to show/hide fields based on tenant config.
 *
 * Reference: .kiro/specs/zzp-module/design.md §2 (Frontend: useFieldConfig)
 */

import { useState, useEffect, useCallback } from 'react';
import { FieldConfig } from '../types/zzp';
import { getFieldConfig } from '../services/fieldConfigService';

type Entity = 'contacts' | 'products' | 'invoices' | 'time_entries';

export function useFieldConfig(entity: Entity) {
  const [config, setConfig] = useState<FieldConfig>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await getFieldConfig(entity);
      if (resp.success) {
        setConfig(resp.data);
      } else {
        setError(resp.error || 'Failed to load field config');
      }
    } catch (err) {
      console.error(`Failed to fetch field config for ${entity}:`, err);
      setError('Failed to load field config');
    } finally {
      setLoading(false);
    }
  }, [entity]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const isVisible = (field: string) => config[field] !== 'hidden';
  const isRequired = (field: string) => config[field] === 'required';

  return { config, isVisible, isRequired, loading, error, refetch: fetchConfig };
}
