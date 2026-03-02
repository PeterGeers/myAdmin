/**
 * Year-End Closure Page
 * 
 * Main page for closing fiscal years.
 * Displays available years, closed years, and provides year closure wizard.
 * 
 * Requires: finance_read permission (year_end_close for closing)
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  VStack,
  HStack,
  Heading,
  Text,
  Spinner,
  useToast,
  Container,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Badge
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import YearClosureWizard from '../components/YearClosureWizard';
import ClosedYearsTable from '../components/ClosedYearsTable';
import {
  getAvailableYears,
  getClosedYears,
  Year,
  ClosedYear
} from '../services/yearEndClosureService';

/**
 * Year-End Closure Page Component
 */
const YearEndClosure: React.FC = () => {
  const { t } = useTypedTranslation('finance');
  const [loading, setLoading] = useState(true);
  const [availableYears, setAvailableYears] = useState<Year[]>([]);
  const [closedYears, setClosedYears] = useState<ClosedYear[]>([]);
  const [showWizard, setShowWizard] = useState(false);
  const toast = useToast();

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  /**
   * Load available and closed years
   */
  const loadData = async () => {
    setLoading(true);
    try {
      const [available, closed] = await Promise.all([
        getAvailableYears(),
        getClosedYears()
      ]);

      setAvailableYears(available);
      setClosedYears(closed);
    } catch (error: any) {
      console.error('Error loading year-end data:', error);
      toast({
        title: t('yearEnd.errors.loadFailed'),
        description: error.message || 'Failed to load year-end data',
        status: 'error',
        duration: 5000,
        isClosable: true
      });
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handle wizard close
   */
  const handleWizardClose = () => {
    setShowWizard(false);
    loadData(); // Reload data after closing wizard
  };

  if (loading) {
    return (
      <Box
        minH="100vh"
        bg="gray.900"
        display="flex"
        alignItems="center"
        justifyContent="center"
      >
        <VStack spacing={4}>
          <Spinner size="xl" color="blue.400" />
          <Text color="gray.300">{t('common.loading')}</Text>
        </VStack>
      </Box>
    );
  }

  return (
    <Box minH="100vh" bg="gray.900" py={8}>
      <Container maxW="container.xl">
        <VStack spacing={8} align="stretch">
          {/* Header */}
          <HStack justify="space-between" align="center">
            <VStack align="start" spacing={1}>
              <Heading color="white" size="xl">
                {t('yearEnd.title')}
              </Heading>
              <Text color="gray.400">
                {t('yearEnd.subtitle')}
              </Text>
            </VStack>

            {availableYears.length > 0 && (
              <Button
                leftIcon={<AddIcon />}
                colorScheme="blue"
                size="lg"
                onClick={() => setShowWizard(true)}
              >
                {t('yearEnd.closeYear')}
              </Button>
            )}
          </HStack>

          {/* No years available message */}
          {availableYears.length === 0 && closedYears.length === 0 && (
            <Alert
              status="info"
              bg="blue.900"
              borderColor="blue.500"
              borderWidth="1px"
              borderRadius="md"
            >
              <AlertIcon color="blue.400" />
              <VStack align="start" spacing={1}>
                <AlertTitle color="blue.200">
                  {t('yearEnd.noYears.title')}
                </AlertTitle>
                <AlertDescription color="gray.300">
                  {t('yearEnd.noYears.description')}
                </AlertDescription>
              </VStack>
            </Alert>
          )}

          {/* Available years info */}
          {availableYears.length > 0 && (
            <Alert
              status="warning"
              bg="orange.900"
              borderColor="orange.500"
              borderWidth="1px"
              borderRadius="md"
            >
              <AlertIcon color="orange.400" />
              <VStack align="start" spacing={1}>
                <AlertTitle color="orange.200">
                  {t('yearEnd.availableYears.title', { count: availableYears.length })}
                </AlertTitle>
                <AlertDescription color="gray.300">
                  {t('yearEnd.availableYears.description')}
                </AlertDescription>
                <HStack mt={2} wrap="wrap" spacing={2}>
                  {availableYears.slice(0, 10).map((y) => (
                    <Badge key={y.year} colorScheme="orange" fontSize="sm">
                      {y.year}
                    </Badge>
                  ))}
                  {availableYears.length > 10 && (
                    <Badge colorScheme="gray" fontSize="sm">
                      +{availableYears.length - 10} more
                    </Badge>
                  )}
                </HStack>
              </VStack>
            </Alert>
          )}

          {/* Closed years table */}
          <ClosedYearsTable years={closedYears} />

          {/* Wizard */}
          {showWizard && (
            <YearClosureWizard
              availableYears={availableYears}
              onClose={handleWizardClose}
            />
          )}
        </VStack>
      </Container>
    </Box>
  );
};

export default YearEndClosure;
