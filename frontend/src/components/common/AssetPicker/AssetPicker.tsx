/**
 * AssetPicker — reusable modal component for browsing and selecting media assets.
 *
 * Displays a grid of asset thumbnails/icons with search, category/media_type
 * filters, sort options, and pagination. Used anywhere the app needs to let
 * a user choose an existing asset instead of uploading a new one.
 *
 * Props:
 *   isOpen / onClose      — Chakra modal controls
 *   onSelect(asset)       — callback when the user picks an asset
 *   defaultCategory       — pre-select a category filter
 *   defaultMediaType      — pre-select a media type filter
 *   allowedMediaTypes     — restrict which media types are shown in the filter
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  Input,
  Select,
  SimpleGrid,
  Box,
  Text,
  Badge,
  Spinner,
  HStack,
  VStack,
  Button,
  Image,
  InputGroup,
  InputLeftElement,
  Icon,
} from '@chakra-ui/react';
import { SearchIcon } from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';
import { buildApiUrl } from '@/config';
import type {
  MediaAsset,
  AssetCategory,
  AssetMediaType,
  AssetSortField,
  SortOrder,
  AssetSearchFilters,
  AssetSearchResponse,
} from '@/types/mediaAsset';

// ─── Props ────────────────────────────────────────────────────────────────────

export interface AssetPickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (asset: MediaAsset) => void;
  defaultCategory?: AssetCategory | '';
  defaultMediaType?: AssetMediaType | '';
  allowedMediaTypes?: AssetMediaType[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

const SORT_OPTIONS: { value: AssetSortField; label: string; order: SortOrder }[] = [
  { value: 'created_at', label: 'Most recent', order: 'desc' },
  { value: 'original_filename', label: 'Filename A-Z', order: 'asc' },
  { value: 'file_size', label: 'File size', order: 'desc' },
  { value: 'reference_count', label: 'Most referenced', order: 'desc' },
];

const CATEGORY_OPTIONS: { value: AssetCategory | ''; label: string }[] = [
  { value: '', label: 'All categories' },
  { value: 'invoices', label: 'Invoices' },
  { value: 'branding', label: 'Branding' },
  { value: 'templates', label: 'Templates' },
  { value: 'landing-pages', label: 'Landing Pages' },
];

const ALL_MEDIA_TYPES: { value: AssetMediaType | ''; label: string }[] = [
  { value: '', label: 'All types' },
  { value: 'image', label: 'Image' },
  { value: 'video', label: 'Video' },
  { value: 'document', label: 'Document' },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(mimeType: string): string {
  if (mimeType.startsWith('video/')) return '🎬';
  if (mimeType === 'application/pdf') return '📄';
  if (mimeType.startsWith('image/')) return '🖼️';
  return '📁';
}

// ─── Component ────────────────────────────────────────────────────────────────

export const AssetPicker: React.FC<AssetPickerProps> = ({
  isOpen,
  onClose,
  onSelect,
  defaultCategory = '',
  defaultMediaType = '',
  allowedMediaTypes,
}) => {
  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState<AssetCategory | ''>(defaultCategory);
  const [mediaType, setMediaType] = useState<AssetMediaType | ''>(defaultMediaType);
  const [sortIndex, setSortIndex] = useState(0);

  // Data
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce timer ref
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setCategory(defaultCategory);
      setMediaType(defaultMediaType);
      setSortIndex(0);
      setPage(1);
      setAssets([]);
      setError(null);
    }
  }, [isOpen, defaultCategory, defaultMediaType]);

  // ── Fetch assets ──────────────────────────────────────────────────────────

  const fetchAssets = useCallback(async (filters: AssetSearchFilters) => {
    setLoading(true);
    setError(null);

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      if (!token) {
        setError('Not authenticated');
        setLoading(false);
        return;
      }

      const params = new URLSearchParams();
      if (filters.q) params.set('q', filters.q);
      if (filters.category) params.set('category', filters.category);
      if (filters.media_type) params.set('media_type', filters.media_type);
      if (filters.sort) params.set('sort', filters.sort);
      if (filters.order) params.set('order', filters.order);
      params.set('page', String(filters.page ?? 1));
      params.set('page_size', String(filters.page_size ?? PAGE_SIZE));

      const url = buildApiUrl('/api/assets/search', params);

      const response = await fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': localStorage.getItem('selectedTenant') || '',
        },
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.error || `HTTP ${response.status}`);
      }

      const result: AssetSearchResponse = await response.json();
      setAssets(result.data);
      setTotalPages(result.pagination.total_pages);
      setTotal(result.pagination.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch assets');
      setAssets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Trigger search (debounced for text input) ─────────────────────────────

  const triggerSearch = useCallback((newPage?: number) => {
    const sort = SORT_OPTIONS[sortIndex];
    fetchAssets({
      q: searchQuery || undefined,
      category: category || undefined,
      media_type: mediaType || undefined,
      sort: sort.value,
      order: sort.order,
      page: newPage ?? page,
      page_size: PAGE_SIZE,
    });
  }, [searchQuery, category, mediaType, sortIndex, page, fetchAssets]);

  // Fetch on filter changes (non-text)
  useEffect(() => {
    if (!isOpen) return;
    setPage(1);
    triggerSearch(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, mediaType, sortIndex, isOpen]);

  // Debounced text search
  useEffect(() => {
    if (!isOpen) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setPage(1);
      triggerSearch(1);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  // Page change
  useEffect(() => {
    if (!isOpen) return;
    triggerSearch(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // ── Filter the available media type options ───────────────────────────────

  const mediaTypeOptions = allowedMediaTypes
    ? ALL_MEDIA_TYPES.filter(
        (opt) => opt.value === '' || allowedMediaTypes.includes(opt.value as AssetMediaType)
      )
    : ALL_MEDIA_TYPES;

  // ── Handle asset selection ────────────────────────────────────────────────

  const handleSelect = (asset: MediaAsset) => {
    onSelect(asset);
    onClose();
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="6xl">
      <ModalOverlay />
      <ModalContent bg="gray.800" color="white" maxH="85vh">
        <ModalHeader color="orange.400">Choose Existing Asset</ModalHeader>
        <ModalCloseButton />
        <ModalBody pb={6} display="flex" flexDirection="column" overflow="hidden">
          {/* Filters row */}
          <HStack spacing={3} mb={4} flexWrap="wrap">
            <InputGroup maxW="280px">
              <InputLeftElement>
                <Icon as={SearchIcon} color="gray.400" />
              </InputLeftElement>
              <Input
                placeholder="Search filename..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                bg="gray.700"
                borderColor="gray.600"
                data-testid="asset-search-input"
              />
            </InputGroup>

            <Select
              value={category}
              onChange={(e) => setCategory(e.target.value as AssetCategory | '')}
              bg="gray.700"
              borderColor="gray.600"
              maxW="180px"
              data-testid="asset-category-filter"
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} style={{ background: '#2D3748' }}>
                  {opt.label}
                </option>
              ))}
            </Select>

            <Select
              value={mediaType}
              onChange={(e) => setMediaType(e.target.value as AssetMediaType | '')}
              bg="gray.700"
              borderColor="gray.600"
              maxW="160px"
              data-testid="asset-media-type-filter"
            >
              {mediaTypeOptions.map((opt) => (
                <option key={opt.value} value={opt.value} style={{ background: '#2D3748' }}>
                  {opt.label}
                </option>
              ))}
            </Select>

            <Select
              value={sortIndex}
              onChange={(e) => setSortIndex(Number(e.target.value))}
              bg="gray.700"
              borderColor="gray.600"
              maxW="180px"
              data-testid="asset-sort-select"
            >
              {SORT_OPTIONS.map((opt, idx) => (
                <option key={opt.value} value={idx} style={{ background: '#2D3748' }}>
                  {opt.label}
                </option>
              ))}
            </Select>

            <Text fontSize="sm" color="gray.400" ml="auto">
              {total} asset{total !== 1 ? 's' : ''}
            </Text>
          </HStack>

          {/* Content area */}
          <Box flex="1" overflowY="auto" minH="300px">
            {loading && (
              <VStack py={10}>
                <Spinner size="lg" color="orange.400" />
                <Text color="gray.400">Loading assets...</Text>
              </VStack>
            )}

            {error && !loading && (
              <Box textAlign="center" py={10}>
                <Text color="red.300">{error}</Text>
              </Box>
            )}

            {!loading && !error && assets.length === 0 && (
              <Box textAlign="center" py={10}>
                <Text color="gray.400">No assets found</Text>
              </Box>
            )}

            {!loading && !error && assets.length > 0 && (
              <SimpleGrid columns={{ base: 2, md: 3, lg: 4, xl: 5 }} spacing={4}>
                {assets.map((asset) => (
                  <Box
                    key={asset.id}
                    bg="gray.700"
                    borderRadius="md"
                    p={3}
                    cursor="pointer"
                    _hover={{ bg: 'gray.600', transform: 'scale(1.02)' }}
                    transition="all 0.15s"
                    onClick={() => handleSelect(asset)}
                    data-testid={`asset-tile-${asset.id}`}
                  >
                    {/* Thumbnail or icon */}
                    <Box
                      h="100px"
                      display="flex"
                      alignItems="center"
                      justifyContent="center"
                      bg="gray.800"
                      borderRadius="sm"
                      mb={2}
                      overflow="hidden"
                    >
                      {asset.presigned_url ? (
                        <Image
                          src={asset.presigned_url}
                          alt={asset.original_filename}
                          maxH="100%"
                          maxW="100%"
                          objectFit="contain"
                        />
                      ) : (
                        <Text fontSize="3xl">{getFileIcon(asset.mime_type)}</Text>
                      )}
                    </Box>

                    {/* Info */}
                    <Text
                      fontSize="xs"
                      color="white"
                      noOfLines={1}
                      title={asset.original_filename}
                      fontWeight="medium"
                    >
                      {asset.original_filename}
                    </Text>
                    <HStack spacing={1} mt={1} flexWrap="wrap">
                      <Text fontSize="xs" color="gray.400">
                        {formatFileSize(asset.file_size)}
                      </Text>
                      <Badge fontSize="2xs" colorScheme="blue">
                        {asset.category}
                      </Badge>
                    </HStack>
                    <Text fontSize="xs" color="gray.500" mt={0.5}>
                      {asset.reference_count} ref{asset.reference_count !== 1 ? 's' : ''}
                    </Text>
                  </Box>
                ))}
              </SimpleGrid>
            )}
          </Box>

          {/* Pagination */}
          {totalPages > 1 && !loading && (
            <HStack spacing={2} justifyContent="center" mt={4} pt={3} borderTop="1px" borderColor="gray.600">
              <Button
                size="sm"
                variant="ghost"
                isDisabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Text fontSize="sm" color="gray.300">
                Page {page} of {totalPages}
              </Text>
              <Button
                size="sm"
                variant="ghost"
                isDisabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </HStack>
          )}
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

export default AssetPicker;
