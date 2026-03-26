import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Select, Input
} from '@chakra-ui/react';
import { TriangleDownIcon, TriangleUpIcon } from '@chakra-ui/icons';
import { useTenant } from '../../context/TenantContext';
import { getAssets, Asset } from '../../services/assetService';

type SortField = 'description' | 'category' | 'purchase_date'
  | 'purchase_amount' | 'book_value' | 'status';

export default function AssetList() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [searchText, setSearchText] = useState('');
  const [sortField, setSortField] = useState<SortField>('purchase_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const toast = useToast();
  const { currentTenant } = useTenant();

  const loadAssets = useCallback(async () => {
    if (!currentTenant) return;
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      const data = await getAssets(params);
      setAssets(data.assets || []);
    } catch (error) {
      toast({
        title: 'Error loading assets',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error', duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [currentTenant, statusFilter, categoryFilter, toast]);

  useEffect(() => { loadAssets(); }, [loadAssets]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sorted = [...assets]
    .filter(a => {
      if (!searchText) return true;
      const s = searchText.toLowerCase();
      return a.description.toLowerCase().includes(s)
        || (a.category || '').toLowerCase().includes(s)
        || a.ledger_account.includes(s);
    })
    .sort((a, b) => {
      const av = a[sortField] ?? '';
      const bv = b[sortField] ?? '';
      const cmp = typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });

  const categories = Array.from(new Set(assets.map(a => a.category).filter(Boolean))) as string[];

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(val);

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null;
    return sortDir === 'asc'
      ? <TriangleUpIcon ml={1} boxSize={3} />
      : <TriangleDownIcon ml={1} boxSize={3} />;
  };

  if (loading) {
    return (
      <Box textAlign="center" py={10}>
        <Spinner size="lg" color="orange.400" />
        <Text color="gray.400" mt={2}>Loading assets...</Text>
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch">
      {/* Filters */}
      <HStack spacing={3} wrap="wrap">
        <Input
          placeholder="Search description..."
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
          bg="gray.700" color="white" borderColor="gray.600"
          size="sm" maxW="250px"
        />
        <Select
          placeholder="All statuses"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          bg="gray.700" color="white" borderColor="gray.600"
          size="sm" maxW="160px"
        >
          <option value="active" style={{ background: '#2D3748' }}>Active</option>
          <option value="disposed" style={{ background: '#2D3748' }}>Disposed</option>
        </Select>
        <Select
          placeholder="All categories"
          value={categoryFilter}
          onChange={e => setCategoryFilter(e.target.value)}
          bg="gray.700" color="white" borderColor="gray.600"
          size="sm" maxW="160px"
        >
          {categories.map(c => (
            <option key={c} value={c} style={{ background: '#2D3748' }}>{c}</option>
          ))}
        </Select>
        <Button size="sm" colorScheme="orange" variant="outline" onClick={loadAssets}>
          Refresh
        </Button>
        <Text color="gray.400" fontSize="sm">{sorted.length} / {assets.length}</Text>
      </HStack>

      {/* Table */}
      {sorted.length === 0 ? (
        <Box bg="gray.800" p={6} borderRadius="md" textAlign="center">
          <Text color="gray.400">No assets found</Text>
        </Box>
      ) : (
        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('description')}>
                  Description <SortIcon field="description" />
                </Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('category')}>
                  Category <SortIcon field="category" />
                </Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('purchase_date')}>
                  Purchase Date <SortIcon field="purchase_date" />
                </Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('purchase_amount')} isNumeric>
                  Purchase Amount <SortIcon field="purchase_amount" />
                </Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('book_value')} isNumeric>
                  Book Value <SortIcon field="book_value" />
                </Th>
                <Th color="gray.400" cursor="pointer" onClick={() => handleSort('status')}>
                  Status <SortIcon field="status" />
                </Th>
              </Tr>
            </Thead>
            <Tbody>
              {sorted.map(asset => (
                <Tr key={asset.id} _hover={{ bg: 'gray.700' }} cursor="pointer">
                  <Td color="white">{asset.description}</Td>
                  <Td>
                    {asset.category
                      ? <Badge colorScheme="blue" fontSize="xs">{asset.category}</Badge>
                      : <Text color="gray.500">—</Text>}
                  </Td>
                  <Td color="gray.300">{asset.purchase_date}</Td>
                  <Td color="gray.300" isNumeric>{formatCurrency(asset.purchase_amount)}</Td>
                  <Td isNumeric fontWeight="bold"
                    color={asset.book_value > 0 ? 'green.300' : 'gray.500'}>
                    {formatCurrency(asset.book_value)}
                  </Td>
                  <Td>
                    <Badge
                      colorScheme={asset.status === 'active' ? 'green' : 'red'}
                      fontSize="xs"
                    >
                      {asset.status}
                    </Badge>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </Box>
      )}
    </VStack>
  );
}
