import React, { useState, useEffect } from 'react';
import {
  Box, VStack, Tabs, TabList, TabPanels, Tab, TabPanel,
  useToast, Spinner, Text, Alert, AlertIcon
} from '@chakra-ui/react';
import { fetchAuthSession } from 'aws-amplify/auth';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';
import { PivotBuilderWithPreview } from '../pivot/PivotBuilderWithPreview';
import MediaAssetAdminPage from '../../pages/MediaAssetAdminPage';
import UserManagement from './UserManagement';
import TemplateManagement from './TemplateManagement/TemplateManagement';
import StorageTab from './StorageTab';
import FinancialTab from './FinancialTab';
import TenantInfoTab from './TenantInfoTab';
import SenderSettingsTab from './SenderSettingsTab';
import MemberSenderIdentitiesTab from './MemberSenderIdentitiesTab';
import AdvancedTab from './AdvancedTab';
import FunctionsTab from './FunctionsTab';
import { LandingPageEditor } from './LandingPage';
// application-form-builder task 2.1 adds the ApplicationFormBuilder authoring view + its
// barrel export; this sub-tab (task 2.2) wires it in referencing that expected export name.
import {
  MembersConfigEditor,
  MembersMailConfigEditor,
  ApplicationFormBuilder,
} from './MembersConfig';

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
  const { t, i18n } = useTypedTranslation('admin');
  // Nederlands-default language for the Members admin sub-tab labels (house `t(nl,en)` style).
  const membersLang: 'nl' | 'en' = i18n.language?.startsWith('nl') ? 'nl' : 'en';
  const { currentTenant } = useTenant(); // Just read from context, don't manage it here

  useEffect(() => {
    loadUserInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const hasFIN = tenantModules.includes('FIN');
  const hasMembers = tenantModules.includes('MEMBERS');

  return (
    <Box minH="100vh" bg="gray.900" p={6}>
      <VStack spacing={6} align="stretch">
        {/* Tabs - key forces re-render when tenant changes */}
        <Tabs key={currentTenant} colorScheme="orange" variant="enclosed" isLazy>
          <TabList>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              {t('tenantAdmin.tabs.users')}
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              ⚡ {t('tenantAdmin.tabs.functions')}
            </Tab>
            {hasFIN && (
              <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
                💰 {t('tenantAdmin.tabs.financial')}
              </Tab>
            )}
            {hasMembers && (
              <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
                👥 {t('tenantAdmin.tabs.membersConfig', 'Members')}
              </Tab>
            )}
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              📁 {t('tenantAdmin.tabs.storage')}
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              🗄️ {t('tenantAdmin.tabs.mediaAssets', 'Media Assets')}
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              {t('tenantAdmin.tabs.templates')}
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              🏢 {t('tenantAdmin.tabs.tenantInfo')}
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              ✉️ {t('tenantAdmin.tabs.senderSettings')}
            </Tab>
            {/* The Members sender-identities surface now lives inside the Members → Mail
                sub-tab (task 7.1 single home), so there is NO standalone top-level tab for it. */}
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              📊 {t('tenantAdmin.tabs.pivotViews')}
            </Tab>
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              🌐 {t('tenantAdmin.tabs.landingPage')}
            </Tab>
            {/* Advanced (raw parameters) — any Tenant_Admin of the current tenant.
                Reaching this dashboard already requires Tenant_Admin (loadUserInfo +
                the render guards), and the backend scopes/filters by tenant + active
                modules and masks secrets, so no extra SysAdmin gate belongs here. */}
            <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
              🔧 {t('tenantAdmin.tabs.advanced')}
            </Tab>
          </TabList>

          <TabPanels>
            <TabPanel>
              <UserManagement tenant={currentTenant} />
            </TabPanel>
            <TabPanel>
              <FunctionsTab tenant={currentTenant} />
            </TabPanel>
            {hasFIN && (
              <TabPanel>
                <FinancialTab tenant={currentTenant} />
              </TabPanel>
            )}
            {hasMembers && (
              <TabPanel>
                {/* Members admin area: the field-config editor + Mail + Application-form
                    authoring surfaces as sibling sections under the same hasMembers gate.
                    (The standalone membership-type catalog tab was retired in spec 03b —
                    membership_type is now a normal enum field authored inline.) */}
                <Tabs colorScheme="orange" variant="soft-rounded" size="sm" isLazy>
                  <TabList>
                    <Tab color="gray.300" _selected={{ color: 'orange.400', bg: 'gray.800' }}>
                      {membersLang === 'nl' ? 'Veldconfiguratie' : 'Field configuration'}
                    </Tab>
                    <Tab
                      color="gray.300"
                      _selected={{ color: 'orange.400', bg: 'gray.800' }}
                      data-testid="members-admin-mail-tab"
                    >
                      {membersLang === 'nl' ? 'Mail' : 'Mail'}
                    </Tab>
                    <Tab
                      color="gray.300"
                      _selected={{ color: 'orange.400', bg: 'gray.800' }}
                      data-testid="members-admin-application-form-tab"
                    >
                      {membersLang === 'nl' ? 'Aanmeldformulier' : 'Application form'}
                    </Tab>
                  </TabList>
                  <TabPanels>
                    <TabPanel px={0}>
                      <MembersConfigEditor tenant={currentTenant} />
                    </TabPanel>
                    <TabPanel px={0}>
                      {/* The typed Mail function authors the SAM-owned config#mail scalars
                          (single door, task 7.1) with the sender-identities surface co-located
                          below — the latter KEEPS its own Flask sender-identities route and is
                          NOT folded into the config#mail put (three-surface model). */}
                      <VStack align="stretch" spacing={8}>
                        <MembersMailConfigEditor tenant={currentTenant} />
                        <MemberSenderIdentitiesTab tenant={currentTenant} />
                      </VStack>
                    </TabPanel>
                    <TabPanel px={0}>
                      {/* Application-form authoring view (spec 11): a focused surface over the
                          same config#fields / config#mail rows the Field-config + Mail sub-tabs
                          own. Component authored by task 2.1. */}
                      <ApplicationFormBuilder tenant={currentTenant} />
                    </TabPanel>
                  </TabPanels>
                </Tabs>
              </TabPanel>
            )}
            <TabPanel>
              <StorageTab tenant={currentTenant} />
            </TabPanel>
            <TabPanel>
              <MediaAssetAdminPage />
            </TabPanel>
            <TabPanel>
              <TemplateManagement />
            </TabPanel>
            <TabPanel>
              <TenantInfoTab tenant={currentTenant} />
            </TabPanel>
            <TabPanel>
              <SenderSettingsTab tenant={currentTenant} />
            </TabPanel>
            {/* The standalone MemberSenderIdentitiesTab panel was removed — it is co-located in
                the Members → Mail sub-tab below so the mail concern has one home (task 7.1). */}
            <TabPanel>
              <PivotBuilderWithPreview />
            </TabPanel>
            <TabPanel>
              <LandingPageEditor tenant={currentTenant} tenantModules={tenantModules} />
            </TabPanel>
            <TabPanel>
              <AdvancedTab tenant={currentTenant} />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </VStack>
    </Box>
  );
}

export default TenantAdminDashboard;
