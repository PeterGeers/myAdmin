/**
 * VAT Netting Configuration Component
 * 
 * Allows configuration of VAT account netting for year-end closure.
 * VAT accounts are netted together into a single opening balance entry.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  VStack,
  HStack,
  Text,
  Select,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Spinner,
  useToast,
  Heading,
  FormControl,
  FormLabel,
  FormHelperText,
  Badge,
  Checkbox,
  Stack,
  Collapse
} from '@chakra-ui/react';
import { InfoIcon, CheckCircleIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import {
  getVATNettingConfig,
  configureVATNetting,
  removeVATNetting,
  getBalanceSheetAccounts,
  AvailableAccount
} from '../../services/yearEndConfigService';

const VATNettingConfig: React.FC = () => {
  const { t } = useTypedTranslation('admin');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([]);
  const [primaryAccount, setPrimaryAccount] = useState<string>('');
  const [availableAccounts, setAvailableAccounts] = useState<AvailableAccount[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const toast = useToast();

  useEffect(() => {
    loadConfiguration();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadConfiguration = async () => {
    setLoading(true);
    try {
      const [config, accounts] = await Promise.all([
        getVATNettingConfig(),
        getBalanceSheetAccounts()
      ]);

      setAvailableAccounts(accounts);

      if (config.vat_accounts && config.vat_accounts.length > 0) {
        setEnabled(true);
        setSelectedAccounts(config.vat_accounts.map(a => a.Account));
        setPrimaryAccount(config.primary_account || '');
      } else {
        setEnabled(false);
        // Set default Dutch VAT accounts
        setSelectedAccounts(['2010', '2020', '2021']);
        setPrimaryAccount('2010');
      }
    } catch (error) {
      console.error('Error loading VAT netting configuration:', error);
      toast({
        title: t('yearEndSettings.vatNetting.errors.loadingError'),
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!enabled) {
      // Remove VAT netting
      setSaving(true);
      try {
        await removeVATNetting();
        toast({
          title: t('yearEndSettings.vatNetting.messages.disabledSuccess'),
          status: 'success',
          duration: 3000
        });
        await loadConfiguration();
      } catch (error) {
        toast({
          title: t('yearEndSettings.vatNetting.errors.saveError'),
          description: error instanceof Error ? error.message : 'Unknown error',
          status: 'error',
          duration: 5000
        });
      } finally {
        setSaving(false);
      }
      return;
    }

    // Validate
    if (selectedAccounts.length === 0) {
      toast({
        title: t('yearEndSettings.vatNetting.errors.noAccountsSelected'),
        status: 'warning',
        duration: 3000
      });
      return;
    }

    if (!primaryAccount) {
      toast({
        title: t('yearEndSettings.vatNetting.errors.noPrimaryAccount'),
        status: 'warning',
        duration: 3000
      });
      return;
    }

    if (!selectedAccounts.includes(primaryAccount)) {
      toast({
        title: t('yearEndSettings.vatNetting.errors.primaryNotInSelected'),
        status: 'warning',
        duration: 3000
      });
      return;
    }

    // Save configuration
    setSaving(true);
    try {
      await configureVATNetting({
        vat_accounts: selectedAccounts,
        primary_account: primaryAccount
      });

      toast({
        title: t('yearEndSettings.vatNetting.messages.saveSuccess'),
        description: t('yearEndSettings.vatNetting.messages.saveSuccessDescription'),
        status: 'success',
        duration: 3000
      });

      await loadConfiguration();
    } catch (error) {
      toast({
        title: t('yearEndSettings.vatNetting.errors.saveError'),
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000
      });
    } finally {
      setSaving(false);
    }
  };

  const handleAccountToggle = (account: string) => {
    if (selectedAccounts.includes(account)) {
      setSelectedAccounts(selectedAccounts.filter(a => a !== account));
      // If removing primary account, clear it
      if (account === primaryAccount) {
        setPrimaryAccount('');
      }
    } else {
      setSelectedAccounts([...selectedAccounts, account]);
    }
  };

  if (loading) {
    return (
      <Box p={6} textAlign="center">
        <Spinner size="lg" />
        <Text mt={4} color="gray.400">{t('yearEndSettings.vatNetting.loading')}</Text>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={4} align="stretch">
        {/* Header */}
        <Box>
          <HStack justify="space-between" mb={2}>
            <Heading size="md">{t('yearEndSettings.vatNetting.title')}</Heading>
            <Badge colorScheme={enabled ? 'green' : 'gray'}>
              {enabled ? t('yearEndSettings.vatNetting.enabled') : t('yearEndSettings.vatNetting.disabled')}
            </Badge>
          </HStack>
          <Text fontSize="sm" color="gray.400">
            {t('yearEndSettings.vatNetting.description')}
          </Text>
        </Box>

        {/* Info Alert */}
        <Alert status="info" variant="left-accent" borderRadius="md" bg="blue.900" color="blue.100" borderColor="blue.700" borderWidth="1px">
          <AlertIcon as={InfoIcon} color="blue.300" />
          <Box>
            <AlertTitle fontSize="sm">{t('yearEndSettings.vatNetting.info.title')}</AlertTitle>
            <AlertDescription fontSize="sm">
              {t('yearEndSettings.vatNetting.info.description')}
            </AlertDescription>
          </Box>
        </Alert>

        {/* Enable/Disable Toggle */}
        <Box p={4} bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
          <Checkbox
            isChecked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            colorScheme="blue"
            size="lg"
          >
            <Text fontWeight="bold">{t('yearEndSettings.vatNetting.enableLabel')}</Text>
          </Checkbox>
          <Text fontSize="sm" color="gray.400" mt={2} ml={7}>
            {t('yearEndSettings.vatNetting.enableHelp')}
          </Text>
        </Box>

        {/* Configuration (shown when enabled) */}
        <Collapse in={enabled} animateOpacity>
          <VStack spacing={4} align="stretch">
            {/* Quick Setup for Dutch VAT */}
            {!showAdvanced && (
              <Box p={4} bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
                <HStack justify="space-between" mb={3}>
                  <Text fontWeight="bold">{t('yearEndSettings.vatNetting.quickSetup.title')}</Text>
                  <Button size="sm" variant="ghost" onClick={() => setShowAdvanced(true)}>
                    {t('yearEndSettings.vatNetting.quickSetup.advancedButton')}
                  </Button>
                </HStack>

                <Alert status="success" variant="subtle" borderRadius="md" mb={3}>
                  <AlertIcon as={CheckCircleIcon} />
                  <Text fontSize="sm">
                    {t('yearEndSettings.vatNetting.quickSetup.dutchVATConfigured')}
                  </Text>
                </Alert>

                <VStack align="start" spacing={2} fontSize="sm" color="gray.400">
                  <Text>• 2010 - Betaalde BTW (Paid VAT)</Text>
                  <Text>• 2020 - Ontvangen BTW Hoog (Received VAT High)</Text>
                  <Text>• 2021 - Ontvangen BTW Laag (Received VAT Low)</Text>
                  <Text mt={2} fontWeight="bold" color="white">
                    {t('yearEndSettings.vatNetting.quickSetup.primaryAccount')}: 2010
                  </Text>
                </VStack>
              </Box>
            )}

            {/* Advanced Configuration */}
            {showAdvanced && (
              <Box p={4} bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
                <HStack justify="space-between" mb={3}>
                  <Text fontWeight="bold">{t('yearEndSettings.vatNetting.advanced.title')}</Text>
                  <Button size="sm" variant="ghost" onClick={() => setShowAdvanced(false)}>
                    {t('yearEndSettings.vatNetting.advanced.simpleButton')}
                  </Button>
                </HStack>

                {/* Account Selection */}
                <FormControl mb={4}>
                  <FormLabel>{t('yearEndSettings.vatNetting.advanced.selectAccounts')}</FormLabel>
                  <Stack spacing={2} maxH="200px" overflowY="auto" p={2} bg="gray.900" borderRadius="md">
                    {availableAccounts
                      .filter(acc => acc.Account.startsWith('20') || acc.Account.startsWith('21'))
                      .map((account) => (
                        <Checkbox
                          key={account.Account}
                          isChecked={selectedAccounts.includes(account.Account)}
                          onChange={() => handleAccountToggle(account.Account)}
                          colorScheme="blue"
                        >
                          <Text fontSize="sm">
                            {account.Account} - {account.AccountName}
                          </Text>
                        </Checkbox>
                      ))}
                  </Stack>
                  <FormHelperText>
                    {t('yearEndSettings.vatNetting.advanced.selectAccountsHelp')}
                  </FormHelperText>
                </FormControl>

                {/* Primary Account Selection */}
                <FormControl>
                  <FormLabel>{t('yearEndSettings.vatNetting.advanced.primaryAccount')}</FormLabel>
                  <Select
                    value={primaryAccount}
                    onChange={(e) => setPrimaryAccount(e.target.value)}
                    placeholder={t('yearEndSettings.vatNetting.advanced.selectPrimary')}
                    bg="gray.900"
                    borderColor="gray.600"
                  >
                    {selectedAccounts.map((account) => {
                      const accountInfo = availableAccounts.find(a => a.Account === account);
                      return (
                        <option key={account} value={account}>
                          {account} - {accountInfo?.AccountName || account}
                        </option>
                      );
                    })}
                  </Select>
                  <FormHelperText>
                    {t('yearEndSettings.vatNetting.advanced.primaryAccountHelp')}
                  </FormHelperText>
                </FormControl>
              </Box>
            )}
          </VStack>
        </Collapse>

        {/* Save Button */}
        <HStack justify="flex-end">
          <Button
            colorScheme="blue"
            onClick={handleSave}
            isLoading={saving}
            loadingText={t('yearEndSettings.vatNetting.saving')}
          >
            {t('yearEndSettings.vatNetting.saveButton')}
          </Button>
        </HStack>
      </VStack>
    </Box>
  );
};

export default VATNettingConfig;
