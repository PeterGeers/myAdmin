import React, { useState } from 'react';
import {
  Box,
  VStack,
  HStack,
  Button,
  Text,
  Input,
  FormControl,
  FormLabel,
  FormErrorMessage,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Spinner,
  Alert,
  AlertIcon,
  AlertDescription,
  Badge,
} from '@chakra-ui/react';
import { SearchIcon } from '@chakra-ui/icons';
import { getVendorHistory } from '../../services/invoiceTestToolService';
import type { VendorTransaction } from '../../types/invoiceTestTool';

/** Regex for vendor name validation (same as InvoiceTestTool). */
const VENDOR_NAME_REGEX = /^[a-zA-Z0-9_-]{1,100}$/;

interface VendorHistoryPanelProps {
  /** Pre-filled vendor name from the parent form (optional). */
  vendorName?: string;
  /** Administration/tenant identifier for filtering (optional). */
  administration?: string;
}

/**
 * VendorHistoryPanel — Displays up to 20 previous transactions for a vendor.
 *
 * Allows the user to submit a vendor name to fetch transaction history.
 * Shows a read-only list with date, amount, and description columns.
 * Displays an informational message when no history is found.
 */
export function VendorHistoryPanel({ vendorName: initialVendorName, administration }: VendorHistoryPanelProps) {
  const [vendorInput, setVendorInput] = useState(initialVendorName || '');
  const [vendorError, setVendorError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<VendorTransaction[] | null>(null);
  const [fetchedVendorName, setFetchedVendorName] = useState<string | null>(null);

  const validateVendor = (name: string): string | null => {
    if (!name.trim()) {
      return 'Vendor name is required to look up history';
    }
    if (!VENDOR_NAME_REGEX.test(name)) {
      return 'Vendor name must be 1–100 characters: letters, numbers, hyphens, underscores only';
    }
    return null;
  };

  const handleVendorChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setVendorInput(value);
    if (vendorError) {
      setVendorError(validateVendor(value));
    }
  };

  const handleSubmit = async () => {
    const error = validateVendor(vendorInput);
    if (error) {
      setVendorError(error);
      return;
    }

    setVendorError(null);
    setIsLoading(true);
    setFetchError(null);
    setTransactions(null);
    setFetchedVendorName(null);

    try {
      const response = await getVendorHistory(vendorInput.trim(), administration || undefined);
      setTransactions(response.transactions);
      setFetchedVendorName(response.vendor_name);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch vendor history';
      setFetchError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  return (
    <Box
      p={5}
      bg="gray.700"
      borderRadius="lg"
      borderWidth="1px"
      borderColor="gray.600"
    >
      <VStack spacing={4} align="stretch">
        {/* Header */}
        <Text fontSize="md" fontWeight="semibold" color="orange.300">
          Vendor Transaction History
        </Text>

        {/* Search Form */}
        <HStack spacing={3} align="flex-end">
          <FormControl isInvalid={!!vendorError} flex={1}>
            <FormLabel color="gray.300" fontSize="sm">
              Vendor Name
            </FormLabel>
            <Input
              value={vendorInput}
              onChange={handleVendorChange}
              onKeyDown={handleKeyDown}
              placeholder="Enter vendor name to look up history"
              size="sm"
              bg="gray.800"
              color="white"
              borderColor="gray.600"
              _placeholder={{ color: 'gray.500' }}
              isDisabled={isLoading}
              maxLength={100}
            />
            {vendorError && (
              <FormErrorMessage>{vendorError}</FormErrorMessage>
            )}
          </FormControl>
          <Button
            size="sm"
            colorScheme="orange"
            variant="outline"
            leftIcon={<SearchIcon />}
            onClick={handleSubmit}
            isLoading={isLoading}
            isDisabled={isLoading || !vendorInput.trim()}
            loadingText="Loading..."
            spinner={<Spinner size="xs" />}
            minW="120px"
          >
            Look Up
          </Button>
        </HStack>

        {/* Error Display */}
        {fetchError && (
          <Alert status="error" bg="red.900" borderRadius="md">
            <AlertIcon />
            <AlertDescription color="gray.200" fontSize="sm">
              {fetchError}
            </AlertDescription>
          </Alert>
        )}

        {/* Results */}
        {transactions !== null && (
          <Box>
            <HStack mb={3} spacing={2}>
              <Text fontSize="sm" color="gray.300">
                History for:
              </Text>
              <Badge colorScheme="orange" fontSize="xs">
                {fetchedVendorName}
              </Badge>
              <Text fontSize="sm" color="gray.400">
                ({transactions.length} transaction{transactions.length !== 1 ? 's' : ''})
              </Text>
            </HStack>

            {transactions.length === 0 ? (
              <Alert status="info" bg="blue.900" borderRadius="md">
                <AlertIcon />
                <AlertDescription color="gray.200" fontSize="sm">
                  No transaction history found for this vendor. Extraction will proceed without historical context.
                </AlertDescription>
              </Alert>
            ) : (
              <Box overflowX="auto" maxH="400px" overflowY="auto">
                <Table size="sm" variant="simple">
                  <Thead position="sticky" top={0} bg="gray.700" zIndex={1}>
                    <Tr>
                      <Th color="gray.400" borderColor="gray.600">Date</Th>
                      <Th color="gray.400" borderColor="gray.600" isNumeric>Amount</Th>
                      <Th color="gray.400" borderColor="gray.600">Description</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {transactions.map((tx, index) => (
                      <Tr key={index} _hover={{ bg: 'gray.650' }}>
                        <Td color="gray.200" borderColor="gray.600" whiteSpace="nowrap">
                          {tx.date || '—'}
                        </Td>
                        <Td color="gray.200" borderColor="gray.600" isNumeric whiteSpace="nowrap">
                          {tx.amount != null ? `€ ${tx.amount.toFixed(2)}` : '—'}
                        </Td>
                        <Td color="gray.200" borderColor="gray.600" maxW="300px" isTruncated>
                          {tx.description || '—'}
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </Box>
            )}
          </Box>
        )}
      </VStack>
    </Box>
  );
}

export default VendorHistoryPanel;
