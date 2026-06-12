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
import { buildApiUrl } from './config';

// FIN module pages
const PDFUploadForm = lazy(() => import('./components/PDFUploadForm'));
const BankingProcessor = lazy(() => import('./components/BankingProcessor'));
const FINReports = lazy(() => import('./components/FINReports'));
const AssetList = lazy(() => import('./components/Assets/AssetList'));

// STR module pages
const STRProcessor = lazy(() => import('./components/STRProcessor'));
const STRInvoice = lazy(() => import('./components/STRInvoice'));
const STRPricing = lazy(() => import('./components/STRPricing'));
const STRReports = lazy(() => import('./components/STRReports'));

// ZZP module pages
const ZZPContacts = lazy(() => import('./pages/ZZPContacts'));
const ZZPProducts = lazy(() => import('./pages/ZZPProducts'));
const ZZPInvoices = lazy(() => import('./pages/ZZPInvoices'));
const ZZPTimeTracking = lazy(() => import('./pages/ZZPTimeTracking'));
const ZZPDebtors = lazy(() => import('./pages/ZZPDebtors'));

// Admin pages (named exports)
const TenantAdminDashboard = lazy(() =>
  import('./components/TenantAdmin/TenantAdminDashboard').then(m => ({
    default: m.TenantAdminDashboard,
  }))
);
const SysAdminDashboard = lazy(() =>
  import('./components/SysAdmin/SysAdminDashboard').then(m => ({
    default: m.SysAdminDashboard,
  }))
);

// Admin pages (default exports)
const MigrationTool = lazy(() => import('./pages/MigrationTool'));
const PasskeySettings = lazy(() => import('./components/settings/PasskeySettings'));

type PageType = 'login' | 'menu' | 'pdf' | 'banking' | 'str' | 'str-invoice' | 'str-pricing' | 'powerbi' | 'fin-reports' | 'str-reports' | 'system-admin' | 'tenant-admin' | 'migration' | 'settings' | 'assets' | 'zzp-invoices' | 'zzp-contacts' | 'zzp-products' | 'zzp-time-tracking' | 'zzp-debtors';

