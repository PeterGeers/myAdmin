/**
 * BtwReport Component Tests
 * 
 * Tests the BTW (VAT) declaration report component with tenant handling.
 * Verifies tenant context integration, API calls, and user interactions.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BtwReport from './BtwReport';
import { useTenant } from '../../context/TenantContext';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';

// Mock dependencies
jest.mock('../../context/TenantContext');
jest.mock('../../services/tenantApiService');

// Mock Chakra UI components to avoid dependency issues
jest.mock('@chakra-ui/react', () => ({
  VStack: ({ children, ...props }: any) => <div data-testid="vstack" {...props}>{children}</div>,
  Alert: ({ children, ...props }: any) => <div data-testid="alert" {...props}>{children}</div>,
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  Card: ({ children, ...props }: any) => <div data-testid="card" {...props}>{children}</div>,
  CardBody: ({ children, ...props }: any) => <div data-testid="card-body" {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: any) => <div data-testid="card-header" {...props}>{children}</div>,
  Grid: ({ children, ...props }: any) => <div data-testid="grid" {...props}>{children}</div>,
  GridItem: ({ children, ...props }: any) => <div data-testid="grid-item" {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h2 data-testid="heading" {...props}>{children}</h2>,
  HStack: ({ children, ...props }: any) => <div data-testid="hstack" {...props}>{children}</div>,
  Select: ({ children, value, onChange, ...props }: any) => (
    <select data-testid="select" value={value} onChange={onChange} {...props}>{children}</select>
  ),
  Text: ({ children, ...props }: any) => <span data-testid="text" {...props}>{children}</span>,
  Button: ({ children, onClick, isDisabled, isLoading, ...props }: any) => (
    <button 
      data-testid="button" 
      onClick={onClick} 
      disabled={isDisabled || isLoading}
      {...props}
    >
      {children}
    </button>
  ),
  Box: ({ children, ...props }: any) => <div data-testid="box" {...props}>{children}</div>,
}));

jest.mock('../filters/FilterPanel', () => {
  return {
    FilterPanel: function MockFilterPanel(props: any) {
      return (
        <div data-testid="filter-panel">
          {props.filters.map((filter: any, index: number) => (
            <div key={index} data-testid={`filter-${filter.label.toLowerCase()}`}>
              <label>{filter.label}</label>
              <select
                data-testid={`${filter.label.toLowerCase()}-select`}
                value={filter.value}
                onChange={(e) => filter.onChange(e.target.value)}
              >
                {filter.options.map((opt: string) => (
                  <option key={opt} value={opt}>
                    {filter.getOptionLabel ? filter.getOptionLabel(opt) : opt}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      );
    }
  };
});

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockTenantAwareGet = tenantAwareGet as jest.MockedFunction<typeof tenantAwareGet>;
const mockTenantAwarePost = tenantAwarePost as jest.MockedFunction<typeof tenantAwarePost>;
const mockRequireTenant = requireTenant as jest.MockedFunction<typeof requireTenant>;

describe('BtwReport', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Default mock implementations
    mockUseTenant.mockReturnValue({
      currentTenant: 'GoodwinSolutions',
      availableTenants: ['GoodwinSolutions', 'TestTenant'],
      setCurrentTenant: jest.fn(),
      hasMultipleTenants: true
    });

    mockTenantAwareGet.mockResolvedValue({
      json: () => Promise.resolve({ success: true, years: ['2024', '2023'] })
    } as Response);

    mockRequireTenant.mockReturnValue('GoodwinSolutions');
  });

  describe('Tenant Context Integration', () => {
    it('uses useTenant hook for tenant context', () => {
      render(<BtwReport />);
      expect(mockUseTenant).toHaveBeenCalled();
    });

    it('initializes filters with current tenant', () => {
      render(<BtwReport />);
      expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
    });

    it('shows warning when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: ['GoodwinSolutions'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<BtwReport />);
      expect(screen.getByText(/no tenant selected/i)).toBeInTheDocument();
    });
  });

  describe('Pre-processing Validation', () => {
    it('validates tenant before generating report', async () => {
      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      fireEvent.click(generateButton);

      expect(mockRequireTenant).toHaveBeenCalled();
    });

    it('shows error when no tenant selected during report generation', async () => {
      mockRequireTenant.mockImplementation(() => {
        throw new Error('No tenant selected');
      });

      // Mock window.alert
      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});

      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Error: No tenant selected. Please select a tenant first.');
      });

      alertSpy.mockRestore();
    });
  });

  describe('Tenant-Aware API Calls', () => {
    it('uses tenant-aware API for fetching available years', () => {
      render(<BtwReport />);
      expect(mockTenantAwareGet).toHaveBeenCalledWith('/api/reports/available-years');
    });

    it('uses tenant-aware API for generating report', async () => {
      mockTenantAwarePost.mockResolvedValueOnce({
        json: () => Promise.resolve({
          success: true,
          html_report: '<div>Test Report</div>',
          transaction: { TransactionNumber: 'T001' }
        })
      } as Response);

      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(mockTenantAwarePost).toHaveBeenCalledWith(
          '/api/btw/generate-report',
          expect.objectContaining({
            administration: 'GoodwinSolutions',
            year: expect.any(String),
            quarter: '1'
          })
        );
      });
    });
  });

  describe('UI State Management', () => {
    it('disables generate button when no tenant selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: ['GoodwinSolutions'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      expect(generateButton).toBeDisabled();
    });

    it('shows quarter selection dropdown', () => {
      render(<BtwReport />);
      
      const quarterFilter = screen.getByTestId('filter-quarter');
      expect(quarterFilter).toBeInTheDocument();
      expect(screen.getByTestId('quarter-select')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('handles API errors during report generation', async () => {
      mockTenantAwarePost.mockResolvedValueOnce({
        json: () => Promise.resolve({
          success: false,
          error: 'Test error'
        })
      } as Response);

      // Mock window.alert
      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});

      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Failed to generate BTW report: Test error');
      });

      alertSpy.mockRestore();
    });

    it('handles network errors during report generation', async () => {
      mockTenantAwarePost.mockRejectedValueOnce(new Error('Network error'));

      // Mock window.alert and console.error
      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Error generating BTW report: Error: Network error');
      });

      alertSpy.mockRestore();
      consoleSpy.mockRestore();
    });
  });

  describe('Component Structure', () => {
    it('renders all required UI elements', () => {
      render(<BtwReport />);
      
      expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      expect(screen.getByText('Generate BTW Report')).toBeInTheDocument();
      expect(screen.getByText('Quarter')).toBeInTheDocument();
      expect(screen.getByText('BTW Declaration Instructions')).toBeInTheDocument();
    });

    it('shows report content after successful generation', async () => {
      mockTenantAwarePost.mockResolvedValueOnce({
        json: () => Promise.resolve({
          success: true,
          html_report: '<div>Test BTW Report Content</div>',
          transaction: { TransactionNumber: 'T001', TransactionDate: '2024-01-01' }
        })
      } as Response);

      render(<BtwReport />);
      
      const generateButton = screen.getByText('Generate BTW Report');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(screen.getByText('BTW Declaration Report')).toBeInTheDocument();
        expect(screen.getByText('Transaction Preview')).toBeInTheDocument();
        expect(screen.getByText('Save Transaction & Upload Report')).toBeInTheDocument();
      });
    });
  });
});