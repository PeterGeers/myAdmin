import React, { useState, useEffect, useCallback } from 'react';
import { ChakraProvider, Box, VStack, Heading, Button, HStack, Text, Alert, AlertIcon, AlertDescription, CloseButton, Link as ChakraLink } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import PDFUploadForm from './components/PDFUploadForm';
import BankConnect from './components/BankConnect';
import BankingProcessor from './components/BankingProcessor';
import STRProcessor from './components/STRProcessor';
import STRInvoice from './components/STRInvoice';
import STRPricing from './components/STRPricing';
import FINReports from './components/FINReports';
import AssetList from './components/Assets/AssetList';
import STRReports from './components/STRReports';
import Login from './pages/Login';
import ProtectedRoute from './components/ProtectedRoute';
import TenantSelector from './components/TenantSelector';
import UserMenu from './components/UserMenu';
import { LanguageSelector } from './components/LanguageSelector';
import theme from './theme';
import { AuthProvider, useAuth } from './context/AuthContext';
import { TenantProvider } from './context/TenantContext';
import { useTenantModules } from './hooks/useTenantModules';
import { TenantAdminDashboard } from './components/TenantAdmin/TenantAdminDashboard';
import { SysAdminDashboard } from './components/SysAdmin/SysAdminDashboard';
import MigrationTool from './pages/MigrationTool';
import PasskeySettings from './components/settings/PasskeySettings';
import { listPasskeys, isPasskeySupported } from './services/authService';
import { HelpButton } from './components/help';

type PageType = 'login' | 'menu' | 'pdf' | 'banking' | 'bank-connect' | 'str' | 'str-invoice' | 'str-pricing' | 'powerbi' | 'fin-reports' | 'str-reports' | 'system-admin' | 'tenant-admin' | 'migration' | 'settings' | 'assets';

function AppContent() {
  const { t } = useTranslation();
  const [currentPage, setCurrentPage] = useState<PageType>('menu');
  const [status, setStatus] = useState({ mode: 'Production', database: '', folder: '' });
  const { isAuthenticated, loading, user, logout, refreshUserRoles } = useAuth();
  const { hasFIN, hasSTR, loading: modulesLoading } = useTenantModules();
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
    import('./config').then(({ buildApiUrl }) => {
      fetch(buildApiUrl('/api/status'))
        .then(res => res.json())
        .then(data => setStatus(data))
        .catch(() => setStatus({ mode: 'Production', database: 'finance', folder: 'Facturen' }));
    });
  }, []);

  // Redirect to menu if user loses module access after tenant switch
  useEffect(() => {
    if (!modulesLoading) {
      // If on STR page but no STR access, redirect to menu
      if ((currentPage === 'str' || currentPage === 'str-invoice' || currentPage === 'str-pricing' || currentPage === 'str-reports') && !hasSTR) {
        setCurrentPage('menu');
      }
      // If on FIN page but no FIN access, redirect to menu
      if ((currentPage === 'pdf' || currentPage === 'banking' || currentPage === 'bank-connect' || currentPage === 'powerbi' || currentPage === 'fin-reports' || currentPage === 'assets') && !hasFIN) {
        setCurrentPage('menu');
      }
    }
  }, [hasSTR, hasFIN, modulesLoading, currentPage]);

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
      <HStack justify="space-between">
        <HStack>
          <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← {t('common:navigation.back')}</Button>
          <Heading color="orange.400" size="lg">{title}</Heading>
        </HStack>
        <HStack spacing={3}>
          {options?.showLanguage && <LanguageSelector />}
          <TenantSelector size="sm" hide={options?.hideTenant} />
          <HelpButton page={currentPage} />
          <UserMenu onLogout={logout} onSettings={() => setCurrentPage('settings')} mode={status.mode} />
        </HStack>
      </HStack>
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
      case 'bank-connect':
        return (
          <ProtectedRoute 
            requiredRoles={['Finance_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              {renderPageHeader(`🏦 ${t('common:navigation.modules.connectBank')}`)}
              <BankConnect />
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
                <HStack justify="space-between">
                  <Heading color="orange.400" size="lg">{t('common:navigation.myAdminDashboard')}</Heading>
                  <HStack spacing={3}>
                    <LanguageSelector />
                    <TenantSelector size="sm" />
                    <HelpButton page={currentPage} />
                    <UserMenu onLogout={logout} onSettings={() => setCurrentPage('settings')} mode={status.mode} />
                  </HStack>
                </HStack>
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
                  {/* Invoice Management - Finance module permissions */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="orange" onClick={() => setCurrentPage('pdf')}>
                      📄 {t('common:navigation.modules.importInvoices')}
                    </Button>
                  )}

                  {/* Banking - Finance CRUD only (requires write access) */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="red" onClick={() => setCurrentPage('banking')}>
                      🏦 {t('common:navigation.modules.importBanking')}
                    </Button>
                  )}

                  {/* STR Bookings - STR module permissions */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('str')}>
                      🏠 {t('common:navigation.modules.importSTRBookings')}
                    </Button>
                  )}

                  {/* STR Invoice - STR module permissions */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="teal" onClick={() => setCurrentPage('str-invoice')}>
                      🧾 {t('common:navigation.modules.strInvoiceGenerator')}
                    </Button>
                  )}

                  {/* STR Pricing - STR CRUD only (requires write access) */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('str-pricing')}>
                      💰 {t('common:navigation.modules.strPricingModel')}
                    </Button>
                  )}

                  {/* FIN Reports - Finance module users */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read', 'Finance_Export'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="purple" onClick={() => setCurrentPage('fin-reports')}>
                      📊 {t('common:navigation.modules.finReports')}
                    </Button>
                  )}

                  {/* Asset Administration - Finance module users */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="yellow" onClick={() => setCurrentPage('assets')}>
                      🏗️ {t('common:navigation.modules.assets', 'Asset Administration')}
                    </Button>
                  )}

                  {/* STR Reports - STR module users */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="cyan" onClick={() => setCurrentPage('str-reports')}>
                      📈 {t('common:navigation.modules.strReports')}
                    </Button>
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

  return renderPage();
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
