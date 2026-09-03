/**
 * AppRoutes - page switch extracted from App.tsx (pure refactor, no behavior change).
 *
 * Renders the authenticated page for the current `currentPage` value. All state
 * and callbacks are owned by AppContent and passed in via props; this module is
 * presentation only. Page wrappers, required roles, and headers are unchanged
 * from the original inline switch.
 */

import { useTranslation } from 'react-i18next';
import ProtectedRoute from './components/ProtectedRoute';
import TenantSelector from './components/TenantSelector';
import UserMenu from './components/UserMenu';
import { LanguageSelector } from './components/LanguageSelector';
import { HelpButton } from './components/help';
import { MainMenu } from './components/MainMenu';
import type { User } from './context/AuthContext';
import { Box, Button, Heading, HStack, Flex } from '@chakra-ui/react';
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
  type PageType,
} from './appPages';

interface AppStatus {
  mode: string;
  database: string;
  folder: string;
}

export interface AppRoutesProps {
  currentPage: PageType;
  setCurrentPage: (page: PageType) => void;
  status: AppStatus;
  user: User | null;
  logout: () => void;
  hasFIN: boolean;
  hasSTR: boolean;
  hasZZP: boolean;
  hasFunction: (fn: string) => boolean;
  modulesLoading: boolean;
  showPasskeyPrompt: boolean;
  setShowPasskeyPrompt: (v: boolean) => void;
  dismissPasskeyPrompt: () => void;
}

export function AppRoutes(props: AppRoutesProps) {
  const {
    currentPage, setCurrentPage, status, user, logout,
    hasFIN, hasSTR, hasZZP, hasFunction, modulesLoading,
    showPasskeyPrompt, setShowPasskeyPrompt, dismissPasskeyPrompt,
  } = props;
  const { t } = useTranslation();

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
}
