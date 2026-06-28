/**
 * TenantManagement Component
 *
 * Orchestrates tenant CRUD, reprovisioning, and invitation operations.
 * Delegates rendering to TenantTable and TenantProvisionModal sub-components.
 */

import React, { useState, useEffect } from 'react';
import { Box, VStack, HStack, Button, Text, Spinner, useToast, useDisclosure } from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import {
  getTenants, createTenant, updateTenant, deleteTenant,
  reprovisionTenant, resendInvitation,
  Tenant, CreateTenantRequest, UpdateTenantRequest,
} from '../../services/sysadminService';
import { useColumnFilters } from '../../hooks/useColumnFilters';
import { TenantTable } from './TenantTable';
import { TenantProvisionModal, TenantDeleteDialog, TenantFormData } from './TenantProvisionModal';
import { ModuleManagement } from './ModuleManagement';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

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

  const [formData, setFormData] = useState<TenantFormData>({
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
    locale: 'nl',
  });

  const toast = useToast();
  const { t } = useTypedTranslation('admin');
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const { isOpen: isModuleOpen, onOpen: onModuleOpen, onClose: onModuleClose } = useDisclosure();
  const cancelRef = React.useRef<HTMLButtonElement>(null);

  const { filters, setFilter, filteredData: displayTenants } = useColumnFilters<Tenant>(tenants, {
    administration: '',
    display_name: '',
    status: '',
    enabled_modules: '',
    user_count: '',
    created_at: '',
  });

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  const loadTenants = async () => {
    setLoading(true);
    try {
      const data = await getTenants({ page: currentPage, per_page: perPage, sort_by: sortBy, sort_order: sortOrder });
      setTenants(data.tenants);
      setTotalPages(data.total_pages);
      setTotalCount(data.total);
    } catch (error) {
      toast({ title: t('tenantManagement.messages.errorLoading'), description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTenants();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, perPage, sortBy, sortOrder]);

  // ---------------------------------------------------------------------------
  // Modal openers
  // ---------------------------------------------------------------------------

  const resetForm = () => {
    setFormData({ administration: '', display_name: '', contact_email: '', phone_number: '', street_address: '', city: '', zipcode: '', country: '', status: 'active', enabled_modules: [], locale: 'nl' });
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
      locale: 'nl',
    });
    setModalMode('edit');
    onModalOpen();
  };

  const openDeleteDialog = () => {
    onDeleteOpen();
  };

  // ---------------------------------------------------------------------------
  // Sort handler
  // ---------------------------------------------------------------------------

  const handleSort = (field: string) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
  };

  // ---------------------------------------------------------------------------
  // CRUD handlers
  // ---------------------------------------------------------------------------

  const handleCreateTenant = async () => {
    if (!formData.administration || !formData.display_name || !formData.contact_email) {
      toast({ title: t('tenantManagement.messages.validationError'), description: t('tenantManagement.messages.requiredFields'), status: 'warning', duration: 3000 });
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
        locale: formData.locale,
        initial_admin_email: formData.contact_email.trim() || undefined,
      };
      await createTenant(request);
      toast({ title: t('tenantManagement.messages.tenantCreated'), description: t('tenantManagement.messages.tenantCreatedSuccess', { name: formData.display_name }), status: 'success', duration: 3000 });
      onModalClose();
      resetForm();
      loadTenants();
    } catch (error) {
      toast({ title: t('tenantManagement.messages.errorCreating'), description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateTenant = async () => {
    if (!selectedTenant) return;
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
        country: formData.country.trim() || undefined,
      };
      await updateTenant(selectedTenant.administration, request);
      toast({ title: t('tenantManagement.messages.tenantUpdated'), description: t('tenantManagement.messages.tenantUpdatedSuccess', { name: formData.display_name }), status: 'success', duration: 3000 });
      onModalClose();
      setSelectedTenant(null);
      loadTenants();
    } catch (error) {
      toast({ title: t('tenantManagement.messages.errorUpdating'), description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteTenant = async () => {
    if (!selectedTenant) return;
    setActionLoading(true);
    try {
      await deleteTenant(selectedTenant.administration);
      toast({ title: t('tenantManagement.messages.tenantDeleted'), description: t('tenantManagement.messages.tenantDeletedSuccess', { name: selectedTenant.display_name }), status: 'success', duration: 3000 });
      onDeleteClose();
      setSelectedTenant(null);
      loadTenants();
    } catch (error) {
      toast({ title: t('tenantManagement.messages.errorDeleting'), description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleReprovision = async () => {
    if (!selectedTenant) return;
    setActionLoading(true);
    try {
      const result = await reprovisionTenant(selectedTenant.administration, { locale: formData.locale });
      const prov = result.provisioning as { chart?: string; chart_rows?: number; modules?: Array<{ name: string; status: string }> };
      const chartStatus = prov?.chart || 'unknown';
      const chartRows = prov?.chart_rows || 0;
      const modulesCreated = (prov?.modules || []).filter((m: { status: string }) => m.status === 'created').length;
      toast({ title: t('tenantManagement.messages.reprovisionComplete'), description: t('tenantManagement.messages.reprovisionDetails', { chart: chartStatus, rows: chartRows, modules: modulesCreated }), status: chartStatus === 'failed' ? 'warning' : 'success', duration: 8000, isClosable: true });
      if (result.warnings && result.warnings.length > 0) {
        toast({ title: t('tenantManagement.messages.reprovisionWarnings'), description: result.warnings.join('; '), status: 'warning', duration: 10000, isClosable: true });
      }
      loadTenants();
    } catch (error) {
      toast({ title: t('tenantManagement.messages.errorReprovisioning'), description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  const handleResendInvitation = async () => {
    if (!selectedTenant || !formData.contact_email) return;
    setActionLoading(true);
    try {
      await resendInvitation(selectedTenant.administration, formData.contact_email);
      toast({ title: t('tenantManagement.messages.invitationResent'), description: t('tenantManagement.messages.invitationResentSuccess', { email: formData.contact_email }), status: 'success', duration: 5000, isClosable: true });
    } catch (error) {
      toast({ title: t('tenantManagement.messages.errorResendingInvitation'), description: error instanceof Error ? error.message : t('tenantManagement.messages.unknownError'), status: 'error', duration: 5000 });
    } finally {
      setActionLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

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

        <TenantTable
          tenants={displayTenants}
          filters={filters}
          setFilter={setFilter}
          sortBy={sortBy}
          sortOrder={sortOrder}
          onSort={handleSort}
          onRowClick={openEditModal}
          currentPage={currentPage}
          totalPages={totalPages}
          perPage={perPage}
          onPageChange={setCurrentPage}
          onPerPageChange={setPerPage}
          t={t}
        />
      </VStack>

      <TenantProvisionModal
        isOpen={isModalOpen}
        onClose={onModalClose}
        modalMode={modalMode}
        selectedTenant={selectedTenant}
        formData={formData}
        setFormData={setFormData}
        actionLoading={actionLoading}
        onCreate={handleCreateTenant}
        onUpdate={handleUpdateTenant}
        onReprovision={handleReprovision}
        onResendInvitation={handleResendInvitation}
        onOpenDelete={openDeleteDialog}
        onOpenEdit={openEditModal}
        onOpenModules={() => { onModalClose(); onModuleOpen(); }}
        t={t}
      />

      <TenantDeleteDialog
        isOpen={isDeleteOpen}
        onClose={onDeleteClose}
        selectedTenant={selectedTenant}
        actionLoading={actionLoading}
        onDelete={handleDeleteTenant}
        cancelRef={cancelRef}
        t={t}
      />

      {selectedTenant && (
        <ModuleManagement
          administration={selectedTenant.administration}
          isOpen={isModuleOpen}
          onClose={() => { onModuleClose(); loadTenants(); }}
        />
      )}
    </Box>
  );
}

export default TenantManagement;
