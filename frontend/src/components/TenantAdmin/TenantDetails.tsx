import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Heading, FormControl, FormLabel, Input,
  Button, useToast, Spinner, Text, Card, CardBody, CardHeader,
  Divider, SimpleGrid
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
      toast({
        title: 'Error loading tenant details',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Only send fields that can be updated
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
      
      toast({
        title: 'Success',
        description: 'Tenant details updated successfully',
        status: 'success',
        duration: 3000,
      });
    } catch (error) {
      toast({
        title: 'Error updating tenant details',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field: keyof TenantDetailsType, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const hasChanges = () => {
    if (!details) return false;
    return JSON.stringify(formData) !== JSON.stringify(details);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minH="400px">
        <VStack spacing={4}>
          <Spinner size="xl" color="orange.400" />
          <Text color="gray.400">Loading tenant details...</Text>
        </VStack>
      </Box>
    );
  }

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        {/* Header */}
        <HStack justify="space-between">
          <Heading size="lg" color="gray.100">Tenant Details</Heading>
          <Button
            colorScheme="orange"
            onClick={handleSave}
            isLoading={saving}
            isDisabled={!hasChanges()}
          >
            Save Changes
          </Button>
        </HStack>

        {/* General Information */}
        <Card bg="gray.800" borderColor="gray.700">
          <CardHeader>
            <Heading size="md" color="gray.100">General Information</Heading>
          </CardHeader>
          <Divider borderColor="gray.700" />
          <CardBody>
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <FormControl>
                <FormLabel color="gray.300">Administration Code</FormLabel>
                <Input
                  value={details?.administration || ''}
                  isReadOnly
                  bg="gray.700"
                  color="gray.400"
                  borderColor="gray.600"
                />
                <Text fontSize="xs" color="gray.500" mt={1}>
                  This field cannot be changed
                </Text>
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">Display Name</FormLabel>
                <Input
                  value={formData.display_name || ''}
                  onChange={(e) => handleChange('display_name', e.target.value)}
                  placeholder="Company Name"
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                />
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">Status</FormLabel>
                <Input
                  value={details?.status || ''}
                  isReadOnly
                  bg="gray.700"
                  color="gray.400"
                  borderColor="gray.600"
                />
                <Text fontSize="xs" color="gray.500" mt={1}>
                  Contact system administrator to change status
                </Text>
              </FormControl>
            </SimpleGrid>
          </CardBody>
        </Card>

        {/* Contact Information */}
        <Card bg="gray.800" borderColor="gray.700">
          <CardHeader>
            <Heading size="md" color="gray.100">Contact Information</Heading>
          </CardHeader>
          <Divider borderColor="gray.700" />
          <CardBody>
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <FormControl>
                <FormLabel color="gray.300">Contact Email</FormLabel>
                <Input
                  type="email"
                  value={formData.contact_email || ''}
                  onChange={(e) => handleChange('contact_email', e.target.value)}
                  placeholder="contact@example.com"
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                />
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">Phone Number</FormLabel>
                <Input
                  type="tel"
                  value={formData.phone_number || ''}
                  onChange={(e) => handleChange('phone_number', e.target.value)}
                  placeholder="+31 6 12345678"
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                />
              </FormControl>
            </SimpleGrid>
          </CardBody>
        </Card>

        {/* Address */}
        <Card bg="gray.800" borderColor="gray.700">
          <CardHeader>
            <Heading size="md" color="gray.100">Address</Heading>
          </CardHeader>
          <Divider borderColor="gray.700" />
          <CardBody>
            <VStack spacing={4} align="stretch">
              <FormControl>
                <FormLabel color="gray.300">Street</FormLabel>
                <Input
                  value={formData.street || ''}
                  onChange={(e) => handleChange('street', e.target.value)}
                  placeholder="Main Street 123"
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                />
              </FormControl>

              <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4}>
                <FormControl>
                  <FormLabel color="gray.300">City</FormLabel>
                  <Input
                    value={formData.city || ''}
                    onChange={(e) => handleChange('city', e.target.value)}
                    placeholder="Amsterdam"
                    bg="gray.700"
                    color="gray.100"
                    borderColor="gray.600"
                    _hover={{ borderColor: 'gray.500' }}
                    _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                  />
                </FormControl>

                <FormControl>
                  <FormLabel color="gray.300">Zipcode</FormLabel>
                  <Input
                    value={formData.zipcode || ''}
                    onChange={(e) => handleChange('zipcode', e.target.value)}
                    placeholder="1012 AB"
                    bg="gray.700"
                    color="gray.100"
                    borderColor="gray.600"
                    _hover={{ borderColor: 'gray.500' }}
                    _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                  />
                </FormControl>

                <FormControl>
                  <FormLabel color="gray.300">Country</FormLabel>
                  <Input
                    value={formData.country || ''}
                    onChange={(e) => handleChange('country', e.target.value)}
                    placeholder="Netherlands"
                    bg="gray.700"
                    color="gray.100"
                    borderColor="gray.600"
                    _hover={{ borderColor: 'gray.500' }}
                    _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                  />
                </FormControl>
              </SimpleGrid>
            </VStack>
          </CardBody>
        </Card>

        {/* Bank Details */}
        <Card bg="gray.800" borderColor="gray.700">
          <CardHeader>
            <Heading size="md" color="gray.100">Bank Details</Heading>
          </CardHeader>
          <Divider borderColor="gray.700" />
          <CardBody>
            <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
              <FormControl>
                <FormLabel color="gray.300">Bank Account Number</FormLabel>
                <Input
                  value={formData.bank_account_number || ''}
                  onChange={(e) => handleChange('bank_account_number', e.target.value)}
                  placeholder="NL12ABCD0123456789"
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                />
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">Bank Name</FormLabel>
                <Input
                  value={formData.bank_name || ''}
                  onChange={(e) => handleChange('bank_name', e.target.value)}
                  placeholder="ING Bank"
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  _hover={{ borderColor: 'gray.500' }}
                  _focus={{ borderColor: 'orange.400', boxShadow: '0 0 0 1px var(--chakra-colors-orange-400)' }}
                />
              </FormControl>
            </SimpleGrid>
          </CardBody>
        </Card>

        {/* Metadata */}
        {details && (
          <Card bg="gray.800" borderColor="gray.700">
            <CardHeader>
              <Heading size="md" color="gray.100">Metadata</Heading>
            </CardHeader>
            <Divider borderColor="gray.700" />
            <CardBody>
              <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                <Box>
                  <Text color="gray.400" fontSize="sm">Created At</Text>
                  <Text color="gray.200">{details.created_at ? new Date(details.created_at).toLocaleString() : 'N/A'}</Text>
                </Box>
                <Box>
                  <Text color="gray.400" fontSize="sm">Updated At</Text>
                  <Text color="gray.200">{details.updated_at ? new Date(details.updated_at).toLocaleString() : 'N/A'}</Text>
                </Box>
              </SimpleGrid>
            </CardBody>
          </Card>
        )}
      </VStack>
    </Box>
  );
}

export default TenantDetails;
