/**
 * BankingProcessor Component
 *
 * Thin orchestration layer that composes the Banking Processor page using
 * extracted sub-components and the useBankingProcessor hook for state/logic.
 */

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
  HStack,
  Heading,
  Input,
  Select,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Table,
  TableContainer,
  Tabs,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tooltip,
  Tr,
  VStack,
} from '@chakra-ui/react';
import React from 'react';
import BankingProcessorTable from './BankingProcessorTable';
import BankingMutatiesTab from './banking/BankingMutatiesTab';
import BankingFileUpload from './BankingFileUpload';
import BankingPatternPanel from './BankingPatternPanel';
import BankingTransactionModal from './BankingTransactionModal';
import { FilterableHeader } from './filters/FilterableHeader';
import { useBankingProcessor, formatAmount } from '../hooks/useBankingProcessor';
import { useTenantFunctions } from '../hooks/useTenantFunctions';

// Re-export types and utilities for backward compatibility
export type { Transaction, CreditCardAccount, LookupData } from './BankingProcessor.types';
export { parseCSVRow, processRevolutTransaction, processRabobankTransaction } from './BankingProcessor.utils';

const BankingProcessor: React.FC = () => {
  const bp = useBankingProcessor();
  const { hasFunction } = useTenantFunctions();

  return (
    <Box w="100%" p={4}>
      <Tabs variant="enclosed" colorScheme="blue">
        <TabList>
          <Tab>{bp.t('tabs.fileProcessing')}</Tab>
          <Tab>{bp.t('tabs.mutaties')}</Tab>
          <Tab>{bp.t('tabs.checkAccounts')}</Tab>
          <Tab>{bp.t('tabs.checkReference')}</Tab>
          {hasFunction('str_channel_revenue') && <Tab>{bp.t('tabs.strChannelRevenue')}</Tab>}
        </TabList>

        <TabPanels>
          {/* File Processing Tab */}
          <TabPanel>
            <BankingFileUpload
              lookupData={bp.lookupData}
              setLookupData={bp.setLookupData}
              testMode={bp.testMode}
              onTransactionsLoaded={bp.setTransactions}
              setLoading={bp.setLoading}
              loading={bp.loading}
              message={bp.message}
              setMessage={bp.setMessage}
              mapLookupData={bp.mapLookupData}
            />

            <BankingProcessorTable
              transactions={bp.transactions}
              chartAccounts={bp.chartAccounts}
              loading={bp.loading}
              patternResults={bp.patternResults}
              updateTransaction={bp.updateTransaction}
              onApplyPatterns={bp.applyPatterns}
              onSaveTransactions={bp.handleSaveTransactions}
              getPatternFieldStyle={bp.getPatternFieldStyle}
              t={bp.t}
            />
          </TabPanel>

          {/* Mutaties Tab */}
          <TabPanel>
            <BankingMutatiesTab
              mutaties={bp.mutaties}
              filterOptions={bp.filterOptions}
              mutatiesFilters={bp.mutatiesFilters}
              setMutatiesFilters={bp.setMutatiesFilters}
              openEditModal={bp.openEditModal}
              openInsertModal={bp.openInsertModal}
              copyToClipboard={bp.copyToClipboard}
              handleRef3Click={bp.handleRef3Click}
            />
          </TabPanel>

          {/* Check Accounts Tab */}
          <TabPanel>
            <CheckAccountsTab bp={bp} />
          </TabPanel>

          {/* Check Reference Tab */}
          <TabPanel>
            <CheckReferenceTab bp={bp} />
          </TabPanel>

          {/* STR Channel Revenue Tab */}
          {hasFunction('str_channel_revenue') && (
            <TabPanel>
              <StrChannelRevenueTab bp={bp} />
            </TabPanel>
          )}
        </TabPanels>
      </Tabs>

      {/* Edit/Insert Record Modal */}
      <BankingTransactionModal
        isOpen={bp.isOpen}
        onClose={bp.onClose}
        editingRecord={bp.editingRecord}
        setEditingRecord={bp.setEditingRecord}
        isInsertMode={bp.isInsertMode}
        loading={bp.loading}
        modalError={bp.modalError}
        chartAccounts={bp.chartAccounts}
        onSave={bp.handleSaveRecord}
        onKeyDown={bp.handleKeyDown}
        t={bp.t}
      />

      {/* Pattern Matching Panel */}
      <BankingPatternPanel
        transactions={bp.transactions}
        loading={bp.loading}
        patternResults={bp.patternResults}
        patternSuggestions={bp.patternSuggestions}
        showPatternApproval={bp.showPatternApproval}
        showSaveConfirmation={bp.showSaveConfirmation}
        onApprovePatterns={bp.approvePatternSuggestions}
        onRejectPatterns={bp.rejectPatternSuggestions}
        onClosePatternApproval={() => bp.setShowPatternApproval(false)}
        onConfirmSave={bp.confirmSaveTransactions}
        onCloseSaveConfirmation={() => bp.setShowSaveConfirmation(false)}
        t={bp.t}
      />
    </Box>
  );
};

