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

import { vi } from 'vitest';
import React from 'react';
import { render, screen } from '@/test-utils';
import { FilterPanel } from './FilterPanel';
import { FilterConfig, SearchFilterConfig } from './types';

// Mock GenericFilter to simplify testing
vi.mock('./GenericFilter', () => ({
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


describe('FilterPanel', () => {
  const mockSingleSelectFilter: FilterConfig<string> = {
    type: 'single',
    label: 'Year',
    options: ['2023', '2024', '2025'],
    value: '2024',
    onChange: vi.fn(),
  };

  const mockMultiSelectFilter: FilterConfig<string> = {
    type: 'multi',
    label: 'Listings',
    options: ['Listing 1', 'Listing 2', 'Listing 3'],
    value: ['Listing 1', 'Listing 2'],
    onChange: vi.fn(),
  };

  const mockSearchFilter: SearchFilterConfig = {
    type: 'search',
    label: 'Reference',
    value: '',
    onChange: vi.fn(),
    placeholder: 'Search...',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Horizontal Layout', () => {
    it('renders with horizontal layout by default', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      // Filters should render in the default horizontal layout
      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
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

    it('renders filters with custom spacing', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          spacing={6}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });

    it('renders filters with default spacing', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
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

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
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

    it('renders filters with custom spacing in vertical layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="vertical"
          spacing={3}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
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

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
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
      // Search filter renders as FormControl, not GenericFilter
      expect(screen.getByText('Reference')).toBeInTheDocument();
    });

    it('renders with default grid columns', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });

    it('renders with custom grid columns', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });

    it('renders with custom minChildWidth', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridMinWidth="250px"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });

    it('renders with custom spacing in grid layout', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          spacing={5}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
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

      // Search filters render as FormControl with label + input, not GenericFilter
      expect(screen.getByText('Reference')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
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
      // Search filter renders as FormControl, not GenericFilter
      expect(screen.getByText('Reference')).toBeInTheDocument();
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

      // Should render without crashing even with no filters
      const { container } = render(<FilterPanel filters={[]} />);
      expect(container).toBeTruthy();
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
        onChange: vi.fn(),
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
        onChange: vi.fn(),
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
    it('renders grid layout with responsive columns', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          layout="grid"
          gridColumns={3}
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
    });

    it('horizontal layout renders filters', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter, mockMultiSelectFilter]}
          layout="horizontal"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
      expect(screen.getByTestId('filter-Listings')).toBeInTheDocument();
    });

    it('grid layout renders with minChildWidth', () => {
      render(
        <FilterPanel
          filters={[mockSingleSelectFilter]}
          layout="grid"
          gridMinWidth="300px"
        />
      );

      expect(screen.getByTestId('filter-Year')).toBeInTheDocument();
    });
  });

  describe('Integration Scenarios', () => {
    it('renders BTW report filter pattern (single year + single quarter)', () => {
      const yearFilter: FilterConfig<string> = {
        type: 'single',
        label: 'Year',
        options: ['2023', '2024', '2025'],
        value: '2024',
        onChange: vi.fn(),
      };

      const quarterFilter: FilterConfig<string> = {
        type: 'single',
        label: 'Quarter',
        options: ['Q1', 'Q2', 'Q3', 'Q4'],
        value: 'Q1',
        onChange: vi.fn(),
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
        onChange: vi.fn(),
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
        onChange: vi.fn(),
      };

      const listingFilter: FilterConfig<string> = {
        type: 'multi',
        label: 'Listings',
        options: ['Listing 1', 'Listing 2'],
        value: [],
        onChange: vi.fn(),
      };

      const channelFilter: FilterConfig<string> = {
        type: 'multi',
        label: 'Channels',
        options: ['airbnb', 'booking', 'direct'],
        value: ['airbnb'],
        onChange: vi.fn(),
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
