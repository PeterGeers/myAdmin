import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Input, Select,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure, FormControl, FormLabel
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';
import { getPendingSignups, provisionSignup, PendingSignup } from '../../services/sysadminService';

export function ProvisioningPanel() {
  const [signups, setSignups] = useState<PendingSignup[]>([]);
  const [loading, setLoading] = useState(true);
  const [provisioning, setProvisioning] = useState(false);
  const [selected, setSelected] = useState<PendingSignup | null>(null);
  const [adminName, setAdminName] = useState('');
  const [locale, setLocale] = useState<'nl' | 'en'>('nl');
  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();
  const { t } = useTypedTranslation('admin');

  useEffect(() => { loadSignups(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSignups = async () => {
    setLoading(true);
    try {
      const data = await getPendingSignups();
      setSignups(data.signups || []);
    } catch (error) {
      toast({
        title: t('provisioning.errorLoading'),
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error', duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const openProvisionModal = (signup: PendingSignup) => {
    setSelected(signup);
    const company = signup.company_name || signup.email.split('@')[0];
    const words = company.replace(/[^a-zA-Z0-9\s]/g, '').split(/\s+/);
    setAdminName(words.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(''));
    setLocale((signup.locale as 'nl' | 'en') || 'nl');
    onOpen();
  };

  const handleProvision = async () => {
    if (!selected) return;
    setProvisioning(true);
    try {
      const result = await provisionSignup({
        email: selected.email,
        administration_name: adminName.trim() || undefined,
        locale,
      });

      toast({
        title: t('provisioning.success'),
        description: t('provisioning.successDetail', {
          name: result.administration,
          email: selected.email
        }),
        status: 'success', duration: 8000, isClosable: true,
      });

      onClose();
      loadSignups();
    } catch (error) {
      toast({
        title: t('provisioning.errorProvisioning'),
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error', duration: 5000,
      });
    } finally {
      setProvisioning(false);
    }
  };

  if (loading) {
    return (
      <Box textAlign="center" py={10}>
        <Spinner size="lg" color="orange.400" />
        <Text color="gray.400" mt={2}>{t('provisioning.loading')}</Text>
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      <HStack justify="space-between">
        <Text color="white" fontSize="lg">{t('provisioning.title')}</Text>
        <HStack>
          <Badge colorScheme="green" fontSize="sm" px={2} py={1}>
            {signups.length} {t('provisioning.pending')}
          </Badge>
          <Button size="sm" colorScheme="orange" variant="outline" onClick={loadSignups}>
            {t('provisioning.refresh')}
          </Button>
        </HStack>
      </HStack>

      {signups.length === 0 ? (
        <Box bg="gray.800" p={6} borderRadius="md" textAlign="center">
          <Text color="gray.400">{t('provisioning.noPending')}</Text>
        </Box>
      ) : (
        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th color="gray.400">{t('provisioning.table.name')}</Th>
                <Th color="gray.400">{t('provisioning.table.email')}</Th>
                <Th color="gray.400">{t('provisioning.table.company')}</Th>
                <Th color="gray.400">{t('provisioning.table.locale')}</Th>
                <Th color="gray.400">{t('provisioning.table.verifiedAt')}</Th>
                <Th color="gray.400">{t('provisioning.table.action')}</Th>
              </Tr>
            </Thead>
            <Tbody>
              {signups.map(signup => (
                <Tr key={signup.id}>
                  <Td color="white">{signup.first_name} {signup.last_name}</Td>
                  <Td color="gray.300">{signup.email}</Td>
                  <Td color="gray.300">{signup.company_name || '—'}</Td>
                  <Td><Badge colorScheme="blue">{signup.locale}</Badge></Td>
                  <Td color="gray.400" fontSize="xs">
                    {signup.verified_at ? new Date(signup.verified_at).toLocaleDateString() : '—'}
                  </Td>
                  <Td>
                    <Button size="xs" colorScheme="green" onClick={() => openProvisionModal(signup)}>
                      {t('provisioning.provisionBtn')}
                    </Button>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}

      <Modal isOpen={isOpen} onClose={onClose} size="md">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader color="orange.400">{t('provisioning.modal.title')}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {selected && (
              <VStack spacing={4} align="stretch">
                <Box>
                  <Text color="gray.400" fontSize="sm">{t('provisioning.modal.signup')}</Text>
                  <Text>{selected.first_name} {selected.last_name} ({selected.email})</Text>
                  {selected.company_name && <Text color="gray.300">{selected.company_name}</Text>}
                </Box>
                <FormControl>
                  <FormLabel color="gray.300">{t('provisioning.modal.adminName')}</FormLabel>
                  <Input
                    value={adminName}
                    onChange={e => setAdminName(e.target.value)}
                    bg="gray.600" color="white" borderColor="gray.500"
                    placeholder="CompanyName"
                  />
                  <Text fontSize="xs" color="gray.500" mt={1}>{t('provisioning.modal.adminNameHint')}</Text>
                </FormControl>
                <FormControl>
                  <FormLabel color="gray.300">{t('provisioning.modal.locale')}</FormLabel>
                  <Select
                    value={locale}
                    onChange={e => setLocale(e.target.value as 'nl' | 'en')}
                    bg="gray.600" color="white" borderColor="gray.500"
                  >
                    <option value="nl" style={{ background: '#2D3748' }}>Nederlands</option>
                    <option value="en" style={{ background: '#2D3748' }}>English</option>
                  </Select>
                </FormControl>
                <Box bg="gray.700" p={3} borderRadius="md">
                  <Text fontSize="sm" color="gray.300">{t('provisioning.modal.willCreate')}</Text>
                  <Text fontSize="xs" color="gray.400" mt={1}>
                    • {t('provisioning.modal.step1')}<br />
                    • {t('provisioning.modal.step2')}<br />
                    • {t('provisioning.modal.step3')}<br />
                    • {t('provisioning.modal.step4')}
                  </Text>
                </Box>
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose}>{t('provisioning.modal.cancel')}</Button>
            <Button
              colorScheme="green"
              onClick={handleProvision}
              isLoading={provisioning}
              isDisabled={!adminName.trim()}
            >
              {t('provisioning.modal.provision')}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </VStack>
  );
}

export default ProvisioningPanel;
