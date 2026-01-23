import React, { useState, useEffect } from 'react';
import { ChakraProvider, Box, VStack, Heading, Button, HStack, Text, Badge } from '@chakra-ui/react';
import PDFUploadForm from './components/PDFUploadForm';
import BankConnect from './components/BankConnect';
import BankingProcessor from './components/BankingProcessor';
import STRProcessor from './components/STRProcessor';
import STRInvoice from './components/STRInvoice';
import STRPricing from './components/STRPricing';
import MyAdminReportsNew from './components/MyAdminReportsNew';
import Login from './pages/Login';
import ProtectedRoute from './components/ProtectedRoute';
import theme from './theme';
import { AuthProvider, useAuth } from './context/AuthContext';

type PageType = 'login' | 'menu' | 'pdf' | 'banking' | 'bank-connect' | 'str' | 'str-invoice' | 'str-pricing' | 'powerbi';

function AppContent() {
  const [currentPage, setCurrentPage] = useState<PageType>('menu');
  const [status, setStatus] = useState({ mode: 'Production', database: '', folder: '' });
  const { isAuthenticated, loading, user, logout } = useAuth();

  useEffect(() => {
    import('./config').then(({ buildApiUrl }) => {
      fetch(buildApiUrl('/api/status'))
        .then(res => res.json())
        .then(data => setStatus(data))
        .catch(() => setStatus({ mode: 'Production', database: 'finance', folder: 'Facturen' }));
    });
  }, []);

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
            requiredRoles={['Administrators', 'Accountants']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">📄 Import Invoices</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
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
            requiredRoles={['Administrators', 'Accountants']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🏦 Import Banking Accounts</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
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
            requiredRoles={['Administrators', 'Accountants']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🏦 Connect Bank (Salt Edge)</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
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
            requiredRoles={['Administrators', 'Accountants']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🏠 Import STR Bookings</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
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
            requiredRoles={['Administrators', 'Accountants']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">🧾 STR Invoice Generator</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
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
            requiredRoles={['Administrators', 'Accountants']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">💰 STR Pricing Model</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
                  </HStack>
                </HStack>
              </Box>
              <STRPricing />
            </Box>
          </ProtectedRoute>
        );

      case 'powerbi':
        return (
          <ProtectedRoute 
            requiredRoles={['Administrators', 'Accountants', 'Viewers']}
            onLoginSuccess={() => setCurrentPage('menu')}
          >
            <Box minH="100vh" bg="gray.900">
              <Box bg="gray.800" p={4} borderBottom="2px" borderColor="orange.500">
                <HStack justify="space-between">
                  <HStack>
                    <Button size="sm" colorScheme="orange" onClick={() => setCurrentPage('menu')}>← Back</Button>
                    <Heading color="orange.400" size="lg">📈 myAdmin Reports</Heading>
                  </HStack>
                  <HStack>
                    <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'}>{status.mode}</Badge>
                    <Text color="gray.400" fontSize="sm">{user?.email}</Text>
                    <Button size="sm" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
                  </HStack>
                </HStack>
              </Box>
              <MyAdminReportsNew />
            </Box>
          </ProtectedRoute>
        );

      default:
        return (
          <ProtectedRoute onLoginSuccess={() => setCurrentPage('menu')}>
            <Box minH="100vh" bg="gray.900" display="flex" alignItems="center" justifyContent="center">
              <VStack spacing={8}>
                <VStack spacing={2}>
                  <Heading color="orange.400" size="2xl">myAdmin Dashboard</Heading>
                  <Badge colorScheme={status.mode === 'Test' ? 'red' : 'green'} fontSize="md" px={3} py={1}>
                    {status.mode} Mode
                  </Badge>
                  <HStack spacing={2}>
                    <Text color="gray.400" fontSize="sm">Logged in as: {user?.email}</Text>
                    <Text color="gray.400" fontSize="sm">Role: {user?.roles?.join(', ') || 'No roles'}</Text>
                    <Button size="xs" variant="ghost" colorScheme="orange" onClick={logout}>Logout</Button>
                  </HStack>
                </VStack>
                <Text color="gray.300" fontSize="lg">Select a component to get started</Text>
                
                <VStack spacing={4} w="400px">
                  {/* Invoice Management - Accountants, Administrators, Finance roles, Viewers */}
                  {(user?.roles?.some(role => ['Administrators', 'Accountants', 'Finance_CRUD', 'Finance_Read', 'Viewers'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="orange" onClick={() => setCurrentPage('pdf')}>
                      📄 Import Invoices
                    </Button>
                  )}

                  {/* Banking - Accountants, Administrators */}
                  {(user?.roles?.some(role => ['Administrators', 'Accountants'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="red" onClick={() => setCurrentPage('banking')}>
                      🏦 Import Banking Accounts
                    </Button>
                  )}

                  {/* STR Bookings - Administrators, STR_CRUD, STR_Read only */}
                  {(user?.roles?.some(role => ['Administrators', 'STR_CRUD', 'STR_Read'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="blue" onClick={() => setCurrentPage('str')}>
                      🏠 Import STR Bookings
                    </Button>
                  )}

                  {/* STR Invoice - Administrators, STR_CRUD, STR_Read only */}
                  {(user?.roles?.some(role => ['Administrators', 'STR_CRUD', 'STR_Read'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="teal" onClick={() => setCurrentPage('str-invoice')}>
                      🧾 STR Invoice Generator
                    </Button>
                  )}

                  {/* STR Pricing - Administrators, STR_CRUD only */}
                  {(user?.roles?.some(role => ['Administrators', 'STR_CRUD'].includes(role))) && (
                    <Button size="lg" w="full" colorScheme="green" onClick={() => setCurrentPage('str-pricing')}>
                      💰 STR Pricing Model
                    </Button>
                  )}

                  {/* Reports - All authenticated users can view reports */}
                  <Button size="lg" w="full" colorScheme="purple" onClick={() => setCurrentPage('powerbi')}>
                    📈 myAdmin Reports
                  </Button>
                </VStack>
              </VStack>
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
        <AppContent />
      </AuthProvider>
    </ChakraProvider>
  );
}

export default App;