function AppContent() {
  const { t } = useTranslation();
  const [currentPage, setCurrentPage] = useState<PageType>('menu');
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
  useEffect(() => {
    if (!modulesLoading) {
      // If on STR page but no STR access, redirect to menu
      if ((currentPage === 'str' || currentPage === 'str-invoice' || currentPage === 'str-pricing' || currentPage === 'str-reports') && !hasSTR) {
        setCurrentPage('menu');
      }
      // If on FIN page but no FIN access, redirect to menu
      if ((currentPage === 'pdf' || currentPage === 'banking' || currentPage === 'powerbi' || currentPage === 'fin-reports' || currentPage === 'assets') && !hasFIN) {
        setCurrentPage('menu');
      }
      // If on ZZP page but no ZZP access, redirect to menu
      if ((currentPage === 'zzp-invoices' || currentPage === 'zzp-contacts' || currentPage === 'zzp-products' || currentPage === 'zzp-time-tracking' || currentPage === 'zzp-debtors') && !hasZZP) {
        setCurrentPage('menu');
      }
    }
  }, [hasSTR, hasFIN, hasZZP, modulesLoading, currentPage]);

  // Show login page if not authenticated
  if (!isAuthenticated && !loading) {
    return <Login onLoginSuccess={() => { refreshUserRoles(); setCurrentPage('menu'); }} />;
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

      case 'migration':
        return (
          <Box minH="100vh" bg="gray.900">
            {renderPageHeader('🔄 Migration Tool')}
            <MigrationTool />
          </Box>
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
            <Box minH="100vh" bg="gray.900">
              {/* Top Header Bar */}
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <Flex wrap="wrap" justify="space-between" align="center" gap={2}>
                  <Heading color="orange.400" size={{ base: 'sm', md: 'lg' }} noOfLines={2}>{t('common:navigation.myAdminDashboard')}</Heading>
                  <HStack spacing={2} flexShrink={0}>
                    <LanguageSelector />
                    <TenantSelector size="sm" />
                    <HelpButton page={currentPage} />
                    <UserMenu onLogout={logout} onSettings={() => setCurrentPage('settings')} mode={status.mode} />
                  </HStack>
                </Flex>
              </Box>

              {/* Main Content */}
              {showPasskeyPrompt && (
                <Box px={6} pt={4} maxW="800px" mx="auto">
                  <Alert status="info" bg="blue.900" borderColor="blue.500" borderWidth="1px" borderRadius="md">
                    <AlertIcon color="blue.400" />
                    <AlertDescription color="gray.200" fontSize="sm" flex="1">
                      {t('auth:passkey.prompt', 'Register a passkey for faster, more secure login.')}{' '}
                      <ChakraLink color="orange.400" onClick={() => { setShowPasskeyPrompt(false); setCurrentPage('settings'); }} cursor="pointer" textDecoration="underline">
                        {t('common:navigation.modules.settings', 'Settings')}
                      </ChakraLink>
                    </AlertDescription>
                    <CloseButton color="gray.400" onClick={dismissPasskeyPrompt} />
                  </Alert>
                </Box>
              )}
              <Box display="flex" alignItems="center" justifyContent="center" minH="calc(100vh - 80px)">
                <VStack spacing={8}>
                  <Text color="gray.300" fontSize="lg">{t('common:navigation.selectComponent')}</Text>
                
                <VStack spacing={4} w="400px">
                  {/* ── FIN Module ──────────────────────────── */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read', 'Finance_Export'].includes(role))) && (
                    <>
                      <Text color="orange.300" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>📁 {t('common:navigation.moduleGroups.fin')}</Text>
                      {user?.roles?.some(role => ['Finance_CRUD'].includes(role)) && (
                        <Button size="lg" w="full" colorScheme="orange" onClick={() => setCurrentPage('pdf')}>
                          📄 {t('common:navigation.modules.importInvoices')}
                        </Button>
                      )}
                      {user?.roles?.some(role => ['Finance_CRUD'].includes(role)) && (
                        <Button size="lg" w="full" colorScheme="red" onClick={() => setCurrentPage('banking')}>
                          🏦 {t('common:navigation.modules.importBanking')}
                        </Button>
                      )}
                      <Button size="lg" w="full" colorScheme="purple" onClick={() => setCurrentPage('fin-reports')}>
                        📊 {t('common:navigation.modules.finReports')}
                      </Button>
                      {user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read'].includes(role)) && hasFunction('assets') && (
                        <Button size="lg" w="full" colorScheme="yellow" onClick={() => setCurrentPage('assets')}>
                          🏗️ {t('common:navigation.modules.assets', 'Asset Administration')}
                        </Button>
                      )}
                    </>
                  )}

                  {/* ── STR Module ──────────────────────────── */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role))) && (
                    <>
                      <Text color="blue.300" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>🏠 {t('common:navigation.moduleGroups.str')}</Text>
                      {user?.roles?.some(role => ['STR_CRUD'].includes(role)) && (
                        <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('str')}>
                          🏠 {t('common:navigation.modules.importSTRBookings')}
                        </Button>
                      )}
                      <Button size="lg" w="full" colorScheme="teal" onClick={() => setCurrentPage('str-invoice')}>
                        🧾 {t('common:navigation.modules.strInvoiceGenerator')}
                      </Button>
                      {user?.roles?.some(role => ['STR_CRUD'].includes(role)) && (
                        <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('str-pricing')}>
                          💰 {t('common:navigation.modules.strPricingModel')}
                        </Button>
                      )}
                      <Button size="lg" w="full" colorScheme="cyan" onClick={() => setCurrentPage('str-reports')}>
                        📈 {t('common:navigation.modules.strReports')}
                      </Button>
                    </>
                  )}

                  {/* ── ZZP Module ──────────────────────────── */}
                  {hasZZP && (user?.roles?.some(role => ['ZZP_Read', 'ZZP_CRUD'].includes(role))) && (
                    <>
                      <Text color="teal.300" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>💼 {t('common:navigation.moduleGroups.zzp')}</Text>
                      <Button size="lg" w="full" colorScheme="teal" onClick={() => setCurrentPage('zzp-invoices')}>
                        🧾 {t('zzp:invoices.title')}
                      </Button>
                      <Button size="lg" w="full" colorScheme="cyan" onClick={() => setCurrentPage('zzp-contacts')}>
                        👥 {t('zzp:contacts.title')}
                      </Button>
                      <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('zzp-products')}>
                        📦 {t('zzp:products.title')}
                      </Button>
                      <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('zzp-time-tracking')}>
                        ⏱️ {t('zzp:timeTracking.title')}
                      </Button>
                      <Button size="lg" w="full" colorScheme="yellow" onClick={() => setCurrentPage('zzp-debtors')}>
                        💰 {t('zzp:debtors.title')}
                      </Button>
                    </>
                  )}

                  {/* ── Admin ───────────────────────────────── */}
                  {(user?.roles?.some(role => ['SysAdmin', 'Tenant_Admin'].includes(role))) && (
                    <Text color="gray.400" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>⚙️ {t('common:navigation.moduleGroups.admin')}</Text>
                  )}

                  {/* System Administration - SysAdmin only */}
                  {(user?.roles?.some(role => ['SysAdmin'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="gray" onClick={() => setCurrentPage('system-admin')}>
                      ⚙️ {t('common:navigation.modules.systemAdministration')}
                    </Button>
                  )}

                  {/* Tenant Administration - Tenant_Admin only */}
                  {(user?.roles?.some(role => ['Tenant_Admin'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="pink" onClick={() => setCurrentPage('tenant-admin')}>
                      🏢 {t('common:navigation.modules.tenantAdministration')}
                    </Button>
                  )}

                  {/* Migration Tool - SysAdmin only (protected by secret + environment variable) */}
                  {(user?.roles?.some(role => ['SysAdmin'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="yellow" onClick={() => setCurrentPage('migration')}>
                      🔄 Migration Tool
                    </Button>
                  )}
                  
                  {/* Loading state */}
                  {modulesLoading && (
                    <Text color="gray.500" fontSize="sm">{t('common:navigation.loadingModules')}</Text>
                  )}
                </VStack>
              </VStack>
            </Box>
            </Box>
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
