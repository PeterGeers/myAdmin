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
import { Th, VStack, HStack, Text, Input } from '@chakra-ui/react';
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
          <Input
            size="xs"
            value={filterValue}
            onChange={(e) => onFilterChange?.(e.target.value)}
            placeholder={placeholder || 'Filter...'}
            bg="gray.600"
            color="white"
            aria-label={`Filter by ${label}`}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
          />
        )}
      </VStack>
    </Th>
  );
};

export default FilterableHeader;
