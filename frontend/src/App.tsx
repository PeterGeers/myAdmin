import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { ChakraProvider, Box, VStack, Heading, Button, HStack, Flex, Text, Alert, AlertIcon, AlertDescription, CloseButton, Link as ChakraLink, Spinner } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
// Critical path — keep eagerly loaded
import Login from './pages/Login';
import ProtectedRoute from './components/ProtectedRoute';
import TenantSelector from './components/TenantSelector';
import UserMenu from './components/UserMenu';
import { LanguageSelector } from './components/LanguageSelector';
import theme from './theme';
import { AuthProvider, useAuth } from './context/AuthContext';
import { TenantProvider } from './context/TenantContext';
import { useTenantModules } from './hooks/useTenantModules';
import { useTenantFunctions } from './hooks/useTenantFunctions';
import { listPasskeys, isPasskeySupported } from './services/authService';
import { HelpButton } from './components/help';
import { MenuGroup } from './components/MenuGroup';
import { buildApiUrl } from './config';
import { MainMenu } from './components/MainMenu';
import {
  PDFUploadForm,
  BankingProcessor,
  FINReports,
  AssetList,
  BudgetPage,
  TransactionsPage,
  CheckAccountsPage,
  CheckReferencePage,
  STRChannelRevenuePage,
  STRProcessor,
  STRInvoice,
  STRPricing,
  STRReports,
  ZZPContacts,
  ZZPProducts,
  ZZPInvoices,
  ZZPTimeTracking,
  ZZPTrips,
  ZZPDebtors,
  ZZPTripQuick,
  ZZPTripImport,
  TenantAdminDashboard,
  SysAdminDashboard,
  PasskeySettings,
  PublicLandingPage,
  resolveInitialPage,
  type PageType,
} from './appPages';

