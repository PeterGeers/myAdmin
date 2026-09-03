import React from 'react';
import { Box, VStack, Heading, Button, HStack, Flex, Text, Alert, AlertIcon, AlertDescription, CloseButton, Link as ChakraLink } from '@chakra-ui/react';
import { useTranslation } from 'react-i18next';
import TenantSelector from './TenantSelector';
import UserMenu from './UserMenu';
import { LanguageSelector } from './LanguageSelector';
import { HelpButton } from './help';
import { MenuGroup } from './MenuGroup';
import type { User } from '../context/AuthContext';
import type { PageType } from '../appPages';

interface MainMenuProps {
  currentPage: PageType;
  setCurrentPage: (page: PageType) => void;
  user: User | null;
  status: { mode: string; database: string; folder: string };
  logout: () => void;
  hasFIN: boolean;
  hasSTR: boolean;
  hasZZP: boolean;
  hasFunction: (name: string) => boolean;
  modulesLoading: boolean;
  showPasskeyPrompt: boolean;
  setShowPasskeyPrompt: (show: boolean) => void;
  dismissPasskeyPrompt: () => void;
}

/**
 * Dashboard landing menu shown when no specific page is selected.
 *
 * Extracted verbatim from the ``default`` branch of ``App``'s ``renderPage``
 * to keep the root component focused on routing. Behavior and markup are
 * unchanged; all previously in-scope values are now passed as props.
 */
