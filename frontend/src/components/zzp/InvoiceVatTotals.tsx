/**
 * InvoiceVatTotals — VAT summary table and invoice totals display.
 * Extracted from ZZPInvoiceDetail to reduce file size.
 */

import React from 'react';
import {
  Box, Flex, VStack, HStack, Text, Divider,
  Table, Thead, Tbody, Tr, Th, Td,
} from '@chakra-ui/react';
import { VatSummaryLine } from '../../types/zzp';

export interface InvoiceVatTotalsProps {
  displayVatSummary: VatSummaryLine[];
  displaySubtotal: number;
  displayVatTotal: number;
  displayGrandTotal: number;
  currency: string;
  isNew: boolean;
  formatCurrency: (amount: number, cur?: string) => string;
  t: (key: string, fallback?: string) => string;
}

export const InvoiceVatTotals: React.FC<InvoiceVatTotalsProps> = ({
  displayVatSummary, displaySubtotal, displayVatTotal, displayGrandTotal,
  currency, isNew, formatCurrency, t,
}) => {
  return (
    <Flex wrap="wrap" gap={6} justify="flex-end">
      {/* VAT breakdown */}
      {(displayVatSummary.length > 0 || !isNew) && (
        <Box minW="280px">
          <Text fontSize="sm" fontWeight="bold" color="gray.300" mb={2}>
            {t('invoices.vatSummary', 'VAT Summary')}
          </Text>
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th color="gray.400">{t('invoices.vatCode', 'VAT Code')}</Th>
                <Th color="gray.400" isNumeric>{t('invoices.vatRate', 'Rate')}</Th>
                <Th color="gray.400" isNumeric>{t('invoices.baseAmount', 'Base')}</Th>
                <Th color="gray.400" isNumeric>{t('invoices.vatAmount', 'VAT')}</Th>
              </Tr>
            </Thead>
            <Tbody>
              {displayVatSummary.map((vs, idx) => (
                <Tr key={idx}>
                  <Td color="white" fontSize="sm">{vs.vat_code}</Td>
                  <Td color="white" fontSize="sm" isNumeric>{vs.vat_rate}%</Td>
                  <Td color="white" fontSize="sm" isNumeric>{formatCurrency(vs.base_amount, currency)}</Td>
                  <Td color="white" fontSize="sm" isNumeric>{formatCurrency(vs.vat_amount, currency)}</Td>
                </Tr>
              ))}
              {displayVatSummary.length === 0 && (
                <Tr><Td colSpan={4}><Text color="gray.500" fontSize="sm">—</Text></Td></Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      )}

      {/* Totals */}
      <VStack align="flex-end" spacing={1} minW="200px">
        <HStack justify="space-between" w="full">
          <Text color="gray.400" fontSize="sm">{t('invoices.subtotal', 'Subtotal')}</Text>
          <Text color="white" fontSize="sm" fontWeight="medium">
            {formatCurrency(displaySubtotal, currency)}
          </Text>
        </HStack>
        <HStack justify="space-between" w="full">
          <Text color="gray.400" fontSize="sm">{t('invoices.vatTotal', 'VAT')}</Text>
          <Text color="white" fontSize="sm" fontWeight="medium">
            {formatCurrency(displayVatTotal, currency)}
          </Text>
        </HStack>
        <Divider borderColor="gray.500" />
        <HStack justify="space-between" w="full">
          <Text color="gray.300" fontSize="md" fontWeight="bold">{t('invoices.grandTotal', 'Total')}</Text>
          <Text color="orange.300" fontSize="md" fontWeight="bold">
            {formatCurrency(displayGrandTotal, currency)}
          </Text>
        </HStack>
      </VStack>
    </Flex>
  );
};