function AppContent() {
  const { t } = useTranslation();
  const [currentPage, setCurrentPage] = useState<PageType>(resolveInitialPage);
  const [status, setStatus] = useState({ mode: 'Production', database: '', folder: '' });
  const { isAuthenticated, loading, user, logout, refreshUserRoles } = useAuth();
  const { hasFIN, hasSTR, hasZZP, loading: modulesLoading } = useTenantModules();
  const { hasFunction } = useTenantFunctions();
  const [showPasskeyPrompt, setShowPasskeyPrompt] = useState(false);

  // Check if user should be prompted to register a passkey
  const checkPasskeyPrompt = useCallback(async () => {
    if (!isAuthenticated || !isPasskeySupported()) return;
    if (localStorage.getItem('passkey_prompt_dismissed') === 'true') return;

    try {
      const credentials = await listPasskeys();
      if (credentials.length === 0) {
        setShowPasskeyPrompt(true);
      }
    } catch {
      // Silently ignore — user may not have permissions or session may be initializing
    }
  }, [isAuthenticated]);

  useEffect(() => {
    checkPasskeyPrompt();
  }, [checkPasskeyPrompt]);

  const dismissPasskeyPrompt = () => {
    setShowPasskeyPrompt(false);
    localStorage.setItem('passkey_prompt_dismissed', 'true');
  };

  useEffect(() => {
    fetch(buildApiUrl('/api/status'))
      .then(res => res.json())
      .then(data => setStatus(data))
      .catch(() => setStatus({ mode: 'Production', database: 'finance', folder: 'Facturen' }));
  }, []);

  // Redirect to menu if user loses module access after tenant switch
  // Only redirect when authenticated and modules have been loaded (not during initial no-tenant state)
  useEffect(() => {
    if (!modulesLoading && isAuthenticated && (hasFIN || hasSTR || hasZZP)) {
      const isZZPPage = currentPage === 'zzp-invoices' || currentPage === 'zzp-contacts' || currentPage === 'zzp-products' || currentPage === 'zzp-time-tracking' || currentPage === 'zzp-trips' || currentPage === 'zzp-trip-quick' || currentPage === 'zzp-trip-import' || currentPage === 'zzp-debtors';
      const isSTRPage = currentPage === 'str' || currentPage === 'str-invoice' || currentPage === 'str-pricing' || currentPage === 'str-reports';
      const isFINPage = currentPage === 'pdf' || currentPage === 'banking' || currentPage === 'powerbi' || currentPage === 'fin-reports' || currentPage === 'assets' || currentPage === 'budget' || currentPage === 'transactions' || currentPage === 'check-accounts' || currentPage === 'check-reference' || currentPage === 'str-channel-revenue';

      // If on STR page but no STR access, redirect to menu
      if (isSTRPage && !hasSTR) {
        setCurrentPage('menu');
      }
      // If on FIN page but no FIN access, redirect to menu
      if (isFINPage && !hasFIN) {
        setCurrentPage('menu');
      }
      // If on ZZP page but no ZZP access, redirect to menu
      if (isZZPPage && !hasZZP) {
        setCurrentPage('menu');
      }
    }
  }, [hasSTR, hasFIN, hasZZP, modulesLoading, isAuthenticated, currentPage]);

  // Show login page if not authenticated
  if (!isAuthenticated && !loading) {
    return <Login onLoginSuccess={() => { refreshUserRoles(); }} />;
  }

  // Show loading state while checking authentication
  if (loading) {
    return (
      <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Heading color="orange.400" size="lg">{t('common:status.loading')}</Heading>
          <Text color="gray.400">{t('common:messages.checkingAuth', 'Checking authentication status')}</Text>
        </VStack>
      </Box>
    );
  }

  const renderPageHeader = (title: string, options?: { hideTenant?: boolean; showLanguage?: boolean }) => (
    <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
      <Flex wrap="wrap" justify="space-between" align="center" gap={2}>
        <HStack minW="0" flex="1">
          <Button size="sm" colorScheme="orange" flexShrink={0} onClick={() => setCurrentPage('menu')}>← {t('common:navigation.back')}</Button>
          <Heading color="orange.400" size={{ base: 'sm', md: 'lg' }} noOfLines={2}>{title}</Heading>
        </HStack>
        <HStack spacing={2} flexShrink={0}>
          {options?.showLanguage && <LanguageSelector />}
          <TenantSelector size="sm" hide={options?.hideTenant} />
          <HelpButton page={currentPage} />
          <UserMenu onLogout={logout} onSettings={() => setCurrentPage('settings')} mode={status.mode} />
        </HStack>
      </Flex>
    </Box>
  );

  const renderPage = () => {
    switch (currentPage) {
      case 'pdf':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📄 ${t('common:navigation.modules.importInvoices')}`)}
              <PDFUploadForm />
            </Box>
          </ProtectedRoute>
        );

      case 'banking':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🏦 ${t('common:navigation.modules.importBanking')}`)}
              <BankingProcessor />
            </Box>
          </ProtectedRoute>
        );
      case 'str':
        return (
          <ProtectedRoute
            requiredRoles={['STR_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🏠 ${t('common:navigation.modules.importSTRBookings')}`)}
              <STRProcessor />
            </Box>
          </ProtectedRoute>
        );
      case 'str-invoice':
        return (
          <ProtectedRoute
            requiredRoles={['STR_CRUD', 'STR_Read', 'STR_Export']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🧾 ${t('common:navigation.modules.strInvoiceGenerator')}`)}
              <STRInvoice />
            </Box>
          </ProtectedRoute>
        );

      case 'str-pricing':
        return (
          <ProtectedRoute
            requiredRoles={['STR_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`💰 ${t('common:navigation.modules.strPricingModel')}`)}
              <STRPricing />
            </Box>
          </ProtectedRoute>
        );

      case 'system-admin':
        return (
          <ProtectedRoute
            requiredRoles={['SysAdmin']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`⚙️ ${t('common:navigation.modules.systemAdministration')}`, { hideTenant: true })}
              <SysAdminDashboard />
            </Box>
          </ProtectedRoute>
        );

      case 'tenant-admin':
        return (
          <ProtectedRoute
            requiredRoles={['Tenant_Admin']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🏢 ${t('common:navigation.modules.tenantAdministration')}`)}
              <TenantAdminDashboard />
            </Box>
          </ProtectedRoute>
        );

      case 'media-asset-admin':
        return (
          <ProtectedRoute
            requiredRoles={['Tenant_Admin', 'SysAdmin']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🏢 Tenant Administration`)}
              <TenantAdminDashboard />
            </Box>
          </ProtectedRoute>
        );

      case 'powerbi':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read', 'Finance_Export']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📊 ${t('common:navigation.modules.finReports')}`)}
              <FINReports />
            </Box>
          </ProtectedRoute>
        );

      case 'fin-reports':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read', 'Finance_Export']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📊 ${t('common:navigation.modules.finReports')}`)}
              <FINReports />
            </Box>
          </ProtectedRoute>
        );

      case 'assets':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🏗️ ${t('common:navigation.modules.assets', 'Asset Administration')}`)}
              <Box p={6}>
                <AssetList />
              </Box>
            </Box>
          </ProtectedRoute>
        );

      case 'budget':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`💰 ${t('common:navigation.modules.budgetGroup', 'Budget')}`)}
              <Box p={6}>
                <BudgetPage />
              </Box>
            </Box>
          </ProtectedRoute>
        );

      case 'transactions':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📋 ${t('common:navigation.modules.transactions', 'Transactions')}`)}
              <TransactionsPage />
            </Box>
          </ProtectedRoute>
        );

      case 'check-accounts':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`✅ ${t('common:navigation.modules.checkAccounts', 'Check Accounts')}`)}
              <CheckAccountsPage />
            </Box>
          </ProtectedRoute>
        );

      case 'check-reference':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD', 'Finance_Read']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`✅ ${t('common:navigation.modules.checkReference', 'Check Reference')}`)}
              <CheckReferencePage />
            </Box>
          </ProtectedRoute>
        );

      case 'str-channel-revenue':
        return (
          <ProtectedRoute
            requiredRoles={['Finance_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📺 ${t('common:navigation.modules.strChannelRevenue', 'STR Channel Revenue')}`)}
              <STRChannelRevenuePage />
            </Box>
          </ProtectedRoute>
        );

      case 'str-reports':
        return (
          <ProtectedRoute
            requiredRoles={['STR_CRUD', 'STR_Read', 'STR_Export']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📈 ${t('common:navigation.modules.strReports')}`)}
              <STRReports />
            </Box>
          </ProtectedRoute>
        );



      case 'zzp-invoices':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🧾 ${t('zzp:invoices.title')}`)}
              <ZZPInvoices />
            </Box>
          </ProtectedRoute>
        );

      case 'zzp-contacts':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`👥 ${t('zzp:contacts.title')}`)}
              <ZZPContacts />
            </Box>
          </ProtectedRoute>
        );

      case 'zzp-products':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📦 ${t('zzp:products.title')}`)}
              <ZZPProducts />
            </Box>
          </ProtectedRoute>
        );

      case 'zzp-time-tracking':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`⏱️ ${t('zzp:timeTracking.title')}`)}
              <ZZPTimeTracking />
            </Box>
          </ProtectedRoute>
        );

      case 'zzp-trips':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🚗 ${t('zzp:trips.title')}`)}
              <ZZPTrips />
            </Box>
          </ProtectedRoute>
        );

      case 'zzp-trip-import':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`📥 ${t('zzp:trips.import.title', 'Ritten Importeren')}`)}
              <ZZPTripImport />
            </Box>
          </ProtectedRoute>
        );

      case 'zzp-trip-quick':
        // Standalone layout — no sidebar, no page header chrome
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <ZZPTripQuick />
          </ProtectedRoute>
        );

      case 'zzp-debtors':
        return (
          <ProtectedRoute
            requiredRoles={['ZZP_Read', 'ZZP_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`💰 ${t('zzp:debtors.title')}`)}
              <ZZPDebtors />
            </Box>
          </ProtectedRoute>
        );

      case 'settings':
        return (
          <ProtectedRoute onLoginSuccess={() => setCurrentPage('menu')}>
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`⚙️ ${t('common:navigation.modules.settings', 'Settings')}`)}
              <Box p={6} maxW="800px" mx="auto">
                <PasskeySettings />
              </Box>
            </Box>
          </ProtectedRoute>
        );

      default:
        return (
          <ProtectedRoute onLoginSuccess={() => setCurrentPage('menu')}>
            <MainMenu
              currentPage={currentPage}
              setCurrentPage={setCurrentPage}
              user={user}
              status={status}
              logout={logout}
              hasFIN={hasFIN}
              hasSTR={hasSTR}
              hasZZP={hasZZP}
              hasFunction={hasFunction}
              modulesLoading={modulesLoading}
              showPasskeyPrompt={showPasskeyPrompt}
              setShowPasskeyPrompt={setShowPasskeyPrompt}
              dismissPasskeyPrompt={dismissPasskeyPrompt}
            />
          </ProtectedRoute>
        );
    }
  };

  return (
    <Suspense
      fallback={
        <Box
          minH="100vh"
          bg="gray.900"
          display="flex"
          alignItems="center"
          justifyContent="center"
        >
          <Spinner size="xl" color="orange.400" thickness="4px" />
        </Box>
      }
    >
      {renderPage()}
    </Suspense>
  );
}

function App() {
  // Detect public landing page route: /p/:tenantSlug (no auth required)
  const basePath = import.meta.env.BASE_URL?.replace(/\/$/, '') || '';
  const pathname = window.location.pathname;
  const path = pathname.startsWith(basePath)
    ? pathname.slice(basePath.length)
    : pathname;
  const isPublicLandingPage = /^\/p\/[a-z0-9-]+\/?$/.test(path);

  if (isPublicLandingPage) {
    return (
      <ChakraProvider theme={theme}>
        <Suspense
          fallback={
            <Box
              display="flex"
              alignItems="center"
              justifyContent="center"
              minH="100vh"
              bg="white"
            >
              <Spinner size="xl" color="orange.400" thickness="4px" />
            </Box>
          }
        >
          <PublicLandingPage />
        </Suspense>
      </ChakraProvider>
    );
  }

  return (
    <ChakraProvider theme={theme}>
      <AuthProvider>
        <TenantProvider>
          <AppContent />
        </TenantProvider>
      </AuthProvider>
    </ChakraProvider>
  );
}

export default App;
