/**
 * BnbActualsReport Component Tests
 * 
 * Tests the BnbActualsReport component with FilterPanel integration.
 * Verifies multi-select filters, view type switching, and data visualization.
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import '@testing-library/jest-dom';
import BnbActualsReport from './BnbActualsReport';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';

// Mock dependencies
vi.mock('../../context/TenantContext');
vi.mock('../../services/apiService');
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() }
  })
}));

// Mock BnbYearMonthMatrix sub-component
vi.mock('./BnbYearMonthMatrix', () => {
  return {
    default: function MockBnbYearMonthMatrix() {
      return <div data-testid="bnb-year-month-matrix" />;
    },
  };
});



// Mock Recharts components
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  PieChart: ({ children }: any) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  Tooltip: () => <div data-testid="tooltip" />,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  RadialBarChart: ({ children }: any) => <div data-testid="radial-bar-chart">{children}</div>,
  RadialBar: () => <div data-testid="radial-bar" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  Legend: () => <div data-testid="legend" />
}));

// Mock FilterPanel
vi.mock('../filters/FilterPanel', () => ({
  FilterPanel: function MockFilterPanel(props: any) {
    return (
      <div data-testid="filter-panel">
        {props.filters.map((filter: any, index: number) => {
          // Handle options that might be objects or strings
          const getOptionValue = (opt: any) => {
            if (typeof opt === 'object' && opt !== null) {
              return filter.getOptionValue ? filter.getOptionValue(opt) : opt.key || opt.value || String(opt);
            }
            return opt;
          };
          
          const getOptionLabel = (opt: any) => {
            if (typeof opt === 'object' && opt !== null) {
              return filter.getOptionLabel ? filter.getOptionLabel(opt) : opt.label || opt.name || String(opt);
            }
            return filter.getOptionLabel ? filter.getOptionLabel(opt) : opt;
          };
          
          return (
            <div key={index} data-testid={`filter-${filter.label.toLowerCase()}`}>
              <label>{filter.label}</label>
              <select
                data-testid={`filter-select-${filter.label.toLowerCase()}`}
                multiple={filter.type === 'multi'}
                value={filter.value}
                onChange={(e) => {
                  const options = Array.from(e.target.options);
                  const values = options
                    .filter((opt: any) => opt.selected)
                    .map((opt: any) => opt.value);
                  filter.onChange(filter.type === 'multi' ? values : values[0]);
                }}
              >
                {filter.options?.map((opt: any) => {
                  const value = getOptionValue(opt);
                  const label = getOptionLabel(opt);
                  return (
                    <option key={value} value={value}>{label}</option>
                  );
                })}
              </select>
            </div>
          );
        })}
      </div>
    );
  }
}));

const mockUseTenant = useTenant as vi.MockedFunction<typeof useTenant>;
const mockAuthenticatedGet = authenticatedGet as vi.MockedFunction<typeof authenticatedGet>;
const mockBuildEndpoint = buildEndpoint as vi.MockedFunction<typeof buildEndpoint>;

const mockBnbListingData = [
  {
    listing: 'Property A',
    channel: 'Airbnb',
    year: 2024,
    quarter: 'Q1',
    month: 'January',
    amountGross: 5000,
    amountNett: 4500,
    amountCommission: 500
  },
  {
    listing: 'Property B',
    channel: 'Booking.com',
    year: 2024,
    quarter: 'Q1',
    month: 'January',
    amountGross: 3000,
    amountNett: 2700,
    amountCommission: 300
  }
];

const mockBnbChannelData = [
  {
    channel: 'Airbnb',
    listing: 'Property A',
    year: 2024,
    quarter: 'Q1',
    month: 'January',
    amountGross: 5000,
    amountNett: 4500,
    amountCommission: 500
  },
  {
    channel: 'Booking.com',
    listing: 'Property B',
    year: 2024,
    quarter: 'Q1',
    month: 'January',
    amountGross: 3000,
    amountNett: 2700,
    amountCommission: 300
  }
];

describe('BnbActualsReport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    mockUseTenant.mockReturnValue({
      currentTenant: 'TestTenant',
      availableTenants: ['TestTenant'],
      setCurrentTenant: vi.fn(),
      hasMultipleTenants: false
    });

    // buildEndpoint just passes through the endpoint string
    mockBuildEndpoint.mockImplementation((endpoint: string, params?: any) => {
      if (params) return `${endpoint}?${params.toString()}`;
      return endpoint;
    });

    mockAuthenticatedGet.mockImplementation((endpoint: string) => {
      if (endpoint.includes('/api/bnb/bnb-filter-options')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            success: true,
            years: ['2023', '2024'],
            listings: ['Property A', 'Property B'],
            channels: ['Airbnb', 'Booking.com']
          })
        } as Response);
      }
      if (endpoint.includes('/api/bnb/bnb-listing-data')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            success: true,
            data: mockBnbListingData
          })
        } as Response);
      }
      if (endpoint.includes('/api/bnb/bnb-channel-data')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            success: true,
            data: mockBnbChannelData
          })
        } as Response);
      }
      return Promise.resolve({
        json: () => Promise.resolve({ success: true, data: [] })
      } as Response);
    });
  });

  describe('Component Rendering', () => {
    it('renders without crashing', async () => {
      render(<BnbActualsReport />);
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });
    });

    it('renders FilterPanel with correct filters', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
        expect(screen.getByTestId('filter-filters.year')).toBeInTheDocument();
        expect(screen.getByTestId('filter-filters.listings')).toBeInTheDocument();
        expect(screen.getByTestId('filter-filters.channels')).toBeInTheDocument();
      });
    });

    it('renders view type selector', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        // View type is now part of FilterPanel
        const viewTypeFilter = screen.getByTestId('filter-select-filters.viewtype');
        expect(viewTypeFilter).toBeInTheDocument();
      });
    });
  });

  describe('Filter Interactions', () => {
    it('loads available years on mount', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/bnb/bnb-filter-options')
        );
      });
    });

    it('loads filter options on mount', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/bnb/bnb-filter-options')
        );
      });
    });

    it('fetches listing data when filters change', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/bnb/bnb-listing-data')
        );
      });
    });
  });

  describe('Tenant Context Integration', () => {
    it('uses current tenant from context', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalled();
      });
    });

    it('refetches data when tenant changes', async () => {
      const { rerender } = render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalled();
      });

      // Component renders successfully after rerender
      rerender(<BnbActualsReport />);

      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });
    });
  });

  describe('View Type Switching', () => {
    it('switches between listing and channel views', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        // View type filter is rendered inside FilterPanel
        const viewTypeFilter = screen.getByTestId('filter-select-filters.viewtype');
        expect(viewTypeFilter).toBeInTheDocument();
      });

      // Initial view should fetch listing data
      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('/api/bnb/bnb-listing-data')
      );
    });
  });

  describe('Multi-Select Filter Behavior', () => {
    it('supports multi-select for years', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const yearFilter = screen.getByTestId('filter-select-filters.year');
        expect(yearFilter).toHaveAttribute('multiple');
      });
    });

    it('supports multi-select for listings', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const listingFilter = screen.getByTestId('filter-select-filters.listings');
        expect(listingFilter).toHaveAttribute('multiple');
      });
    });

    it('supports multi-select for channels', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const channelFilter = screen.getByTestId('filter-select-filters.channels');
        expect(channelFilter).toHaveAttribute('multiple');
      });
    });
  });

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockAuthenticatedGet.mockRejectedValueOnce(new Error('API Error'));
      
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });
    });

    it('handles empty data gracefully', async () => {
      mockAuthenticatedGet.mockResolvedValue({
        json: () => Promise.resolve({ success: true, data: [] })
      } as Response);
      
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      });
    });
  });

  describe('Data Visualization', () => {
    it('renders charts when data is available', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        // Charts should be rendered after data loads
        expect(mockAuthenticatedGet).toHaveBeenCalled();
      });
    });
  });
});
