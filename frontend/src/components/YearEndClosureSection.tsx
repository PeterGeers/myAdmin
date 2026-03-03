/**
 * Year-End Closure Section Component
 * 
 * Displays year-end closure status and actions within reports.
 * Designed to be embedded in Aangifte IB and other year-end reports.
 */

import React, { useState, useEffect } from 'react';
import {
  Alert,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Heading,
  HStack,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Spinner,
  Text,
  Textarea,
  useToast,
  VStack
} from '@chakra-ui/react';
import { CheckCircleIcon, WarningIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import {
  getYearStatus,
  validateYear,
  closeYear,
  reopenYear,
  YearStatus,
  YearValidation
} from '../services/yearEndClosureService';

interface YearEndClosureSectionProps {
  year: number;
  onYearClosed?: () => void;
  onYearReopened?: () => void;
}

/**
 * Year-End Closure Section Component
 */
const YearEndClosureSection: React.FC<YearEndClosureSectionProps> = ({
  year,
  onYearClosed,
  onYearReopened
}) => {
  const { t } = useTypedTranslation('finance');
  const { t: tCommon } = useTypedTranslation('common');
  const toast = useToast();

  const [yearStatus, setYearStatus] = useState<YearStatus | null>(null);
  const [validation, setValidation] = useState<YearValidation | null>(null);
  const [loading, setLoading] = useState(false);
  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [showReopenDialog, setShowReopenDialog] = useState(false);
  const [notes, setNotes] = useState('');
  const [canReopen, setCanReopen] = useState(true);
  const [reopenBlockedReason, setReopenBlockedReason] = useState<string>('');

  /**
   * Fetch year status and validation
   */
  const fetchYearStatus = async () => {
    try {
      const status = await getYearStatus(year);
      console.log('Year status response:', status);
      
      // Check if year is closed by presence of closed_date or closed flag
      const isYearClosed = status.closed === true || !!status.closed_date;
      
      // If year is closed, check if next year is also closed (blocks reopening)
      if (isYearClosed) {
        try {
          const nextYearStatus = await getYearStatus(year + 1);
          const isNextYearClosed = nextYearStatus.closed === true || !!nextYearStatus.closed_date;
          
          if (isNextYearClosed) {
            setCanReopen(false);
            setReopenBlockedReason(
              t('yearEnd.reopen.blockedByNextYear', { year: year, nextYear: year + 1 })
            );
          } else {
            setCanReopen(true);
            setReopenBlockedReason('');
          }
        } catch (error) {
          // If we can't check next year, assume we can reopen
          console.error('Error checking next year status:', error);
          setCanReopen(true);
          setReopenBlockedReason('');
        }
      }
      
      // If year is open, also fetch validation info
      if (!isYearClosed) {
        try {
          const validationResult = await validateYear(year);
          console.log('Validation result:', validationResult);
          // Merge validation info into status
          setYearStatus({
            ...status,
            can_close: validationResult.can_close,
            errors: validationResult.errors,
            warnings: validationResult.warnings,
            info: validationResult.info
          });
        } catch (error) {
          // If validation fails, just show basic status
          console.error('Error fetching validation:', error);
          setYearStatus(status);
        }
      } else {
        console.log('Year is closed, setting status:', status);
        setYearStatus(status);
      }
    } catch (error) {
      console.error('Error fetching year status:', error);
    }
  };

  /**
   * Fetch validation when opening close dialog
   */
  const handleOpenCloseDialog = async () => {
    setLoading(true);
    try {
      const result = await validateYear(year);
      setValidation(result);
      setShowCloseDialog(true);
    } catch (error: any) {
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
   * Handle year closure
   */
  const handleCloseYear = async () => {
    setLoading(true);
    try {
      const result = await closeYear(year, notes);

      toast({
        title: t('yearEnd.wizard.success'),
        description: result.message,
        status: 'success',
        duration: 5000,
        isClosable: true
      });

      setShowCloseDialog(false);
      setNotes('');
      await fetchYearStatus();
      
      if (onYearClosed) {
        onYearClosed();
      }
    } catch (error: any) {
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
   * Handle year reopening
   */
  const handleReopenYear = async () => {
    setLoading(true);
    try {
      const result = await reopenYear(year);

      toast({
        title: t('yearEnd.reopen.success'),
        description: result.message,
        status: 'success',
        duration: 5000,
        isClosable: true
      });

      setShowReopenDialog(false);
      await fetchYearStatus();
      
      if (onYearReopened) {
        onYearReopened();
      }
    } catch (error: any) {
      toast({
        title: t('yearEnd.reopen.failed'),
        description: error.message || 'Failed to reopen year',
        status: 'error',
        duration: 5000,
        isClosable: true
      });
    } finally {
      setLoading(false);
    }
  };

  // Load year status on mount and when year changes
  useEffect(() => {
    fetchYearStatus();
  }, [year]);

  if (!yearStatus) {
    return (
      <Card bg="gray.700">
        <CardBody>
          <HStack spacing={2}>
            <Spinner size="sm" color="gray.400" />
            <Text color="gray.400">{tCommon('messages.loading')}</Text>
          </HStack>
        </CardBody>
      </Card>
    );
  }

  const isClosed = yearStatus.closed === true || !!yearStatus.closed_date;

  return (
    <>
      <Card bg="gray.700">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="white">
              {t('yearEnd.title')}
            </Heading>
            <Badge colorScheme={isClosed ? 'red' : 'green'} fontSize="sm">
              {isClosed ? t('yearEnd.status.closed') : t('yearEnd.status.open')}
            </Badge>
          </HStack>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            {/* Status Information */}
            <Box>
              <Text color="white" fontWeight="bold" mb={2}>
                {t('yearEnd.status.title')}: {year}
              </Text>
              
              {isClosed && yearStatus.closed_date && (
                <VStack spacing={1} align="stretch">
                  <Text color="gray.300" fontSize="sm">
                    {t('yearEnd.closedDate')}: {new Date(yearStatus.closed_date).toLocaleDateString()}
                  </Text>
                  {yearStatus.closed_by && (
                    <Text color="gray.300" fontSize="sm">
                      {t('yearEnd.closedBy')}: {yearStatus.closed_by}
                    </Text>
                  )}
                  {yearStatus.notes && (
                    <Text color="gray.300" fontSize="sm">
                      {t('yearEnd.notes')}: {yearStatus.notes}
                    </Text>
                  )}
                </VStack>
              )}

              {!isClosed && yearStatus.info && (
                <VStack spacing={2} align="stretch" mt={2}>
                  <HStack>
                    <CheckCircleIcon color="green.400" />
                    <Text color="gray.300" fontSize="sm">
                      {t('yearEnd.netResult')}: {yearStatus.info.net_result_formatted}
                    </Text>
                  </HStack>
                  <HStack>
                    <CheckCircleIcon color="green.400" />
                    <Text color="gray.300" fontSize="sm">
                      {t('yearEnd.balanceSheetAccounts')}: {yearStatus.info.balance_sheet_accounts}
                    </Text>
                  </HStack>
                  {yearStatus.info.previous_year_closed !== undefined && (
                    <HStack>
                      {yearStatus.info.previous_year_closed ? (
                        <CheckCircleIcon color="green.400" />
                      ) : (
                        <WarningIcon color="orange.400" />
                      )}
                      <Text color="gray.300" fontSize="sm">
                        {t('yearEnd.previousYear')} ({year - 1}): {
                          yearStatus.info.previous_year_closed 
                            ? t('yearEnd.status.closed') 
                            : t('yearEnd.status.open')
                        }
                      </Text>
                    </HStack>
                  )}
                </VStack>
              )}
            </Box>

            <Divider borderColor="gray.600" />

            {/* Action Buttons */}
            <HStack spacing={3}>
              {!isClosed && (
                <Button
                  colorScheme="orange"
                  onClick={handleOpenCloseDialog}
                  isLoading={loading}
                  size="sm"
                >
                  {t('yearEnd.actions.closeYear', { year })}
                </Button>
              )}

              {isClosed && (
                <Button
                  colorScheme="red"
                  onClick={() => setShowReopenDialog(true)}
                  size="sm"
                  bg="red.600"
                  color="white"
                  _hover={{ bg: 'red.700' }}
                  isDisabled={!canReopen}
                  title={!canReopen ? reopenBlockedReason : ''}
                >
                  {t('yearEnd.actions.reopenYear', { year })}
                </Button>
              )}
            </HStack>
            
            {/* Warning message if reopen is blocked */}
            {isClosed && !canReopen && (
              <Alert status="warning" bg="orange.900" borderRadius="md">
                <AlertIcon />
                <Text color="white" fontSize="sm">
                  {reopenBlockedReason}
                </Text>
              </Alert>
            )}
          </VStack>
        </CardBody>
      </Card>

      {/* Close Year Dialog */}
      <Modal
        isOpen={showCloseDialog}
        onClose={() => setShowCloseDialog(false)}
        size="xl"
        closeOnOverlayClick={!loading}
      >
        <ModalOverlay bg="blackAlpha.800" />
        <ModalContent bg="gray.800" borderColor="gray.700" borderWidth="1px">
          <ModalHeader color="white">
            {t('yearEnd.wizard.confirmTitle', { year })}
          </ModalHeader>
          <ModalCloseButton color="gray.400" isDisabled={loading} />

          <ModalBody>
            <VStack spacing={4} align="stretch">
              {/* Validation Results */}
              {validation && (
                <>
                  {/* Errors */}
                  {validation.errors && validation.errors.length > 0 && (
                    <Alert status="error" bg="red.900" borderRadius="md">
                      <AlertIcon />
                      <Box>
                        <Text fontWeight="bold" color="white">
                          {t('yearEnd.wizard.cannotClose')}
                        </Text>
                        <VStack align="start" mt={2} spacing={1}>
                          {validation.errors.map((error, idx) => (
                            <Text key={idx} fontSize="sm" color="white">
                              • {error}
                            </Text>
                          ))}
                        </VStack>
                      </Box>
                    </Alert>
                  )}

                  {/* Warnings */}
                  {validation.warnings && validation.warnings.length > 0 && (
                    <Alert status="warning" bg="orange.900" borderRadius="md">
                      <AlertIcon />
                      <Box>
                        <Text fontWeight="bold" color="white">
                          {t('yearEnd.wizard.warnings')}
                        </Text>
                        <VStack align="start" mt={2} spacing={1}>
                          {validation.warnings.map((warning, idx) => (
                            <Text key={idx} fontSize="sm" color="white">
                              • {warning}
                            </Text>
                          ))}
                        </VStack>
                      </Box>
                    </Alert>
                  )}

                  {/* Success Info */}
                  {validation.can_close && validation.info && (
                    <Alert status="success" bg="green.900" borderRadius="md">
                      <AlertIcon />
                      <Box>
                        <Text fontWeight="bold" color="white">
                          {t('yearEnd.wizard.readyToClose')}
                        </Text>
                        <VStack align="start" mt={2} spacing={1}>
                          <Text fontSize="sm" color="white">
                            • {t('yearEnd.netResult')}: {validation.info.net_result_formatted}
                          </Text>
                          <Text fontSize="sm" color="white">
                            • {t('yearEnd.balanceSheetAccounts')}: {validation.info.balance_sheet_accounts}
                          </Text>
                        </VStack>
                      </Box>
                    </Alert>
                  )}
                </>
              )}

              {/* Notes Field */}
              {validation?.can_close && (
                <Box>
                  <Text color="white" fontWeight="bold" mb={2}>
                    {t('yearEnd.wizard.notesLabel')} ({tCommon('labels.optional')})
                  </Text>
                  <Textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder={t('yearEnd.wizard.notesPlaceholder')}
                    bg="gray.700"
                    color="white"
                    borderColor="gray.600"
                    _hover={{ borderColor: 'gray.500' }}
                    _focus={{ borderColor: 'blue.500' }}
                    rows={3}
                  />
                </Box>
              )}
            </VStack>
          </ModalBody>

          <ModalFooter>
            <HStack spacing={3}>
              <Button
                variant="ghost"
                onClick={() => setShowCloseDialog(false)}
                isDisabled={loading}
                color="gray.300"
              >
                {tCommon('actions.cancel')}
              </Button>
              {validation?.can_close && (
                <Button
                  colorScheme="orange"
                  onClick={handleCloseYear}
                  isLoading={loading}
                >
                  {t('yearEnd.actions.confirmClose')}
                </Button>
              )}
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Reopen Year Dialog */}
      <Modal
        isOpen={showReopenDialog}
        onClose={() => setShowReopenDialog(false)}
        size="md"
        closeOnOverlayClick={!loading}
      >
        <ModalOverlay bg="blackAlpha.800" />
        <ModalContent bg="gray.800" borderColor="gray.700" borderWidth="1px">
          <ModalHeader color="white">
            {t('yearEnd.reopen.confirmTitle', { year })}
          </ModalHeader>
          <ModalCloseButton color="gray.400" isDisabled={loading} />

          <ModalBody>
            <Alert status="warning" bg="orange.900" borderRadius="md">
              <AlertIcon />
              <Box>
                <Text color="white">
                  {t('yearEnd.reopen.warning')}
                </Text>
              </Box>
            </Alert>
          </ModalBody>

          <ModalFooter>
            <HStack spacing={3}>
              <Button
                variant="ghost"
                onClick={() => setShowReopenDialog(false)}
                isDisabled={loading}
                color="gray.300"
              >
                {tCommon('actions.cancel')}
              </Button>
              <Button
                colorScheme="red"
                onClick={handleReopenYear}
                isLoading={loading}
              >
                {t('yearEnd.actions.confirmReopen')}
              </Button>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </>
  );
};

export default YearEndClosureSection;
