import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast, Spinner,
  Table, Thead, Tbody, Tr, Td, Select, Input, useDisclosure,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, FormControl, FormLabel
} from '@chakra-ui/react';
import { AddIcon } from '@chakra-ui/icons';
import { useTenant } from '../../context/TenantContext';
import { getAssets, Asset, generateDepreciation, disposeAsset } from '../../services/assetService';
import AssetForm from './AssetForm';
import AssetDetail from './AssetDetail';
import { FilterableHeader } from '../filters/FilterableHeader';
import { useFilterableTable } from '../../hooks/useFilterableTable';

export default function AssetList() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');
  const { isOpen: isFormOpen, onOpen: onFormOpen, onClose: onFormClose } = useDisclosure();
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const { isOpen: isDepOpen, onOpen: onDepOpen, onClose: onDepClose } = useDisclosure();
  const [depYear, setDepYear] = useState(new Date().getFullYear());
  const [depPeriod, setDepPeriod] = useState('annual');
  const [depRunning, setDepRunning] = useState(false);
  const [depResults, setDepResults] = useState<{ entries_created: number; entries_skipped: number; details: Array<{ asset_id: number; description: string; amount?: number; status: string; reason?: string }> } | null>(null);
  const [disposeDate, setDisposeDate] = useState('');
  const [disposeAmount, setDisposeAmount] = useState('0');
  const [disposing, setDisposing] = useState(false);
  const { isOpen: isDisposeOpen, onOpen: onDisposeOpen, onClose: onDisposeClose } = useDisclosure();
  const toast = useToast();
  const { currentTenant } = useTenant();

  const openCreate = () => {
    setSelectedAsset(null);
    setFormMode('create');
    onFormOpen();
  };

  const openEdit = () => {
    setFormMode('edit');
    onDetailClose();
    onFormOpen();
  };

  const openDetail = (asset: Asset) => {
    setSelectedAsset(asset);
    onDetailOpen();
  };

  const handleGenerateDepreciation = async () => {
    setDepRunning(true);
    setDepResults(null);
    try {
      const result = await generateDepreciation({ year: depYear, period: depPeriod });
      setDepResults(result as typeof depResults);
      if (result.entries_created > 0) {
        loadAssets(); // refresh book values
      }
    } catch (error) {
      toast({
        title: 'Error generating depreciation',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error', duration: 5000,
      });
    } finally {
      setDepRunning(false);
    }
  };

  const loadAssets = useCallback(async () => {
    if (!currentTenant) return;
    setLoading(true);
    try {
      const data = await getAssets({});
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
  }, [currentTenant, toast]);

  useEffect(() => { loadAssets(); }, [loadAssets]);

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(val);

  // Build flat rows with formatted currency for filtering
  const assetRows = useMemo(() => assets.map(a => ({
    ...a,
    category_display: a.category || '—',
    purchase_amount_display: formatCurrency(a.purchase_amount),
    book_value_display: formatCurrency(a.book_value),
  })), [assets]);

  // Combined column filtering + sorting via framework hook
  const {
    filters,
    setFilter,
    handleSort: frameworkHandleSort,
    sortField,
    sortDirection,
    processedData,
  } = useFilterableTable(assetRows, {
    initialFilters: {
      id: '',
      description: '',
      category_display: '',
      purchase_date: '',
      purchase_amount_display: '',
      book_value_display: '',
      status: '',
    },
    defaultSort: { field: 'purchase_date', direction: 'desc' as const },
  });

  if (loading) {
    return (
      <Box textAlign="center" py={10}>
        <Spinner size="lg" color="orange.400" />
        <Text color="gray.400" mt={2}>Loading assets...</Text>
      </Box>
    );
  }

  return (
    <>
    <VStack spacing={4} align="stretch">
      {/* Action buttons */}
      <HStack spacing={3} wrap="wrap">
        <Button leftIcon={<AddIcon />} colorScheme="orange" size="sm" onClick={openCreate}>
          New Asset
        </Button>
        <Button colorScheme="green" size="sm" onClick={() => { setDepResults(null); onDepOpen(); }}>
          Generate Depreciation
        </Button>
        <Button size="sm" colorScheme="orange" variant="outline" onClick={loadAssets}>
          Refresh
        </Button>
        <Text color="gray.400" fontSize="sm">{processedData.length} / {assets.length}</Text>
      </HStack>

      {/* Table */}
      {processedData.length === 0 && !loading ? (
        <Box bg="gray.800" p={6} borderRadius="md" textAlign="center">
          <Text color="gray.400">No assets found</Text>
        </Box>
      ) : (
        <Box bg="gray.800" borderRadius="md" overflowX="auto">
          <Table variant="simple" size="sm">
            <Thead>
              <Tr>
                <FilterableHeader
                  label="ID"
                  filterValue={filters.id}
                  onFilterChange={(v) => setFilter('id', v)}
                  sortable
                  sortDirection={sortField === 'id' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('id')}
                />
                <FilterableHeader
                  label="Description"
                  filterValue={filters.description}
                  onFilterChange={(v) => setFilter('description', v)}
                  sortable
                  sortDirection={sortField === 'description' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('description')}
                />
                <FilterableHeader
                  label="Category"
                  filterValue={filters.category_display}
                  onFilterChange={(v) => setFilter('category_display', v)}
                  sortable
                  sortDirection={sortField === 'category_display' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('category_display')}
                />
                <FilterableHeader
                  label="Purchase Date"
                  filterValue={filters.purchase_date}
                  onFilterChange={(v) => setFilter('purchase_date', v)}
                  sortable
                  sortDirection={sortField === 'purchase_date' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('purchase_date')}
                />
                <FilterableHeader
                  label="Purchase Amount"
                  filterValue={filters.purchase_amount_display}
                  onFilterChange={(v) => setFilter('purchase_amount_display', v)}
                  isNumeric
                  sortable
                  sortDirection={sortField === 'purchase_amount' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('purchase_amount')}
                />
                <FilterableHeader
                  label="Book Value"
                  filterValue={filters.book_value_display}
                  onFilterChange={(v) => setFilter('book_value_display', v)}
                  isNumeric
                  sortable
                  sortDirection={sortField === 'book_value' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('book_value')}
                />
                <FilterableHeader
                  label="Status"
                  filterValue={filters.status}
                  onFilterChange={(v) => setFilter('status', v)}
                  sortable
                  sortDirection={sortField === 'status' ? sortDirection : null}
                  onSort={() => frameworkHandleSort('status')}
                />
              </Tr>
            </Thead>
            <Tbody>
              {processedData.map(asset => (
                <Tr key={asset.id} _hover={{ bg: 'gray.700' }} cursor="pointer"
                  onClick={() => openDetail(asset)}>
                  <Td color="gray.500" fontSize="xs">{asset.id}</Td>
                  <Td color="white">{asset.description}</Td>
                  <Td>
                    {asset.category
                      ? <Badge colorScheme="blue" fontSize="xs">{asset.category}</Badge>
                      : <Text color="gray.500">—</Text>}
                  </Td>
                  <Td color="gray.300">{asset.purchase_date}</Td>
                  <Td color="gray.300" isNumeric>{asset.purchase_amount_display}</Td>
                  <Td isNumeric fontWeight="bold"
                    color={asset.book_value > 0 ? 'green.300' : 'gray.500'}>
                    {asset.book_value_display}
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

    {/* Create/Edit Modal */}
    <AssetForm
      isOpen={isFormOpen}
      onClose={onFormClose}
      onSaved={loadAssets}
      mode={formMode}
      asset={selectedAsset as Record<string, unknown> | null}
    />

    {/* Detail Modal */}
    <AssetDetail
      isOpen={isDetailOpen}
      onClose={onDetailClose}
      assetId={selectedAsset?.id || null}
      onEdit={openEdit}
      onDispose={() => {
        onDetailClose();
        setDisposeDate(new Date().toISOString().split('T')[0]);
        setDisposeAmount('0');
        onDisposeOpen();
      }}
      onDeleted={loadAssets}
    />

    {/* Generate Depreciation Modal */}
    <Modal isOpen={isDepOpen} onClose={onDepClose} size="lg">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader color="orange.400">Generate Depreciation</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4} align="stretch">
            <HStack spacing={3}>
              <FormControl>
                <FormLabel color="gray.300">Year</FormLabel>
                <Input
                  type="number"
                  value={depYear}
                  onChange={e => setDepYear(parseInt(e.target.value))}
                  bg="gray.700" color="white" borderColor="gray.600"
                />
              </FormControl>
              <FormControl>
                <FormLabel color="gray.300">Period</FormLabel>
                <Select
                  value={depPeriod}
                  onChange={e => setDepPeriod(e.target.value)}
                  bg="gray.700" color="white" borderColor="gray.600"
                >
                  <option value="annual" style={{ background: '#2D3748' }}>Annual</option>
                  <option value="Q1" style={{ background: '#2D3748' }}>Q1 (Jan-Mar)</option>
                  <option value="Q2" style={{ background: '#2D3748' }}>Q2 (Apr-Jun)</option>
                  <option value="Q3" style={{ background: '#2D3748' }}>Q3 (Jul-Sep)</option>
                  <option value="Q4" style={{ background: '#2D3748' }}>Q4 (Oct-Dec)</option>
                  {Array.from({ length: 12 }, (_, i) => {
                    const m = String(i + 1).padStart(2, '0');
                    return <option key={m} value={`M${m}`} style={{ background: '#2D3748' }}>M{m}</option>;
                  })}
                </Select>
              </FormControl>
            </HStack>

            {depResults && (
              <Box bg="gray.700" p={3} borderRadius="md">
                <HStack spacing={4} mb={2}>
                  <Badge colorScheme="green" fontSize="sm" px={2}>{depResults.entries_created} created</Badge>
                  <Badge colorScheme="gray" fontSize="sm" px={2}>{depResults.entries_skipped} skipped</Badge>
                </HStack>
                {depResults.details.map((d, i) => (
                  <HStack key={i} fontSize="sm" py={1} borderBottom="1px" borderColor="gray.600">
                    <Text color="white" flex={1}>{d.description}</Text>
                    {d.amount && (
                      <Text color="green.300">
                        {new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(d.amount)}
                      </Text>
                    )}
                    <Badge colorScheme={d.status === 'created' ? 'green' : 'gray'} fontSize="xs">
                      {d.status}
                    </Badge>
                    {d.reason && <Text color="gray.400" fontSize="xs">{d.reason}</Text>}
                  </HStack>
                ))}
              </Box>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onDepClose}>Close</Button>
          <Button
            colorScheme="green"
            onClick={handleGenerateDepreciation}
            isLoading={depRunning}
            isDisabled={!!depResults?.entries_created}
          >
            {depResults ? 'Done' : 'Generate'}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
    {/* Dispose Modal */}
    <Modal isOpen={isDisposeOpen} onClose={onDisposeClose} size="md">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white">
        <ModalHeader color="red.400">Dispose Asset</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4} align="stretch">
            {selectedAsset && (
              <Text>Disposing: <strong>{selectedAsset.description}</strong> (Book value: {new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(selectedAsset.book_value)})</Text>
            )}
            <FormControl isRequired>
              <FormLabel color="gray.300">Disposal Date</FormLabel>
              <Input type="date" value={disposeDate}
                onChange={e => setDisposeDate(e.target.value)}
                bg="gray.700" color="white" borderColor="gray.600" />
            </FormControl>
            <FormControl>
              <FormLabel color="gray.300">Sale Amount (€) — 0 if scrapped</FormLabel>
              <Input type="number" step="0.01" value={disposeAmount}
                onChange={e => setDisposeAmount(e.target.value)}
                bg="gray.700" color="white" borderColor="gray.600" />
            </FormControl>
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onDisposeClose}>Cancel</Button>
          <Button colorScheme="red" isLoading={disposing} isDisabled={!disposeDate}
            onClick={async () => {
              if (!selectedAsset) return;
              setDisposing(true);
              try {
                const result = await disposeAsset(selectedAsset.id, {
                  disposal_date: disposeDate,
                  disposal_amount: parseFloat(disposeAmount || '0'),
                });
                toast({
                  title: 'Asset disposed',
                  description: `Write-off: ${new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(result.write_off)}`,
                  status: 'success', duration: 5000, isClosable: true,
                });
                onDisposeClose();
                loadAssets();
              } catch (error) {
                toast({
                  title: 'Error disposing asset',
                  description: error instanceof Error ? error.message : 'Unknown error',
                  status: 'error', duration: 5000,
                });
              } finally {
                setDisposing(false);
              }
            }}>
            Dispose
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
    </>
  );
}
