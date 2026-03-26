import React, { useState, useEffect } from 'react';
import {
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, Button, VStack, HStack, Text,
  Badge, Box, Table, Thead, Tbody, Tr, Th, Td, Spinner, Divider
} from '@chakra-ui/react';
import { getAsset, AssetDetail as AssetDetailType } from '../../services/assetService';

interface AssetDetailProps {
  isOpen: boolean;
  onClose: () => void;
  assetId: number | null;
  onEdit: () => void;
  onDispose: () => void;
}

export default function AssetDetail({ isOpen, onClose, assetId, onEdit, onDispose }: AssetDetailProps) {
  const [asset, setAsset] = useState<AssetDetailType | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !assetId) return;
    setLoading(true);
    getAsset(assetId)
      .then(res => setAsset(res.asset))
      .catch(() => setAsset(null))
      .finally(() => setLoading(false));
  }, [isOpen, assetId]);

  const fmt = (val: number) =>
    new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(val);

  const typeBadge = (type: string) => {
    const colors: Record<string, string> = {
      purchase: 'blue', depreciation: 'orange', disposal: 'red'
    };
    return <Badge colorScheme={colors[type] || 'gray'} fontSize="xs">{type}</Badge>;
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader color="orange.400">
          {asset?.description || 'Asset Detail'}
        </ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          {loading ? (
            <Box textAlign="center" py={6}><Spinner color="orange.400" /></Box>
          ) : !asset ? (
            <Text color="gray.400">Asset not found</Text>
          ) : (
            <VStack spacing={4} align="stretch">
              {/* Metadata */}
              <Box bg="gray.700" p={4} borderRadius="md">
                <HStack justify="space-between" mb={2}>
                  <Text fontWeight="bold" fontSize="lg">{asset.description}</Text>
                  <Badge colorScheme={asset.status === 'active' ? 'green' : 'red'} fontSize="sm">
                    {asset.status}
                  </Badge>
                </HStack>
                <HStack spacing={6} wrap="wrap" fontSize="sm" color="gray.300">
                  <Text>Category: {asset.category || '—'}</Text>
                  <Text>Account: {asset.ledger_account}</Text>
                  <Text>Method: {asset.depreciation_method}</Text>
                  <Text>Frequency: {asset.depreciation_frequency}</Text>
                </HStack>
                <HStack spacing={6} wrap="wrap" fontSize="sm" color="gray.300" mt={1}>
                  <Text>Purchased: {asset.purchase_date}</Text>
                  <Text>Life: {asset.useful_life_years || '—'} years</Text>
                  {asset.reference_number && <Text>Ref: {asset.reference_number}</Text>}
                </HStack>
                {asset.notes && (
                  <Text fontSize="sm" color="gray.400" mt={2}>{asset.notes}</Text>
                )}
              </Box>

              {/* Book Value Summary */}
              <HStack spacing={4} justify="center">
                <Box textAlign="center" p={3} bg="gray.700" borderRadius="md" flex={1}>
                  <Text fontSize="xs" color="gray.400">Purchase</Text>
                  <Text fontSize="lg" fontWeight="bold">{fmt(asset.purchase_amount)}</Text>
                </Box>
                <Box textAlign="center" p={3} bg="gray.700" borderRadius="md" flex={1}>
                  <Text fontSize="xs" color="gray.400">Depreciation</Text>
                  <Text fontSize="lg" fontWeight="bold" color="orange.300">
                    -{fmt(asset.total_depreciation)}
                  </Text>
                </Box>
                <Box textAlign="center" p={3} bg="gray.700" borderRadius="md" flex={1}>
                  <Text fontSize="xs" color="gray.400">Book Value</Text>
                  <Text fontSize="lg" fontWeight="bold"
                    color={asset.book_value > 0 ? 'green.300' : 'gray.500'}>
                    {fmt(asset.book_value)}
                  </Text>
                </Box>
                <Box textAlign="center" p={3} bg="gray.700" borderRadius="md" flex={1}>
                  <Text fontSize="xs" color="gray.400">Residual</Text>
                  <Text fontSize="lg" fontWeight="bold" color="gray.300">
                    {fmt(asset.residual_value)}
                  </Text>
                </Box>
              </HStack>

              {/* Transaction History */}
              <Divider borderColor="gray.600" />
              <Text fontWeight="bold" color="gray.300">Transaction History</Text>
              {asset.transactions.length === 0 ? (
                <Text color="gray.500" fontSize="sm">No transactions linked</Text>
              ) : (
                <Box overflowX="auto">
                  <Table variant="simple" size="sm">
                    <Thead>
                      <Tr>
                        <Th color="gray.400">Type</Th>
                        <Th color="gray.400">Date</Th>
                        <Th color="gray.400">Description</Th>
                        <Th color="gray.400" isNumeric>Amount</Th>
                        <Th color="gray.400">Debet</Th>
                        <Th color="gray.400">Credit</Th>
                        <Th color="gray.400">Period</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {asset.transactions.map(tx => (
                        <Tr key={tx.ID}>
                          <Td>{typeBadge(tx.type)}</Td>
                          <Td color="gray.300">{tx.TransactionDate}</Td>
                          <Td color="white" maxW="200px" isTruncated title={tx.TransactionDescription}>
                            {tx.TransactionDescription}
                          </Td>
                          <Td color="gray.300" isNumeric>{fmt(tx.TransactionAmount)}</Td>
                          <Td color="gray.300">{tx.Debet}</Td>
                          <Td color="gray.300">{tx.Credit}</Td>
                          <Td color="gray.400" fontSize="xs">{tx.Ref2 || '—'}</Td>
                        </Tr>
                      ))}
                    </Tbody>
                  </Table>
                </Box>
              )}

              {/* Disposal info */}
              {asset.status === 'disposed' && asset.disposal_date && (
                <Box bg="red.900" p={3} borderRadius="md">
                  <Text fontSize="sm" color="red.200">
                    Disposed on {asset.disposal_date} for {fmt(asset.disposal_amount || 0)}
                  </Text>
                </Box>
              )}
            </VStack>
          )}
        </ModalBody>
        <ModalFooter>
          {asset && asset.status === 'active' && (
            <>
              <Button colorScheme="red" variant="outline" mr="auto" onClick={onDispose}>
                Dispose
              </Button>
              <Button colorScheme="orange" variant="outline" mr={3} onClick={onEdit}>
                Edit
              </Button>
            </>
          )}
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
