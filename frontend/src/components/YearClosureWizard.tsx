/**
 * Year Closure Wizard Component
 * 
 * Step-by-step wizard for closing fiscal years.
 * 
 * Step 1: Select year to close
 * Step 2: Validation and confirmation
 * 
 * Shows validation errors, warnings, P&L result, and balance sheet accounts.
 */

import React, { useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  Button,
  Select,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Text,
  VStack,
  HStack,
  Spinner,
  useToast,
  FormControl,
  FormLabel,
  Textarea,
  Box,
  Divider,
  Badge
} from '@chakra-ui/react';
import { CheckCircleIcon, WarningIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import {
  validateYear,
  closeYear,
  Year,
  YearValidation
} from '../services/yearEndClosureService';

interface YearClosureWizardProps {
  availableYears: Year[];
  onClose: () => void;
}

/**
 * Year Closure Wizard Component
 */
const YearClosureWizard: React.FC<YearClosureWizardProps> = ({
  availableYears,
  onClose
}) => {
  const { t } = useTypedTranslation('finance');
  const [step, setStep] = useState(1);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [validation, setValidation] = useState<YearValidation | null>(null);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState('');
  const toast = useToast();

  /**
   * Handle year validation (Step 1 -> Step 2)
   */
  const handleValidate = async () => {
    if (!selectedYear) return;

    setLoading(true);
    try {
      const result = await validateYear(selectedYear);
      setValidation(result);
      setStep(2);
    } catch (error: any) {
      console.error('Validation error:', error);
      toast({
        title: t('yearEnd.wizard.validationFailed'),
        description: error.message || 'Failed to validate year',
        status: 'error',
        duration: 5000,
        isClosable: true
      });
    } finally {
      setLoading(false);
    }
  };

  /**
   * Handle year closure (Step 2 -> Complete)
   */
  const handleCloseYear = async () => {
    if (!selectedYear) return;

    setLoading(true);
    try {
      const result = await closeYear(selectedYear, notes);

      toast({
        title: t('yearEnd.wizard.success'),
        description: result.message,
        status: 'success',
        duration: 5000,
        isClosable: true
      });

      onClose();
    } catch (error: any) {
      console.error('Close year error:', error);
      toast({
        title: t('yearEnd.wizard.closeFailed'),
        description: error.message || 'Failed to close year',
        status: 'error',
        duration: 5000,
        isClosable: true
      });
    } finally {
      setLoading(false);
    }
  };

  /**
   * Go back to step 1
   */
  const handleBack = () => {
    setStep(1);
    setValidation(null);
  };

  return (
    <Modal isOpen={true} onClose={onClose} size="xl" closeOnOverlayClick={!loading}>
      <ModalOverlay bg="blackAlpha.800" />
      <ModalContent bg="gray.800" borderColor="gray.700" borderWidth="1px">
        <ModalHeader color="white">
          {t('yearEnd.wizard.title')} - {t('yearEnd.wizard.step', { current: step, total: 2 })}
        </ModalHeader>
        <ModalCloseButton color="gray.400" isDisabled={loading} />

        <ModalBody>
          {/* Step 1: Select Year */}
          {step === 1 && (
            <VStack spacing={4} align="stretch">
              <Text color="gray.300">
                {t('yearEnd.wizard.selectYearPrompt')}
              </Text>
              <FormControl>
                <FormLabel color="gray.400">
                  {t('yearEnd.wizard.year')}
                </FormLabel>
                <Select
                  placeholder={t('yearEnd.wizard.selectYearPlaceholder')}
                  value={selectedYear || ''}
                  onChange={(e) => setSelectedYear(Number(e.target.value))}
                  bg="gray.700"
                  borderColor="gray.600"
                  color="white"
                  _hover={{ borderColor: 'gray.500' }}
                >
                  {availableYears.map((y) => (
                    <option key={y.year} value={y.year}>
                      {y.year}
                    </option>
                  ))}
                </Select>
              </FormControl>

              <Alert status="info" bg="blue.900" borderColor="blue.500" borderWidth="1px">
                <AlertIcon color="blue.400" />
                <VStack align="start" spacing={1}>
                  <AlertTitle color="blue.200">
                    {t('yearEnd.wizard.sequentialNote')}
                  </AlertTitle>
                  <AlertDescription color="gray.300" fontSize="sm">
                    {t('yearEnd.wizard.sequentialDescription')}
                  </AlertDescription>
                </VStack>
              </Alert>
            </VStack>
          )}

          {/* Step 2: Validation & Confirmation */}
          {step === 2 && validation && (
            <VStack spacing={4} align="stretch">
              {/* Errors */}
              {validation.errors.length > 0 && (
                <Alert status="error" bg="red.900" borderColor="red.500" borderWidth="1px">
                  <AlertIcon color="red.400" />
                  <VStack align="start" spacing={2} flex="1">
                    <AlertTitle color="red.200">
                      {t('yearEnd.wizard.cannotClose')}
                    </AlertTitle>
                    {validation.errors.map((error, i) => (
                      <Text key={i} color="gray.300" fontSize="sm">
                        • {error}
                      </Text>
                    ))}
                  </VStack>
                </Alert>
              )}

              {/* Warnings */}
              {validation.warnings.length > 0 && (
                <Alert status="warning" bg="orange.900" borderColor="orange.500" borderWidth="1px">
                  <AlertIcon color="orange.400" />
                  <VStack align="start" spacing={2} flex="1">
                    <AlertTitle color="orange.200">
                      {t('yearEnd.wizard.warnings')}
                    </AlertTitle>
                    {validation.warnings.map((warning, i) => (
                      <Text key={i} color="gray.300" fontSize="sm">
                        • {warning}
                      </Text>
                    ))}
                  </VStack>
                </Alert>
              )}

              {/* Success - Can Close */}
              {validation.can_close && (
                <>
                  <Alert status="success" bg="green.900" borderColor="green.500" borderWidth="1px">
                    <AlertIcon color="green.400" />
                    <VStack align="start" spacing={1}>
                      <AlertTitle color="green.200">
                        {t('yearEnd.wizard.readyToClose', { year: selectedYear })}
                      </AlertTitle>
                      <AlertDescription color="gray.300" fontSize="sm">
                        {t('yearEnd.wizard.reviewBeforeClosing')}
                      </AlertDescription>
                    </VStack>
                  </Alert>

                  {/* Summary Information */}
                  <Box bg="gray.700" p={4} borderRadius="md" borderWidth="1px" borderColor="gray.600">
                    <VStack align="start" spacing={3}>
                      <Text color="white" fontWeight="bold">
                        {t('yearEnd.wizard.summary')}
                      </Text>
                      <Divider borderColor="gray.600" />
                      
                      <HStack justify="space-between" w="full">
                        <Text color="gray.400">
                          {t('yearEnd.wizard.netPLResult')}
                        </Text>
                        <Badge
                          colorScheme={validation.info.net_result >= 0 ? 'green' : 'red'}
                          fontSize="md"
                          px={3}
                          py={1}
                        >
                          {validation.info.net_result_formatted}
                        </Badge>
                      </HStack>

                      <HStack justify="space-between" w="full">
                        <Text color="gray.400">
                          {t('yearEnd.wizard.balanceSheetAccounts')}
                        </Text>
                        <Badge colorScheme="blue" fontSize="md" px={3} py={1}>
                          {validation.info.balance_sheet_accounts}
                        </Badge>
                      </HStack>
                    </VStack>
                  </Box>

                  {/* Notes Field */}
                  <FormControl>
                    <FormLabel color="gray.400">
                      {t('yearEnd.wizard.notes')} ({t('common.optional')})
                    </FormLabel>
                    <Textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder={t('yearEnd.wizard.notesPlaceholder')}
                      bg="gray.700"
                      borderColor="gray.600"
                      color="white"
                      rows={3}
                      _hover={{ borderColor: 'gray.500' }}
                      _focus={{ borderColor: 'blue.500' }}
                    />
                  </FormControl>
                </>
              )}
            </VStack>
          )}

          {/* Loading State */}
          {loading && (
            <HStack justify="center" py={4}>
              <Spinner color="blue.400" />
              <Text color="gray.300">{t('common.processing')}</Text>
            </HStack>
          )}
        </ModalBody>

        <ModalFooter>
          <HStack spacing={3}>
            <Button
              variant="ghost"
              onClick={onClose}
              isDisabled={loading}
              color="gray.400"
              _hover={{ bg: 'gray.700' }}
            >
              {t('common.buttons.cancel')}
            </Button>

            {step === 2 && (
              <Button
                variant="outline"
                onClick={handleBack}
                isDisabled={loading}
                colorScheme="gray"
              >
                {t('common.buttons.back')}
              </Button>
            )}

            {step === 1 && (
              <Button
                colorScheme="blue"
                onClick={handleValidate}
                isDisabled={!selectedYear || loading}
                isLoading={loading}
              >
                {t('common.buttons.next')}
              </Button>
            )}

            {step === 2 && validation?.can_close && (
              <Button
                colorScheme="red"
                onClick={handleCloseYear}
                isDisabled={loading}
                isLoading={loading}
                leftIcon={<CheckCircleIcon />}
              >
                {t('yearEnd.wizard.closeYearButton', { year: selectedYear })}
              </Button>
            )}
          </HStack>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default YearClosureWizard;
