/**
 * Year-End Settings Component
 * 
 * Purpose-centric configuration screen for year-end closure accounts.
 * Allows tenant admins to assign accounts to required purposes.
 * 
 * Requires: Tenant_Admin role
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
  Divider
} from '@chakra-ui/react';
import { CheckCircleIcon, WarningIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import {
  validateConfiguration,
  getConfiguredPurposes,
  setAccountPurpose,
  getAvailableAccounts,
  ConfigurationValidation,
  RequiredPurpose,
  AvailableAccount
} from '../../services/yearEndConfigService';

interface YearEndSettingsProps {
  tenant: string;
}

const YearEndSettings: React.FC<YearEndSettingsProps> = ({ tenant }) => {
  const { t } = useTypedTranslation('admin');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [userRoles, setUserRoles] = useState<string[]>([]);
  const [validation, setValidation] = useState<ConfigurationValidation | null>(null);
  const [requiredPurposes, setRequiredPurposes] = useState<Record<string, RequiredPurpose>>({});
  const [selectedAccounts, setSelectedAccounts] = useState<Record<string, string>>({});
  const [availableAccounts, setAvailableAccounts] = useState<Record<string, AvailableAccount[]>>({});
  const toast = useToast();

  // Check user roles on mount
  useEffect(() => {
    checkUserRoles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkUserRoles = async () => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      
      if (!token) {
        throw new Error('No authentication token available');
      }

      // Decode JWT to get user's roles
      const payload = JSON.parse(atob(token.split('.')[1]));
      const roles = payload['cognito:groups'] || [];
      
      setUserRoles(roles);
    } catch (error) {
      console.error('Error checking user roles:', error);
      toast({
        title: 'Authentication error',
        description: 'Failed to verify user permissions',
        status: 'error',
        duration: 5000
      });
    }
  };

  // Load configuration
  const loadConfiguration = async () => {
    setLoading(true);
    try {
      const [validationResult, purposesData] = await Promise.all([
        validateConfiguration(),
        getConfiguredPurposes()
      ]);

      setValidation(validationResult);
      setRequiredPurposes(purposesData.required_purposes);

      // Set currently selected accounts
      const selected: Record<string, string> = {};
      Object.entries(validationResult.configured_purposes).forEach(([purpose, info]) => {
        selected[purpose] = info.account_code;
      });
      setSelectedAccounts(selected);

      // Load available accounts for each purpose
      const accounts: Record<string, AvailableAccount[]> = {};
      for (const [purposeName, purposeInfo] of Object.entries(purposesData.required_purposes)) {
        const vwFilter = purposeInfo.expected_vw as 'Y' | 'N';
        accounts[purposeName] = await getAvailableAccounts(vwFilter);
      }
      setAvailableAccounts(accounts);

    } catch (error) {
      toast({
        title: t('yearEndSettings.errors.loadingError'),
        description: error instanceof Error ? error.message : t('yearEndSettings.messages.unknownError'),
        status: 'error',
        duration: 5000
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tenant && userRoles.length > 0) {
      // Only load configuration if user has proper role
      if (userRoles.includes('Tenant_Admin')) {
        loadConfiguration();
      } else {
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant, userRoles]);

  // Handle account selection change
  const handleAccountChange = (purpose: string, accountCode: string) => {
    setSelectedAccounts(prev => ({
      ...prev,
      [purpose]: accountCode
    }));
  };

  // Save configuration
  const handleSave = async () => {
    setSaving(true);
    try {
      // Save each purpose assignment
      for (const [purpose, accountCode] of Object.entries(selectedAccounts)) {
        if (accountCode) {
          await setAccountPurpose(accountCode, purpose);
        }
      }

      toast({
        title: t('yearEndSettings.messages.saveSuccess'),
        description: t('yearEndSettings.messages.saveSuccessDescription'),
        status: 'success',
        duration: 3000
      });

      // Reload to get updated validation
      await loadConfiguration();

    } catch (error) {
      toast({
        title: t('yearEndSettings.messages.saveError'),
        description: error instanceof Error ? error.message : t('yearEndSettings.messages.unknownError'),
        status: 'error',
        duration: 5000
      });
    } finally {
      setSaving(false);
    }
  };

  // Get purpose display name
  const getPurposeDisplayName = (purpose: string): string => {
    const names: Record<string, string> = {
      'equity_result': t('yearEndSettings.purposes.equityResult.label'),
      'pl_closing': t('yearEndSettings.purposes.plClosing.label')
    };
    return names[purpose] || purpose;
  };

  if (loading) {
    return (
      <Box p={6} textAlign="center">
        <Spinner size="xl" />
        <Text mt={4} color="gray.400">{t('yearEndSettings.loading')}</Text>
      </Box>
    );
  }

  // Check for Tenant_Admin role
  if (!userRoles.includes('Tenant_Admin')) {
    return (
      <Box p={6}>
        <Alert status="error" bg="red.900" color="red.100" borderColor="red.700" borderWidth="1px">
          <AlertIcon color="red.300" />
          <Box>
            <AlertTitle>{t('yearEndSettings.accessDenied')}</AlertTitle>
            <AlertDescription>
              {t('yearEndSettings.accessDeniedMessage')}
            </AlertDescription>
          </Box>
        </Alert>
      </Box>
    );
  }

  return (
    <Box p={6}>
      <VStack spacing={6} align="stretch">
        {/* Header */}
        <Box>
          <Heading size="lg" mb={2}>{t('yearEndSettings.title')}</Heading>
          <Text color="gray.400">
            {t('yearEndSettings.subtitle')}
          </Text>
        </Box>

        {/* Validation Status */}
        {validation && (
          <Alert
            status={validation.valid ? 'success' : 'warning'}
            variant="left-accent"
            borderRadius="md"
            bg={validation.valid ? 'green.900' : 'orange.900'}
            color={validation.valid ? 'green.100' : 'orange.100'}
            borderColor={validation.valid ? 'green.700' : 'orange.700'}
            borderWidth="1px"
          >
            <AlertIcon as={validation.valid ? CheckCircleIcon : WarningIcon} color={validation.valid ? 'green.300' : 'orange.300'} />
            <Box flex="1">
              <AlertTitle>
                {validation.valid ? t('yearEndSettings.status.complete') : t('yearEndSettings.status.incomplete')}
              </AlertTitle>
              <AlertDescription>
                {validation.valid
                  ? t('yearEndSettings.status.completeMessage')
                  : t('yearEndSettings.status.incompleteMessage')}
              </AlertDescription>
            </Box>
          </Alert>
        )}

        {/* Errors */}
        {validation && validation.errors.length > 0 && (
          <Alert status="error" variant="left-accent" borderRadius="md" bg="red.900" color="red.100" borderColor="red.700" borderWidth="1px">
            <AlertIcon color="red.300" />
            <Box flex="1">
              <AlertTitle>{t('yearEndSettings.errors.title')}</AlertTitle>
              <VStack align="start" spacing={1} mt={2}>
                {validation.errors.map((error, index) => (
                  <Text key={index} fontSize="sm">• {error}</Text>
                ))}
              </VStack>
            </Box>
          </Alert>
        )}

        {/* Warnings */}
        {validation && validation.warnings.length > 0 && (
          <Alert status="warning" variant="left-accent" borderRadius="md" bg="orange.900" color="orange.100" borderColor="orange.700" borderWidth="1px">
            <AlertIcon color="orange.300" />
            <Box flex="1">
              <AlertTitle>{t('yearEndSettings.warnings.title')}</AlertTitle>
              <VStack align="start" spacing={1} mt={2}>
                {validation.warnings.map((warning, index) => (
                  <Text key={index} fontSize="sm">• {warning}</Text>
                ))}
              </VStack>
            </Box>
          </Alert>
        )}

        <Divider />

        {/* Account Purpose Configuration */}
        <VStack spacing={6} align="stretch">
          {Object.entries(requiredPurposes).map(([purposeName, purposeInfo]) => (
            <Box
              key={purposeName}
              p={5}
              bg="gray.800"
              borderRadius="md"
              border="1px"
              borderColor="gray.700"
            >
              <FormControl>
                <HStack justify="space-between" mb={2}>
                  <FormLabel mb={0} fontWeight="bold" color="white">
                    {getPurposeDisplayName(purposeName)}
                  </FormLabel>
                  <Badge colorScheme={purposeInfo.expected_vw === 'Y' ? 'orange' : 'blue'}>
                    VW={purposeInfo.expected_vw} ({purposeInfo.expected_vw === 'Y' ? 'P&L' : 'Balance Sheet'})
                  </Badge>
                </HStack>

                <Text fontSize="sm" color="gray.400" mb={3}>
                  {purposeInfo.description}
                </Text>

                <Select
                  value={selectedAccounts[purposeName] || ''}
                  onChange={(e) => handleAccountChange(purposeName, e.target.value)}
                  placeholder={t('yearEndSettings.form.selectAccount')}
                  bg="gray.900"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                >
                  {availableAccounts[purposeName]?.map((account) => (
                    <option key={account.Account} value={account.Account}>
                      {account.Account} - {account.AccountName}
                      {account.current_purpose && account.current_purpose !== purposeName
                        ? ` (assigned to ${account.current_purpose})`
                        : ''}
                    </option>
                  ))}
                </Select>

                <FormHelperText color="gray.500">
                  Example: {purposeInfo.example}
                </FormHelperText>
              </FormControl>
            </Box>
          ))}
        </VStack>

        {/* Save Button */}
        <HStack justify="flex-end" pt={4}>
          <Button
            colorScheme="blue"
            onClick={handleSave}
            isLoading={saving}
            loadingText={t('yearEndSettings.saving')}
            isDisabled={Object.keys(selectedAccounts).length === 0}
          >
            {t('yearEndSettings.form.saveButton')}
          </Button>
        </HStack>

        {/* Help Text */}
        <Box p={4} bg="gray.800" borderRadius="md" border="1px" borderColor="gray.700">
          <Heading size="sm" mb={2}>{t('yearEndSettings.help.title')}</Heading>
          <VStack align="start" spacing={2} fontSize="sm" color="gray.400">
            <Text>
              {t('yearEndSettings.help.description')}
            </Text>
            <Text>
              <strong>{t('yearEndSettings.purposes.equityResult.label')}:</strong> {t('yearEndSettings.help.equityResultHelp')}
            </Text>
            <Text>
              <strong>{t('yearEndSettings.purposes.plClosing.label')}:</strong> {t('yearEndSettings.help.plClosingHelp')}
            </Text>
          </VStack>
        </Box>
      </VStack>
    </Box>
  );
};

export default YearEndSettings;
