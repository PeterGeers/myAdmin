/**
 * ZZP Time Tracking page — mobile-first design with responsive card/table layout.
 * Quick-add flow, summary tabs with Recharts bar chart, invoice-from-entries action.
 * Reference: .kiro/specs/zzp-module/design.md §6.2
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, useToast, Spinner, Checkbox, Select,
  Table, Thead, Tbody, Tr, Th, Td, HStack, VStack, Badge,
  useDisclosure, Tabs, TabList, TabPanels, Tab, TabPanel, Input,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { TimeEntry, TimeSummary, Contact } from '../types/zzp';
import { getTimeEntries, getTimeSummary } from '../services/timeTrackingService';
import { getContacts } from '../services/contactService';
import { createInvoiceFromTimeEntries } from '../services/zzpInvoiceService';
import { TimeEntryModal } from '../components/zzp/TimeEntryModal';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';

/* ─── Quick-Add Bar ─── */
interface QuickAddBarProps {
  contacts: Contact[];
  onAdded: () => void;
}

const QuickAddBar: React.FC<QuickAddBarProps> = ({ contacts, onAdded }) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const [contactId, setContactId] = useState('');
  const [hours, setHours] = useState('');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [rate, setRate] = useState('');
  const [saving, setSaving] = useState(false);

  const handleQuickAdd = async () => {
    if (!contactId || !hours || !date || !rate) return;
    try {
      setSaving(true);
      const { createTimeEntry } = await import('../services/timeTrackingService');
      const resp = await createTimeEntry({
        contact_id: Number(contactId),
        entry_date: date,
        hours: Number(hours),
        hourly_rate: Number(rate),
        is_billable: true,
      });
      if (resp.success) {
        toast({ title: 'Entry added', status: 'success', duration: 2000 });
        setHours('');
        onAdded();
      } else {
        toast({ title: resp.error || 'Error', status: 'error' });
      }
    } catch {
      toast({ title: 'Error', status: 'error' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box bg="gray.700" p={3} borderRadius="md" mb={4}>
      <Text fontSize="sm" fontWeight="bold" color="gray.300" mb={2}>{t('timeTracking.quickAdd')}</Text>
      <Flex wrap="wrap" gap={2} align="flex-end">
        <Select size="sm" w={{ base: '100%', md: '200px' }} bg="gray.600" color="white"
          borderColor="gray.500" placeholder={t('timeTracking.contact')}
          value={contactId} onChange={e => setContactId(e.target.value)}>
          {contacts.map(c => (
            <option key={c.id} value={c.id}>{c.company_name}</option>
          ))}
        </Select>
        <Input type="date" size="sm" w={{ base: '48%', md: '150px' }} bg="gray.600" color="white"
          borderColor="gray.500" value={date} onChange={e => setDate(e.target.value)}
          aria-label={t('timeTracking.date')} />
        <Input type="number" size="sm" w={{ base: '24%', md: '90px' }} bg="gray.600" color="white"
          borderColor="gray.500" placeholder={t('timeTracking.hours')} step="0.25"
          value={hours} onChange={e => setHours(e.target.value)}
          aria-label={t('timeTracking.hours')} />
        <Input type="number" size="sm" w={{ base: '24%', md: '100px' }} bg="gray.600" color="white"
          borderColor="gray.500" placeholder={t('timeTracking.rate')} step="0.01"
          value={rate} onChange={e => setRate(e.target.value)}
          aria-label={t('timeTracking.rate')} />
        <Button size="sm" colorScheme="orange" onClick={handleQuickAdd}
          isLoading={saving} isDisabled={!contactId || !hours || !date || !rate}>
          +
        </Button>
      </Flex>
    </Box>
  );
};

/* ─── Summary Tabs ─── */
interface SummaryTabsProps {
  t: (key: string, fallback?: string) => string;
}

const SummaryTabs: React.FC<SummaryTabsProps> = ({ t }) => {
  const [groupBy, setGroupBy] = useState<'contact' | 'project' | 'period'>('contact');
  const [period, setPeriod] = useState('month');
  const [summaryData, setSummaryData] = useState<TimeSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getTimeSummary(groupBy, groupBy === 'period' ? period : undefined);
      if (resp.success) setSummaryData(resp.data || []);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, [groupBy, period]);

  useEffect(() => { loadSummary(); }, [loadSummary]);

  const chartData = summaryData.map(s => ({
    name: s.project_name || s.period || `Contact ${s.contact_id}` || '—',
    hours: s.total_hours,
    amount: s.total_amount,
  }));

  return (
    <Box bg="gray.700" p={4} borderRadius="md" mt={4}>
      <Text fontSize="md" fontWeight="bold" color="white" mb={3}>{t('timeTracking.summary')}</Text>
      <Tabs variant="soft-rounded" colorScheme="orange" size="sm"
        onChange={idx => setGroupBy(['contact', 'project', 'period'][idx] as any)}>
        <TabList>
          <Tab color="gray.300" _selected={{ color: 'white', bg: 'orange.500' }}>{t('timeTracking.byContact')}</Tab>
          <Tab color="gray.300" _selected={{ color: 'white', bg: 'orange.500' }}>{t('timeTracking.byProject')}</Tab>
          <Tab color="gray.300" _selected={{ color: 'white', bg: 'orange.500' }}>{t('timeTracking.byPeriod')}</Tab>
        </TabList>
        <TabPanels>
          {/* By Contact */}
          <TabPanel px={0}>
            {loading ? <Spinner color="white" size="sm" /> : (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#4A5568" />
                  <XAxis dataKey="name" tick={{ fill: '#A0AEC0', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#A0AEC0', fontSize: 12 }} />
                  <Tooltip formatter={(v) => `€ ${Number(v).toFixed(2)}`}
                    contentStyle={{ backgroundColor: '#2D3748', border: 'none', color: '#fff' }} />
                  <Bar dataKey="amount" name={t('timeTracking.amount')} fill="#ED8936" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </TabPanel>
          {/* By Project */}
          <TabPanel px={0}>
            {loading ? <Spinner color="white" size="sm" /> : (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#4A5568" />
                  <XAxis dataKey="name" tick={{ fill: '#A0AEC0', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#A0AEC0', fontSize: 12 }} />
                  <Tooltip formatter={(v) => `€ ${Number(v).toFixed(2)}`}
                    contentStyle={{ backgroundColor: '#2D3748', border: 'none', color: '#fff' }} />
                  <Bar dataKey="hours" name={t('timeTracking.hours')} fill="#3182CE" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </TabPanel>
          {/* By Period */}
          <TabPanel px={0}>
            <HStack mb={3}>
              <Select size="xs" w="120px" bg="gray.600" color="white" borderColor="gray.500"
                value={period} onChange={e => setPeriod(e.target.value)}>
                <option value="week">{t('timeTracking.week')}</option>
                <option value="month">{t('timeTracking.month')}</option>
                <option value="quarter">{t('timeTracking.quarter')}</option>
                <option value="year">{t('timeTracking.year')}</option>
              </Select>
            </HStack>
            {loading ? <Spinner color="white" size="sm" /> : (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#4A5568" />
                  <XAxis dataKey="name" tick={{ fill: '#A0AEC0', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#A0AEC0', fontSize: 12 }} />
                  <Tooltip formatter={(v) => `€ ${Number(v).toFixed(2)}`}
                    contentStyle={{ backgroundColor: '#2D3748', border: 'none', color: '#fff' }} />
                  <Bar dataKey="amount" name={t('timeTracking.amount')} fill="#ED8936" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="hours" name={t('timeTracking.hours')} fill="#3182CE" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

/* ─── Mobile Card ─── */
interface TimeCardProps {
  entry: TimeEntry;
  selected: boolean;
  onToggle: () => void;
  onClick: () => void;
}

const TimeCard: React.FC<TimeCardProps> = ({ entry, selected, onToggle, onClick }) => (
  <Box bg="gray.700" p={3} borderRadius="md" mb={2}
    borderLeft={entry.is_billed ? '3px solid' : 'none'} borderColor="green.400">
    <Flex justify="space-between" align="center">
      <HStack spacing={2}>
        {!entry.is_billed && (
          <Checkbox isChecked={selected} onChange={onToggle} colorScheme="orange"
            onClick={e => e.stopPropagation()} />
        )}
        <Box cursor="pointer" onClick={onClick}>
          <Text fontSize="sm" fontWeight="bold" color="white">
            {entry.entry_date} — {entry.contact?.company_name || `Contact #${entry.contact_id}`}
          </Text>
          <Text fontSize="xs" color="gray.400">{entry.project_name || ''}</Text>
        </Box>
      </HStack>
      <VStack spacing={0} align="flex-end">
        <Text fontSize="sm" fontWeight="bold" color="white">{entry.hours}h</Text>
        <Text fontSize="xs" color="gray.400">€ {(entry.hours * entry.hourly_rate).toFixed(2)}</Text>
      </VStack>
    </Flex>
    <Flex mt={1} gap={2}>
      {entry.is_billable && <Badge colorScheme="blue" variant="subtle" fontSize="2xs">Billable</Badge>}
      {entry.is_billed && <Badge colorScheme="green" variant="subtle" fontSize="2xs">Billed</Badge>}
    </Flex>
  </Box>
);

/* ─── Main Page ─── */
const ZZPTimeTracking: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const [entries, setEntries] = useState<TimeEntry[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [disabled, setDisabled] = useState(false);
  const [selected, setSelected] = useState<TimeEntry | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Build flat rows with promoted nested fields for column filtering
  const entryRows = React.useMemo(
    () => entries.map(e => ({
      ...e,
      contact_name: e.contact?.company_name || `#${e.contact_id}`,
      total: e.hours * e.hourly_rate,
      billable_text: e.is_billable ? 'Yes' : 'No',
      billed_text: e.is_billed ? 'Yes' : 'No',
    })),
    [entries],
  );

  // Combined column filtering + sorting via framework hook
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable(entryRows, {
    initialFilters: {
      entry_date: '',
      contact_name: '',
      project_name: '',
      hours: '',
      hourly_rate: '',
      total: '',
      billable_text: '',
      billed_text: '',
    },
    defaultSort: { field: 'entry_date', direction: 'desc' as const },
  });

  const loadEntries = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getTimeEntries({});
      if (resp.success) {
        setEntries(resp.data || []);
        setDisabled(false);
      } else {
        setDisabled(true);
      }
    } catch {
      setDisabled(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadEntries(); }, [loadEntries]);
  useEffect(() => {
    getContacts().then(resp => { if (resp.success) setContacts(resp.data); });
  }, []);

  const handleRowClick = (entry: TimeEntry) => { setSelected(entry); onOpen(); };
  const handleNew = () => { setSelected(null); onOpen(); };
  const handleSaved = () => { onClose(); setSelectedIds(new Set()); loadEntries(); };

  const toggleSelection = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleInvoiceSelected = async () => {
    if (selectedIds.size === 0) return;
    // All selected entries must belong to the same contact
    const selectedEntries = entries.filter(e => selectedIds.has(e.id));
    const contactIds = new Set(selectedEntries.map(e => e.contact_id));
    if (contactIds.size > 1) {
      toast({ title: t('timeTracking.selectEntries'), status: 'warning' });
      return;
    }
    const contactId = selectedEntries[0].contact_id;
    try {
      const resp = await createInvoiceFromTimeEntries(
        contactId,
        Array.from(selectedIds),
      );
      if (resp.success) {
        toast({ title: 'Invoice created', status: 'success' });
        setSelectedIds(new Set());
        loadEntries();
      } else {
        toast({ title: resp.error || 'Error', status: 'error' });
      }
    } catch {
      toast({ title: 'Error creating invoice', status: 'error' });
    }
  };

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(amount);

  // Disabled state
  if (!loading && disabled) {
    return (
      <Box p={6}>
        <Text fontSize="xl" fontWeight="bold" color="white" mb={4}>{t('timeTracking.title')}</Text>
        <Text color="gray.400">{t('timeTracking.disabled')}</Text>
      </Box>
    );
  }

  const unbilledSelected = entries.filter(e => selectedIds.has(e.id) && !e.is_billed);

  return (
    <Box p={6}>
      {/* Header */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('timeTracking.title')}</Text>
        <HStack spacing={2}>
          {unbilledSelected.length > 0 && (
            <Button size="sm" colorScheme="blue" onClick={handleInvoiceSelected}>
              {t('timeTracking.invoiceSelected')} ({unbilledSelected.length})
            </Button>
          )}
          <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleNew}>
            {t('timeTracking.newEntry')}
          </Button>
        </HStack>
      </Flex>

      {/* Quick-add bar */}
      <QuickAddBar contacts={contacts} onAdded={loadEntries} />

      {/* Content */}
      {loading ? <Spinner color="white" /> : (
        <>
          {/* Mobile cards */}
          <Box display={{ base: 'block', md: 'none' }}>
            {processedData.map(entry => (
              <TimeCard key={entry.id} entry={entry}
                selected={selectedIds.has(entry.id)}
                onToggle={() => toggleSelection(entry.id)}
                onClick={() => handleRowClick(entry)} />
            ))}
            {processedData.length === 0 && (
              <Text color="gray.500">{t('common.noData')}</Text>
            )}
          </Box>

          {/* Desktop table */}
          <Box display={{ base: 'none', md: 'block' }} overflowX="auto">
            <Table variant="simple" size="sm" bg="gray.800" color="white">
              <Thead>
                <Tr>
                  <Th color="gray.400" w="40px" />
                  <FilterableHeader
                    label={t('timeTracking.date')}
                    filterValue={filters.entry_date}
                    onFilterChange={(v) => setFilter('entry_date', v)}
                    sortable
                    sortDirection={sortField === 'entry_date' ? sortDirection : null}
                    onSort={() => handleSort('entry_date')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.contact')}
                    filterValue={filters.contact_name}
                    onFilterChange={(v) => setFilter('contact_name', v)}
                    sortable
                    sortDirection={sortField === 'contact_name' ? sortDirection : null}
                    onSort={() => handleSort('contact_name')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.project')}
                    filterValue={filters.project_name}
                    onFilterChange={(v) => setFilter('project_name', v)}
                    sortable
                    sortDirection={sortField === 'project_name' ? sortDirection : null}
                    onSort={() => handleSort('project_name')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.hours')}
                    filterValue={filters.hours}
                    onFilterChange={(v) => setFilter('hours', v)}
                    isNumeric
                    sortable
                    sortDirection={sortField === 'hours' ? sortDirection : null}
                    onSort={() => handleSort('hours')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.rate')}
                    filterValue={filters.hourly_rate}
                    onFilterChange={(v) => setFilter('hourly_rate', v)}
                    isNumeric
                    sortable
                    sortDirection={sortField === 'hourly_rate' ? sortDirection : null}
                    onSort={() => handleSort('hourly_rate')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.total')}
                    filterValue={filters.total}
                    onFilterChange={(v) => setFilter('total', v)}
                    isNumeric
                    sortable
                    sortDirection={sortField === 'total' ? sortDirection : null}
                    onSort={() => handleSort('total')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.billable')}
                    filterValue={filters.billable_text}
                    onFilterChange={(v) => setFilter('billable_text', v)}
                    sortable
                    sortDirection={sortField === 'billable_text' ? sortDirection : null}
                    onSort={() => handleSort('billable_text')}
                  />
                  <FilterableHeader
                    label={t('timeTracking.billed')}
                    filterValue={filters.billed_text}
                    onFilterChange={(v) => setFilter('billed_text', v)}
                    sortable
                    sortDirection={sortField === 'billed_text' ? sortDirection : null}
                    onSort={() => handleSort('billed_text')}
                  />
                </Tr>
              </Thead>
              <Tbody>
                {processedData.map(entry => (
                  <Tr key={entry.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                    onClick={() => handleRowClick(entry)}>
                    <Td onClick={e => e.stopPropagation()}>
                      {!entry.is_billed && (
                        <Checkbox isChecked={selectedIds.has(entry.id)}
                          onChange={() => toggleSelection(entry.id)} colorScheme="orange" />
                      )}
                    </Td>
                    <Td>{entry.entry_date}</Td>
                    <Td>{entry.contact_name}</Td>
                    <Td>{entry.project_name || '-'}</Td>
                    <Td isNumeric>{entry.hours}</Td>
                    <Td isNumeric>{formatCurrency(entry.hourly_rate)}</Td>
                    <Td isNumeric>{formatCurrency(entry.total)}</Td>
                    <Td>
                      {entry.is_billable
                        ? <Badge colorScheme="blue" variant="subtle">Yes</Badge>
                        : <Badge colorScheme="gray" variant="subtle">No</Badge>}
                    </Td>
                    <Td>
                      {entry.is_billed
                        ? <Badge colorScheme="green" variant="subtle">Yes</Badge>
                        : <Badge colorScheme="gray" variant="subtle">No</Badge>}
                    </Td>
                  </Tr>
                ))}
                {processedData.length === 0 && (
                  <Tr><Td colSpan={9}><Text color="gray.500">{t('common.noData')}</Text></Td></Tr>
                )}
              </Tbody>
            </Table>
          </Box>
        </>
      )}

      {/* Summary tabs */}
      <SummaryTabs t={t} />

      {/* Time entry modal */}
      <TimeEntryModal isOpen={isOpen} onClose={onClose}
        entry={selected} onSaved={handleSaved} />
    </Box>
  );
};

export default ZZPTimeTracking;
