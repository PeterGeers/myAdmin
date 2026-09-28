/**
 * Hook that re-resolves user.roles on every in-app tenant switch.
 *
 * The bridge between TenantContext (which owns `currentTenant`) and AuthContext
 * (which owns `user.roles`). It reads `currentTenant` from `useTenant()` and
 * `refreshRolesForTenant` from `useAuth()`, so it MUST be mounted UNDER both
 * providers — which is exactly where `AppContent` and the context tests'
 * `Harness` sit. Extracting it into a hook lets the tests exercise the REAL
 * production wiring rather than a copy of the effect.
 *
 * Co-located with the module/function refreshes so all three settle on the same
 * `currentTenant` trigger. The mount-time roles are already resolved by
 * AuthProvider's checkAuthState(), so the very first non-null tenant (the mount
 * tenant) is recorded and skipped once to avoid a redundant double-fetch that
 * would clobber the login/mount resolution; every later change is a real in-app
 * switch that must re-resolve roles.
 *
 * The effect returns a cleanup that cancels a late resolution — AuthContext's
 * refreshRolesForTenant also carries its own seq guard, so the most recently
 * selected tenant always wins under rapid switches.
 */

import { useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';

export function useTenantRoleSync(): void {
  const { refreshRolesForTenant } = useAuth();
  const { currentTenant } = useTenant();

  // `currentTenant` starts null and TenantProvider resolves it to the persisted
  // tenant after mount. That first non-null value is the mount tenant whose
  // roles checkAuthState() already resolved, so we record it and skip it once;
  // every later change is a real in-app switch that must re-resolve roles.
  const mountTenantHandledRef = useRef(false);

  useEffect(() => {
    if (!currentTenant) {
      return;
    }
    // Skip the first non-null tenant (the mount resolution already covered it)
    // to avoid a redundant double-fetch that would clobber login/mount roles.
    if (!mountTenantHandledRef.current) {
      mountTenantHandledRef.current = true;
      return;
    }

    let cancelled = false;
    void (async () => {
      await refreshRolesForTenant(currentTenant);
      if (cancelled) {
        return;
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [currentTenant, refreshRolesForTenant]);
}
