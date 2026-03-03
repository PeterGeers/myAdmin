/**
 * Closed Years Table Component
 * 
 * Displays a table of closed fiscal years with details.
 * Shows year, closure date, closed by user, notes, status, and actions.
 */

import React, { useState } from 'react';
import {
  Box,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Badge,
  Text,
  Heading,
  VStack,
  IconButton,
  useToast,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Button,
  useDisclosure
} from '@chakra-ui/react';
import { CheckCircleIcon, DeleteIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { ClosedYear, reopenYear } from '../services/yearEndClosureService';

interface ClosedYearsTableProps {
  years: ClosedYear[];
  onYearReopened?: () => void;
}

/**
 * Closed Years Table Component
 */
const ClosedYearsTable: React.FC<ClosedYearsTableProps> = ({ years, onYearReopened }) => {
  const { t } = useTypedTranslation('finance');
  const { t: tCommon } = useTypedTranslation('common');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  // Format date for display
  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Handle reopen year click
  const handleReopenClick = (year: number) => {
    setSelectedYear(year);
    onOpen();
  };

  // Confirm reopen year
  const handleConfirmReopen = async () => {
    if (!selectedYear) return;

    setLoading(true);
    try {
      await reopenYear(selectedYear);
      
      toast({
        title: t('yearEnd.reopen.success'),
        description: t('yearEnd.reopen.successMessage', { year: selectedYear }),
        status: 'success',
        duration: 5000,
        isClosable: true
      });

      onClose();
      if (onYearReopened) {
        onYearReopened();
      }
    } catch (error: any) {
      console.error('Reopen year error:', error);
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

  // No closed years
  if (years.length === 0) {
    return (
      <Box
        bg="gray.800"
        borderRadius="lg"
        p={6}
        borderWidth="1px"
        borderColor="gray.700"
      >
        <Heading size="md" color="white" mb={4}>
          {t('yearEnd.closedYears.title')}
        </Heading>
        <Text color="gray.400">
          {t('yearEnd.closedYears.noYears')}
        </Text>
      </Box>
    );
  }

  return (
    <Box
      bg="gray.800"
      borderRadius="lg"
      p={6}
      borderWidth="1px"
      borderColor="gray.700"
    >
      <VStack align="stretch" spacing={4}>
        <Heading size="md" color="white">
          {t('yearEnd.closedYears.title')}
        </Heading>

        <Box overflowX="auto">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th color="gray.400" borderColor="gray.700">
                  {t('yearEnd.table.year')}
                </Th>
                <Th color="gray.400" borderColor="gray.700">
                  {t('yearEnd.table.closedDate')}
                </Th>
                <Th color="gray.400" borderColor="gray.700">
                  {t('yearEnd.table.closedBy')}
                </Th>
                <Th color="gray.400" borderColor="gray.700">
                  {t('yearEnd.table.notes')}
                </Th>
                <Th color="gray.400" borderColor="gray.700">
                  {t('yearEnd.table.status')}
                </Th>
                <Th color="gray.400" borderColor="gray.700">
                  {t('yearEnd.table.actions')}
                </Th>
              </Tr>
            </Thead>
            <Tbody>
              {years.map((year) => (
                <Tr key={year.year} _hover={{ bg: 'gray.700' }}>
                  <Td color="white" fontWeight="bold" borderColor="gray.700">
                    {year.year}
                  </Td>
                  <Td color="gray.300" borderColor="gray.700">
                    {formatDate(year.closed_date)}
                  </Td>
                  <Td color="gray.300" borderColor="gray.700">
                    {year.closed_by}
                  </Td>
                  <Td color="gray.300" borderColor="gray.700">
                    {year.notes || '-'}
                  </Td>
                  <Td borderColor="gray.700">
                    <Badge
                      colorScheme="green"
                      display="flex"
                      alignItems="center"
                      gap={1}
                      w="fit-content"
                    >
                      <CheckCircleIcon />
                      {t('yearEnd.table.closed')}
                    </Badge>
                  </Td>
                  <Td borderColor="gray.700">
                    <IconButton
                      aria-label={t('yearEnd.reopen.button')}
                      icon={<DeleteIcon />}
                      size="sm"
                      colorScheme="red"
                      variant="ghost"
                      onClick={() => handleReopenClick(year.year)}
                      title={t('yearEnd.reopen.button')}
                    />
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>

        <Text color="gray.400" fontSize="sm">
          {t('yearEnd.closedYears.count', { count: years.length })}
        </Text>
      </VStack>

      {/* Confirmation Dialog */}
      <AlertDialog
        isOpen={isOpen}
        leastDestructiveRef={cancelRef}
        onClose={onClose}
      >
        <AlertDialogOverlay bg="blackAlpha.800">
          <AlertDialogContent bg="gray.800" borderColor="gray.700" borderWidth="1px">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="white">
              {t('yearEnd.reopen.confirmTitle')}
            </AlertDialogHeader>

            <AlertDialogBody color="gray.300">
              {t('yearEnd.reopen.confirmMessage', { year: selectedYear })}
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button
                ref={cancelRef}
                onClick={onClose}
                variant="ghost"
                color="gray.400"
                _hover={{ bg: 'gray.700' }}
              >
                {tCommon('buttons.cancel')}
              </Button>
              <Button
                colorScheme="red"
                onClick={handleConfirmReopen}
                ml={3}
                isLoading={loading}
              >
                {t('yearEnd.reopen.confirm')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
};

export default ClosedYearsTable;
