/**
 * Tenant Details Component - Redesigned
 * 
 * Grid layout: 2 columns wide, 1 column small screen.
 * Sections: General Info, Contact, Address, Bank Details, Metadata.
 * Matches BankingProcessor form style.
 */

import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, FormControl, FormLabel, Input,
  Button, useToast, Spinner, Text, SimpleGrid, Divider,
} from '@chakra-ui/react';
import { getTenantDetails, updateTenantDetails, TenantDetails as TenantDetailsType } from '../../services/tenantAdminApi';

interface TenantDetailsProps {
  tenant: string;
}

export function TenantDetails({ tenant }: TenantDetailsProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [details, setDetails] = useState<TenantDetailsType | null>(null);
  const [formData, setFormData] = useState<Partial<TenantDetailsType>>({});
  const toast = useToast();

  useEffect(() => {
    loadDetails();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  const loadDetails = async () => {
    setLoading(true);
    try {
      const response = await getTenantDetails();
      setDetails(response.tenant);
      setFormData(response.tenant);
    } catch (error) {
      toast({ title: 'Error loading tenant details', description: error instanceof Error ? error.message : 'Unknown error', status: 'error', duration: 5000 });
    } finally { setLoading(false); }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updateData = {
        display_name: formData.display_name,
        contact_email: formData.contact_email,
        phone_number: formData.phone_number,
        street: formData.street,
        city: formData.city,
        zipcode: formData.zipcode,
        country: formData.country,
        bank_account_number: formData.bank_account_number,
        bank_name: formData.bank_name,
      };
      const response = await updateTenantDetails(updateData);
      setDetails(response.tenant);
      setFormData(response.tenant);
      toast({ title: 'Tenant details updated', status: 'success', duration: 3000 });
    } catch (error) {
      toast({ title: 'Error updating tenant details', description: error instanceof Error ? error.message : 'Unknown error', status: 'error', duration: 5000 });
    } finally { setSaving(false); }
  };

  const handleChange = (field: keyof TenantDetailsType, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const hasChanges = () => details ? JSON.stringify(formData) !== JSON.stringify(details) : false;

  const inputProps = {
    bg: 'gray.700', color: 'gray.100', borderColor: 'gray.600',
    _hover: { borderColor: 'gray.500' },
    _focus: { borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' },
    size: 'sm' as const,
  };

  const readOnlyProps = { ...inputProps, color: 'gray.400', bg: 'gray.700', isReadOnly: true };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minH="200px">
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={5} align="stretch">
      {/* Save button */}
      <HStack justify="flex-end">
        <Button colorScheme="orange" onClick={handleSave} isLoading={saving} isDisabled={!hasChanges()} size="sm">
          Save Changes
        </Button>
      </HStack>

      {/* Company Info */}
      <Box>
        <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>Company Info</Text>
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Administration Code</FormLabel>
            <Input value={details?.administration || ''} {...readOnlyProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Display Name</FormLabel>
            <Input value={formData.display_name || ''} onChange={e => handleChange('display_name', e.target.value)} placeholder="Company Name" {...inputProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Status</FormLabel>
            <Input value={details?.status || ''} {...readOnlyProps} />
          </FormControl>
        </SimpleGrid>
      </Box>

      <Divider borderColor="gray.700" />

      {/* Contact */}
      <Box>
        <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>Contact</Text>
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Email</FormLabel>
            <Input type="email" value={formData.contact_email || ''} onChange={e => handleChange('contact_email', e.target.value)} placeholder="contact@example.com" {...inputProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Phone</FormLabel>
            <Input type="tel" value={formData.phone_number || ''} onChange={e => handleChange('phone_number', e.target.value)} placeholder="+31 6 12345678" {...inputProps} />
          </FormControl>
        </SimpleGrid>
      </Box>

      <Divider borderColor="gray.700" />

      {/* Address */}
      <Box>
        <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>Address</Text>
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
          <FormControl gridColumn={{ md: 'span 2' }}>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Street</FormLabel>
            <Input value={formData.street || ''} onChange={e => handleChange('street', e.target.value)} placeholder="Main Street 123" {...inputProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>City</FormLabel>
            <Input value={formData.city || ''} onChange={e => handleChange('city', e.target.value)} placeholder="Amsterdam" {...inputProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Zipcode</FormLabel>
            <Input value={formData.zipcode || ''} onChange={e => handleChange('zipcode', e.target.value)} placeholder="1012 AB" {...inputProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Country</FormLabel>
            <Input value={formData.country || ''} onChange={e => handleChange('country', e.target.value)} placeholder="Netherlands" {...inputProps} />
          </FormControl>
        </SimpleGrid>
      </Box>

      <Divider borderColor="gray.700" />

      {/* Bank Details */}
      <Box>
        <Text color="gray.400" fontSize="sm" fontWeight="bold" mb={2}>Bank Details</Text>
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Account Number</FormLabel>
            <Input value={formData.bank_account_number || ''} onChange={e => handleChange('bank_account_number', e.target.value)} placeholder="NL12ABCD0123456789" {...inputProps} />
          </FormControl>
          <FormControl>
            <FormLabel color="gray.300" fontSize="sm" mb={0}>Bank Name</FormLabel>
            <Input value={formData.bank_name || ''} onChange={e => handleChange('bank_name', e.target.value)} placeholder="ING Bank" {...inputProps} />
          </FormControl>
        </SimpleGrid>
      </Box>

      {/* Metadata */}
      {details && (
        <>
          <Divider borderColor="gray.700" />
          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
            <Box>
              <Text color="gray.500" fontSize="xs">Created</Text>
              <Text color="gray.300" fontSize="sm">{details.created_at ? new Date(details.created_at).toLocaleString() : 'N/A'}</Text>
            </Box>
            <Box>
              <Text color="gray.500" fontSize="xs">Updated</Text>
              <Text color="gray.300" fontSize="sm">{details.updated_at ? new Date(details.updated_at).toLocaleString() : 'N/A'}</Text>
            </Box>
          </SimpleGrid>
        </>
      )}
    </VStack>
  );
}

export default TenantDetails;
