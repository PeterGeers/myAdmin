/**
 * ZZP Debtors & Creditors page — two tabs for receivables and payables,
 * aging analysis chart, and send-reminder action per overdue invoice.
 * Follows BankingProcessor pattern: Chakra Table, row-click shows related invoices.
 * Reference: .kiro/specs/zzp-module/design.md §6.2
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Text, Spinner, useToast,
  Tabs, TabList, TabPanels, Tab, TabPanel,
  Table, Thead, Tbody, Tr, Th, Td,
  Badge, Button, Stat, StatLabel, StatNumber, StatGroup,
  Collapse, IconButton, HStack,
} from '@chakra-ui/react';
import { ChevronDownIcon, ChevronUpIcon, EmailIcon, RepeatClockIcon, CheckCircleIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { AgingData, InvoiceStatus } from '../types/zzp';
import { getReceivables, getPayables, getAging, sendReminder, markOverdue, runPaymentCheck } from '../services/debtorService';
import { InvoiceStatusBadge } from '../components/zzp/InvoiceStatusBadge';
import { AgingChart } from '../components/zzp/AgingChart';

/** Shape returned by receivables/payables endpoints */
interface DebtorGroup {
  contact: { id: number; client_id: string; company_name: string };
  total: number;
  invoices: {
    id: number;
    invoice_number: string;
    invoice_date: string;
    due_date: string;
    grand_total: number;
    status: InvoiceStatus;
    days_overdue?: number;
  }[];
}

const formatCurrency = (amount: number) =>
  new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(amount);

