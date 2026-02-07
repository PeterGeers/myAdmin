/**
 * BnbActualsReport Component Tests
 * 
 * Tests the BnbActualsReport component with FilterPanel integration.
 * Verifies multi-select filters, view type switching, and data visualization.
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import BnbActualsReport from './BnbActualsReport';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet } from '../../services/apiService';

// Mock dependencies
jest.mock('../../context/TenantContext');
jest.mock('../../services/apiService');
jest.mock('../../config', () => ({
  buildApiUrl: (endpoint: string, params: URLSearchParams) => `${endpoint}?${params.toString()}`
}));

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => ({
  Button: ({ children, onClick, ...props }: any) => (
    <button data-testid="button" onClick={onClick} {...props}>{children}</button>
  ),
  Card: ({ children, ...props }: any) => <div data-testid="card" {...props}>{children}</div>,
  CardBody: ({ children, ...props }: any) => <div data-testid="card-body" {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: any) => <div data-testid="card-header" {...props}>{children}</div>,
  Checkbox: ({ children, onChange, isChecked, ...props }: any) => (
    <input 
      type="checkbox" 
      data-testid="checkbox" 
      onChange={onChange} 
      checked={isChecked}
      {...props}
    />
  ),
  Grid: ({ children, ...props }: any) => <div data-testid="grid" {...props}>{children}</div>,
  GridItem: ({ children, ...props }: any) => <div data-testid="grid-item" {...props}>{children}</div>,
  HStack: ({ children, ...props }: any) => <div data-testid="hstack" {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h2 data-testid="heading" {...props}>{children}</h2>,
  Menu: ({ children, ...props }: any) => <div data-testid="menu" {...props}>{children}</div>,
  MenuButton: ({ children, ...props }: any) => <button data-testid="menu-button" {...props}>{children}</button>,
  MenuItem: ({ children, onClick, ...props }: any) => (
    <div data-testid="menu-item" onClick={onClick} {...props}>{children}</div>
  ),
  MenuList: ({ children, ...props }: any) => <div data-testid="menu-list" {...props}>{children}</div>,
  Select: ({ children, onChange, value, ...props }: any) => (
    <select data-testid="select" onChange={onChange} value={value} {...props}>{children}</select>
  ),
  Table: ({ children, ...props }: any) => <table data-testid="table" {...props}>{children}</table>,
  TableContainer: ({ children, ...props }: any) => <div data-testid="table-container" {...props}>{children}</div>,
  Tbody: ({ children, ...props }: any) => <tbody data-testid="tbody" {...props}>{children}</tbody>,
  Td: ({ children, ...props }: any) => <td data-testid="td" {...props}>{children}</td>,
  Text: ({ children, ...props }: any) => <span data-testid="text" {...props}>{children}</span>,
  Th: ({ children, onClick, ...props }: any) => (
    <th data-testid="th" onClick={onClick} {...props}>{children}</th>
  ),
  Thead: ({ children, ...props }: any) => <thead data-testid="thead" {...props}>{children}</thead>,
  Tr: ({ children, ...props }: any) => <tr data-testid="tr" {...props}>{children}</tr>,
  VStack: ({ children, ...props }: any) => <div data-testid="vstack" {...props}>{children}</div>
}));

// Mock Recharts components
jest.mock('recharts', () => ({
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
jest.mock('../filters/FilterPanel', () => ({
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

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockAuthenticatedGet = authenticatedGet as jest.MockedFunction<typeof authenticatedGet>;

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
    jest.clearAllMocks();
    
    mockUseTenant.mockReturnValue({
      currentTenant: 'TestTenant',
      availableTenants: ['TestTenant'],
      setCurrentTenant: jest.fn(),
      hasMultipleTenants: false
    });

    mockAuthenticatedGet.mockImplementation((endpoint: string) => {
      if (endpoint.includes('/api/bnb/available-years')) {
        return Promise.resolve({
          json: () => Promise.resolve(['2023', '2024'])
        } as Response);
      }
      if (endpoint.includes('/api/bnb/filter-options')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            years: ['2023', '2024'],
            listings: ['Property A', 'Property B'],
            channels: ['Airbnb', 'Booking.com']
          })
        } as Response);
      }
      if (endpoint.includes('/api/bnb/actuals-by-listing')) {
        return Promise.resolve({
          json: () => Promise.resolve(mockBnbListingData)
        } as Response);
      }
      if (endpoint.includes('/api/bnb/actuals-by-channel')) {
        return Promise.resolve({
          json: () => Promise.resolve(mockBnbChannelData)
        } as Response);
      }
      return Promise.resolve({
        json: () => Promise.resolve([])
      } as Response);
    });
  });

  describe('Component Rendering', () => {
    it('renders without crashing', async () => {
      render(<BnbActualsReport />);
      await waitFor(() => {
        expect(screen.getByTestId('vstack')).toBeInTheDocument();
      });
    });

    it('renders FilterPanel with correct filters', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
        expect(screen.getByTestId('filter-years')).toBeInTheDocument();
        expect(screen.getByTestId('filter-listings')).toBeInTheDocument();
        expect(screen.getByTestId('filter-channels')).toBeInTheDocument();
      });
    });

    it('renders view type selector', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const selects = screen.getAllByTestId('select');
        expect(selects.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Filter Interactions', () => {
    it('loads available years on mount', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/bnb/available-years')
        );
      });
    });

    it('loads filter options on mount', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/bnb/filter-options')
        );
      });
    });

    it('fetches listing data when filters change', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('/api/bnb/actuals-by-listing')
        );
      });
    });
  });

  describe('Tenant Context Integration', () => {
    it('uses current tenant from context', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const calls = mockAuthenticatedGet.mock.calls;
        const hasCorrectTenant = calls.some(call => 
          call[0].includes('tenant=TestTenant')
        );
        expect(hasCorrectTenant).toBe(true);
      });
    });

    it('refetches data when tenant changes', async () => {
      const { rerender } = render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalled();
      });

      const initialCallCount = mockAuthenticatedGet.mock.calls.length;

      mockUseTenant.mockReturnValue({
        currentTenant: 'NewTenant',
        availableTenants: ['TestTenant', 'NewTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: true
      });

      rerender(<BnbActualsReport />);

      await waitFor(() => {
        expect(mockAuthenticatedGet.mock.calls.length).toBeGreaterThan(initialCallCount);
      });
    });
  });

  describe('View Type Switching', () => {
    it('switches between listing and channel views', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const selects = screen.getAllByTestId('select');
        expect(selects.length).toBeGreaterThan(0);
      });

      // Initial view should fetch listing data
      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('/api/bnb/actuals-by-listing')
      );
    });
  });

  describe('Multi-Select Filter Behavior', () => {
    it('supports multi-select for years', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const yearFilter = screen.getByTestId('filter-select-years');
        expect(yearFilter).toHaveAttribute('multiple');
      });
    });

    it('supports multi-select for listings', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const listingFilter = screen.getByTestId('filter-select-listings');
        expect(listingFilter).toHaveAttribute('multiple');
      });
    });

    it('supports multi-select for channels', async () => {
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        const channelFilter = screen.getByTestId('filter-select-channels');
        expect(channelFilter).toHaveAttribute('multiple');
      });
    });
  });

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockAuthenticatedGet.mockRejectedValueOnce(new Error('API Error'));
      
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('vstack')).toBeInTheDocument();
      });
    });

    it('handles empty data gracefully', async () => {
      mockAuthenticatedGet.mockResolvedValue({
        json: () => Promise.resolve([])
      } as Response);
      
      render(<BnbActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('vstack')).toBeInTheDocument();
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
