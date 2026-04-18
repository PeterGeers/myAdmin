/**
 * Parameter Management Component
 *
 * Allows tenant admins to view, create, edit, and delete parameters.
 * System-scope parameters are read-only (row-click disabled).
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - useTableConfig('parameters') for parameter-driven column/filter config
 * - useFilterableTable for combined filtering + sorting
 * - FilterableHeader for inline column text filters with sort indicators
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Td, Badge, Button, Grid,
  useToast, useDisclosure, Spinner, Text, HStack,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter, ModalCloseButton,
  FormControl, FormLabel, Input, Textarea, Switch, Select,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { Parameter, ParameterCreateRequest } from '../../types/parameterTypes';
import { getParameters, createParameter, updateParameter, deleteParameter } from '../../services/parameterService';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';
import { useTableConfig } from '../../hooks/useTableConfig';

interface Props { tenant: string; }

/**
 * Extended parameter with a display-friendly value string for filtering.
 * Secrets show '********', objects are JSON-stringified.
 */
interface ParameterRow extends Parameter {
  displayValue: string;
}

/**
 * Map column keys (from useTableConfig) to translation-based display labels.
 */
function useColumnLabels() {
  const { t } = useTypedTranslation('admin');
  return useMemo<Record<string, string>>(() => ({
    namespace: t('tenantAdmin.parameters.namespace'),
    key: t('tenantAdmin.parameters.key'),
    value: t('tenantAdmin.parameters.value'),
    value_type: t('tenantAdmin.parameters.valueType'),
    scope_origin: t('tenantAdmin.parameters.scope'),
  }), [t]);
}

/** Convert a Parameter's value to a display string */
function toDisplayValue(p: Parameter): string {
  if (p.is_secret) return '********';
  if (typeof p.value === 'object') return JSON.stringify(p.value);
  return String(p.value ?? '');
}