export function MainMenu({
  currentPage,
  setCurrentPage,
  user,
  status,
  logout,
  hasFIN,
  hasSTR,
  hasZZP,
  hasFunction,
  modulesLoading,
  showPasskeyPrompt,
  setShowPasskeyPrompt,
  dismissPasskeyPrompt,
}: MainMenuProps) {
  const { t } = useTranslation();

  return (
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

              {/* Import group */}
              {user?.roles?.some(role => ['Finance_CRUD'].includes(role)) && (
                <MenuGroup icon="📥" label={t('common:navigation.groups.import')} colorScheme="orange">
                  <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('pdf')}>
                    📄 {t('common:navigation.modules.importInvoices')}
                  </Button>
                  <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('banking')}>
                    🏦 {t('common:navigation.modules.banking')}
                  </Button>
                  {hasFunction('assets') && (
                    <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('assets')}>
                      🏗️ {t('common:navigation.modules.assets', 'Asset Administration')}
                    </Button>
                  )}
                  {hasFunction('str_channel_revenue') && (
                    <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('str-channel-revenue')}>
                      📡 {t('common:navigation.modules.strChannelRevenue')}
                    </Button>
                  )}
                </MenuGroup>
              )}

              {/* Transactions — direct button */}
              {user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read'].includes(role)) && (
                <Button size="lg" w="full" colorScheme="blue" justifyContent="flex-start" onClick={() => setCurrentPage('transactions')}>
                  📋 {t('common:navigation.modules.transactions')}
                </Button>
              )}

              {/* Validation group */}
              {user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read'].includes(role)) && (
                <MenuGroup icon="✅" label={t('common:navigation.groups.validation')} colorScheme="green">
                  <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('check-accounts')}>
                    🔍 {t('common:navigation.modules.checkAccounts')}
                  </Button>
                  <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('check-reference')}>
                    🔗 {t('common:navigation.modules.checkReference')}
                  </Button>
                </MenuGroup>
              )}

              {/* Budget — direct button */}
              {user?.roles?.some(role => ['Finance_CRUD', 'Finance_Read'].includes(role)) && hasFunction('budget') && (
                <Button size="lg" w="full" colorScheme="orange" variant="outline" justifyContent="flex-start" onClick={() => setCurrentPage('budget')}>
                  💰 {t('common:navigation.modules.budgetGroup', 'Budget')}
                </Button>
              )}

              {/* Reports — direct button */}
              <Button size="lg" w="full" colorScheme="purple" justifyContent="flex-start" onClick={() => setCurrentPage('fin-reports')}>
                📊 {t('common:navigation.modules.finReports')}
              </Button>
            </>
          )}

          {/* ── STR Module ──────────────────────────── */}
          {hasSTR && (user?.roles?.some(role => ['STR_CRUD', 'STR_Read', 'STR_Export'].includes(role))) && (
            <>
              <Text color="blue.300" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>🏠 {t('common:navigation.moduleGroups.str')}</Text>
              {user?.roles?.some(role => ['STR_CRUD'].includes(role)) && (
                <Button size="lg" w="full" colorScheme="blue" justifyContent="flex-start" onClick={() => setCurrentPage('str')}>
                  🏠 {t('common:navigation.modules.importSTRBookings')}
                </Button>
              )}
              <Button size="lg" w="full" colorScheme="teal" justifyContent="flex-start" onClick={() => setCurrentPage('str-invoice')}>
                🧾 {t('common:navigation.modules.strInvoiceGenerator')}
              </Button>
              {user?.roles?.some(role => ['STR_CRUD'].includes(role)) && (
                <Button size="lg" w="full" colorScheme="green" justifyContent="flex-start" onClick={() => setCurrentPage('str-pricing')}>
                  💰 {t('common:navigation.modules.strPricingModel')}
                </Button>
              )}
              <Button size="lg" w="full" colorScheme="cyan" justifyContent="flex-start" onClick={() => setCurrentPage('str-reports')}>
                📈 {t('common:navigation.modules.strReports')}
              </Button>
            </>
          )}

          {/* ── ZZP Module ──────────────────────────── */}
          {hasZZP && (user?.roles?.some(role => ['ZZP_Read', 'ZZP_CRUD'].includes(role))) && (
            <>
              <Text color="teal.300" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>💼 {t('common:navigation.moduleGroups.zzp')}</Text>

              {/* Administration group */}
              <MenuGroup icon="📋" label={t('common:navigation.groups.administration')} colorScheme="teal">
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-products')}>
                  📦 {t('zzp:products.title')}
                </Button>
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-contacts')}>
                  👥 {t('zzp:contacts.title')}
                </Button>
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-debtors')}>
                  💰 {t('zzp:debtors.title')}
                </Button>
              </MenuGroup>

              {/* Invoices group */}
              <MenuGroup icon="🧾" label={t('common:navigation.groups.invoices')} colorScheme="cyan">
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-invoices')}>
                  🧾 {t('zzp:invoices.title')}
                </Button>
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-time-tracking')}>
                  ⏱️ {t('zzp:timeTracking.title')}
                </Button>
              </MenuGroup>

              {/* Trip Registration group */}
              <MenuGroup icon="🚗" label={t('common:navigation.groups.tripRegistration')} colorScheme="orange">
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-trips')}>
                  🚗 {t('zzp:trips.title')}
                </Button>
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-trip-quick')}>
                  ⚡ {t('zzp:trips.quickEntry')}
                </Button>
                <Button size="sm" w="full" variant="ghost" color="white" justifyContent="flex-start" _hover={{ bg: 'whiteAlpha.200' }} _active={{ bg: 'whiteAlpha.300' }} onClick={() => setCurrentPage('zzp-trip-import')}>
                  📥 {t('zzp:trips.import.title')}
                </Button>
              </MenuGroup>
            </>
          )}

          {/* ── Admin ───────────────────────────────── */}
          {(user?.roles?.some(role => ['SysAdmin', 'Tenant_Admin'].includes(role))) && (
            <Text color="gray.400" fontSize="sm" fontWeight="bold" alignSelf="flex-start" mt={2}>⚙️ {t('common:navigation.moduleGroups.admin')}</Text>
          )}

          {/* System Administration - SysAdmin only */}
          {(user?.roles?.some(role => ['SysAdmin'].includes(role))) && (
            <Button size="lg" w="full" colorScheme="gray" justifyContent="flex-start" onClick={() => setCurrentPage('system-admin')}>
              ⚙️ {t('common:navigation.modules.systemAdministration')}
            </Button>
          )}

          {/* Tenant Administration - Tenant_Admin only */}
          {(user?.roles?.some(role => ['Tenant_Admin'].includes(role))) && (
            <Button size="lg" w="full" colorScheme="pink" justifyContent="flex-start" onClick={() => setCurrentPage('tenant-admin')}>
              🏢 {t('common:navigation.modules.tenantAdministration')}
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
  );
}
