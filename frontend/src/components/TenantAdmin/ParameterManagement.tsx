/**
 * Parameter Management Component
 *
 * Allows tenant admins to view, edit, and delete parameters.
 * All parameter rows are clickable to open the edit modal.
 * Actions (edit, reset, customize) are consolidated into the modal —
 * no inline action buttons or Add Parameter button.
 *
 * Uses the table-filter-framework-v2 hybrid approach:
 * - useTableConfig('parameters') for parameter-driven column/filter config
 * - useFilterableTable for combined filtering + sorting
 * - FilterableHeader for inline column text filters with sort indicators
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Td, Badge, Button, Grid, HStack,
  useToast, useDisclosure, Spinner, Text,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody, ModalFooter, ModalCloseButton,
  FormControl, FormLabel, Input, Textarea, Select, Code,
  AlertDialog, AlertDialogOverlay, AlertDialogContent, AlertDialogHeader,
  AlertDialogBody, AlertDialogFooter,
} from '@chakra-ui/react';
import { Parameter, ParameterCreateRequest } from '../../types/parameterTypes';
import { getParameters, createParameter, updateParameter, deleteParameter, getParameterDefault } from '../../services/parameterService';
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
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formNs, setFormNs] = useState('');
  const [formKey, setFormKey] = useState('');
  const [formValue, setFormValue] = useState('');
  const [formType, setFormType] = useState<string>('string');
  const [formSecret, setFormSecret] = useState(false);
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const { isOpen: isResetOpen, onOpen: onResetOpen, onClose: onResetClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const resetCancelRef = useRef<HTMLButtonElement>(null);
  const [defaultValue, setDefaultValue] = useState<any>(null);
  const [defaultSource, setDefaultSource] = useState<string>('');
  const [loadingDefault, setLoadingDefault] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

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

  const handleRowClick = (p: Parameter) => {
    const readOnly = p.scope_origin === 'system' || p.id === null;
    setIsReadOnly(readOnly);
    setEditing(p);
    setFormNs(p.namespace); setFormKey(p.key);
    const initialValue = typeof p.value === 'object' ? JSON.stringify(p.value, null, 2) : String(p.value ?? '');
    setFormValue(initialValue);
    setFormType(p.value_type); setFormSecret(p.is_secret);
    // Validate initial JSON value
    if (p.value_type === 'json') {
      try {
        JSON.parse(initialValue);
        setJsonError(null);
      } catch (e: any) {
        setJsonError(`Invalid JSON: ${e.message}`);
      }
    } else {
      setJsonError(null);
    }
    onOpen();
  };

  /** Validate JSON on every value change when formType is 'json' */
  const handleValueChange = (newValue: string) => {
    setFormValue(newValue);
    if (formType === 'json') {
      try {
        JSON.parse(newValue);
        setJsonError(null);
      } catch (e: any) {
        setJsonError(`Invalid JSON: ${e.message}`);
      }
    }
  };

  /** Re-indent current JSON value with 2-space formatting */
  const handleFormat = () => {
    try {
      const parsed = JSON.parse(formValue);
      setFormValue(JSON.stringify(parsed, null, 2));
      setJsonError(null);
    } catch {
      // Button should be disabled when invalid, but guard anyway
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      let parsedValue: any = formValue;
      if (formType === 'number') parsedValue = Number(formValue);
      else if (formType === 'boolean') parsedValue = formValue === 'true';
      else if (formType === 'json') parsedValue = JSON.parse(formValue);
      if (editing?.id) {
        const res = await updateParameter(editing.id, { value: parsedValue, value_type: formType as any });
        if (res.success) { toast({ title: t('tenantAdmin.parameters.updated'), status: 'success', duration: 3000 }); onClose(); load(); }
        else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      } else if (editing && !editing.id) {
        // Code default (no DB row yet) — create a tenant-scope row with the edited value
        const req: ParameterCreateRequest = { scope: 'tenant', namespace: formNs, key: formKey, value: parsedValue, value_type: formType as any, is_secret: formSecret };
        const res = await createParameter(req);
        if (res.success) { toast({ title: t('tenantAdmin.parameters.updated'), status: 'success', duration: 3000 }); onClose(); load(); }
        else toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) { toast({ title: t('tenantAdmin.parameters.title'), description: e.message, status: 'error', duration: 5000 }); }
    finally { setSaving(false); }
  };

  const handleCustomize = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      let parsedValue: any = formValue;
      if (formType === 'number') parsedValue = Number(formValue);
      else if (formType === 'boolean') parsedValue = formValue === 'true';
      else if (formType === 'json') parsedValue = JSON.parse(formValue);
      const req: ParameterCreateRequest = {
        scope: 'tenant', namespace: formNs, key: formKey,
        value: parsedValue, value_type: formType as any, is_secret: formSecret,
      };
      const res = await createParameter(req);
      if (res.success) {
        toast({ title: t('tenantAdmin.parameters.customized'), status: 'success', duration: 3000 });
        onClose();
        load();
      } else {
        toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) {
      toast({ title: t('tenantAdmin.parameters.title'), description: e.message, status: 'error', duration: 5000 });
    } finally { setSaving(false); }
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

  const handleResetToDefault = async () => {
    if (!editing) return;
    setLoadingDefault(true);
    try {
      const res = await getParameterDefault(editing.namespace, editing.key);
      if (res.success && res.has_default) {
        setDefaultValue(res.value);
        setDefaultSource(res.source || '');
        onResetOpen();
      } else {
        toast({ title: 'Error', description: 'Failed to fetch default value', status: 'error', duration: 5000 });
      }
    } catch (e: any) {
      toast({ title: 'Error', description: 'Failed to fetch default value', status: 'error', duration: 5000 });
    } finally {
      setLoadingDefault(false);
    }
  };

  const handleConfirmReset = async () => {
    if (!editing?.id) return;
    try {
      const res = await deleteParameter(editing.id);
      if (res.success) {
        toast({ title: t('tenantAdmin.parameters.resetToDefault'), status: 'success', duration: 3000 });
        onResetClose();
        onClose();
        load();
      } else {
        toast({ title: 'Error', description: res.error, status: 'error', duration: 5000 });
      }
    } catch (e: any) {
      toast({ title: 'Error', description: e.message, status: 'error', duration: 5000 });
    }
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
            <Badge colorScheme={p.scope_origin === 'tenant' ? 'orange' : 'purple'} fontSize="xs">
              {p.scope_origin === 'system' ? 'system default' : 'tenant override'}
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
              cursor="pointer"
              _hover={{ bg: 'gray.600' }}
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
            {`${isReadOnly ? t('tenantAdmin.parameters.viewParameter') : t('tenantAdmin.parameters.editParameter')} - ${editing?.namespace}.${editing?.key}`}
          </ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            <Grid templateColumns="repeat(2, 1fr)" gap={4}>
              <FormControl>
                <FormLabel color="white">{t('tenantAdmin.parameters.namespace')}</FormLabel>
                <Input value={formNs} isDisabled bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('tenantAdmin.parameters.key')}</FormLabel>
                <Input value={formKey} isDisabled bg="gray.600" color="white" />
              </FormControl>
              <FormControl>
                <FormLabel color="white">{t('tenantAdmin.parameters.valueType')}</FormLabel>
                <Select value={formType} isDisabled bg="gray.600" color="white">
                  <option value="string">string</option>
                  <option value="number">number</option>
                  <option value="boolean">boolean</option>
                  <option value="json">json</option>
                </Select>
              </FormControl>
              <FormControl gridColumn="span 2">
                <HStack justify="space-between">
                  <FormLabel color="white" mb={0}>{t('tenantAdmin.parameters.value')}</FormLabel>
                  {formType === 'json' && (
                    <Button
                      size="xs"
                      variant="ghost"
                      colorScheme="blue"
                      isDisabled={!!jsonError || isReadOnly}
                      onClick={handleFormat}
                    >
                      Format
                    </Button>
                  )}
                </HStack>
                {formType === 'boolean' ? (
                  <Select value={formValue} onChange={e => handleValueChange(e.target.value)} isDisabled={isReadOnly} bg="gray.600" color="white">
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </Select>
                ) : formType === 'json' ? (
                  <>
                    <Textarea value={formValue} onChange={e => handleValueChange(e.target.value)} isDisabled={isReadOnly} rows={5} bg="gray.600" color="white" fontFamily="mono" />
                    {jsonError && (
                      <Text color="red.300" fontSize="xs" mt={1}>{jsonError}</Text>
                    )}
                  </>
                ) : (
                  <Input value={formValue} onChange={e => handleValueChange(e.target.value)} isDisabled={isReadOnly} type={formType === 'number' ? 'number' : 'text'} bg="gray.600" color="white" />
                )}
              </FormControl>
            </Grid>
          </ModalBody>
          <ModalFooter>
            {isReadOnly ? (
              <>
                <Button colorScheme="orange" mr={3} onClick={handleCustomize} isLoading={saving}>
                  {t('tenantAdmin.parameters.customize')}
                </Button>
                <Button colorScheme="gray" onClick={onClose}>Cancel</Button>
              </>
            ) : (
              <>
                {editing?.id && editing?.has_code_default && (
                  <Button colorScheme="red" variant="ghost" mr="auto" onClick={handleResetToDefault} isLoading={loadingDefault}>
                    {t('tenantAdmin.parameters.resetToDefaultBtn')}
                  </Button>
                )}
                {editing?.id && !editing?.has_code_default && (
                  <Button colorScheme="red" variant="ghost" mr="auto" onClick={onDeleteOpen}>Delete</Button>
                )}
                <Button colorScheme="gray" mr={3} onClick={onClose}>Cancel</Button>
                <Button colorScheme="orange" onClick={handleSave} isLoading={saving} isDisabled={formType === 'json' && !!jsonError}>Save</Button>
              </>
            )}
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

      <AlertDialog isOpen={isResetOpen} leastDestructiveRef={resetCancelRef as any} onClose={onResetClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.700" maxW="lg">
            <AlertDialogHeader color="white">
              Reset: {editing?.namespace}.{editing?.key}
            </AlertDialogHeader>
            <AlertDialogBody color="gray.300">
              <Text fontWeight="bold" mb={1}>{t('tenantAdmin.parameters.currentValue')}</Text>
              {editing?.is_secret ? (
                <Code display="block" p={2} mb={4} bg="gray.600" color="white" whiteSpace="pre" fontFamily="mono">
                  ********
                </Code>
              ) : editing?.value_type === 'json' ? (
                <Code display="block" p={2} mb={4} bg="gray.600" color="white" whiteSpace="pre" fontFamily="mono" overflowX="auto">
                  {typeof editing?.value === 'object' ? JSON.stringify(editing.value, null, 2) : String(editing?.value ?? '')}
                </Code>
              ) : (
                <Code display="block" p={2} mb={4} bg="gray.600" color="white" whiteSpace="pre" fontFamily="mono">
                  {String(editing?.value ?? '')}
                </Code>
              )}

              <Text fontWeight="bold" mb={1}>
                {t('tenantAdmin.parameters.defaultValue')} ({defaultSource})
              </Text>
              {editing?.is_secret ? (
                <Code display="block" p={2} bg="gray.600" color="white" whiteSpace="pre" fontFamily="mono">
                  ********
                </Code>
              ) : editing?.value_type === 'json' ? (
                <Code display="block" p={2} bg="gray.600" color="white" whiteSpace="pre" fontFamily="mono" overflowX="auto">
                  {typeof defaultValue === 'object' ? JSON.stringify(defaultValue, null, 2) : String(defaultValue ?? '')}
                </Code>
              ) : (
                <Code display="block" p={2} bg="gray.600" color="white" whiteSpace="pre" fontFamily="mono">
                  {String(defaultValue ?? '')}
                </Code>
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={resetCancelRef} onClick={onResetClose} colorScheme="gray">Cancel</Button>
              <Button colorScheme="red" onClick={handleConfirmReset} ml={3}>
                {t('tenantAdmin.parameters.resetToDefaultBtn')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
