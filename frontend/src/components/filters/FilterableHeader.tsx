/**
 * FilterableHeader Component
 *
 * Renders a Chakra UI `<Th>` element with a column label, optional sort
 * indicator, and optional text filter `<Input>`. Used in the hybrid approach
 * where text search filters live inside column headers while dropdown and
 * multi-select filters remain above the table in `FilterPanel`.
 *
 * @module filters/FilterableHeader
 * @see .kiro/specs/table-filter-framework-v2/design.md §4
 */

import React from 'react';
import { Th, VStack, HStack, Text, Input, InputGroup, InputLeftElement } from '@chakra-ui/react';
import { SearchIcon } from '@chakra-ui/icons';
import { FilterableHeaderProps } from './types';

/**
 * Table header cell with optional inline text filter and sort indicator.
 *
 * @example
 * ```tsx
 * <FilterableHeader
 *   label="Account Name"
 *   filterValue={filters.AccountName}
 *   onFilterChange={(v) => setFilter('AccountName', v)}
 *   sortable
 *   sortDirection={sortField === 'AccountName' ? sortDirection : null}
 *   onSort={() => handleSort('AccountName')}
 * />
 * ```
 */
export const FilterableHeader: React.FC<FilterableHeaderProps> = ({
  label,
  filterValue,
  onFilterChange,
  sortable = false,
  sortDirection,
  onSort,
  placeholder,
  isNumeric = false,
  w,
  maxW,
}) => {
  const ariaSortValue = sortable
    ? sortDirection === 'asc'
      ? 'ascending'
      : sortDirection === 'desc'
        ? 'descending'
        : 'none'
    : undefined;

  return (
    <Th
      bg="gray.700"
      aria-sort={ariaSortValue}
      isNumeric={isNumeric}
      w={w}
      maxW={maxW}
    >
      <VStack spacing={1} align={isNumeric ? 'flex-end' : 'flex-start'}>
        {/* Label row with optional sort indicator */}
        <HStack
          spacing={1}
          cursor={sortable ? 'pointer' : 'default'}
          onClick={sortable ? onSort : undefined}
          role={sortable ? 'button' : undefined}
          aria-label={sortable ? `Sort by ${label}` : undefined}
        >
          <Text
            fontSize="xs"
            color="gray.300"
            fontWeight="bold"
            textTransform="uppercase"
          >
            {label}
          </Text>
          {sortable && sortDirection && (
            <Text fontSize="xs" color="orange.300">
              {sortDirection === 'asc' ? '↑' : '↓'}
            </Text>
          )}
        </HStack>

        {/* Optional filter input */}
        {filterValue !== undefined && (
          <InputGroup size="xs">
            <InputLeftElement pointerEvents="none" h="24px">
              <SearchIcon color="gray.300" boxSize="10px" />
            </InputLeftElement>
            <Input
              value={filterValue}
              onChange={(e) => onFilterChange?.(e.target.value)}
              placeholder={placeholder || 'Filter...'}
              bg="gray.600"
              color="white"
              pl="24px"
              aria-label={`Filter by ${label}`}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
            />
          </InputGroup>
        )}
      </VStack>
    </Th>
  );
};

export default FilterableHeader;
