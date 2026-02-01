import React, { useState, useEffect } from 'react';
import { ChakraProvider, Box, VStack, Heading, Button, HStack, Text, Breadcrumb, BreadcrumbItem, BreadcrumbLink } from '@chakra-ui/react';
import { ChevronRightIcon } from '@chakra-ui/icons';
import PDFUploadForm from './components/PDFUploadForm';
import BankConnect from './components/BankConnect';
import BankingProcessor from './components/BankingProcessor';
import STRProcessor from './components/STRProcessor';
import STRInvoice from './components/STRInvoice';
import STRPricing from './components/STRPricing';
import FINReports from './components/FINReports';
import STRReports from './components/STRReports';
import Login from './pages/Login';
import ProtectedRoute from './components/ProtectedRoute';
import TenantSelector from './components/TenantSelector';
import UserMenu from './components/UserMenu';
import theme from './theme';
import { AuthProvider, useAuth } from './context/AuthContext';
import { TenantProvider } from './context/TenantContext';
import { useTenantModules } from './hooks/useTenantModules';
import { TenantAdminDashboard } from './components/TenantAdmin/TenantAdminDashboard';
import SystemAdmin from './components/SystemAdmin';

type PageType = 'login' | 'menu' | 'pdf' | 'banking' | 'bank-connect' | 'str' | 'str-invoice' | 'str-pricing' | 'powerbi' | 'fin-reports' | 'str-reports' | 'system-admin' | 'tenant-admin';

function AppContent() {
  const [currentPage, setCurrentPage] = useState<PageType>('menu');
  const [status, setStatus] = useState({ mode: 'Production', database: '', folder: '' });
  const { isAuthenticated, loading, user, logout } = useAuth();
  const { hasFIN, hasSTR, loading: modulesLoading } = useTenantModules();

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
      if ((currentPage === 'pdf' || currentPage === 'banking' || currentPage === 'bank-connect' || currentPage === 'powerbi' || currentPage === 'fin-reports') && !hasFIN) {
        setCurrentPage('menu');
      }
    }
  }, [hasSTR, hasFIN, modulesLoading, currentPage]);

  // Show login page if not authenticated
  if (!isAuthenticated && !loading) {
    return <Login onLoginSuccess={() => setCurrentPage('menu')} />;
  }

  // Show loading state while checking authentication
  if (loading) {
    return (
      <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Heading color="orange.400" size="lg">Loading...</Heading>
          <Text color="gray.400">Checking authentication status</Text>
        </VStack>
      </Box>
    );
  }

  const renderPage = () => {
    switch (currentPage) {
      case 'pdf':
        return (
          <ProtectedRoute 
            requiredRoles={['Finance_CRUD']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">📄 Import Invoices</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🏦 Import Banking Accounts</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🏦 Connect Bank (Salt Edge)</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🏠 Import STR Bookings</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🧾 STR Invoice Generator</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">💰 STR Pricing Model</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <VStack align="start" spacing={1}>
                    <HStack>
                      <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                      <Heading color="orange.400" size="lg">⚙️ System Administration</Heading>
                    </HStack>
                    <Breadcrumb spacing="8px" separator={<ChevronRightIcon color="gray.500" />} fontSize="sm" color="gray.400" ml={20}>
                      <BreadcrumbItem>
                        <BreadcrumbLink onClick={() => setCurrentPage('menu')}>Dashboard</BreadcrumbLink>
                      </BreadcrumbItem>
                      <BreadcrumbItem isCurrentPage>
                        <BreadcrumbLink>System Administration</BreadcrumbLink>
                      </BreadcrumbItem>
                    </Breadcrumb>
                  </VStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
              <SystemAdmin />
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <VStack align="start" spacing={1}>
                    <HStack>
                      <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                      <Heading color="orange.400" size="lg">🏢 Tenant Administration</Heading>
                    </HStack>
                    <Breadcrumb spacing="8px" separator={<ChevronRightIcon color="gray.500" />} fontSize="sm" color="gray.400" ml={20}>
                      <BreadcrumbItem>
                        <BreadcrumbLink onClick={() => setCurrentPage('menu')}>Dashboard</BreadcrumbLink>
                      </BreadcrumbItem>
                      <BreadcrumbItem isCurrentPage>
                        <BreadcrumbLink>Tenant Administration</BreadcrumbLink>
                      </BreadcrumbItem>
                    </Breadcrumb>
                  </VStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
              <TenantAdminDashboard />
            </Box>
          </ProtectedRoute>
        );

      case 'powerbi':
        // Legacy route - redirect to fin-reports
        return (
          <ProtectedRoute 
            requiredRoles={['Finance_CRUD', 'Finance_Read', 'Finance_Export']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">📊 FIN Reports</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">📊 FIN Reports</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
              <FINReports />
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
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">📈 STR Reports</Heading>
                  </HStack>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>
              <STRReports />
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
                  <Heading color="orange.400" size="lg">myAdmin Dashboard</Heading>
                  <HStack spacing={3}>
                    <TenantSelector size="sm" />
                    <UserMenu onLogout={logout} mode={status.mode} />
                  </HStack>
                </HStack>
              </Box>

              {/* Main Content */}
              <Box display="flex" alignItems="center" justifyContent="center" minH="calc(100vh - 80px)">
                <VStack spacing={8}>
                  <Text color="gray.300" fontSize="lg">Select a component to get started</Text>
                
                <VStack spacing={4} w="400px">
                  {/* Invoice Management - Finance module permissions */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="orange" onClick={() => setCurrentPage('pdf')}>
                      📄 Import Invoices
                    </Button>
                  )}

                  {/* Banking - Finance CRUD only (requires write access) */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="red" onClick={() => setCurrentPage('banking')}>
                      🏦 Import Banking Accounts
                    </Button>
                  )}

                  {/* STR Bookings - STR module permissions */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('str')}>
                      🏠 Import STR Bookings
                    </Button>
                  )}

                  {/* STR Invoice - STR module permissions */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="teal" onClick={() => setCurrentPage('str-invoice')}>
                      🧾 STR Invoice Generator
                    </Button>
                  )}

                  {/* STR Pricing - STR CRUD only (requires write access) */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('str-pricing')}>
                      💰 STR Pricing Model
                    </Button>
                  )}

                  {/* FIN Reports - Finance module users */}
                  {hasFIN && (user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read', 'Finance_Export'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="purple" onClick={() => setCurrentPage('fin-reports')}>
                      📊 FIN Reports
                    </Button>
                  )}

                  {/* STR Reports - STR module users */}
                  {hasSTR && (user?.roles?.some(role => ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="cyan" onClick={() => setCurrentPage('str-reports')}>
                      📈 STR Reports
                    </Button>
                  )}

                  {/* System Administration - SysAdmin only */}
                  {(user?.roles?.some(role => ['SysAdmin'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="gray" onClick={() => setCurrentPage('system-admin')}>
                      ⚙️ System Administration
                    </Button>
                  )}

                  {/* Tenant Administration - Tenant_Admin only */}
                  {(user?.roles?.some(role => ['Tenant_Admin'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="pink" onClick={() => setCurrentPage('tenant-admin')}>
                      🏢 Tenant Administration
                    </Button>
                  )}
                  
                  {/* Loading state */}
                  {modulesLoading && (
                    <Text color="gray.500" fontSize="sm">Loading available modules...</Text>
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