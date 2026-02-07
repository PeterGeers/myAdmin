/**
 * FilterPanel Component
 * 
 * A container component for organizing multiple filters with flexible layout options.
 * Supports horizontal, vertical, and grid layouts with responsive design.
 * 
 * @module filters/FilterPanel
 */

import React from 'react';
import { Box, SimpleGrid, HStack, VStack, FormControl, FormLabel, Input } from '@chakra-ui/react';
import { GenericFilter } from './GenericFilter';
import { FilterConfig, SearchFilterConfig } from './types';

/**
 * Filter panel layout modes
 */
export type FilterPanelLayout = 'horizontal' | 'vertical' | 'grid';

/**
 * FilterPanel props interface
 */
export interface FilterPanelProps {
  /** Array of filter configurations */
  filters: (FilterConfig<any> | SearchFilterConfig)[];
  
  /** Layout mode for organizing filters (default: 'horizontal') */
  layout?: FilterPanelLayout;
  
  /** Size variant for all filters (default: 'md') */
  size?: 'sm' | 'md' | 'lg';
  
  /** Spacing between filters in pixels (default: 4) */
  spacing?: number;
  
  /** Disable all filters */
  disabled?: boolean;
  
  /** Number of columns for grid layout (default: 2) */
  gridColumns?: number;
  
  /** Minimum width for each filter in grid layout */
  gridMinWidth?: string;
  
  /** Label text color (default: 'white' for dark backgrounds) */
  labelColor?: string;
  
  /** Select/Button background color (default: 'gray.600' for dark backgrounds) */
  bg?: string;
  
  /** Select/Button text color (default: 'white') */
  color?: string;
}

/**
 * FilterPanel - Container component for organizing multiple filters
 * 
 * Provides flexible layout options for displaying multiple GenericFilter components
 * in a cohesive, responsive interface. Supports mixing single and multi-select filters.
 * 
 * **Layout Modes:**
 * - `horizontal`: Filters arranged in a row (wraps on mobile)
 * - `vertical`: Filters stacked vertically
 * - `grid`: Filters arranged in a responsive grid
 * 
 * **Features:**
 * - Responsive design (mobile-friendly)
 * - Consistent spacing and alignment
 * - Supports mixing filter types (single, multi, range, search)
 * - Matches myAdmin design system
 * - Accessible keyboard navigation
 * 
 * @example
 * // Horizontal layout with year and quarter filters
 * <FilterPanel
 *   layout="horizontal"
 *   filters={[
 *     {
 *       type: 'single',
 *       label: 'Year',
 *       options: ['2023', '2024', '2025'],
 *       value: selectedYear,
 *       onChange: setSelectedYear
 *     },
 *     {
 *       type: 'single',
 *       label: 'Quarter',
 *       options: ['Q1', 'Q2', 'Q3', 'Q4'],
 *       value: selectedQuarter,
 *       onChange: setSelectedQuarter
 *     }
 *   ]}
 * />
 * 
 * @example
 * // Grid layout with multiple filters
 * <FilterPanel
 *   layout="grid"
 *   gridColumns={3}
 *   filters={[
 *     {
 *       type: 'multi',
 *       label: 'Years',
 *       options: ['2022', '2023', '2024', '2025'],
 *       value: selectedYears,
 *       onChange: setSelectedYears
 *     },
 *     {
 *       type: 'multi',
 *       label: 'Listings',
 *       options: listings,
 *       value: selectedListings,
 *       onChange: setSelectedListings,
 *       getOptionLabel: (listing) => listing.name
 *     },
 *     {
 *       type: 'multi',
 *       label: 'Channels',
 *       options: ['airbnb', 'booking', 'direct'],
 *       value: selectedChannels,
 *       onChange: setSelectedChannels
 *     }
 *   ]}
 * />
 * 
 * @example
 * // Vertical layout for mobile-first design
 * <FilterPanel
 *   layout="vertical"
 *   spacing={3}
 *   filters={[
 *     {
 *       type: 'single',
 *       label: 'Year',
 *       options: years,
 *       value: selectedYear,
 *       onChange: setSelectedYear
 *     },
 *     {
 *       type: 'search',
 *       label: 'Reference Number',
 *       value: searchTerm,
 *       onChange: setSearchTerm,
 *       placeholder: 'Search...'
 *     }
 *   ]}
 * />
 */
export function FilterPanel({
  filters,
  layout = 'horizontal',
  size = 'md',
  spacing = 4,
  disabled = false,
  gridColumns = 2,
  gridMinWidth = '200px',
  labelColor = 'white',
  bg = 'gray.600',
  color = 'white',
}: FilterPanelProps): React.ReactElement {
  // Render individual filter based on its configuration
  const renderFilter = (filter: FilterConfig<any> | SearchFilterConfig, index: number) => {
    const key = `filter-${index}-${filter.label}`;
    
    // Handle search filter type
    if (filter.type === 'search') {
      const searchFilter = filter as SearchFilterConfig;
      return (
        <Box key={key} minW={layout === 'horizontal' ? '200px' : undefined}>
          <FormControl isDisabled={disabled || searchFilter.disabled || false} size={searchFilter.size || size}>
            <FormLabel htmlFor={`search-${key}`} color={labelColor} fontSize="sm">
              {searchFilter.label}
            </FormLabel>
            <Input
              id={`search-${key}`}
              value={searchFilter.value}
              onChange={(e) => searchFilter.onChange(e.target.value)}
              placeholder={searchFilter.placeholder || 'Search...'}
              size={searchFilter.size || size}
              bg={bg}
              color={color}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
            />
          </FormControl>
        </Box>
      );
    }
    
    // Determine if multi-select based on filter type
    const isMultiSelect = filter.type === 'multi';
    
    // Convert filter config to GenericFilter props
    const filterProps = {
      values: Array.isArray(filter.value) ? filter.value : filter.value ? [filter.value] : [],
      onChange: (values: any[]) => {
        if (isMultiSelect) {
          filter.onChange(values);
        } else {
          filter.onChange(values[0] || null);
        }
      },
      availableOptions: filter.options || [],
      multiSelect: isMultiSelect,
      disabled: disabled || filter.disabled || false,
      label: filter.label,
      placeholder: filter.placeholder,
      size: filter.size || size,
      renderOption: filter.renderOption,
      getOptionLabel: filter.getOptionLabel,
      getOptionValue: filter.getOptionValue,
      isLoading: filter.isLoading || false,
      error: filter.error || null,
      treatEmptyAsSelected: filter.treatEmptyAsSelected || false,
      labelColor: labelColor,
      bg: bg,
      color: color,
    };
    
    return (
      <Box key={key} minW={layout === 'horizontal' ? '150px' : undefined}>
        <GenericFilter {...filterProps} />
      </Box>
    );
  };
  
  // Render based on layout mode
  switch (layout) {
    case 'vertical':
      return (
        <VStack spacing={spacing} align="stretch" width="100%">
          {filters.map((filter, index) => renderFilter(filter, index))}
        </VStack>
      );
    
    case 'grid':
      return (
        <SimpleGrid
          columns={{ base: 1, md: gridColumns }}
          spacing={spacing}
          width="100%"
          minChildWidth={gridMinWidth}
        >
          {filters.map((filter, index) => renderFilter(filter, index))}
        </SimpleGrid>
      );
    
    case 'horizontal':
    default:
      return (
        <HStack
          spacing={spacing}
          wrap="wrap"
          align="end"
          width="100%"
        >
          {filters.map((filter, index) => renderFilter(filter, index))}
        </HStack>
      );
  }
}

export default FilterPanel;