export default function ParameterManagement({ tenant }: Props) {
  const { t } = useTypedTranslation('admin');
  const columnLabels = useColumnLabels();

  const [params, setParams] = useState<Record<string, Parameter[]>>({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Parameter | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formNs, setFormNs] = useState('');
  const [formKey, setFormKey] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formType, setFormType] = useState<string>('string');
  const [formSecret, setFormSecret] = useState(false);
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Parameter-driven table configuration
  const tableConfig = useTableConfig('parameters');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getParameters();
      setParams(data.parameters || {});
    } catch (e: any) {
      toast({ title: t('tenantAdmin.parameters.loading'), description: e.message, status: 'error', duration: 5000 });
    } finally { setLoading(false); }
  }, [toast, t]);

  useEffect(() => { load(); }, [load, tenant]);

  // Build flat parameter array with pre-computed display value
  const allParams: ParameterRow[] = useMemo(() => {
    const namespaces = Object.keys(params).sort();
    return namespaces.flatMap(ns =>
      (params[ns] || []).map(p => ({
        ...p,
        displayValue: toDisplayValue(p),
      }))
    );
  }, [params]);

  // Build initial filters from configured filterable columns
  const initialFilters = useMemo(
    () => Object.fromEntries(tableConfig.filterableColumns.map((col) => [col, ''])),
    [tableConfig.filterableColumns],
  );

  // For filtering, we need the 'value' column to match against the display
  // string (secrets masked, objects stringified). Create a filterable view
  // where the 'value' field is the display string.
  const filterableData = useMemo(
    () => allParams.map(p => ({ ...p, value: p.displayValue })),
    [allParams],
  );

  // Combined filtering + sorting via framework hook
  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<ParameterRow>(filterableData as ParameterRow[], {
    initialFilters,
    defaultSort: tableConfig.defaultSort,
  });

  // Map processed rows back to original ParameterRow objects (with real value)
  // so that row-click opens the modal with the actual value, not the display string.
  const displayRows = useMemo(
    () => processedData.map(row => {
      const original = allParams.find(
        p => p.namespace === row.namespace && p.key === row.key && p.scope_origin === row.scope_origin
      );
      return original || row;
    }),
    [processedData, allParams],
  );

  const handleAdd = () => {
    setIsNew(true); setEditing(null);
    setFormNs(''); setFormKey(''); setFormValue(''); setFormType('string'); setFormSecret(false);
    onOpen();
  };

  const handleRowClick = (p: Parameter) => {
    if (p.scope_origin === 'system') return;
    setIsNew(false); setEditing(p);
    setFormNs(p.namespace); setFormKey(p.key);
    setFormValue(typeof p.value === 'object' ? JSON.stringify(p.value, null, 2) : String(p.value ?? ''));
    setFormType(p.value_type); setFormSecret(p.is_secret);
    onOpen();
  };

  const handleSave = async () => {
    if (!formNs.trim() || !formKey.trim()) {
      toast({ title: t('tenantAdmin.parameters.namespace') + ' and ' + t('tenantAdmin.parameters.key') + ' are required', status: 'warning', duration: 3000 }); return;
    }
    setSaving(true);
    try {
      let parsedValue: any = formValue;
      if (formType === 'number') parsedValue = Number(formValue);
      else if (formType === 'boolean') parsedValue = formValue === 'true';
      else if (formType === 'json') parsedValue = JSON.parse(formValue);
      if (isNew) {
        const req: ParameterCreateRequest = { scope: 'tenant', namespace: formNs, key: formKey, value: parsedValue, value_type: formType as any, is_secret: formSecret };
        const res = await createParameter(req);
        if (res.success) { toast({ title: t('tenantAdmin.parameters.created'), status: 'success', duration: 3000 }); onClose(); load(); }
        else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      } else if (editing?.id) {
        const res = await updateParameter(editing.id, { value: parsedValue, value_type: formType as any });
        if (res.success) { toast({ title: t('tenantAdmin.parameters.updated'), status: 'success', duration: 3000 }); onClose(); load(); }
        else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) { toast({ title: t('tenantAdmin.parameters.title'), description: e.message, status: 'error', duration: 5000 }); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    if (!editing?.id) return;
    try {
      const res = await deleteParameter(editing.id);
      if (res.success) { toast({ title: t('tenantAdmin.parameters.deleted'), status: 'success', duration: 3000 }); onClose(); onDeleteClose(); load(); }
      else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
    } catch (e: any) { toast({ title: t('tenantAdmin.parameters.deleteParameter'), description: e.message, status: 'error', duration: 5000 }); }
    finally { onDeleteClose(); }
  };

  /** Render a table cell with column-specific styling */
  const renderCellValue = (p: ParameterRow, col: string) => {
    switch (col) {
      case 'value':
        return (
          <Td color="white" fontSize="sm" maxW="300px" isTruncated>
            {p.displayValue}
          </Td>
        );
      case 'value_type':
        return <Td><Badge colorScheme="blue" fontSize="xs">{p.value_type}</Badge></Td>;
      case 'scope_origin':
        return (
          <Td>
            <Badge colorScheme={p.scope_origin === 'tenant' ? 'orange' : 'gray'} fontSize="xs">
              {p.scope_origin}
            </Badge>
          </Td>
        );
      default:
        return <Td color="white" fontSize="sm">{(p as any)[col]}</Td>;
    }
  };

  if (loading) return <Box p={4}><Spinner color="orange.400" /><Text color="gray.400" display="inline" ml={2}>Loading parameters...</Text></Box>;

  return (
    <Box>
      <HStack mb={4} justify="flex-end">
        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleAdd}>
          {t('tenantAdmin.parameters.addParameter')}
        </Button>
      </HStack>
      <Table variant="simple" size="sm">
        <Thead>
          <Tr>
            {tableConfig.columns.map((col) => {
              const isFilterable = tableConfig.filterableColumns.includes(col);
              return (
                <FilterableHeader
                  key={col}
                  label={columnLabels[col] || col}
                  filterValue={isFilterable ? filters[col] : undefined}
                  onFilterChange={isFilterable ? (v) => setFilter(col, v) : undefined}
                  sortable
                  sortDirection={sortField === col ? sortDirection : null}
                  onSort={() => handleSort(col)}
                />
              );
            })}
          </Tr>
        </Thead>
        <Tbody>
          {displayRows.map((p, i) => (
            <Tr
              key={`${p.namespace}-${p.key}-${i}`}
              cursor={p.scope_origin !== 'system' ? 'pointer' : 'default'}
              _hover={p.scope_origin !== 'system' ? { bg: 'gray.600' } : {}}
              onClick={() => handleRowClick(p)}
            >
              {tableConfig.columns.map((col) => (
                <React.Fragment key={col}>
                  {renderCellValue(p, col)}
                </React.Fragment>
              ))}
            </Tr>
          ))}
          {displayRows.length === 0 && (
            <Tr>
              <Td colSpan={tableConfig.columns.length} color="gray.500" textAlign="center">
                {t('tenantAdmin.parameters.noParameters')}
              </Td>
            </Tr>
          )}
        </Tbody>
      </Table>

      <Modal isOpen={isOpen} onClose={onClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.700">
          <ModalHeader color="white">
            {isNew
              ? t('tenantAdmin.parameters.addParameter')
              : `${t('tenantAdmin.parameters.editParameter')} - ${editing?.namespace}.${editing?.key}`}
          </ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            <Grid templateColumns="repeat(2, 1fr)" gap={4}>
              <FormControl>
                <FormLabel color="white">{t('tenantAdmin.parameters.namespace')}</FormLabel>
                <Input value={formNs} onChange={e => setFormNs(e.target.value)} isDisabled={!isNew} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('tenantAdmin.parameters.key')}</FormLabel>
                <Input value={formKey} onChange={e => setFormKey(e.target.value)} isDisabled={!isNew} bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('tenantAdmin.parameters.valueType')}</FormLabel>
                <Select value={formType} onChange={e => setFormType(e.target.value)} bg="gray.600" color="white">
                  <option value="string">string</option>
                  <option value="number">number</option>
                  <option value="boolean">boolean</option>
                  <option value="json">json</option>
                </Select>
              </FormControl>
              {isNew && (
                <FormControl display="flex" alignItems="flex-end">
                  <FormLabel color="white" mb={0} mr={3}>{t('tenantAdmin.parameters.secret')}</FormLabel>
                  <Switch isChecked={formSecret} onChange={e => setFormSecret(e.target.checked)} colorScheme="orange" />
                </FormControl>
              )}
              <FormControl gridColumn="span 2">
                <FormLabel color="white">{t('tenantAdmin.parameters.value')}</FormLabel>
                {formType === 'boolean' ? (
                  <Select value={formValue} onChange={e => setFormValue(e.target.value)} bg="gray.600" color="white">
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </Select>
                ) : formType === 'json' ? (
                  <Textarea value={formValue} onChange={e => setFormValue(e.target.value)} rows={5} bg="gray.600" color="white" fontFamily="mono" />
                ) : (
                  <Input value={formValue} onChange={e => setFormValue(e.target.value)} type={formType === 'number' ? 'number' : 'text'} bg="gray.600" color="white" />
                )}
              </FormControl>
            </Grid>
          </ModalBody>
          <ModalFooter>
            {!isNew && editing?.id && <Button colorScheme="red" variant="ghost" mr="auto" onClick={onDeleteOpen}>Delete</Button>}
            <Button colorScheme="gray" mr={3} onClick={onClose}>Cancel</Button>
            <Button colorScheme="orange" onClick={handleSave} isLoading={saving}>{isNew ? 'Create' : 'Save'}</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef as any} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.700">
            <AlertDialogHeader color="white">Delete Parameter</AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              Delete <strong>{editing?.namespace}.{editing?.key}</strong>? This cannot be undone.
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose} colorScheme="gray">Cancel</Button>
              <Button colorScheme="red" onClick={handleDelete} ml={3}>Delete</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