// ---------------------------------------------------------------------------
// Sub-sections (kept inline to preserve original rendering, each < 200 lines)
// ---------------------------------------------------------------------------

interface TabProps {
  bp: ReturnType<typeof useBankingProcessor>;
}

const CheckAccountsTab: React.FC<TabProps> = ({ bp }) => (
  <VStack align="stretch" spacing={4}>
    <HStack justify="space-between">
      <Heading size="md">{bp.t('checkAccounts.title')}</Heading>
      <HStack wrap="wrap" spacing={3}>
        <Button onClick={bp.checkBankingAccounts} isLoading={bp.checkingAccounts} colorScheme="blue" size="sm">
          {bp.t('checkAccounts.checkBalances')}
        </Button>
        <FormControl maxW="130px">
          <FormLabel color="white" fontSize="sm">{bp.t('checkAccounts.endDate')}</FormLabel>
          <Input type="date" value={bp.endDate} onChange={(e) => bp.setEndDate(e.target.value)} onKeyDown={bp.handleKeyDown} bg="gray.600" color="white" size="sm" />
        </FormControl>
        <Button onClick={bp.checkSequenceNumbers} isLoading={bp.checkingSequence} colorScheme="orange" size="sm">
          {bp.t('checkSequence.checkSequence')}
        </Button>
        <FormControl maxW="160px">
          <FormLabel color="white" fontSize="sm">{bp.t('checkSequence.selectAccount')}</FormLabel>
          <Select value={bp.selectedAccount} onChange={(e) => bp.setSelectedAccount(e.target.value)} bg="gray.600" color="white" size="sm">
            {bp.lookupData.bank_accounts.map((account) => (
              <option key={`${account.Account}-${account.administration}`} value={`${account.Account}-${account.administration}`}>
                {account.Account} - {account.rekeningNummer}
              </option>
            ))}
          </Select>
        </FormControl>
        <FormControl maxW="130px">
          <FormLabel color="white" fontSize="sm">Start Date</FormLabel>
          <Tooltip label="Set by annual closure" isDisabled={bp.openingBalanceDate === null} placement="top" hasArrow>
            <Input
              type="date"
              value={bp.sequenceStartDate}
              onChange={(e) => bp.setSequenceStartDate(e.target.value)}
              onKeyDown={bp.handleKeyDown}
              isReadOnly={bp.openingBalanceDate !== null}
              bg={bp.openingBalanceDate !== null ? 'gray.700' : 'gray.600'}
              color="white"
              size="sm"
              cursor={bp.openingBalanceDate !== null ? 'not-allowed' : undefined}
            />
          </Tooltip>
          {bp.openingBalanceDate !== null && (
            <Text fontSize="xs" color="orange.300" mt={1}>Set by annual closure</Text>
          )}
        </FormControl>
      </HStack>
    </HStack>

    {bp.bankingBalances.length > 0 && (
      <TableContainer>
        <Table size="sm" variant="simple">
          <Thead>
            <Tr>
              <Th color="white" w="20px"></Th>
              <Th color="white">Administration</Th>
              <Th color="white">Account</Th>
              <Th color="white">Account Name</Th>
              <Th color="white" isNumeric>Calculated Balance</Th>
            </Tr>
          </Thead>
          <Tbody>
            {bp.bankingBalances
              .sort((a, b) => a.Administration !== b.Administration ? a.Administration.localeCompare(b.Administration) : a.Reknum.localeCompare(b.Reknum))
              .map((balance) => {
                const rowKey = `${balance.Reknum}-${balance.Administration}`;
                const isExpanded = bp.expandedRows.has(rowKey);
                return (
                  <React.Fragment key={rowKey}>
                    <Tr>
                      <Td color="white" fontSize="sm" w="20px">
                        <Button size="xs" variant="ghost" onClick={() => bp.toggleRowExpansion(rowKey)} color="white">
                          {isExpanded ? '▼' : '▶'}
                        </Button>
                      </Td>
                      <Td color="white" fontSize="sm">{balance.Administration}</Td>
                      <Td color="white" fontSize="sm">{balance.Reknum}</Td>
                      <Td color="white" fontSize="sm">{balance.account_name}</Td>
                      <Td color="white" fontSize="sm" isNumeric>
                        €{Number(balance.calculated_balance).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                      </Td>
                    </Tr>
                    {isExpanded && balance.last_transactions && balance.last_transactions.length > 0 && (
                      <Tr>
                        <Td colSpan={5} p={0}>
                          <Box bg="gray.800" p={2}>
                            <Text color="white" fontSize="xs" mb={2} fontWeight="bold">
                              Last Transaction Date: {balance.last_transaction_date ? new Date(balance.last_transaction_date).toLocaleDateString('nl-NL') : 'N/A'}
                            </Text>
                            <Table size="xs" variant="simple">
                              <Thead>
                                <Tr>
                                  <Th color="gray.300" fontSize="xs">Description</Th>
                                  <Th color="gray.300" fontSize="xs" isNumeric pr={4}>Amount</Th>
                                  <Th color="gray.300" fontSize="xs" pl={4}>Debet</Th>
                                  <Th color="gray.300" fontSize="xs">Credit</Th>
                                  <Th color="gray.300" fontSize="xs">Ref2</Th>
                                  <Th color="gray.300" fontSize="xs">Ref3</Th>
                                </Tr>
                              </Thead>
                              <Tbody>
                                {balance.last_transactions.map((transaction, txIndex) => (
                                  <Tr key={txIndex}>
                                    <Td color="gray.300" fontSize="xs" maxW="200px" isTruncated title={transaction.TransactionDescription}>
                                      {transaction.TransactionDescription}
                                    </Td>
                                    <Td color="gray.300" fontSize="xs" isNumeric pr={4}>
                                      €{Number(transaction.TransactionAmount).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                                    </Td>
                                    <Td color="gray.300" fontSize="xs" pl={4}>{transaction.Debet}</Td>
                                    <Td color="gray.300" fontSize="xs">{transaction.Credit}</Td>
                                    <Td color="gray.300" fontSize="xs">{transaction.Ref2}</Td>
                                    <Td color="gray.300" fontSize="xs" maxW="100px" isTruncated title={transaction.Ref3}>{transaction.Ref3}</Td>
                                  </Tr>
                                ))}
                              </Tbody>
                            </Table>
                          </Box>
                        </Td>
                      </Tr>
                    )}
                  </React.Fragment>
                );
              })}
          </Tbody>
        </Table>
      </TableContainer>
    )}

    {bp.sequenceResult && (
      <Box bg="gray.800" p={4} borderRadius="md">
        <Heading size="sm" color="white" mb={3}>
          {bp.sequenceResult.check_type === 'balance_comparison' ? 'Balance Check Results' : 'Sequence Check Results'}
        </Heading>
        <Grid templateColumns="repeat(2, 1fr)" gap={4} mb={4}>
          <Text color="white" fontSize="sm">Account: {bp.sequenceResult.account_code} ({bp.sequenceResult.administration})</Text>
          <Text color="white" fontSize="sm">IBAN: {bp.sequenceResult.iban}</Text>
          <Text color="white" fontSize="sm">Since: {bp.sequenceResult.start_date}</Text>
          <Text color="white" fontSize="sm">Total Transactions: {bp.sequenceResult.total_transactions}</Text>
          {bp.sequenceResult.check_type === 'balance_comparison' ? (
            <Text color="white" fontSize="sm" gridColumn="span 2">{bp.sequenceResult.message}</Text>
          ) : (
            <Text color="white" fontSize="sm" gridColumn="span 2">Sequence Range: {bp.sequenceResult.first_sequence} - {bp.sequenceResult.last_sequence}</Text>
          )}
        </Grid>

        {bp.sequenceResult.has_gaps ? (
          <Box>
            <Text color="red.300" fontWeight="bold" mb={2}>
              ⚠️ {bp.sequenceResult.sequence_issues.length} {bp.sequenceResult.check_type === 'balance_comparison' ? 'Balance Issues' : 'Sequence Issues'} Found:
            </Text>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="gray.300" fontSize="xs">Expected</Th>
                  <Th color="gray.300" fontSize="xs">Found</Th>
                  <Th color="gray.300" fontSize="xs">Gap</Th>
                  <Th color="gray.300" fontSize="xs">Date</Th>
                  <Th color="gray.300" fontSize="xs">Description</Th>
                </Tr>
              </Thead>
              <Tbody>
                {bp.sequenceResult.sequence_issues.map((issue, index) => (
                  <Tr key={index}>
                    <Td color="gray.300" fontSize="xs">{issue.expected}</Td>
                    <Td color="gray.300" fontSize="xs">{issue.found}</Td>
                    <Td color="gray.300" fontSize="xs">{issue.gap > 0 ? `+${issue.gap}` : issue.gap}</Td>
                    <Td color="gray.300" fontSize="xs">{issue.date ? new Date(issue.date).toLocaleDateString('nl-NL') : ''}</Td>
                    <Td color="gray.300" fontSize="xs" maxW="200px" isTruncated title={issue.description}>{issue.description}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        ) : (
          <Text color="green.300" fontWeight="bold">
            {bp.sequenceResult.check_type === 'balance_comparison'
              ? '✅ Balance matches — no discrepancies found!'
              : '✅ All sequence numbers are consecutive - no gaps found!'}
          </Text>
        )}
      </Box>
    )}

    {bp.bankingBalances.length === 0 && !bp.checkingAccounts && !bp.sequenceResult && (
      <Text color="white" textAlign="center" py={8}>{bp.t('checkAccounts.noAccounts')}</Text>
    )}
  </VStack>
);

const CheckReferenceTab: React.FC<TabProps> = ({ bp }) => (
  <VStack align="stretch" spacing={4}>
    <Box bg="gray.800" p={4} borderRadius="md">
      <Heading size="sm" color="white" mb={4}>Check Reference Numbers</Heading>
      <HStack spacing={4} mb={4} wrap="wrap">
        <FormControl maxW="180px">
          <FormLabel color="white" fontSize="sm">Administration</FormLabel>
          <Input value={bp.currentTenant || bp.checkRefFilters.administration} isReadOnly bg="gray.700" color="white" size="sm" cursor="not-allowed" />
        </FormControl>
        <FormControl maxW="150px">
          <FormLabel color="white" fontSize="sm">Ledger</FormLabel>
          <Select
            value={bp.checkRefFilters.ledger}
            onChange={(e) => {
              bp.setCheckRefFilters((prev) => ({ ...prev, ledger: e.target.value }));
            }}
            bg="gray.600"
            color="white"
            size="sm"
          >
            <option value="all">All</option>
            {bp.availableLedgers.map((ledger) => (
              <option key={ledger} value={ledger}>{ledger}</option>
            ))}
          </Select>
        </FormControl>
        <Button onClick={bp.fetchCheckRefData} isLoading={bp.loading} colorScheme="green" size="sm" alignSelf="flex-end">
          Check References
        </Button>
      </HStack>

      {bp.refSummaryData.length > 0 && (
        <VStack align="stretch" spacing={4}>
          <HStack justify="space-between">
            <Heading size="xs" color="white">Reference Summary ({bp.processedRefSummary.length})</Heading>
            <Text color="orange.300" fontWeight="bold" fontSize="sm">
              Total: {formatAmount((bp.refSummaryData).reduce((sum, row) => sum + (parseFloat(String(row.total_amount)) || 0), 0))}
            </Text>
          </HStack>
          <TableContainer maxH="300px" overflowY="auto">
            <Table size="sm" variant="simple">
              <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                <Tr>
                  <FilterableHeader label="Reference" filterValue={bp.refSummaryFilters.ReferenceNumber} onFilterChange={(v) => bp.setRefSummaryFilter('ReferenceNumber', v)} sortable sortDirection={bp.refSummarySortField === 'ReferenceNumber' ? bp.refSummarySortDirection : null} onSort={() => bp.handleRefSummarySort('ReferenceNumber')} />
                  <FilterableHeader label="Count" filterValue={bp.refSummaryFilters.transaction_count} onFilterChange={(v) => bp.setRefSummaryFilter('transaction_count', v)} sortable sortDirection={bp.refSummarySortField === 'transaction_count' ? bp.refSummarySortDirection : null} onSort={() => bp.handleRefSummarySort('transaction_count')} isNumeric />
                  <FilterableHeader label="Total Amount" filterValue={bp.refSummaryFilters.total_amount} onFilterChange={(v) => bp.setRefSummaryFilter('total_amount', v)} sortable sortDirection={bp.refSummarySortField === 'total_amount' ? bp.refSummarySortDirection : null} onSort={() => bp.handleRefSummarySort('total_amount')} isNumeric />
                </Tr>
              </Thead>
              <Tbody>
                {(bp.processedRefSummary).map((row, index) => (
                  <Tr key={index} onClick={() => bp.fetchReferenceDetails(row.ReferenceNumber)} _hover={{ bg: 'gray.700', cursor: 'pointer' }} bg={bp.selectedReference === row.ReferenceNumber ? 'gray.600' : 'transparent'}>
                    <Td color="white" fontSize="xs" maxW="200px" isTruncated title={row.ReferenceNumber}>{row.ReferenceNumber}</Td>
                    <Td color="white" fontSize="xs" isNumeric>{row.transaction_count}</Td>
                    <Td color="white" fontSize="xs" isNumeric>{formatAmount(Number(row.total_amount))}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>

          {bp.selectedReferenceDetails.length > 0 && (
            <Box>
              <Heading size="xs" color="white" mb={2}>
                Transactions for Reference: {bp.selectedReference} ({bp.processedRefDetails.length})
              </Heading>
              <TableContainer maxH="300px" overflowY="auto">
                <Table size="sm" variant="simple">
                  <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                    <Tr>
                      <FilterableHeader label="Transaction Number" filterValue={bp.refDetailsFilters.TransactionNumber} onFilterChange={(v) => bp.setRefDetailsFilter('TransactionNumber', v)} sortable sortDirection={bp.refDetailsSortField === 'TransactionNumber' ? bp.refDetailsSortDirection : null} onSort={() => bp.handleRefDetailsSort('TransactionNumber')} />
                      <FilterableHeader label="Date" filterValue={bp.refDetailsFilters.TransactionDate} onFilterChange={(v) => bp.setRefDetailsFilter('TransactionDate', v)} sortable sortDirection={bp.refDetailsSortField === 'TransactionDate' ? bp.refDetailsSortDirection : null} onSort={() => bp.handleRefDetailsSort('TransactionDate')} />
                      <FilterableHeader label="Amount" filterValue={bp.refDetailsFilters.Amount} onFilterChange={(v) => bp.setRefDetailsFilter('Amount', v)} sortable sortDirection={bp.refDetailsSortField === 'Amount' ? bp.refDetailsSortDirection : null} onSort={() => bp.handleRefDetailsSort('Amount')} isNumeric />
                      <FilterableHeader label="Description" filterValue={bp.refDetailsFilters.TransactionDescription} onFilterChange={(v) => bp.setRefDetailsFilter('TransactionDescription', v)} sortable sortDirection={bp.refDetailsSortField === 'TransactionDescription' ? bp.refDetailsSortDirection : null} onSort={() => bp.handleRefDetailsSort('TransactionDescription')} />
                    </Tr>
                  </Thead>
                  <Tbody>
                    {(bp.processedRefDetails).map((transaction, index) => (
                      <Tr key={index}>
                        <Td color="white" fontSize="xs">{transaction.TransactionNumber || '-'}</Td>
                        <Td color="white" fontSize="xs">{transaction.TransactionDate ? new Date(transaction.TransactionDate).toISOString().split('T')[0] : '-'}</Td>
                        <Td color="white" fontSize="xs" isNumeric>{formatAmount(Number(transaction.Amount ?? 0))}</Td>
                        <Td color="white" fontSize="xs" maxW="300px" isTruncated title={transaction.TransactionDescription}>{transaction.TransactionDescription}</Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </VStack>
      )}
    </Box>

    {bp.refSummaryData.length === 0 && (
      <Text color="white" textAlign="center" py={8}>Use the button above to check reference numbers</Text>
    )}
  </VStack>
);

const StrChannelRevenueTab: React.FC<TabProps> = ({ bp }) => (
  <VStack align="stretch" spacing={4}>
    <Box bg="gray.800" p={4} borderRadius="md">
      <Heading size="sm" color="white" mb={4}>STR Channel Revenue Calculator</Heading>
      <Text color="gray.300" fontSize="sm" mb={4}>Calculate monthly STR revenue based on account 1600 transactions</Text>

      <HStack spacing={4} mb={4} wrap="wrap">
        <FormControl maxW="120px">
          <FormLabel color="white" fontSize="sm">Year</FormLabel>
          <Input type="number" value={bp.strChannelFilters.year} onChange={(e) => bp.setStrChannelFilters((prev) => ({ ...prev, year: parseInt(e.target.value) || new Date().getFullYear() }))} onKeyDown={bp.handleKeyDown} bg="gray.600" color="white" size="sm" />
        </FormControl>
        <FormControl maxW="120px">
          <FormLabel color="white" fontSize="sm">Month</FormLabel>
          <Select value={bp.strChannelFilters.month} onChange={(e) => bp.setStrChannelFilters((prev) => ({ ...prev, month: parseInt(e.target.value) }))} bg="gray.600" color="white" size="sm">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => (
              <option key={month} value={month}>{new Date(2000, month - 1).toLocaleString('default', { month: 'long' })}</option>
            ))}
          </Select>
        </FormControl>
        <FormControl maxW="180px">
          <FormLabel color="white" fontSize="sm">Administration</FormLabel>
          <Input value={bp.currentTenant || bp.strChannelFilters.administration} isReadOnly bg="gray.700" color="white" size="sm" cursor="not-allowed" />
        </FormControl>
        <Button onClick={bp.fetchStrChannelPreview} isLoading={bp.loading} colorScheme="blue" size="sm" alignSelf="flex-end">
          {bp.t('strChannel.previewData')}
        </Button>
        <Button onClick={bp.calculateStrChannelRevenue} isLoading={bp.loading} colorScheme="green" size="sm" alignSelf="flex-end" isDisabled={bp.strChannelPreview.length === 0}>
          {bp.t('strChannel.calculateRevenue')}
        </Button>
      </HStack>

      {bp.strChannelPreview.length > 0 && (
        <VStack align="stretch" spacing={4}>
          <Heading size="xs" color="white">Channel Data Preview ({bp.strChannelPreview.length})</Heading>
          <TableContainer maxH="200px" overflowY="auto">
            <Table size="sm" variant="simple">
              <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                <Tr>
                  <Th color="white" fontSize="xs">Channel</Th>
                  <Th color="white" fontSize="xs">Account</Th>
                  <Th color="white" fontSize="xs" isNumeric>Transactions</Th>
                  <Th color="white" fontSize="xs" isNumeric>Total Amount</Th>
                  <Th color="white" fontSize="xs">Date Range</Th>
                </Tr>
              </Thead>
              <Tbody>
                {(bp.strChannelPreview).map((row, index) => (
                  <Tr key={index}>
                    <Td color="white" fontSize="xs">{String(row.ReferenceNumber ?? '')}</Td>
                    <Td color="white" fontSize="xs">{String(row.Reknum ?? '')}</Td>
                    <Td color="white" fontSize="xs" isNumeric>{String(row.transaction_count ?? '')}</Td>
                    <Td color="white" fontSize="xs" isNumeric>{formatAmount(Number(row.total_amount ?? 0))}</Td>
                    <Td color="white" fontSize="xs">
                      {row.first_date ? new Date(String(row.first_date)).toLocaleDateString('nl-NL') : '-'} - {row.last_date ? new Date(String(row.last_date)).toLocaleDateString('nl-NL') : '-'}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </VStack>
      )}

      {bp.strChannelTransactions.length > 0 && (
        <VStack align="stretch" spacing={4}>
          <HStack justify="space-between">
            <Heading size="xs" color="white">Proposed Transactions ({bp.strChannelTransactions.length})</Heading>
            <Button onClick={bp.saveStrChannelTransactions} isLoading={bp.loading} colorScheme="orange" size="sm">Save to Database</Button>
          </HStack>

          {bp.strChannelSummary && (
            <Box bg="gray.700" p={3} borderRadius="md">
              <Text color="white" fontSize="sm">
                <strong>Reference:</strong> {bp.strChannelSummary.ref1} |{' '}
                <strong>Period:</strong> {bp.strChannelSummary.month}/{bp.strChannelSummary.year} |{' '}
                <strong>End Date:</strong> {bp.strChannelSummary.end_date}
              </Text>
            </Box>
          )}

          <TableContainer maxH="400px" overflowY="auto">
            <Table size="sm" variant="simple">
              <Thead position="sticky" top={0} bg="gray.800" zIndex={1}>
                <Tr>
                  <Th color="white" fontSize="xs">Date</Th>
                  <Th color="white" fontSize="xs">Description</Th>
                  <Th color="white" fontSize="xs" isNumeric>Amount</Th>
                  <Th color="white" fontSize="xs">Debet</Th>
                  <Th color="white" fontSize="xs">Credit</Th>
                  <Th color="white" fontSize="xs">Reference</Th>
                </Tr>
              </Thead>
              <Tbody>
                {(bp.strChannelTransactions).map((transaction, index) => (
                  <Tr key={index}>
                    <Td color="white" fontSize="xs">{transaction.TransactionDate}</Td>
                    <Td color="white" fontSize="xs" maxW="200px" isTruncated title={transaction.TransactionDescription}>{transaction.TransactionDescription}</Td>
                    <Td color="white" fontSize="xs" isNumeric>{formatAmount(Number(transaction.TransactionAmount ?? 0))}</Td>
                    <Td color="white" fontSize="xs">{transaction.Debet}</Td>
                    <Td color="white" fontSize="xs">{transaction.Credit}</Td>
                    <Td color="white" fontSize="xs">{transaction.ReferenceNumber}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </VStack>
      )}
    </Box>

    {bp.strChannelPreview.length === 0 && bp.strChannelTransactions.length === 0 && (
      <Text color="white" textAlign="center" py={8}>{bp.t('strChannel.noChannels')}</Text>
    )}
  </VStack>
);

export default BankingProcessor;
