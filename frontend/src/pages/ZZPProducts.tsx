/**
 * ZZP Products page — Chakra Table with row-click modal for CRUD.
 * Follows BankingProcessor pattern per ui-patterns.md.
 *
 * Uses the table-filter-framework-v2:
 * - useFilterableTable + FilterableHeader for inline column text filters + sort
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Flex, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td, useDisclosure,
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { Product } from '../types/zzp';
import { getProducts } from '../services/productService';
import { ProductModal } from '../components/zzp/ProductModal';
import { FilterableHeader } from '../components/filters/FilterableHeader';
import { useFilterableTable } from '../hooks/useFilterableTable';

const INITIAL_FILTERS: Record<string, string> = {
  product_code: '',
  name: '',
  product_type: '',
  unit_price: '',
  vat_code: '',
  unit_of_measure: '',
  external_reference: '',
};

const ZZPProducts: React.FC = () => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Product | null>(null);

  const {
    filters,
    setFilter,
    handleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable<Product>(products, {
    initialFilters: INITIAL_FILTERS,
    defaultSort: { field: 'product_code', direction: 'asc' },
  });

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

  const columnSortDirection = (field: string): 'asc' | 'desc' | null =>
    sortField === field ? sortDirection : null;

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
                <FilterableHeader
                  label={t('products.productCode')}
                  filterValue={filters.product_code}
                  onFilterChange={(v) => setFilter('product_code', v)}
                  sortable
                  sortDirection={columnSortDirection('product_code')}
                  onSort={() => handleSort('product_code')}
                />
                <FilterableHeader
                  label={t('products.name')}
                  filterValue={filters.name}
                  onFilterChange={(v) => setFilter('name', v)}
                  sortable
                  sortDirection={columnSortDirection('name')}
                  onSort={() => handleSort('name')}
                />
                <FilterableHeader
                  label="Type"
                  filterValue={filters.product_type}
                  onFilterChange={(v) => setFilter('product_type', v)}
                  sortable
                  sortDirection={columnSortDirection('product_type')}
                  onSort={() => handleSort('product_type')}
                />
                <FilterableHeader
                  label={t('products.unitPrice')}
                  filterValue={filters.unit_price}
                  onFilterChange={(v) => setFilter('unit_price', v)}
                  sortable
                  sortDirection={columnSortDirection('unit_price')}
                  onSort={() => handleSort('unit_price')}
                  isNumeric
                />
                <FilterableHeader
                  label={t('products.vatCode')}
                  filterValue={filters.vat_code}
                  onFilterChange={(v) => setFilter('vat_code', v)}
                  sortable
                  sortDirection={columnSortDirection('vat_code')}
                  onSort={() => handleSort('vat_code')}
                />
                <FilterableHeader
                  label={t('products.unitOfMeasure')}
                  filterValue={filters.unit_of_measure}
                  onFilterChange={(v) => setFilter('unit_of_measure', v)}
                  sortable
                  sortDirection={columnSortDirection('unit_of_measure')}
                  onSort={() => handleSort('unit_of_measure')}
                />
                <FilterableHeader
                  label={t('products.externalReference')}
                  filterValue={filters.external_reference}
                  onFilterChange={(v) => setFilter('external_reference', v)}
                  sortable
                  sortDirection={columnSortDirection('external_reference')}
                  onSort={() => handleSort('external_reference')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map(p => (
                <Tr key={p.id} _hover={{ bg: 'gray.700', cursor: 'pointer' }}
                  onClick={() => handleRowClick(p)}>
                  <Td>{p.product_code}</Td>
                  <Td>{p.name}</Td>
                  <Td><Badge variant="subtle">{p.product_type}</Badge></Td>
                  <Td isNumeric>&euro; {Number(p.unit_price).toFixed(2)}</Td>
                  <Td>{p.vat_code}</Td>
                  <Td>{p.unit_of_measure}</Td>
                  <Td>{p.external_reference || '-'}</Td>
                </Tr>
              ))}
              {processedData.length === 0 && (
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
