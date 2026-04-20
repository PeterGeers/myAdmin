import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Td, Badge, Button, Grid,
  useToast, useDisclosure, Spinner, Text, HStack, Select,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter, ModalCloseButton,
  FormControl, FormLabel, Input,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { TaxRate, TaxRateCreateRequest } from '../../types/taxRateTypes';
import { getTaxRates, createTaxRate, updateTaxRate, deleteTaxRate } from '../../services/taxRateService';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';

interface Props { tenant: string; isSysAdmin?: boolean; }

function getDateStatus(from: string, to: string | null): 'active' | 'future' | 'expired' {
  const today = new Date().toISOString().split('T')[0];
  if (from > today) return 'future';
  if (to && to < today && to !== '9999-12-31') return 'expired';
  return 'active';
}
const statusColors: Record<string, string> = { active: 'green', future: 'blue', expired: 'gray' };

export default function TaxRateManagement({ tenant, isSysAdmin = false }: Props) {
  const { t } = useTypedTranslation('admin');
  const [rates, setRates] = useState<TaxRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<TaxRate | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formType, setFormType] = useState('');
  const [formCode, setFormCode] = useState('');
  const [formRate, setFormRate] = useState('');
  const [formFrom, setFormFrom] = useState('');
  const [formTo, setFormTo] = useState('');
  const [formLedger, setFormLedger] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formMethod, setFormMethod] = useState('percentage');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const data = await getTaxRates(); setRates(data.tax_rates || []); }
    catch (e: any) { toast({ title: t('tenantAdmin.taxRates.loading'), description: e.message, status: 'error', duration: 5000 }); }
    finally { setLoading(false); }
  }, [toast, t]);

  useEffect(() => { load(); }, [load]);

  const taxRateRows = useMemo(() => rates.map(r => ({
    ...r,
    status_text: getDateStatus(r.effective_from, r.effective_to),
    effective_to_display: r.effective_to === '9999-12-31' ? '∞' : r.effective_to || '-',
    ledger_display: r.ledger_account || '-',
    description_display: r.description || '-',
  })), [rates]);

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable(taxRateRows, {
    initialFilters: {
      tax_type: '',
      tax_code: '',
      rate: '',
      ledger_display: '',
      effective_from: '',
      effective_to_display: '',
      status_text: '',
      scope_origin: '',
      description_display: '',
    },
    defaultSort: { field: 'tax_type', direction: 'asc' as const },
  });

  const canEdit = (r: TaxRate) => r.scope_origin === 'tenant' || isSysAdmin;

  const handleAdd = () => {
    setIsNew(true); setEditing(null);
    setFormType(''); setFormCode(''); setFormRate(''); setFormFrom('');
    setFormTo(''); setFormLedger(''); setFormDesc(''); setFormMethod('percentage');
    onOpen();
  };

  const handleRowClick = (r: TaxRate) => {
    if (!canEdit(r)) return;
    setIsNew(false); setEditing(r);
    setFormType(r.tax_type); setFormCode(r.tax_code); setFormRate(String(r.rate));
    setFormFrom(r.effective_from); setFormTo(r.effective_to === '9999-12-31' ? '' : r.effective_to || '');
    setFormLedger(r.ledger_account || ''); setFormDesc(r.description || ''); setFormMethod(r.calc_method);
    onOpen();
  };

  const handleSave = async () => {
    if (!formType || !formCode || !formRate || !formFrom) {
      toast({ title: t('tenantAdmin.taxRates.taxType') + ', ' + t('tenantAdmin.taxRates.taxCode') + ', ' + t('tenantAdmin.taxRates.rate') + ' required', status: 'warning', duration: 3000 }); return;
    }
    setSaving(true);
    try {
      if (isNew) {
        const req: TaxRateCreateRequest = {
          tax_type: formType, tax_code: formCode, rate: Number(formRate),
          effective_from: formFrom, effective_to: formTo || undefined,
          ledger_account: formLedger || undefined, description: formDesc || undefined, calc_method: formMethod,
        };
        if (isSysAdmin && tenant === '_system_') req.administration = '_system_';
        const res = await createTaxRate(req);
        if (res.success) { toast({ title: t('tenantAdmin.taxRates.created'), status: 'success', duration: 3000 }); onClose(); load(); }
        else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      } else if (editing) {
        const res = await updateTaxRate(editing.id, {
          rate: Number(formRate), description: formDesc || undefined,
          ledger_account: formLedger || undefined, effective_from: formFrom,
          effective_to: formTo || undefined, calc_method: formMethod,
        });
        if (res.success) { toast({ title: t('tenantAdmin.taxRates.updated'), status: 'success', duration: 3000 }); onClose(); load(); }
        else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) { toast({ title: t('tenantAdmin.taxRates.title'), description: e.message, status: 'error', duration: 5000 }); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    if (!editing) return;
    try {
      const res = await deleteTaxRate(editing.id);
      if (res.success) { toast({ title: t('tenantAdmin.taxRates.deleted'), status: 'success', duration: 3000 }); onClose(); onDeleteClose(); load(); }
      else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
    } catch (e: any) { toast({ title: t('tenantAdmin.taxRates.deleteTaxRate'), description: e.message, status: 'error', duration: 5000 }); }
    finally { onDeleteClose(); }
  };

  if (loading) return <Box p={4}><Spinner color="orange.400" /><Text color="gray.400" display="inline" ml={2}>Loading tax rates...</Text></Box>;

  return (
    <Box>
      <HStack mb={4} justify="flex-end">
        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleAdd}>{t('tenantAdmin.taxRates.addTaxRate')}</Button>
      </HStack>
      <Table variant="simple" size="sm">
        <Thead>
          <Tr>
            <FilterableHeader
              label={t('tenantAdmin.taxRates.taxType')}
              filterValue={filters.tax_type}
              onFilterChange={(v) => setFilter('tax_type', v)}
              sortable
              sortDirection={sortField === 'tax_type' ? sortDirection : null}
              onSort={() => handleSort('tax_type')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.taxCode')}
              filterValue={filters.tax_code}
              onFilterChange={(v) => setFilter('tax_code', v)}
              sortable
              sortDirection={sortField === 'tax_code' ? sortDirection : null}
              onSort={() => handleSort('tax_code')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.rate')}
              filterValue={filters.rate}
              onFilterChange={(v) => setFilter('rate', v)}
              isNumeric
              sortable
              sortDirection={sortField === 'rate' ? sortDirection : null}
              onSort={() => handleSort('rate')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.ledgerAccount')}
              filterValue={filters.ledger_display}
              onFilterChange={(v) => setFilter('ledger_display', v)}
              sortable
              sortDirection={sortField === 'ledger_display' ? sortDirection : null}
              onSort={() => handleSort('ledger_display')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.effectiveFrom')}
              filterValue={filters.effective_from}
              onFilterChange={(v) => setFilter('effective_from', v)}
              sortable
              sortDirection={sortField === 'effective_from' ? sortDirection : null}
              onSort={() => handleSort('effective_from')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.effectiveTo')}
              filterValue={filters.effective_to_display}
              onFilterChange={(v) => setFilter('effective_to_display', v)}
              sortable
              sortDirection={sortField === 'effective_to_display' ? sortDirection : null}
              onSort={() => handleSort('effective_to_display')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.status')}
              filterValue={filters.status_text}
              onFilterChange={(v) => setFilter('status_text', v)}
              sortable
              sortDirection={sortField === 'status_text' ? sortDirection : null}
              onSort={() => handleSort('status_text')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.scopeOrigin')}
              filterValue={filters.scope_origin}
              onFilterChange={(v) => setFilter('scope_origin', v)}
              sortable
              sortDirection={sortField === 'scope_origin' ? sortDirection : null}
              onSort={() => handleSort('scope_origin')}
            />
            <FilterableHeader
              label={t('tenantAdmin.taxRates.description')}
              filterValue={filters.description_display}
              onFilterChange={(v) => setFilter('description_display', v)}
              sortable
              sortDirection={sortField === 'description_display' ? sortDirection : null}
              onSort={() => handleSort('description_display')}
            />
          </Tr>
        </Thead>
        <Tbody>
          {processedData.map(r => {
            const status = r.status_text;
            return (
              <Tr key={r.id} cursor={canEdit(r) ? 'pointer' : 'default'} _hover={canEdit(r) ? { bg: 'gray.600' } : {}} onClick={() => handleRowClick(r)}>
                <Td color="white" fontSize="sm">{r.tax_type}</Td>
                <Td color="white" fontSize="sm">{r.tax_code}</Td>
                <Td color="white" fontSize="sm" isNumeric>{r.rate}</Td>
                <Td color="white" fontSize="sm">{r.ledger_display}</Td>
                <Td color="white" fontSize="sm">{r.effective_from}</Td>
                <Td color="white" fontSize="sm">{r.effective_to_display}</Td>
                <Td><Badge colorScheme={statusColors[status]} fontSize="xs">{status}</Badge></Td>
                <Td><Badge colorScheme={r.scope_origin === 'tenant' ? 'orange' : 'gray'} fontSize="xs">{r.scope_origin}</Badge></Td>
                <Td color="white" fontSize="sm" maxW="200px" isTruncated>{r.description_display}</Td>
              </Tr>);
          })}
          {processedData.length === 0 && <Tr><Td colSpan={9} color="gray.500" textAlign="center">{t('tenantAdmin.taxRates.noTaxRates')}</Td></Tr>}
        </Tbody>
      </Table>

      <Modal isOpen={isOpen} onClose={onClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.700">
          <ModalHeader color="white">{isNew ? t('tenantAdmin.taxRates.addTaxRate') : `${t('tenantAdmin.taxRates.editTaxRate')} - ${editing?.tax_type} ${editing?.tax_code}`}</ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            <Grid templateColumns="repeat(2, 1fr)" gap={4}>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.taxType')}</FormLabel>
                <Input value={formType} onChange={e => setFormType(e.target.value)} isDisabled={!isNew} placeholder="btw, tourist_tax, btw_accommodation" bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.taxCode')}</FormLabel>
                <Input value={formCode} onChange={e => setFormCode(e.target.value)} isDisabled={!isNew} placeholder="zero, low, high, standard" bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.rate')}</FormLabel>
                <Input value={formRate} onChange={e => setFormRate(e.target.value)} type="number" step="0.001" bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.ledgerAccount')}</FormLabel>
                <Input value={formLedger} onChange={e => setFormLedger(e.target.value)} bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.effectiveFrom')}</FormLabel>
                <Input value={formFrom} onChange={e => setFormFrom(e.target.value)} type="date" bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.effectiveTo')}</FormLabel>
                <Input value={formTo} onChange={e => setFormTo(e.target.value)} type="date" bg="gray.600" color="white" /></FormControl>
              <FormControl gridColumn="span 2"><FormLabel color="white">{t('tenantAdmin.taxRates.description')}</FormLabel>
                <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.taxRates.calcMethod')}</FormLabel>
                <Select value={formMethod} onChange={e => setFormMethod(e.target.value)} bg="gray.600" color="white">
                  <option value="percentage">percentage</option><option value="fixed_per_night">fixed_per_night</option>
                  <option value="fixed_per_guest_night">fixed_per_guest_night</option><option value="percentage_of_room_price">percentage_of_room_price</option>
                </Select></FormControl>
            </Grid>
          </ModalBody>
          <ModalFooter>
            {!isNew && editing && <Button colorScheme="red" variant="ghost" mr="auto" onClick={onDeleteOpen}>Delete</Button>}
            <Button colorScheme="gray" mr={3} onClick={onClose}>Cancel</Button>
            <Button colorScheme="orange" onClick={handleSave} isLoading={saving}>{isNew ? 'Create' : 'Save'}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef as any} onClose={onDeleteClose}>
        <AlertDialogOverlay><AlertDialogContent bg="gray.700">
          <AlertDialogHeader color="white">{t('tenantAdmin.taxRates.deleteTaxRate')}</AlertDialogHeader>
          <AlertDialogBody color="gray.300">Delete <strong>{editing?.tax_type} {editing?.tax_code}</strong> ({editing?.rate}%) from {editing?.effective_from}?</AlertDialogBody>
          <AlertDialogFooter>
            <Button ref={cancelRef} onClick={onDeleteClose} colorScheme="gray">Cancel</Button>
            <Button colorScheme="red" onClick={handleDelete} ml={3}>Delete</Button>
          </AlertDialogFooter>
        </AlertDialogContent></AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
