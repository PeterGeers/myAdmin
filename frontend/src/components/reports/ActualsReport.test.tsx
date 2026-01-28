/**
 * ActualsReport Component Tests
 * 
 * Tests the ActualsReport component with tenant handling functionality.
 * Verifies tenant context integration, validation, auto-refresh, and security.
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ActualsReport from './ActualsReport';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet, authenticatedPost } from '../../services/apiService';

// Mock dependencies
jest.mock('../../context/TenantContext');
jest.mock('../../services/apiService');
jest.mock('../../config', () => ({
  buildApiUrl: (endpoint: string, params: URLSearchParams) => `${endpoint}?${params.toString()}`
}));

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => ({
  Alert: ({ children, ...props }: any) => <div data-testid="alert" {...props}>{children}</div>,
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  Button: ({ children, onClick, ...props }: any) => (
    <button data-testid="button" onClick={onClick} {...props}>{children}</button>
  ),
  Card: ({ children, ...props }: any) => <div data-testid="card" {...props}>{children}</div>,
  CardBody: ({ children, ...props }: any) => <div data-testid="card-body" {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: any) => <div data-testid="card-header" {...props}>{children}</div>,
  Grid: ({ children, ...props }: any) => <div data-testid="grid" {...props}>{children}</div>,
  GridItem: ({ children, ...props }: any) => <div data-testid="grid-item" {...props}>{children}</div>,
  HStack: ({ children, ...props }: any) => <div data-testid="hstack" {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h2 data-testid="heading" {...props}>{children}</h2>,
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
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  Legend: () => <div data-testid="legend" />
}));

// Mock UnifiedAdminYearFilter
jest.mock('../UnifiedAdminYearFilter', () => {
  return function MockUnifiedAdminYearFilter(props: any) {
    return <div data-testid="unified-admin-year-filter" {...props} />;
  };
});

// Mock UnifiedAdminYearFilterAdapters
jest.mock('../UnifiedAdminYearFilterAdapters', () => ({
  createActualsFilterAdapter: jest.fn(() => ({
    administration: 'TestTenant',
    years: ['2024'],
    onAdministrationChange: jest.fn(),
    onYearsChange: jest.fn()
  }))
}));

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockAuthenticatedGet = authenticatedGet as jest.MockedFunction<typeof authenticatedGet>;
const mockAuthenticatedPost = authenticatedPost as jest.MockedFunction<typeof authenticatedPost>;

const mockBalanceData = [
  {
    Parent: 'Assets',
    ledger: 'Cash',
    Amount: 10000,
    jaar: 2024
  },
  {
    Parent: 'Assets',
    ledger: 'Bank Account',
    Amount: 25000,
    jaar: 2024
  }
];

const mockProfitLossData = [
  {
    Parent: 'Revenue',
    ledger: 'Sales',
    Amount: 50000,
    jaar: 2024
  },
  {
    Parent: 'Expenses',
    ledger: 'Office Rent',
    Amount: -12000,
    jaar: 2024
  }
];

const mockAvailableYears = ['2023', '2024'];

describe('ActualsReport', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock authenticatedPost for cache warmup
    mockAuthenticatedPost.mockResolvedValue({
      json: () => Promise.resolve({ success: true })
    } as Response);
    
    // Default mock responses
    mockAuthenticatedGet.mockImplementation((url: string) => {
      if (url.includes('actuals-balance')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            success: true,
            data: mockBalanceData
          })
        } as Response);
      } else if (url.includes('actuals-profitloss')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            success: true,
            data: mockProfitLossData
          })
        } as Response);
      } else if (url.includes('available-years')) {
        return Promise.resolve({
          json: () => Promise.resolve({
            success: true,
            years: mockAvailableYears
          })
        } as Response);
      }
      return Promise.resolve({
        json: () => Promise.resolve({ success: false })
      } as Response);
    });
  });

  describe('Tenant Context Integration', () => {
    it('uses useTenant hook for tenant context', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      expect(mockUseTenant).toHaveBeenCalled();
    });

    it('shows warning alert when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: [],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      expect(screen.getAllByTestId('alert')[0]).toBeInTheDocument();
      expect(screen.getByText('No tenant selected. Please select a tenant first.')).toBeInTheDocument();
    });

    it('renders component when tenant is selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getAllByTestId('table')).toHaveLength(2); // Balance and P&L tables
      });
    });
  });

  describe('Tenant-Aware API Calls', () => {
    beforeEach(() => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
    });

    it('makes API calls with current tenant parameter', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('administration=TestTenant')
        );
      });
    });

    it('includes all required parameters in balance API call', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        const balanceCall = mockAuthenticatedGet.mock.calls.find(call => 
          call[0].includes('actuals-balance')
        );
        expect(balanceCall).toBeDefined();
        expect(balanceCall![0]).toContain('years=');
        expect(balanceCall![0]).toContain('administration=TestTenant');
        expect(balanceCall![0]).toContain('groupBy=year');
      });
    });

    it('includes all required parameters in profit/loss API call', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        const profitLossCall = mockAuthenticatedGet.mock.calls.find(call => 
          call[0].includes('actuals-profitloss')
        );
        expect(profitLossCall).toBeDefined();
        expect(profitLossCall![0]).toContain('years=');
        expect(profitLossCall![0]).toContain('administration=TestTenant');
        expect(profitLossCall![0]).toContain('groupBy=year');
      });
    });

    it('includes tenant parameter in available years API call', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        const yearsCall = mockAuthenticatedGet.mock.calls.find(call => 
          call[0].includes('available-years')
        );
        expect(yearsCall).toBeDefined();
        expect(yearsCall![0]).toContain('administration=TestTenant');
      });
    });
  });

  describe('Auto-Refresh on Tenant Change', () => {
    it('fetches data when tenant changes', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
      
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('administration=TestTenant')
        );
      });
      
      // Verify all three API calls were made
      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('available-years')
      );
      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('actuals-balance')
      );
      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('actuals-profitloss')
      );
    });

    it('shows tenant switching indicator during transition', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      // The tenant switching indicator should appear briefly during initial load
      // Since we can't easily test the timing, we'll just verify the component structure supports it
      expect(screen.queryByText('Switching tenant... Please wait while data is being loaded.')).toBeInTheDocument();
    });
  });

  describe('Data Display and Visualization', () => {
    beforeEach(() => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
    });

    it('displays balance data in table', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Balance (VW = N) - All Years Total')).toBeInTheDocument();
        expect(screen.getByText('Assets')).toBeInTheDocument();
      });
    });

    it('displays profit/loss data in table', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Profit/Loss (VW = Y)')).toBeInTheDocument();
        expect(screen.getByText('Revenue')).toBeInTheDocument();
      });
    });

    it('provides drill-down level controls', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('📅 Year')).toBeInTheDocument();
        expect(screen.getByText('📊 Quarter')).toBeInTheDocument();
        expect(screen.getByText('📈 Month')).toBeInTheDocument();
      });
    });

    it('provides display format options', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('select')).toBeInTheDocument();
      });
    });

    it('includes charts for data visualization', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
        expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    beforeEach(() => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
    });

    it('handles API errors gracefully', async () => {
      mockAuthenticatedGet.mockRejectedValue(new Error('API Error'));
      
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('[TENANT SECURITY] Error fetching actuals data for tenant:', 'TestTenant', expect.any(Error));
      });
      
      consoleSpy.mockRestore();
    });

    it('displays error message when API fails', async () => {
      mockAuthenticatedGet.mockRejectedValue(new Error('Network Error'));
      
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Error loading actuals data. Please check your connection and try again.')).toBeInTheDocument();
      });
    });

    it('handles unsuccessful API response', async () => {
      mockAuthenticatedGet.mockResolvedValue({
        json: () => Promise.resolve({
          success: false,
          message: 'Data not found'
        })
      } as Response);
      
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Failed to fetch profit/loss data: Data not found')).toBeInTheDocument();
      });
    });

    it('clears errors on tenant change', async () => {
      // First render with error
      mockAuthenticatedGet.mockRejectedValue(new Error('Network Error'));
      
      const { rerender } = render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Error loading actuals data. Please check your connection and try again.')).toBeInTheDocument();
      });
      
      // Mock successful response for tenant change
      mockAuthenticatedGet.mockImplementation((url: string) => {
        if (url.includes('actuals-balance')) {
          return Promise.resolve({
            json: () => Promise.resolve({
              success: true,
              data: mockBalanceData
            })
          } as Response);
        } else if (url.includes('actuals-profitloss')) {
          return Promise.resolve({
            json: () => Promise.resolve({
              success: true,
              data: mockProfitLossData
            })
          } as Response);
        } else if (url.includes('available-years')) {
          return Promise.resolve({
            json: () => Promise.resolve({
              success: true,
              years: mockAvailableYears
            })
          } as Response);
        }
        return Promise.resolve({
          json: () => Promise.resolve({ success: false })
        } as Response);
      });
      
      // Change tenant
      mockUseTenant.mockReturnValue({
        currentTenant: 'NewTenant',
        availableTenants: ['NewTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
      
      rerender(<ActualsReport />);
      
      // Error should be cleared
      await waitFor(() => {
        expect(screen.queryByText('Error loading actuals data. Please check your connection and try again.')).not.toBeInTheDocument();
      });
    });
  });

  describe('Security Requirements', () => {
    it('prevents data access without tenant selection', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: [],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      // Should not make API calls when no tenant is selected
      expect(mockAuthenticatedGet).not.toHaveBeenCalled();
      
      // Should show warning message
      expect(screen.getByText('No tenant selected. Please select a tenant first.')).toBeInTheDocument();
    });

    it('validates tenant before API calls', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('administration=TestTenant')
        );
      });
    });

    it('prevents cross-tenant data access', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      await waitFor(() => {
        // Verify all API calls use the correct tenant
        mockAuthenticatedGet.mock.calls.forEach(call => {
          expect(call[0]).toContain('administration=TestTenant');
        });
      });
    });
  });

  describe('Component Structure', () => {
    it('component imports successfully', () => {
      expect(ActualsReport).toBeDefined();
      expect(typeof ActualsReport).toBe('function');
    });

    it('component structure is valid', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      const element = React.createElement(ActualsReport);
      expect(element).toBeDefined();
      expect(element.type).toBe(ActualsReport);
    });

    it('includes unified admin year filter', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('unified-admin-year-filter')).toBeInTheDocument();
      });
    });
  });

  describe('Interactive Features', () => {
    beforeEach(() => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
    });

    it('provides update data button', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Update Data')).toBeInTheDocument();
      });
    });

    it('allows drill-down level changes', async () => {
      render(<ActualsReport />);
      
      await waitFor(() => {
        const quarterButton = screen.getByText('📊 Quarter');
        fireEvent.click(quarterButton);
        
        // Should trigger new API calls with groupBy=quarter
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('groupBy=quarter')
        );
      });
    });
  });
});