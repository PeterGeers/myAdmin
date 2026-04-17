/**
 * ZZP Products page — Chakra Table with row-click modal for CRUD.
 * Follows BankingProcessor pattern per ui-patterns.md.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, useDisclosure,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Product } from '../types/zzp';
import { getProducts } from '../services/productService';
import { ProductModal } from '../components/zzp/ProductModal';

const ZZPProducts: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Product | null>(null);

  const loadProducts = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await getProducts();
      if (resp.success) setProducts(resp.data);
    } catch {
      toast({ title: 'Error loading products', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadProducts(); }, [loadProducts]);

  const handleRowClick = (p: Product) => { setSelected(p); onOpen(); };
  const handleNew = () => { setSelected(null); onOpen(); };
  const handleSaved = () => { onClose(); loadProducts(); };

  return (
    <Box p={6}>
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <Text fontSize="xl" fontWeight="bold" color="white">{t('products.title')}</Text>
        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={handleNew}>
          {t('products.newProduct')}
        </Button>
      </Flex>

      {loading ? <Spinner color="white" /> : (
        <Box overflowX="auto">
          <Table variant="simple" size="sm" bg="gray.800" color="white">
            <Thead>
              <Tr>
                <Th color="gray.400">{t('products.productCode')}</Th>
                <Th color="gray.400">{t('products.name')}</Th>
                <Th color="gray.400">Type</Th>
                <Th color="gray.400" isNumeric>{t('products.unitPrice')}</Th>
                <Th color="gray.400">{t('products.vatCode')}</Th>
                <Th color="gray.400" display={{ base: 'none', md: 'table-cell' }}>{t('products.unitOfMeasure')}</Th>
                <Th color="gray.400" display={{ base: 'none', lg: 'table-cell' }}>{t('products.externalReference')}</Th>
              </Tr>
            </Thead>
            <Tbody>
              {products.map(p => (
                <Tr key={p.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(p)}>
                  <Td>{p.product_code}</Td>
                  <Td>{p.name}</Td>
                  <Td><Badge variant="subtle">{p.product_type}</Badge></Td>
                  <Td isNumeric>&euro; {Number(p.unit_price).toFixed(2)}</Td>
                  <Td>{p.vat_code}</Td>
                  <Td display={{ base: 'none', md: 'table-cell' }}>{p.unit_of_measure}</Td>
                  <Td display={{ base: 'none', lg: 'table-cell' }}>{p.external_reference || '-'}</Td>
                </Tr>
              ))}
              {products.length === 0 && (
                <Tr><Td colSpan={7}><Text color="gray.500">{t('common.noData')}</Text></Td></Tr>
              )}
            </Tbody>
          </Table>
        </Box>
      )}

      <ProductModal isOpen={isOpen} onClose={onClose}
        product={selected} onSaved={handleSaved} />
    </Box>
  );
};

export default ZZPProducts;
