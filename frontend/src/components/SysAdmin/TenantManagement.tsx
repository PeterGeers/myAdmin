import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Input, Select,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl,
  FormLabel, Checkbox, Stack, IconButton, Tooltip,
  AlertDialog, AlertDialogBody, AlertDialogFooter, AlertDialogHeader,
  AlertDialogContent, AlertDialogOverlay
} from '@chakra-ui/react';
import { AddIcon, EditIcon, DeleteIcon, ViewIcon, ChevronLeftIcon, ChevronRightIcon } from '@chakra-ui/icons';
import { getTenants, createTenant, updateTenant, deleteTenant, Tenant, CreateTenantRequest, UpdateTenantRequest } from '../../services/sysadminService';

export function TenantManagement() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [modalMode, setModalMode] = useState<'create' | 'edit' | 'view'>('create');
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  
  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('administration');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  
  // Form state
  const [formData, setFormData] = useState({
    administration: '',
    display_name: '',
    contact_email: '',
    phone_number: '',
    street_address: '',
    city: '',
    zipcode: '',
    country: '',
    status: 'active' as 'active' | 'suspended' | 'inactive',
    enabled_modules: [] as string[]
  });
  
  const toast = useToast();
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  useEffect(() => {
    loadTenants();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, perPage, searchTerm, statusFilter, sortBy, sortOrder]);

  const loadTenants = async () => {
    setLoading(true);
    try {
      const data = await getTenants({
        page: currentPage,
        per_page: perPage,
        search: searchTerm || undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        sort_by: sortBy,
        sort_order: sortOrder
      });
      
      setTenants(data.tenants);
      setTotalPages(data.total_pages);
      setTotalCount(data.total);
    } catch (error) {
      toast({
        title: 'Error loading tenants',
        description: error instanceof Error ? error.message : 'Unknown error',
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
      enabled_modules: []
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
      administration: tenant.administration,
      display_name: tenant.display_name,
      contact_email: tenant.contact_email,
      phone_number: tenant.phone_number || '',
      street_address: tenant.street_address || '',
      city: tenant.city || '',
      zipcode: tenant.zipcode || '',
      country: tenant.country || '',
      status: tenant.status,
      enabled_modules: tenant.enabled_modules
    });
    setModalMode('edit');
    onModalOpen();
  };

  const openViewModal = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    setFormData({
      administration: tenant.administration,
      display_name: tenant.display_name,
      contact_email: tenant.contact_email,
      phone_number: tenant.phone_number || '',
      street_address: tenant.street_address || '',
      city: tenant.city || '',
      zipcode: tenant.zipcode || '',
      country: tenant.country || '',
      status: tenant.status,
      enabled_modules: tenant.enabled_modules
    });
    setModalMode('view');
    onModalOpen();
  };

  const openDeleteDialog = (tenant: Tenant) => {
    setSelectedTenant(tenant);
    onDeleteOpen();
  };

  const handleCreateTenant = async () => {
    if (!formData.administration || !formData.display_name || !formData.contact_email) {
      toast({
        title: 'Validation Error',
        description: 'Administration, display name, and contact email are required',
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
        enabled_modules: formData.enabled_modules
      };

      await createTenant(request);

      toast({
        title: 'Tenant created',
        description: `Tenant "${formData.display_name}" created successfully`,
        status: 'success',
        duration: 3000,
      });

      onModalClose();
      resetForm();
      loadTenants();
    } catch (error) {
      toast({
        title: 'Error creating tenant',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateTenant = async () => {
    if (!selectedTenant) re </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}

export default TenantManagement;
>
                  <br />
                  <Text color="orange.400">This tenant has {selectedTenant.user_count} user(s). Deletion may fail if users are still active.</Text>
                </>
              )}
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>Cancel</Button>
              <Button colorScheme="red" onClick={handleDeleteTenant} ml={3} isLoading={actionLoading}>
                Delete
              </Button>
           Size="lg" fontWeight="bold" color="orange.400">
              Delete Tenant
            </AlertDialogHeader>
            <AlertDialogBody>
              Are you sure you want to delete tenant <Text as="span" fontWeight="bold" color="orange.400">"{selectedTenant?.display_name}"</Text>?
              <br /><br />
              <Text color="red.400">Warning: This action cannot be undone. The tenant will be marked as deleted.</Text>
              {selectedTenant && selectedTenant.user_count > 0 && (
                <                  isLoading={actionLoading}
                >
                  {modalMode === 'create' ? 'Create' : 'Update'}
                </Button>
              </>
            )}
          </ModalFooter>
        </ModalContent>
      </Modal>

      {/* Delete Confirmation Dialog */}
      <AlertDialog isOpen={isDeleteOpen} leastDestructiveRef={cancelRef} onClose={onDeleteClose}>
        <AlertDialogOverlay>
          <AlertDialogContent bg="gray.800" color="white">
            <AlertDialogHeader fontt="ghost" mr={3} onClick={onModalClose}>Close</Button>
                <Button colorScheme="orange" onClick={() => { onModalClose(); openEditModal(selectedTenant!); }}>
                  Edit
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" mr={3} onClick={onModalClose}>Cancel</Button>
                <Button
                  colorScheme="orange"
                  onClick={modalMode === 'create' ? handleCreateTenant : handleUpdateTenant}
  {selectedTenant.updated_at && (
                      <HStack>
                        <Text color="gray.500">Updated:</Text>
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
                <Button variannt.status}
                      </Badge>
                    </HStack>
                    <HStack>
                      <Text color="gray.500">Users:</Text>
                      <Text color="gray.300">{selectedTenant.user_count}</Text>
                    </HStack>
                    <HStack>
                      <Text color="gray.500">Created:</Text>
                      <Text color="gray.300">{new Date(selectedTenant.created_at).toLocaleString()}</Text>
                    </HStack>
                         </Text>
                </FormControl>
              )}

              {modalMode === 'view' && selectedTenant && (
                <Box>
                  <Text color="gray.400" fontSize="sm" mb={2}>Additional Information:</Text>
                  <VStack align="stretch" spacing={2} fontSize="sm">
                    <HStack>
                      <Text color="gray.500">Status:</Text>
                      <Badge colorScheme={getStatusColor(selectedTenant.status)}>
                        {selectedTena   </Checkbox>
                    <Checkbox
                      isChecked={formData.enabled_modules.includes('STR')}
                      onChange={() => toggleModule('STR')}
                      colorScheme="orange"
                    >
                      <Text color="gray.300">STR - Short-Term Rental</Text>
                    </Checkbox>
                  </Stack>
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    TENADMIN module is added automatically
           ntrol>

              {modalMode === 'create' && (
                <FormControl>
                  <FormLabel color="gray.300">Enabled Modules</FormLabel>
                  <Stack spacing={2}>
                    <Checkbox
                      isChecked={formData.enabled_modules.includes('FIN')}
                      onChange={() => toggleModule('FIN')}
                      colorScheme="orange"
                    >
                      <Text color="gray.300">FIN - Financial Management</Text>
                 
              </HStack>

              <FormControl isDisabled={modalMode === 'view'}>
                <FormLabel color="gray.300">Country</FormLabel>
                <Input
                  placeholder="Netherlands"
                  value={formData.country}
                  onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                  bg="gray.700"
                  borderColor="gray.600"
                  isReadOnly={modalMode === 'view'}
                />
              </FormCo               <FormControl isDisabled={modalMode === 'view'}>
                  <FormLabel color="gray.300">Zipcode</FormLabel>
                  <Input
                    placeholder="1012 AB"
                    value={formData.zipcode}
                    onChange={(e) => setFormData({ ...formData, zipcode: e.target.value })}
                    bg="gray.700"
                    borderColor="gray.600"
                    isReadOnly={modalMode === 'view'}
                  />
                </FormControl>
                <FormControl isDisabled={modalMode === 'view'}>
                  <FormLabel color="gray.300">City</FormLabel>
                  <Input
                    placeholder="Amsterdam"
                    value={formData.city}
                    onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                    bg="gray.700"
                    borderColor="gray.600"
                    isReadOnly={modalMode === 'view'}
                  />
                </FormControl>

 abled={modalMode === 'view'}>
                <FormLabel color="gray.300">Street Address</FormLabel>
                <Input
                  placeholder="123 Main Street"
                  value={formData.street_address}
                  onChange={(e) => setFormData({ ...formData, street_address: e.target.value })}
                  bg="gray.700"
                  borderColor="gray.600"
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              <HStack>{modalMode === 'view'}>
                <FormLabel color="gray.300">Phone Number</FormLabel>
                <Input
                  placeholder="+31 6 12345678"
                  value={formData.phone_number}
                  onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                  bg="gray.700"
                  borderColor="gray.600"
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              <FormControl isDisormData.status}
                    onChange={(e) => setFormData({ ...formData, status: e.target.value as any })}
                    bg="gray.700"
                    borderColor="gray.600"
                  >
                    <option value="active">Active</option>
                    <option value="suspended">Suspended</option>
                    <option value="inactive">Inactive</option>
                  </Select>
                </FormControl>
              )}

              <FormControl isDisabled=com"
                  value={formData.contact_email}
                  onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })}
                  bg="gray.700"
                  borderColor="gray.600"
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              {modalMode === 'edit' && (
                <FormControl>
                  <FormLabel color="gray.300">Status</FormLabel>
                  <Select
                    value={flay_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  bg="gray.700"
                  borderColor="gray.600"
                  isReadOnly={modalMode === 'view'}
                />
              </FormControl>

              <FormControl isRequired isDisabled={modalMode === 'view'}>
                <FormLabel color="gray.300">Contact Email</FormLabel>
                <Input
                  type="email"
                  placeholder="admin@example. />
                {modalMode === 'create' && (
                  <Text fontSize="xs" color="gray.500" mt={1}>
                    Lowercase, no spaces. This cannot be changed later.
                  </Text>
                )}
              </FormControl>

              <FormControl isRequired isDisabled={modalMode === 'view'}>
                <FormLabel color="gray.300">Display Name</FormLabel>
                <Input
                  placeholder="e.g., Goodwin Solutions"
                  value={formData.dispalMode === 'view' || modalMode === 'edit'}>
                <FormLabel color="gray.300">Administration ID</FormLabel>
                <Input
                  placeholder="e.g., goodwinsolutions"
                  value={formData.administration}
                  onChange={(e) => setFormData({ ...formData, administration: e.target.value.toLowerCase() })}
                  bg="gray.700"
                  borderColor="gray.600"
                  isReadOnly={modalMode === 'edit' || modalMode === 'view'}
               ent bg="gray.800" color="white">
          <ModalHeader color="orange.400">
            {modalMode === 'create' && 'Create New Tenant'}
            {modalMode === 'edit' && `Edit Tenant: ${selectedTenant?.display_name}`}
            {modalMode === 'view' && `Tenant Details: ${selectedTenant?.display_name}`}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl isRequired={modalMode === 'create'} isDisabled={modcurrentPage === 1}
            />
            <IconButton
              aria-label="Next page"
              icon={<ChevronRightIcon />}
              size="sm"
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              isDisabled={currentPage === totalPages}
            />
          </HStack>
        </HStack>
      </VStack>

      {/* Create/Edit/View Modal */}
      <Modal isOpen={isModalOpen} onClose={onModalClose} size="xl">
        <ModalOverlay />
        <ModalContalue="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
            </Select>
          </HStack>
          <HStack>
            <Text color="gray.400" fontSize="sm">
              Page {currentPage} of {totalPages}
            </Text>
            <IconButton
              aria-label="Previous page"
              icon={<ChevronLeftIcon />}
              size="sm"
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              isDisabled={Tbody>
          </Table>
        </Box>

        {/* Pagination */}
        <HStack justify="space-between">
          <HStack>
            <Text color="gray.400" fontSize="sm">Rows per page:</Text>
            <Select
              value={perPage}
              onChange={(e) => setPerPage(Number(e.target.value))}
              bg="gray.700"
              borderColor="gray.600"
              size="sm"
              maxW="80px"
            >
              <option value="5">5</option>
              <option v                  aria-label="Delete"
                          icon={<DeleteIcon />}
                          size="sm"
                          variant="ghost"
                          colorScheme="red"
                          onClick={() => openDeleteDialog(tenant)}
                          isDisabled={tenant.administration === 'myAdmin'}
                        />
                      </Tooltip>
                    </HStack>
                  </Td>
                </Tr>
              ))}
            </>
                      <Tooltip label="Edit">
                        <IconButton
                          aria-label="Edit"
                          icon={<EditIcon />}
                          size="sm"
                          variant="ghost"
                          colorScheme="orange"
                          onClick={() => openEditModal(tenant)}
                        />
                      </Tooltip>
                      <Tooltip label="Delete">
                        <IconButton
        DateString()}
                  </Td>
                  <Td>
                    <HStack spacing={1}>
                      <Tooltip label="View">
                        <IconButton
                          aria-label="View"
                          icon={<ViewIcon />}
                          size="sm"
                          variant="ghost"
                          colorScheme="blue"
                          onClick={() => openViewModal(tenant)}
                        />
                      </Tooltip            <HStack spacing={1}>
                      {tenant.enabled_modules.map(module => (
                        <Badge key={module} colorScheme={getModuleBadgeColor(module)} fontSize="xs">
                          {module}
                        </Badge>
                      ))}
                    </HStack>
                  </Td>
                  <Td color="gray.400">{tenant.user_count}</Td>
                  <Td color="gray.400" fontSize="sm">
                    {new Date(tenant.created_at).toLocale            </Tr>
            </Thead>
            <Tbody>
              {tenants.map((tenant) => (
                <Tr key={tenant.administration}>
                  <Td color="orange.400" fontWeight="bold">{tenant.administration}</Td>
                  <Td color="gray.300">{tenant.display_name}</Td>
                  <Td>
                    <Badge colorScheme={getStatusColor(tenant.status)}>
                      {tenant.status}
                    </Badge>
                  </Td>
                  <Td>
        or="pointer" onClick={() => handleSort('status')}>
                  Status {sortBy === 'status' && (sortOrder === 'asc' ? '↑' : '↓')}
                </Th>
                <Th color="gray.400">Modules</Th>
                <Th color="gray.400">Users</Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('created_at')}>
                  Created {sortBy === 'created_at' && (sortOrder === 'asc' ? '↑' : '↓')}
                </Th>
                <Th color="gray.400">Actions</Th>
         <Thead>
              <Tr>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('administration')}>
                  Administration {sortBy === 'administration' && (sortOrder === 'asc' ? '↑' : '↓')}
                </Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('display_name')}>
                  Display Name {sortBy === 'display_name' && (sortOrder === 'asc' ? '↑' : '↓')}
                </Th>
                <Th color="gray.400" curs     </HStack>
          <HStack>
            <Text color="gray.400" fontSize="sm">
              Total: <Text as="span" color="orange.400" fontWeight="bold">{totalCount}</Text>
            </Text>
            <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={openCreateModal}>
              Create Tenant
            </Button>
          </HStack>
        </HStack>

        {/* Table */}
        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple">
     ect
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              bg="gray.700"
              borderColor="gray.600"
              maxW="150px"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="inactive">Inactive</option>
              <option value="deleted">Deleted</option>
            </Select>
          </VStack>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        {/* Header & Filters */}
        <HStack justify="space-between" wrap="wrap" spacing={4}>
          <HStack spacing={4}>
            <Input
              placeholder="Search tenants..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              bg="gray.700"
              borderColor="gray.600"
              maxW="300px"
            />
            <Sel  };

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
          <Text color="gray.400">Loading tenants...</Text>
    toggleModule = (module: string) => {
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
t(null);
      loadTenants();
    } catch (error) {
      toast({
        title: 'Error deleting tenant',
        description: error instanceof Error ? error.message : 'Unknown error',
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

  consttatus: 'error',
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
        title: 'Tenant deleted',
        description: `Tenant "${selectedTenant.display_name}" has been deleted`,
        status: 'success',
        duration: 3000,
      });

      onDeleteClose();
      setSelectedTenanndefined
      };

      await updateTenant(selectedTenant.administration, request);

      toast({
        title: 'Tenant updated',
        description: `Tenant "${formData.display_name}" updated successfully`,
        status: 'success',
        duration: 3000,
      });

      onModalClose();
      setSelectedTenant(null);
      loadTenants();
    } catch (error) {
      toast({
        title: 'Error updating tenant',
        description: error instanceof Error ? error.message : 'Unknown error',
        sturn;

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
        country: formData.country.trim() || u