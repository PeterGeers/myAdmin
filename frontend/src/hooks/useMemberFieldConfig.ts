/**
 * Hook for fetching the Members module's resolved field configuration.
 *
 * Pairs with `frontend/src/services/fieldConfigService.ts` /
 * `frontend/src/hooks/useFieldConfig.ts` (the ZZP field-config seam) but reaches
 * the SAM Members module instead of the Flask backend: it calls
 * `getFieldConfig<FieldConfig>()` from `membersApiService.ts`, which fetches
 * `GET /members/field-config` and unwraps the module's `{ data: ... }` envelope.
 *
 * The resolved field config (fixed base ⊕ tenant overlay + scope dimensions)
 * drives the compact/full view switch on the Members Overzicht page (R7.6) and
 * carries the localized labels the `members` i18n namespace complements (R7.8).
 *
 * Return contract mirrors `useFieldConfig`'s (loading/error/refetch), adapted to
 * the module's resolved-payload response (no `{ success, data }` envelope — the
 * service already unwraps it): `{ fieldConfig, loading, error, refetch }`.
 *
 * _Requirements: R7.6, R7.8_
 */

import { useState, useEffect, useCallback } from 'react';
import type { FieldConfig } from '../types/members';
import { getFieldConfig } from '../services/membersApiService';

export function useMemberFieldConfig() {
  const [fieldConfig, setFieldConfig] = useState<FieldConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const cfg = await getFieldConfig<FieldConfig>();
      setFieldConfig(cfg ?? null);
    } catch (err) {
      console.error('Failed to fetch members field config:', err);
      setFieldConfig(null);
      setError('Failed to load field config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return { fieldConfig, loading, error, refetch: fetchConfig };
}
