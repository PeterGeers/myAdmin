import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl,
  FormLabel, Checkbox, Stack, Input, Select, IconButton,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay
} from '@chakra-ui/react';
import { AddIcon, ChevronLeftIcon, ChevronRightIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { getTenants, createTenant, updateTenant, deleteTenant, reprovisionTenant, Tenant, CreateTenantRequest, UpdateTenantRequest } from '../../services/sysadminService';
import { useColumnFilters } from '../../hooks/useColumnFilters';
import { FilterableHeader } from '../filters/FilterableHeader';
import { ModuleManagement } from './ModuleManagement';

export function TenantManagement() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit' | 'view'>('create');
  
  const [currentPage, setCurrentPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  
  const [sortBy, setSortBy] = useState<string>('administration');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  
  const [formData, setFormData] = useState({
    administration: '',
    display_name: '',
    contact_email: '',
    phone_number: '',
    street_address: '',
    city: '',
    zipcode: '',
    country: '',
    status: 'active' as 'active' | 'suspended' | 'inactive' | 'deleted',
    enabled_modules: [] as string[],
    locale: 'nl' as 'nl' | 'en'
  });
  
  const toast = useToast();
  const { t } = useTypedTranslation('admin');
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const { isOpen: isModuleOpen, onOpen: onModuleOpen, onClose: onModuleClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  // Client-side column filtering on the current page of results
  const {
    filters,
    setFilter,
    filteredData: displayTenants,
  } = useColumnFilters<Tenant>(tenants, {
    administration: '',
    display_name: '',
    status: '',
    enabled_modules: '',
    user_count: '',
    created_at: '',
  });

  useEffect(() => {
    loadTenants();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, perPage, sortBy, sortOrder]);

  const loadTenants = async () => {
    setLoading(true);
    try {
      const data = await getTenants({
        page: currentPage,
        per_page: perPage,
        sort_by: sortBy,
        sort_order: sortOrder
      });
      
      setTenants(data.tenants);
      setTotalPages(data.total_pages);
      setTotalCount(data.total);
    } catch (error) {
      toast({
        title: t('tenantManagement.messages.errorLoading'),
        description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      administration: '',
      display_name: '',
      contact_email: '',
      phone_number: '',
      street_address: '',
      city: '',
      zipcode: '',
      country: '',
      status: 'active',
      enabled_modules: [],
      locale: 'nl'
    });
  };

  const openCreateModal = () => {
    resetForm();
    setModalMode('create');
    onModalOpen();
  };

  const openEditModal = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    setFormData({
      administration: tenant.administration || '',
      display_name: tenant.display_name || '',
      contact_email: tenant.contact_email || '',
      phone_number: tenant.phone_number || '',
      street_address: tenant.street_address || '',
      city: tenant.city || '',
      zipcode: tenant.zipcode || '',
      country: tenant.country || '',
      status: tenant.status,
      enabled_modules: tenant.enabled_modules || [],
      locale: 'nl'
    });
    setModalMode('edit');
    onModalOpen();
  };

  const openDeleteDialog = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    onDeleteOpen();
  };

  const handleCreateTenant = async () => {
    if (!formData.administration || !formData.display_name || !formData.contact_email) {
      toast({
        title: t('tenantManagement.messages.validationError'),
        description: t('tenantManagement.messages.requiredFields'),
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setActionLoading(true);
    try {
      const request: CreateTenantRequest = {
        administration: formData.administration.toLowerCase().trim(),
        display_name: formData.display_name.trim(),
        contact_email: formData.contact_email.trim(),
        phone_number: formData.phone_number.trim() || undefined,
        street_address: formData.street_address.trim() || undefined,
        city: formData.city.trim() || undefined,
        zipcode: formData.zipcode.trim() || undefined,
        country: formData.country.trim() || undefined,
        enabled_modules: formData.enabled_modules,
        locale: formData.locale
      };

      await createTenant(request);

      toast({
        title: t('tenantManagement.messages.tenantCreated'),
        description: t('tenantManagement.messages.tenantCreatedSuccess', { name: formData.display_name }),
        status: 'success',
        duration: 3000,
      });

      onModalClose();
      resetForm();
      loadTenants();
    } catch (error) {
      toast({
        title: t('tenantManagement.messages.errorCreating'),
        description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateTenant = async () => {
    console.log('handleUpdateTenant called');
    console.log('selectedTenant:', selectedTenant);
    console.log('formData:', formData);
    
    if (!selectedTenant) {
      console.log('No selectedTenant, returning');
      return;
    }

    setActionLoading(true);
    try {
      const request: UpdateTenantRequest = {
        display_name: formData.display_name.trim(),
        status: formData.status,
        contact_email: formData.contact_email.trim(),
        phone_number: formData.phone_number.trim() || undefined,
        street_address: formData.street_address.trim() || undefined,
        city: formData.city.trim() || undefined,
        zipcode: formData.zipcode.trim() || undefined,
        country: formData.country.trim() || undefined
      };

      console.log('Calling updateTenant with:', selectedTenant.administration, request);
      const result = await updateTenant(selectedTenant.administration, request);
      console.log('updateTenant result:', result);

      toast({
        title: t('tenantManagement.messages.tenantUpdated'),
        description: t('tenantManagement.messages.tenantUpdatedSuccess', { name: formData.display_name }),
        status: 'success',
        duration: 3000,
      });

      onModalClose();
      setSelectedTenant(null);
      loadTenants();
    } catch (error) {
      console.error('Error updating tenant:', error);
      toast({
        title: t('tenantManagement.messages.errorUpdating'),
        description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteTenant = async () => {
    if (!selectedTenant) return;

    setActionLoading(true);
    try {
      await deleteTenant(selectedTenant.administration);

      toast({
        title: t('tenantManagement.messages.tenantDeleted'),
        description: t('tenantManagement.messages.tenantDeletedSuccess', { name: selectedTenant.display_name }),
        status: 'success',
        duration: 3000,
      });

      onDeleteClose();
      setSelectedTenant(null);
      loadTenants();
    } catch (error) {
      toast({
        title: t('tenantManagement.messages.errorDeleting'),
        description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
  };

  const getSortDirection = (field: string): 'asc' | 'desc' | null => {
    return sortBy === field ? sortOrder : null;
  };

  const handleReprovision = async () => {
    if (!selectedTenant) return;

    setActionLoading(true);
    try {
      const result = await reprovisionTenant(selectedTenant.administration, {
        locale: formData.locale
      });

      const prov = result.provisioning as { chart?: string; chart_rows?: number; modules?: Array<{ name: string; status: string }> };
      const chartStatus = prov?.chart || 'unknown';
      const chartRows = prov?.chart_rows || 0;
      const modulesCreated = (prov?.modules || []).filter((m: { status: string }) => m.status === 'created').length;

      toast({
        title: t('tenantManagement.messages.reprovisionComplete'),
        description: t('tenantManagement.messages.reprovisionDetails', {
          chart: chartStatus,
          rows: chartRows,
          modules: modulesCreated
        }),
        status: chartStatus === 'failed' ? 'warning' : 'success',
        duration: 8000,
        isClosable: true,
      });

      if (result.warnings && result.warnings.length > 0) {
        toast({
          title: t('tenantManagement.messages.reprovisionWarnings'),
          description: result.warnings.join('; '),
          status: 'warning',
          duration: 10000,
          isClosable: true,
        });
      }

      loadTenants();
    } catch (error) {
      toast({
        title: t('tenantManagement.messages.errorReprovisioning'),
        description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'),
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const toggleModule = (module: string) => {
    setFormData(prev => ({
      ...prev,
      enabled_modules: prev.enabled_modules.includes(module)
        ? prev.enabled_modules.filter(m => m !== module)
        : [...prev.enabled_modules, module]
    }));
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'green';
      case 'suspended': return 'orange';
      case 'inactive': return 'gray';
      case 'deleted': return 'red';
      default: return 'gray';
    }
  };

  const getModuleBadgeColor = (module: string) => {
    switch (module) {
      case 'FIN': return 'blue';
      case 'STR': return 'purple';
      case 'ADMIN': return 'orange';
      case 'TENADMIN': return 'teal';
      default: return 'gray';
    }
  };

  if (loading && tenants.length === 0) {
    return (
      <Box display="flex" justifyContent="center" p={8}>
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">{t('tenantManagement.loading')}</Text>
        </VStack>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        <HStack justify="space-between" wrap="wrap" spacing={4}>
          <HStack>
            <Text color="gray.400" fontSize="sm">
              {t('tenantManagement.total')}: <Text as="span" color="orange.400" fontWeight="bold">{totalCount}</Text>
            </Text>
            <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={openCreateModal}>
              {t('tenantManagement.createTenant')}
            </Button>
          </HStack>
        </HStack>

        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple">
            <Thead>
              <Tr>
                <FilterableHeader
                  label={t('tenantManagement.table.administration')}
                  filterValue={filters.administration}
                  onFilterChange={(v) => setFilter('administration', v)}
                  sortable
                  sortDirection={getSortDirection('administration')}
                  onSort={() => handleSort('administration')}
                />
                <FilterableHeader
                  label={t('tenantManagement.table.displayName')}
                  filterValue={filters.display_name}
                  onFilterChange={(v) => setFilter('display_name', v)}
                  sortable
                  sortDirection={getSortDirection('display_name')}
                  onSort={() => handleSort('display_name')}
                />
                <FilterableHeader
                  label={t('tenantManagement.table.status')}
                  filterValue={filters.status}
                  onFilterChange={(v) => setFilter('status', v)}
                  sortable
                  sortDirection={getSortDirection('status')}
                  onSort={() => handleSort('status')}
                />
                <FilterableHeader
                  label={t('tenantManagement.table.modules')}
                  filterValue={filters.enabled_modules}
                  onFilterChange={(v) => setFilter('enabled_modules', v)}
                />
                <FilterableHeader
                  label={t('tenantManagement.table.users')}
                  filterValue={filters.user_count}
                  onFilterChange={(v) => setFilter('user_count', v)}
                />
                <FilterableHeader
                  label={t('tenantManagement.table.created')}
                  filterValue={filters.created_at}
                  onFilterChange={(v) => setFilter('created_at', v)}
                  sortable
                  sortDirection={getSortDirection('created_at')}
                  onSort={() => handleSort('created_at')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {displayTenants.map((tenant) => (
                <Tr
                  key={tenant.administration}
                  _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => openEditModal(tenant)}
                >
                  <Td color="orange.400" fontWeight="bold">
                    {tenant.administration}
                  </Td>
                  <Td color="gray.300">{tenant.display_name}</Td>
                  <Td>
                    <Badge colorScheme={getStatusColor(tenant.status)}>
                      {tenant.status}
                    </Badge>
                  </Td>
                  <Td>
                    <HStack spacing={1}>
                      {tenant.enabled_modules.map(module => (
                        <Badge key={module} colorScheme={getModuleBadgeColor(module)} fontSize="xs">
                          {module}
                        </Badge>
                      ))}
                    </HStack>
                  </Td>
                  <Td color="gray.400">{tenant.user_count}</Td>
                  <Td color="gray.400" fontSize="sm">
                    {new Date(tenant.created_at).toLocaleDateString()}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>

        <HStack justify="space-between">
          <HStack>
            <Text color="gray.400" fontSize="sm">{t('tenantManagement.rowsPerPage')}:</Text>
            <Select
              value={perPage}
              onChange={(e) => setPerPage(Number(e.target.value))}
              bg="gray.600"
              color="white"
              borderColor="gray.500"
              size="sm"
              maxW="80px"
            >
              <option style={{ background: '#2D3748', color: 'white' }} value="5">5</option>
              <option style={{ background: '#2D3748', color: 'white' }} value="10">10</option>
              <option style={{ background: '#2D3748', color: 'white' }} value="25">25</option>
              <option style={{ background: '#2D3748', color: 'white' }} value="50">50</option>
            </Select>
          </HStack>
          <HStack>
            <Text color="gray.400" fontSize="sm">
              {t('tenantManagement.page')} {currentPage} {t('tenantManagement.of')} {totalPages}
            </Text>
            <IconButton
              aria-label={t('tenantManagement.actions.previousPage')}
              icon={<ChevronLeftIcon />}
              size="sm"
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              isDisabled={currentPage === 1}
            />
            <IconButton
              aria-label={t('tenantManagement.actions.nextPage')}
              icon={<ChevronRightIcon />}
              size="sm"
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              isDisabled={currentPage === totalPages}
            />
          </HStack>
        </HStack>
      </VStack>

      <Modal isOpen={isModalOpen} onClose={onModalClose} size="xl">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader color="orange.400">
            {modalMode === 'create' && t('tenantManagement.modal.createTitle')}
            {modalMode === 'edit' && t('tenantManagement.modal.editTitle', { name: selectedTenant?.display_name })}
            {modalMode === 'view' && t('tenantManagement.modal.viewTitle', { name: selectedTenant?.display_name })}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired={modalMode === 'create'} isDisabled={modalMode === 'view' || modalMode === 'edit'}>
                <FormLabel color="white">{t('tenantManagement.modal.administrationId')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.administrationPlaceholder')}
                  value={formData.administration}
                  onChange={(e) => setFormData({ ...formData, administration: e.target.value.toLowerCase() })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'edit' || modalMode === 'view'}
                />
                {modalMode === 'create' && (
                  <Text fontSize="xs" color="gray.400" mt={1}>
                    {t('tenantManagement.modal.administrationHelp')}
                  </Text>
                )}
              </FormControl>

              <FormControl isRequired isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.displayName')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.displayNamePlaceholder')}
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              <FormControl isRequired isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.contactEmail')}</FormLabel>
                <Input
                  type="email"
                  placeholder={t('tenantManagement.modal.contactEmailPlaceholder')}
                  value={formData.contact_email}
                  onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              {modalMode === 'edit' && (
                <FormControl>
                  <FormLabel color="white">{t('tenantManagement.status')}</FormLabel>
                  <Select
                    value={formData.status}
                    onChange={(e) => setFormData({ ...formData, status: e.target.value as any })}
                    bg="gray.600"
                    color="white"
                    borderColor="gray.500"
                  >
                    <option style={{ background: '#2D3748', color: 'white' }} value="active">{t('tenantManagement.status.active')}</option>
                    <option style={{ background: '#2D3748', color: 'white' }} value="suspended">{t('tenantManagement.status.suspended')}</option>
                    <option style={{ background: '#2D3748', color: 'white' }} value="inactive">{t('tenantManagement.status.inactive')}</option>
                  </Select>
                </FormControl>
              )}

              <FormControl isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.phoneNumber')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.phonePlaceholder')}
                  value={formData.phone_number}
                  onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              <FormControl isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.streetAddress')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.streetPlaceholder')}
                  value={formData.street_address}
                  onChange={(e) => setFormData({ ...formData, street_address: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              <HStack>
                <FormControl isDisabled={modalMode === 'view'}>
                  <FormLabel color="white">{t('tenantManagement.modal.city')}</FormLabel>
                  <Input
                    placeholder={t('tenantManagement.modal.cityPlaceholder')}
                    value={formData.city}
                    onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                    bg="gray.600"
                    color="white"
                    borderColor="gray.500"
                    _placeholder={{ color: 'gray.400' }}
                    isReadOnly={modalMode === 'view'}
                  />
                </FormControl>

                <FormControl isDisabled={modalMode === 'view'}>
                  <FormLabel color="white">{t('tenantManagement.modal.zipcode')}</FormLabel>
                  <Input
                    placeholder={t('tenantManagement.modal.zipcodePlaceholder')}
                    value={formData.zipcode}
                    onChange={(e) => setFormData({ ...formData, zipcode: e.target.value })}
                    bg="gray.600"
                    color="white"
                    borderColor="gray.500"
                    _placeholder={{ color: 'gray.400' }}
                    isReadOnly={modalMode === 'view'}
                  />
                </FormControl>
              </HStack>

              <FormControl isDisabled={modalMode === 'view'}>
                <FormLabel color="white">{t('tenantManagement.modal.country')}</FormLabel>
                <Input
                  placeholder={t('tenantManagement.modal.countryPlaceholder')}
                  value={formData.country}
                  onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                  bg="gray.600"
                  color="white"
                  borderColor="gray.500"
                  _placeholder={{ color: 'gray.400' }}
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              {modalMode === 'create' && (
                <FormControl>
                  <FormLabel color="gray.300">{t('tenantManagement.modal.locale')}</FormLabel>
                  <Select
                    value={formData.locale}
                    onChange={(e) => setFormData({ ...formData, locale: e.target.value as 'nl' | 'en' })}
                    bg="gray.600"
                    color="white"
                    borderColor="gray.500"
                  >
                    <option value="nl" style={{ background: '#2D3748' }}>{t('tenantManagement.modal.localeNL')}</option>
                    <option value="en" style={{ background: '#2D3748' }}>{t('tenantManagement.modal.localeEN')}</option>
                  </Select>
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    {t('tenantManagement.modal.localeHint')}
                  </Text>
                </FormControl>
              )}

              {modalMode === 'create' && (
                <FormControl>
                  <FormLabel color="gray.300">{t('tenantManagement.modal.enabledModules')}</FormLabel>
                  <Stack spacing={2}>
                    <Checkbox
                      isChecked={formData.enabled_modules.includes('FIN')}
                      onChange={() => toggleModule('FIN')}
                      colorScheme="orange"
                    >
                      <Text color="gray.300">{t('tenantManagement.modal.moduleFinancial')}</Text>
                    </Checkbox>
                    <Checkbox
                      isChecked={formData.enabled_modules.includes('STR')}
                      onChange={() => toggleModule('STR')}
                      colorScheme="orange"
                    >
                      <Text color="gray.300">{t('tenantManagement.modal.moduleSTR')}</Text>
                    </Checkbox>
                  </Stack>
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    {t('tenantManagement.modal.moduleAutoAdded')}
                  </Text>
                </FormControl>
              )}

              {modalMode === 'view' && selectedTenant && (
                <Box>
                  <Text color="gray.400" fontSize="sm" mb={2}>{t('tenantManagement.modal.additionalInfo')}</Text>
                  <VStack align="stretch" spacing={2} fontSize="sm">
                    <HStack>
                      <Text color="gray.500">{t('tenantManagement.status')}:</Text>
                      <Badge colorScheme={getStatusColor(selectedTenant.status)}>
                        {t(`tenantManagement.status.${selectedTenant.status}`)}
                      </Badge>
                    </HStack>
                    <HStack>
                      <Text color="gray.500">{t('tenantManagement.modal.userCount')}:</Text>
                      <Text color="gray.300">{selectedTenant.user_count}</Text>
                    </HStack>
                    <HStack>
                      <Text color="gray.500">{t('tenantManagement.modal.createdAt')}:</Text>
                      <Text color="gray.300">{new Date(selectedTenant.created_at).toLocaleString()}</Text>
                    </HStack>
                    {selectedTenant.updated_at && (
                      <HStack>
                        <Text color="gray.500">{t('tenantManagement.modal.updatedAt')}:</Text>
                        <Text color="gray.300">{new Date(selectedTenant.updated_at).toLocaleString()}</Text>
                      </HStack>
                    )}
                  </VStack>
                </Box>
              )}
            </VStack>
          </ModalBody>
          <ModalFooter>
            {modalMode === 'view' ? (
              <>
                <Button variant="ghost" mr={3} onClick={onModalClose}>{t('tenantManagement.actions.close')}</Button>
                <Button colorScheme="orange" onClick={() => { onModalClose(); openEditModal(selectedTenant!); }}>
                  {t('tenantManagement.actions.edit')}
                </Button>
              </>
            ) : modalMode === 'edit' ? (
              <>
                <Button 
                  variant="ghost" 
                  mr="auto"
                  colorScheme="red"
                  onClick={() => { onModalClose(); openDeleteDialog(selectedTenant!); }}
                  isDisabled={selectedTenant?.administration === 'myAdmin'}
                >
                  {t('tenantManagement.actions.delete')}
                </Button>
                <Button
                  variant="outline"
                  colorScheme="green"
                  onClick={handleReprovision}
                  isLoading={actionLoading}
                  title={t('tenantManagement.actions.reprovisionTooltip')}
                >
                  {t('tenantManagement.actions.reprovision')}
                </Button>
                <Button 
                  variant="outline" 
                  colorScheme="blue"
                  onClick={() => { onModalClose(); onModuleOpen(); }}
                >
                  {t('tenantManagement.actions.manageModules')}
                </Button>
                <Button variant="ghost" mr={3} onClick={onModalClose}>{t('tenantManagement.actions.cancel')}</Button>
                <Button
                  colorScheme="orange"
                  onClick={handleUpdateTenant}
                  isLoading={actionLoading}
                >
                  {t('tenantManagement.actions.update')}
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" mr={3} onClick={onModalClose}>{t('tenantManagement.actions.cancel')}</Button>
                <Button
                  colorScheme="orange"
                  onClick={handleCreateTenant}
                  isLoading={actionLoading}
                >
                  {t('tenantManagement.actions.create')}
                </Button>
              </>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white">
            <AlertDialogHeader fontSize="lg" fontWeight="bold" color="orange.400">
              {t('tenantManagement.deleteDialog.title')}
            </AlertDialogHeader>
            <AlertDialogBody>
              {t('tenantManagement.deleteDialog.confirmMessage')} <Text as="span" fontWeight="bold" color="orange.400">"{selectedTenant?.display_name}"</Text>?
              <br /><br />
              <Text color="red.400">{t('tenantManagement.deleteDialog.warning')}</Text>
              {selectedTenant && selectedTenant.user_count > 0 && (
                <>
                  <br />
                  <Text color="orange.400">{t('tenantManagement.deleteDialog.hasUsers', { count: selectedTenant.user_count })}</Text>
                </>
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>{t('tenantManagement.actions.cancel')}</Button>
              <Button colorScheme="red" onClick={handleDeleteTenant} ml={3} isLoading={actionLoading}>
                {t('tenantManagement.actions.delete')}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {selectedTenant && (
        <ModuleManagement
          administration={selectedTenant.administration}
          isOpen={isModuleOpen}
          onClose={() => {
            onModuleClose();
            loadTenants(); // Refresh tenant list to show updated modules
          }}
        />
      )}
    </Box>
  );
}

export default TenantManagement;
