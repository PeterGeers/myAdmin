import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Th, Td, Badge, Button, Grid,
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
import { FilterPanel } from '../../components/filters/FilterPanel';
import { SearchFilterConfig } from '../../components/filters/types';

interface Props { tenant: string; }

export default function ParameterManagement({ tenant }: Props) {
  const { t } = useTypedTranslation('admin');
  const [params, setParams] = useState<Record<string, Parameter[]>>({});
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ namespace: '', key: '', value: '', value_type: '', scope_origin: '' });
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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getParameters();
      setParams(data.parameters || {});
    } catch (e: any) {
      toast({ title: t('tenantAdmin.parameters.loading'), description: e.message, status: 'error', duration: 5000 });
    } finally { setLoading(false); }
  }, [tenant, toast]);

  useEffect(() => { load(); }, [load]);

  const namespaces = Object.keys(params).sort();
  const allParams: Parameter[] = namespaces.flatMap(ns => params[ns] || []);

  const filteredParams = useMemo(() => allParams.filter(p => {
    const pValue = p.is_secret ? '********' : typeof p.value === 'object' ? JSON.stringify(p.value) : String(p.value ?? '');
    return (
      (!filters.namespace || p.namespace.toLowerCase().includes(filters.namespace.toLowerCase())) &&
      (!filters.key || p.key.toLowerCase().includes(filters.key.toLowerCase())) &&
      (!filters.value || pValue.toLowerCase().includes(filters.value.toLowerCase())) &&
      (!filters.value_type || p.value_type.toLowerCase().includes(filters.value_type.toLowerCase())) &&
      (!filters.scope_origin || (p.scope_origin || '').toLowerCase().includes(filters.scope_origin.toLowerCase()))
    );
  }), [allParams, filters]);

  const searchFilters: SearchFilterConfig[] = [
    { type: 'search', label: t('tenantAdmin.parameters.namespace'), value: filters.namespace, onChange: (v) => setFilters(prev => ({ ...prev, namespace: v })), placeholder: 'Filter...', size: 'sm' },
    { type: 'search', label: t('tenantAdmin.parameters.key'), value: filters.key, onChange: (v) => setFilters(prev => ({ ...prev, key: v })), placeholder: 'Filter...', size: 'sm' },
    { type: 'search', label: t('tenantAdmin.parameters.value'), value: filters.value, onChange: (v) => setFilters(prev => ({ ...prev, value: v })), placeholder: 'Filter...', size: 'sm' },
    { type: 'search', label: t('tenantAdmin.parameters.valueType'), value: filters.value_type, onChange: (v) => setFilters(prev => ({ ...prev, value_type: v })), placeholder: 'Filter...', size: 'sm' },
    { type: 'search', label: t('tenantAdmin.parameters.scope'), value: filters.scope_origin, onChange: (v) => setFilters(prev => ({ ...prev, scope_origin: v })), placeholder: 'Filter...', size: 'sm' },
  ];

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

  if (loading) return <Box p={4}><Spinner color="orange.400" /><Text color="gray.400" display="inline" ml={2}>Loading parameters...</Text></Box>;

  return (
    <Box>
      <HStack mb={4} justify="flex-end">
        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleAdd}>{t('tenantAdmin.parameters.addParameter')}</Button>
      </HStack>
      <Box mb={4}>
        <FilterPanel filters={searchFilters} layout="horizontal" size="sm" spacing={2} />
      </Box>
      <Table variant="simple" size="sm">
        <Thead><Tr><Th color="gray.400">{t('tenantAdmin.parameters.namespace')}</Th><Th color="gray.400">{t('tenantAdmin.parameters.key')}</Th><Th color="gray.400">{t('tenantAdmin.parameters.value')}</Th><Th color="gray.400">{t('tenantAdmin.parameters.valueType')}</Th><Th color="gray.400">{t('tenantAdmin.parameters.scope')}</Th></Tr></Thead>
        <Tbody>
          {filteredParams.map((p, i) => (
            <Tr key={`${p.namespace}-${p.key}-${i}`} cursor={p.scope_origin !== 'system' ? 'pointer' : 'default'} _hover={p.scope_origin !== 'system' ? { bg: 'gray.600' } : {}} onClick={() => handleRowClick(p)}>
              <Td color="white" fontSize="sm">{p.namespace}</Td>
              <Td color="white" fontSize="sm">{p.key}</Td>
              <Td color="white" fontSize="sm" maxW="300px" isTruncated>{p.is_secret ? '********' : typeof p.value === 'object' ? JSON.stringify(p.value) : String(p.value ?? '')}</Td>
              <Td><Badge colorScheme="blue" fontSize="xs">{p.value_type}</Badge></Td>
              <Td><Badge colorScheme={p.scope_origin === 'tenant' ? 'orange' : 'gray'} fontSize="xs">{p.scope_origin}</Badge></Td>
            </Tr>
          ))}
          {filteredParams.length === 0 && <Tr><Td colSpan={5} color="gray.500" textAlign="center">{t('tenantAdmin.parameters.noParameters')}</Td></Tr>}
        </Tbody>
      </Table>

      <Modal isOpen={isOpen} onClose={onClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.700">
          <ModalHeader color="white">{isNew ? t('tenantAdmin.parameters.addParameter') : `${t('tenantAdmin.parameters.editParameter')} - ${editing?.namespace}.${editing?.key}`}</ModalHeader>
          <ModalCloseButton color="white" />
          <ModalBody>
            <Grid templateColumns="repeat(2, 1fr)" gap={4}>
              <FormControl><FormLabel color="white">{t('tenantAdmin.parameters.namespace')}</FormLabel>
                <Input value={formNs} onChange={e => setFormNs(e.target.value)} isDisabled={!isNew} bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.parameters.key')}</FormLabel>
                <Input value={formKey} onChange={e => setFormKey(e.target.value)} isDisabled={!isNew} bg="gray.600" color="white" /></FormControl>
              <FormControl><FormLabel color="white">{t('tenantAdmin.parameters.valueType')}</FormLabel>
                <Select value={formType} onChange={e => setFormType(e.target.value)} bg="gray.600" color="white">
                  <option value="string">string</option><option value="number">number</option>
                  <option value="boolean">boolean</option><option value="json">json</option>
                </Select></FormControl>
              {isNew && (<FormControl display="flex" alignItems="flex-end">
                <FormLabel color="white" mb={0} mr={3}>{t('tenantAdmin.parameters.secret')}</FormLabel>
                <Switch isChecked={formSecret} onChange={e => setFormSecret(e.target.checked)} colorScheme="orange" />
              </FormControl>)}
              <FormControl gridColumn="span 2"><FormLabel color="white">{t('tenantAdmin.parameters.value')}</FormLabel>
                {formType === 'boolean' ? (
                  <Select value={formValue} onChange={e => setFormValue(e.target.value)} bg="gray.600" color="white">
                    <option value="true">true</option><option value="false">false</option></Select>
                ) : formType === 'json' ? (
                  <Textarea value={formValue} onChange={e => setFormValue(e.target.value)} rows={5} bg="gray.600" color="white" fontFamily="mono" />
                ) : (
                  <Input value={formValue} onChange={e => setFormValue(e.target.value)} type={formType === 'number' ? 'number' : 'text'} bg="gray.600" color="white" />
                )}</FormControl>
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
        <AlertDialogOverlay><AlertDialogContent bg="gray.700">
          <AlertDialogHeader color="white">Delete Parameter</AlertDialogHeader>
          <AlertDialogBody color="gray.300">Delete <strong>{editing?.namespace}.{editing?.key}</strong>? This cannot be undone.</AlertDialogBody>
          <AlertDialogFooter>
            <Button ref={cancelRef} onClick={onDeleteClose} colorScheme="gray">Cancel</Button>
            <Button colorScheme="red" onClick={handleDelete} ml={3}>Delete</Button>
          </AlertDialogFooter>
        </AlertDialogContent></AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