const ZZPDebtors: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();

  const [receivables, setReceivables] = useState<DebtorGroup[]>([]);
  const [payables, setPayables] = useState<DebtorGroup[]>([]);
  const [aging, setAging] = useState<AgingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedContact, setExpandedContact] = useState<number | null>(null);
  const [reminderLoading, setReminderLoading] = useState<number | null>(null);
  const [overdueLoading, setOverdueLoading] = useState(false);
  const [paymentCheckLoading, setPaymentCheckLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      // Silently run overdue detection before loading data so statuses are fresh
      await markOverdue().catch(() => {});
      const [recvResp, payResp, agingResp] = await Promise.all([
        getReceivables(),
        getPayables(),
        getAging(),
      ]);
      if (recvResp.success) setReceivables(recvResp.data?.by_contact ?? recvResp.data ?? []);
      if (payResp.success) setPayables(payResp.data?.by_contact ?? payResp.data ?? []);
      if (agingResp.success) setAging(agingResp.data);
    } catch {
      toast({ title: 'Error loading debtor data', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadData(); }, [loadData]);

  const toggleContact = (contactId: number) => {
    setExpandedContact(prev => (prev === contactId ? null : contactId));
  };

  const handleSendReminder = async (invoiceId: number) => {
    try {
      setReminderLoading(invoiceId);
      const resp = await sendReminder(invoiceId);
      if (resp.success) {
        toast({ title: t('debtors.reminderSent', 'Reminder sent'), status: 'success' });
        loadData();
      } else {
        toast({ title: resp.error || 'Failed to send reminder', status: 'error' });
      }
    } catch {
      toast({ title: 'Error sending reminder', status: 'error' });
    } finally {
      setReminderLoading(null);
    }
  };

  const handleCheckOverdue = async () => {
    try {
      setOverdueLoading(true);
      const resp = await markOverdue();
      if (resp.success) {
        const count = resp.updated || 0;
        toast({
          title: count > 0
            ? t('debtors.overdueMarked', '{{count}} invoice(s) marked as overdue').replace('{{count}}', String(count))
            : t('debtors.noOverdue', 'No new overdue invoices found'),
          status: count > 0 ? 'warning' : 'info',
        });
        loadData();
      } else {
        toast({ title: resp.error || 'Error checking overdue', status: 'error' });
      }
    } catch {
      toast({ title: 'Error checking overdue invoices', status: 'error' });
    } finally {
      setOverdueLoading(false);
    }
  };

  const handleRunPaymentCheck = async () => {
    try {
      setPaymentCheckLoading(true);
      const resp = await runPaymentCheck();
      if (resp.success) {
        const { matched = 0, partial = 0, unmatched = 0 } = resp;
        toast({
          title: t('debtors.paymentCheckResult', 'Payment check: {{matched}} matched, {{partial}} partial, {{unmatched}} unmatched')
            .replace('{{matched}}', String(matched))
            .replace('{{partial}}', String(partial))
            .replace('{{unmatched}}', String(unmatched)),
          status: matched > 0 ? 'success' : 'info',
          duration: 6000,
        });
        loadData();
      } else {
        toast({ title: resp.error || 'Error running payment check', status: 'error' });
      }
    } catch {
      toast({ title: 'Error running payment check', status: 'error' });
    } finally {
      setPaymentCheckLoading(false);
    }
  };

  const renderContactTable = (groups: DebtorGroup[], showReminder: boolean) => (
    <Box overflowX="auto">
      <Table variant="simple" size="sm" bg="gray.800" color="white">
        <Thead>
          <Tr>
            <Th color="gray.400" w="40px" />
            <Th color="gray.400">{t('contacts.clientId')}</Th>
            <Th color="gray.400">{t('contacts.companyName')}</Th>
            <Th color="gray.400" isNumeric>{t('debtors.totalOutstanding')}</Th>
            <Th color="gray.400" isNumeric>{t('invoices.invoiceNumber', 'Invoices')}</Th>
          </Tr>
        </Thead>
        <Tbody>
          {groups.map(group => {
            const isExpanded = expandedContact === group.contact.id;
            const overdueCount = group.invoices.filter(
              inv => inv.status === 'overdue'
            ).length;
            return (
              <React.Fragment key={group.contact.id}>
                {/* Contact summary row */}
                <Tr
                  _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => toggleContact(group.contact.id)}
                >
                  <Td>
                    <IconButton
                      aria-label="Toggle invoices"
                      icon={isExpanded ? <ChevronUpIcon /> : <ChevronDownIcon />}
                      size="xs"
                      variant="ghost"
                      color="gray.400"
                    />
                  </Td>
                  <Td fontWeight="semibold">{group.contact.client_id}</Td>
                  <Td>
                    {group.contact.company_name}
                    {overdueCount > 0 && (
                      <Badge ml={2} colorScheme="red" variant="subtle" fontSize="xs">
                        {overdueCount} overdue
                      </Badge>
                    )}
                  </Td>
                  <Td isNumeric fontWeight="semibold">{formatCurrency(group.total)}</Td>
                  <Td isNumeric>{group.invoices.length}</Td>
                </Tr>

                {/* Expanded invoice rows */}
                {isExpanded && (
                  <Tr>
                    <Td colSpan={5} p={0}>
                      <Collapse in={isExpanded} animateOpacity>
                        <Box bg="gray.750" px={6} py={3}>
                          <Table variant="simple" size="sm" color="gray.300">
                            <Thead>
                              <Tr>
                                <Th color="gray.500">{t('invoices.invoiceNumber')}</Th>
                                <Th color="gray.500">{t('invoices.invoiceDate')}</Th>
                                <Th color="gray.500">{t('invoices.dueDate')}</Th>
                                <Th color="gray.500">Status</Th>
                                <Th color="gray.500" isNumeric>{t('invoices.grandTotal')}</Th>
                                {showReminder && <Th color="gray.500" />}
                              </Tr>
                            </Thead>
                            <Tbody>
                              {group.invoices.map(inv => (
                                <Tr key={inv.id}>
                                  <Td>{inv.invoice_number}</Td>
                                  <Td>{inv.invoice_date}</Td>
                                  <Td>{inv.due_date}</Td>
                                  <Td><InvoiceStatusBadge status={inv.status} /></Td>
                                  <Td isNumeric>{formatCurrency(inv.grand_total)}</Td>
                                  {showReminder && (
                                    <Td>
                                      {(inv.status === 'overdue' || inv.status === 'sent') && (
                                        <Button
                                          size="xs"
                                          leftIcon={<EmailIcon />}
                                          colorScheme={inv.status === 'overdue' ? 'red' : 'orange'}
                                          variant="outline"
                                          isLoading={reminderLoading === inv.id}
                                          onClick={e => {
                                            e.stopPropagation();
                                            handleSendReminder(inv.id);
                                          }}
                                        >
                                          {t('debtors.sendReminder')}
                                        </Button>
                                      )}
                                    </Td>
                                  )}
                                </Tr>
                              ))}
                            </Tbody>
                          </Table>
                        </Box>
                      </Collapse>
                    </Td>
                  </Tr>
                )}
              </React.Fragment>
            );
          })}
          {groups.length === 0 && (
            <Tr>
              <Td colSpan={5}>
                <Text color="gray.500">{t('common.noData')}</Text>
              </Td>
            </Tr>
          )}
        </Tbody>
      </Table>
    </Box>
  );

  if (loading) {
    return (
      <Box p={6} textAlign="center">
        <Spinner color="white" size="lg" />
      </Box>
    );
  }

  const receivablesTotal = receivables.reduce((sum, g) => sum + g.total, 0);
  const payablesTotal = payables.reduce((sum, g) => sum + g.total, 0);

  return (
    <Box p={6}>
      {/* Header: title + actions */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">
          {t('debtors.title', 'Debtors & Creditors')}
        </Text>
        <HStack spacing={2}>
          <Button
            leftIcon={<RepeatClockIcon />}
            size="sm"
            variant="outline"
            colorScheme="orange"
            color="white"
            isLoading={overdueLoading}
            onClick={handleCheckOverdue}
          >
            {t('debtors.checkOverdue', 'Check Overdue')}
          </Button>
          <Button
            leftIcon={<CheckCircleIcon />}
            size="sm"
            variant="outline"
            colorScheme="green"
            color="white"
            isLoading={paymentCheckLoading}
            onClick={handleRunPaymentCheck}
          >
            {t('debtors.runPaymentCheck', 'Payment Check')}
          </Button>
        </HStack>
      </Flex>

      {/* Summary stats */}
      <StatGroup mb={6}>
        <Stat bg="gray.800" p={4} borderRadius="md" mr={4}>
          <StatLabel color="gray.400">{t('debtors.receivables')}</StatLabel>
          <StatNumber color="green.400">{formatCurrency(receivablesTotal)}</StatNumber>
        </Stat>
        <Stat bg="gray.800" p={4} borderRadius="md" mr={4}>
          <StatLabel color="gray.400">{t('debtors.payables')}</StatLabel>
          <StatNumber color="red.400">{formatCurrency(payablesTotal)}</StatNumber>
        </Stat>
        {aging && (
          <Stat bg="gray.800" p={4} borderRadius="md">
            <StatLabel color="gray.400">{t('debtors.totalOutstanding')}</StatLabel>
            <StatNumber color="orange.400">
              {formatCurrency(aging.total_outstanding)}
            </StatNumber>
          </Stat>
        )}
      </StatGroup>

      {/* Aging chart */}
      {aging?.buckets && (
        <Box bg="gray.800" p={4} borderRadius="md" mb={6}>
          <Text fontSize="md" fontWeight="semibold" color="white" mb={3}>
            {t('debtors.aging')}
          </Text>
          <AgingChart buckets={aging.buckets} />
        </Box>
      )}

      {/* Tabs: Debiteuren / Crediteuren */}
      <Tabs variant="soft-rounded" colorScheme="orange">
        <TabList mb={4}>
          <Tab color="gray.400" _selected={{ color: 'white', bg: 'orange.500' }}>
            <HStack spacing={2}>
              <Text>{t('debtors.receivables')}</Text>
              {receivables.length > 0 && (
                <Badge colorScheme="green" variant="solid" fontSize="xs">
                  {receivables.length}
                </Badge>
              )}
            </HStack>
          </Tab>
          <Tab color="gray.400" _selected={{ color: 'white', bg: 'orange.500' }}>
            <HStack spacing={2}>
              <Text>{t('debtors.payables')}</Text>
              {payables.length > 0 && (
                <Badge colorScheme="red" variant="solid" fontSize="xs">
                  {payables.length}
                </Badge>
              )}
            </HStack>
          </Tab>
        </TabList>

        <TabPanels>
          <TabPanel px={0}>
            {renderContactTable(receivables, true)}
          </TabPanel>
          <TabPanel px={0}>
            {renderContactTable(payables, false)}
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default ZZPDebtors;
