/**
 * Tenant-Admin Dashboard — registry-driven renderer.
 *
 * Replaces the flat, hardcoded tab list with per-module conditionals (hasFIN,
 * hasMembers). The applicable surfaces are derived by the backend from tenant
 * entitlements + module admin declarations and exposed via
 * GET /api/tenant/admin-surfaces. This component maps one ordered surface array
 * into both tabs and panels — tab order and panel order cannot drift apart.
 *
 * See .kiro/specs/Common/Tenant/admin-surface-registry/ for the spec.
 */

import React, { useState, useEffect } from 'react';
import {
  Box, VStack, Tabs, TabList, TabPanels, Tab, TabPanel,
  useToast, Spinner, Text, Alert, AlertIcon,
} from '@chakra-ui/react';
import { fetchAuthSession } from 'aws-amplify/auth';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { useTenantAdminSurfaces } from '../../hooks/useTenantAdminSurfaces';
import { SurfaceComponent } from './adminSurfaceComponents';

interface TenantInfo {
  name: string;
  displayName: string;
}

interface TenantModulesResponse {
  tenant: string;
  available_modules: string[];
  user_module_permissions: string[];
  tenant_enabled_modules: string[];
}

export function TenantAdminDashboard() {
  const [loading, setLoading] = useState(true);
  const [userTenants, setUserTenants] = useState<TenantInfo[]>([]);
  const [userRoles, setUserRoles] = useState<string[]>([]);
  const [tenantModules, setTenantModules] = useState<string[]>([]);
  const toast = useToast();
  const { t } = useTypedTranslation('admin');
  const { currentTenant } = useTenant(); // Just read from context, don't manage it here
  const { surfaces: derivedSurfaces, fallbackSurfaceIds, loading: surfacesLoading, error: surfacesError } = useTenantAdminSurfaces();

  useEffect(() => {
    loadUserInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Requirement 8.2 — a failed surface fetch degrades to the baseline surfaces
  // AND is surfaced to the operator rather than failing silently.
  useEffect(() => {
    if (surfacesError) {
      toast({
        title: t('tenantAdmin.surfaceErrorTitle', 'Error loading tenant administration'),
        description: surfacesError,
        status: 'error',
        duration: 5000,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surfacesError]);

  useEffect(() => {
    if (currentTenant) {
      loadTenantModules();
    }

  }, [currentTenant]);

  const loadTenantModules = async () => {
    try {
      const response = await authenticatedGet(buildEndpoint('/api/tenant/modules'));
      const data: TenantModulesResponse = await response.json();
      setTenantModules(data.available_modules || []);
    } catch (error) {
      console.error('Error loading tenant modules:', error);
      // If error, default to empty array (no modules)
      setTenantModules([]);
    }
  };

  const loadUserInfo = async () => {
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      if (!token) {
        throw new Error('No authentication token available');
      }

      // Decode JWT to get user's tenants
      const payload = JSON.parse(atob(token.split('.')[1]));
      // Tolerant parse of custom:tenants. It may be a JSON array string
      // (e.g. '["h-dcn","x"]') OR a bare scalar string (e.g. "h-dcn").
      // Matches authService.getCurrentUserTenants semantics: a non-JSON
      // scalar is treated as a SINGLE tenant (no comma-splitting).
      const rawTenants = payload['custom:tenants'];
      let tenants: string[] = [];
      if (rawTenants) {
        try {
          const parsed = JSON.parse(rawTenants);
          tenants = Array.isArray(parsed) ? parsed : [String(parsed)];
        } catch {
          tenants = [rawTenants];
        }
      }

      // Get merged roles (global + per-tenant) from API
      let roles: string[] = [];
      try {
        const tenant = currentTenant || (tenants.length > 0 ? tenants[0] : '');
        const resp = await authenticatedGet('/api/auth/me', tenant ? { tenant } : {});
        if (resp.ok) {
          const data = await resp.json();
          roles = data.roles || [];
        }
      } catch {
        // Fallback to JWT roles
        roles = payload['cognito:groups'] || [];
      }

      // Check if user has Tenant_Admin role
      if (!roles.includes('Tenant_Admin')) {
        toast({
          title: t('tenantAdmin.accessDenied'),
          description: t('tenantAdmin.noPermissions'),
          status: 'error',
          duration: 5000,
        });
        return;
      }

      setUserRoles(roles);

      // Convert tenant names to TenantInfo objects
      const tenantInfos: TenantInfo[] = tenants.map((t: string) => ({
        name: t,
        displayName: t
      }));

      setUserTenants(tenantInfos);

    } catch (error) {
      toast({
        title: 'Error loading user information',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">{t('tenantAdmin.loading')}</Text>
        </VStack>
      </Box>
    );
  }

  if (!userRoles.includes('Tenant_Admin')) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="error">
          <AlertIcon />
          {t('tenantAdmin.accessDenied')}: {t('tenantAdmin.noPermissions')}
        </Alert>
      </Box>
    );
  }

  if (userTenants.length === 0) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="warning">
          <AlertIcon />
          {t('tenantAdmin.noTenants')}
        </Alert>
      </Box>
    );
  }

  if (!currentTenant) {
    return (
      <Box minH="100vh" bg="gray.900" p={8}>
        <Alert status="info">
          <AlertIcon />
          {t('tenantAdmin.selectTenant')}
        </Alert>
      </Box>
    );
  }

  const surfaces = surfacesLoading || surfacesError
    ? fallbackSurfaceIds.map((id) => ({ id, kind: 'always' as const, order: 0, label_key: `tenantAdmin.tabs.${id}` }))
    : derivedSurfaces;

  return (
    <Box minH="100vh" bg="gray.900" p={6}>
      <VStack spacing={6} align="stretch">
        {/* Tabs - key forces re-render when tenant changes */}
        <Tabs key={currentTenant} colorScheme="orange" variant="soft-rounded" size="sm" isLazy>
          <TabList>
            {surfaces.map((s) => (
              <Tab
                key={s.id}
                color="gray.300"
                _selected={{ color: 'orange.400', bg: 'gray.800' }}
              >
                {t(s.label_key)}
              </Tab>
            ))}
          </TabList>

          <TabPanels>
            {surfaces.map((s) => (
              <TabPanel key={s.id} px={0}>
                <SurfaceComponent surface={s} tenant={currentTenant} tenantModules={tenantModules} />
              </TabPanel>
            ))}
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
}

export default TenantAdminDashboard;
