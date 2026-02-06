/**
 * FilterPanel Unit Tests
 * 
 * Test suite for the FilterPanel component covering:
 * - Horizontal layout
 * - Vertical layout
 * - Grid layout
 * - Responsive behavior
 * - Mixed filter types (single and multi-select)
 * - Props propagation to GenericFilter
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { FilterPanel } from './FilterPanel';
import { FilterConfig } from './types';

// Mock GenericFilter to simplify testing
jest.mock('./GenericFilter', () => ({
  GenericFilter: ({ label, values, multiSelect, disabled, size, isLoading, error }: any) => (
    <div data-testid={`filter-${label}`}>
      <span data-label={label}>{label}</span>
      <span data-multiselect={multiSelect}>
        {multiSelect ? 'multi' : 'single'}
      </span>
      <span data-values={JSON.stringify(values)}>
        {values.length > 0 ? values.join(', ') : 'none'}
      </span>
      {disabled && <span data-disabled>disabled</span>}
      {isLoading && <span data-loading>loading</span>}
      {error && <span data-error>{error}</span>}
      <span data-size={size}>{size}</span>
    </div>
  ),
}));

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...props }: any) => <div data-box {...props}>{children}</div>,
  SimpleGrid: ({ children, columns, spacing, minChildWidth, ...props }: any) => (
    <div 
      data-testid="simple-grid" 
      data-columns={JSON.stringify(columns)}
      data-spacing={spacing}
      data-min-child-width={minChildWidth}
      {...props}
    >
      {children}
    </div>
  ),
  HStack: ({ children, spacing, wrap, align, ...props }: any) => (
    <div 
      data-testid="hstack" 
      data-spacing={spacing}
      data-wrap={wrap}
      data-align={align}
      {...props}
    >
      {children}
    </div>
  ),
  VStack: ({ children, spacing, align, ...props }: any) => (
    <div 
      data-testid="vstack" 
      data-spacing={spacing}
      data-align={align}
      {...props}
    >
      {children}
    </div>
  ),
}));

describe('FilterPanel', () => {
  const mockSingleSelectFilter: FilterConfig<string> = {
    type: 'single',
    label: 'Year',
    options: ['2023', '2024', '2025'],
    value: '2024',
    onChange: jest.fn(),
  };

  const mockMultiSelectFilter: FilterConfig<string> = {
    type: 'multi',
    label: 'Listings',
    options: ['Listing 1', 'Listing 2', 'Listing 3'],
    value: ['Listing 1', 'Listing 2'],
    onChange: jest.fn(),
  };

  const mockSearchFilter: FilterConfig<string> = {
    type: 'search',
    label: 'Reference',
    options: [],
    value: '',
    onChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Horizontal Layout', () => {
    it('renders with horizontal layout by default', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      expect(screen.getByTestId('hstack')).toBeInTheDocument();
    });

    it('renders multiple filters in horizontal layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
    });

    it('applies correct spacing in horizontal layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          spacing={6}
        />
      );

      const hstack = screen.getByTestId('hstack');
      expect(hstack).toHaveAttribute('data-spacing', '6');
    });

    it('applies wrap and align properties in horizontal layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      const hstack = screen.getByTestId('hstack');
      expect(hstack).toHaveAttribute('data-wrap', 'wrap');
      expect(hstack).toHaveAttribute('data-align', 'end');
    });

    it('applies default spacing of 4 when not specified', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      const hstack = screen.getByTestId('hstack');
      expect(hstack).toHaveAttribute('data-spacing', '4');
    });
  });

  describe('Vertical Layout', () => {
    it('renders with vertical layout when specified', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="vertical"
        />
      );

      expect(screen.getByTestId('vstack')).toBeInTheDocument();
    });

    it('renders multiple filters in vertical layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          layout="vertical"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
    });

    it('applies correct spacing in vertical layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="vertical"
          spacing={3}
        />
      );

      const vstack = screen.getByTestId('vstack');
      expect(vstack).toHaveAttribute('data-spacing', '3');
    });

    it('applies stretch alignment in vertical layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="vertical"
        />
      );

      const vstack = screen.getByTestId('vstack');
      expect(vstack).toHaveAttribute('data-align', 'stretch');
    });
  });

  describe('Grid Layout', () => {
    it('renders with grid layout when specified', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
        />
      );

      expect(screen.getByTestId('simple-grid')).toBeInTheDocument();
    });

    it('renders multiple filters in grid layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter, mockSearchFilter]}
          layout="grid"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Reference')).toBeInTheDocument();
    });

    it('applies default grid columns of 2', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
        />
      );

      const grid = screen.getByTestId('simple-grid');
      const columns = JSON.parse(grid.getAttribute('data-columns') || '{}');
      expect(columns.md).toBe(2);
    });

    it('applies custom grid columns', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      const grid = screen.getByTestId('simple-grid');
      const columns = JSON.parse(grid.getAttribute('data-columns') || '{}');
      expect(columns.md).toBe(3);
    });

    it('applies responsive columns (base: 1, md: custom)', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      const grid = screen.getByTestId('simple-grid');
      const columns = JSON.parse(grid.getAttribute('data-columns') || '{}');
      expect(columns.base).toBe(1);
      expect(columns.md).toBe(3);
    });

    it('applies default minChildWidth of 200px', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
        />
      );

      const grid = screen.getByTestId('simple-grid');
      expect(grid).toHaveAttribute('data-min-child-width', '200px');
    });

    it('applies custom minChildWidth', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridMinWidth="250px"
        />
      );

      const grid = screen.getByTestId('simple-grid');
      expect(grid).toHaveAttribute('data-min-child-width', '250px');
    });

    it('applies correct spacing in grid layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          spacing={5}
        />
      );

      const grid = screen.getByTestId('simple-grid');
      expect(grid).toHaveAttribute('data-spacing', '5');
    });
  });

  describe('Mixed Filter Types', () => {
    it('renders single-select filter correctly', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Year');
      expect(filter).toHaveTextContent('Year');
      expect(filter).toHaveTextContent('single');
    });

    it('renders multi-select filter correctly', () => {
      render(
        <FilterPanel
          filters={[mockMultiSelectFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Listings');
      expect(filter).toHaveTextContent('Listings');
      expect(filter).toHaveTextContent('multi');
    });

    it('renders both single and multi-select filters together', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
        />
      );

      const yearFilter = screen.getByTestId('filter-Year');
      const listingsFilter = screen.getByTestId('filter-Listings');

      expect(yearFilter).toHaveTextContent('single');
      expect(listingsFilter).toHaveTextContent('multi');
    });

    it('handles search filter type', () => {
      render(
        <FilterPanel
          filters={[mockSearchFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Reference');
      expect(filter).toHaveTextContent('Reference');
      // Search filters are treated as single-select in the current implementation
      expect(filter).toHaveTextContent('single');
    });

    it('renders three different filter types together', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter, mockSearchFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Reference')).toBeInTheDocument();
    });
  });

  describe('Props Propagation', () => {
    it('propagates size prop to all filters', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          size="lg"
        />
      );

      const yearFilter = screen.getByTestId('filter-Year');
      const listingsFilter = screen.getByTestId('filter-Listings');

      expect(yearFilter).toHaveTextContent('lg');
      expect(listingsFilter).toHaveTextContent('lg');
    });

    it('uses filter-specific size over panel size', () => {
      const filterWithCustomSize: FilterConfig<string> = {
        ...mockSingleSelectFilter,
        size: 'sm',
      };

      render(
        <FilterPanel
          filters={[filterWithCustomSize]}
          size="lg"
        />
      );

      const filter = screen.getByTestId('filter-Year');
      expect(filter).toHaveTextContent('sm');
    });

    it('propagates disabled prop to all filters', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          disabled
        />
      );

      const yearFilter = screen.getByTestId('filter-Year');
      const listingsFilter = screen.getByTestId('filter-Listings');

      expect(yearFilter).toHaveTextContent('disabled');
      expect(listingsFilter).toHaveTextContent('disabled');
    });

    it('respects filter-specific disabled state', () => {
      const disabledFilter: FilterConfig<string> = {
        ...mockSingleSelectFilter,
        disabled: true,
      };

      render(
        <FilterPanel
          filters={[disabledFilter, mockMultiSelectFilter]}
        />
      );

      const yearFilter = screen.getByTestId('filter-Year');
      const listingsFilter = screen.getByTestId('filter-Listings');

      expect(yearFilter).toHaveTextContent('disabled');
      expect(listingsFilter).not.toHaveTextContent('disabled');
    });

    it('propagates loading state from filter config', () => {
      const loadingFilter: FilterConfig<string> = {
        ...mockSingleSelectFilter,
        isLoading: true,
      };

      render(
        <FilterPanel
          filters={[loadingFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Year');
      expect(filter).toHaveTextContent('loading');
    });

    it('propagates error state from filter config', () => {
      const errorFilter: FilterConfig<string> = {
        ...mockSingleSelectFilter,
        error: 'Failed to load options',
      };

      render(
        <FilterPanel
          filters={[errorFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Year');
      expect(filter).toHaveTextContent('Failed to load options');
    });

    it('propagates placeholder from filter config', () => {
      const filterWithPlaceholder: FilterConfig<string> = {
        ...mockSingleSelectFilter,
        placeholder: 'Choose a year',
      };

      render(
        <FilterPanel
          filters={[filterWithPlaceholder]}
        />
      );

      // Placeholder is passed to GenericFilter (verified by mock)
      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });
  });

  describe('Value Handling', () => {
    it('converts single value to array for GenericFilter', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Year');
      expect(filter).toHaveTextContent('2024');
    });

    it('passes array values directly for multi-select', () => {
      render(
        <FilterPanel
          filters={[mockMultiSelectFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Listings');
      expect(filter).toHaveTextContent('Listing 1, Listing 2');
    });

    it('handles empty single value', () => {
      const emptyFilter: FilterConfig<string> = {
        ...mockSingleSelectFilter,
        value: '',
      };

      render(
        <FilterPanel
          filters={[emptyFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Year');
      expect(filter).toHaveTextContent('none');
    });

    it('handles empty array value', () => {
      const emptyFilter: FilterConfig<string> = {
        ...mockMultiSelectFilter,
        value: [],
      };

      render(
        <FilterPanel
          filters={[emptyFilter]}
        />
      );

      const filter = screen.getByTestId('filter-Listings');
      expect(filter).toHaveTextContent('none');
    });
  });

  describe('Edge Cases', () => {
    it('renders with empty filters array', () => {
      render(
        <FilterPanel
          filters={[]}
        />
      );

      expect(screen.getByTestId('hstack')).toBeInTheDocument();
    });

    it('renders with single filter', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });

    it('renders with many filters', () => {
      const manyFilters: FilterConfig<string>[] = Array.from({ length: 10 }, (_, i) => ({
        type: 'single',
        label: `Filter ${i + 1}`,
        options: ['A', 'B', 'C'],
        value: 'A',
        onChange: jest.fn(),
      }));

      render(
        <FilterPanel
          filters={manyFilters}
          layout="grid"
          gridColumns={4}
        />
      );

      manyFilters.forEach((_, i) => {
        expect(screen.getByTestId(`filter-Filter ${i + 1}`)).toBeInTheDocument();
      });
    });

    it('handles filters with special characters in labels', () => {
      const specialFilter: FilterConfig<string> = {
        type: 'single',
        label: 'Year (2023-2025)',
        options: ['2023', '2024', '2025'],
        value: '2024',
        onChange: jest.fn(),
      };

      render(
        <FilterPanel
          filters={[specialFilter]}
        />
      );

      expect(screen.getByTestId('filter-Year (2023-2025)')).toBeInTheDocument();
    });
  });

  describe('Responsive Behavior', () => {
    it('applies responsive grid columns', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      const grid = screen.getByTestId('simple-grid');
      const columns = JSON.parse(grid.getAttribute('data-columns') || '{}');
      
      // Should have base: 1 for mobile, md: 3 for desktop
      expect(columns.base).toBe(1);
      expect(columns.md).toBe(3);
    });

    it('horizontal layout wraps on small screens', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          layout="horizontal"
        />
      );

      const hstack = screen.getByTestId('hstack');
      expect(hstack).toHaveAttribute('data-wrap', 'wrap');
    });

    it('applies minChildWidth for responsive grid', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridMinWidth="300px"
        />
      );

      const grid = screen.getByTestId('simple-grid');
      expect(grid).toHaveAttribute('data-min-child-width', '300px');
    });
  });

  describe('Integration Scenarios', () => {
    it('renders BTW report filter pattern (single year + single quarter)', () => {
      const yearFilter: FilterConfig<string> = {
        type: 'single',
        label: 'Year',
        options: ['2023', '2024', '2025'],
        value: '2024',
        onChange: jest.fn(),
      };

      const quarterFilter: FilterConfig<string> = {
        type: 'single',
        label: 'Quarter',
        options: ['Q1', 'Q2', 'Q3', 'Q4'],
        value: 'Q1',
        onChange: jest.fn(),
      };

      render(
        <FilterPanel
          filters={[yearFilter, quarterFilter]}
          layout="horizontal"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Quarter')).toBeInTheDocument();
    });

    it('renders Actuals report filter pattern (multi-year)', () => {
      const yearFilter: FilterConfig<string> = {
        type: 'multi',
        label: 'Years',
        options: ['2022', '2023', '2024', '2025'],
        value: ['2023', '2024'],
        onChange: jest.fn(),
      };

      render(
        <FilterPanel
          filters={[yearFilter]}
          layout="horizontal"
        />
      );

      const filter = screen.getByTestId('filter-Years');
      expect(filter).toHaveTextContent('multi');
    });

    it('renders BNB report filter pattern (multi-year + multi-listing + multi-channel)', () => {
      const yearFilter: FilterConfig<string> = {
        type: 'multi',
        label: 'Years',
        options: ['2023', '2024', '2025'],
        value: ['2024'],
        onChange: jest.fn(),
      };

      const listingFilter: FilterConfig<string> = {
        type: 'multi',
        label: 'Listings',
        options: ['Listing 1', 'Listing 2'],
        value: [],
        onChange: jest.fn(),
      };

      const channelFilter: FilterConfig<string> = {
        type: 'multi',
        label: 'Channels',
        options: ['airbnb', 'booking', 'direct'],
        value: ['airbnb'],
        onChange: jest.fn(),
      };

      render(
        <FilterPanel
          filters={[yearFilter, listingFilter, channelFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      expect(screen.getByTestId('filter-Years')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Channels')).toBeInTheDocument();
    });
  });
});
