/**
 * Closed Years Table Component
 * 
 * Displays a table of closed fiscal years with details.
 * Shows year, closure date, closed by user, notes, and status.
 */

import React from 'react';
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
  VStack
} from '@chakra-ui/react';
import { CheckCircleIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { ClosedYear } from '../services/yearEndClosureService';

interface ClosedYearsTableProps {
  years: ClosedYear[];
}

/**
 * Closed Years Table Component
 */
const ClosedYearsTable: React.FC<ClosedYearsTableProps> = ({ years }) => {
  const { t } = useTypedTranslation('finance');

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
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>

        <Text color="gray.400" fontSize="sm">
          {t('yearEnd.closedYears.count', { count: years.length })}
        </Text>
      </VStack>
    </Box>
  );
};

export default ClosedYearsTable;
