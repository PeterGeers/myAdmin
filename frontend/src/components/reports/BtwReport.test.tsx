/**
 * BtwReport Component Tests
 * 
 * Tests the BTW (VAT) declaration report component with tenant handling.
 * Verifies tenant context integration, API calls, and user interactions.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import BtwReport from './BtwReport';
import { useTenant } from '../../context/TenantContext';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';

// Mock dependencies
jest.mock('../../context/TenantContext');
jest.mock('../../services/tenantApiService');

// Mock useTypedTranslation to return keys (avoids needing full i18n setup)
jest.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: jest.fn() }
  })
}));

// Mock Chakra UI components to avoid dependency issues
jest.mock('@chakra-ui/react', () => ({
  VStack: ({ children, ...props }: any) => <div data-testid="vstack" {...props}>{children}</div>,
  Alert: ({ children, status, ...props }: any) => <div data-testid="alert" {...props}>{children}</div>,
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  Card: ({ children, bg, ...props }: any) => <div data-testid="card" {...props}>{children}</div>,
  CardBody: ({ children, ...props }: any) => <div data-testid="card-body" {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: any) => <div data-testid="card-header" {...props}>{children}</div>,
  Grid: ({ children, templateColumns, ...props }: any) => <div data-testid="grid" {...props}>{children}</div>,
  GridItem: ({ children, colSpan, ...props }: any) => <div data-testid="grid-item" {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h2 data-testid="heading" {...props}>{children}</h2>,
  HStack: ({ children, ...props }: any) => <div data-testid="hstack" {...props}>{children}</div>,
  Select: ({ children, value, onChange, ...props }: any) => (
    <select data-testid="select" value={value} onChange={onChange} {...props}>{children}</select>
  ),
  Text: ({ children, ...props }: any) => <span data-testid="text" {...props}>{children}</span>,
  Button: ({ children, onClick, isDisabled, isLoading, colorScheme, ...props }: any) => (
    <button 
      data-testid="button" 
      onClick={onClick} 
      disabled={isDisabled || isLoading}
      {...props}
    >
      {children}
    </button>
  ),
  Box: ({ children, bg, ...props }: any) => <div data-testid="box" {...props}>{children}</div>,
}));

jest.mock('../filters/FilterPanel', () => {
  return {
    FilterPanel: function MockFilterPanel(props: any) {
      return (
        <div data-testid="filter-panel">
          {props.filters.map((filter: any, index: number) => (
            <div key={index} data-testid={`filter-${filter.label}`}>
              <label>{filter.label}</label>
              <select
                data-testid={`${filter.label}-select`}
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

// Helper to render and wait for async effects (fetchBtwAvailableYears on mount)
async function renderAndSettle(ui: React.ReactElement) {
  const result = render(ui);
  // Wait for the mount effect (fetchBtwAvailableYears) to settle
  await waitFor(() => {
    expect(mockTenantAwareGet).toHaveBeenCalled();
  });
  return result;
}

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
    it('uses useTenant hook for tenant context', async () => {
      await renderAndSettle(<BtwReport />);
      expect(mockUseTenant).toHaveBeenCalled();
    });

    it('initializes filters with current tenant', async () => {
      await renderAndSettle(<BtwReport />);
      expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
    });

    it('shows warning when no tenant is selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: ['GoodwinSolutions'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<BtwReport />);
      // With mocked t(), the key is returned as-is
      await waitFor(() => {
        expect(screen.getByText('common:messages.noTenantSelected')).toBeInTheDocument();
      });
    });
  });

  describe('Pre-processing Validation', () => {
    it('validates tenant before generating report', async () => {
      await renderAndSettle(<BtwReport />);
      
      // t('actions.generateReport') returns the key 'actions.generateReport'
      const generateButton = screen.getByText('actions.generateReport');
      fireEvent.click(generateButton);

      expect(mockRequireTenant).toHaveBeenCalled();
    });

    it('shows error when no tenant selected during report generation', async () => {
      mockRequireTenant.mockImplementation(() => {
        throw new Error('No tenant selected');
      });

      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});

      await renderAndSettle(<BtwReport />);
      
      const generateButton = screen.getByText('actions.generateReport');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Error: No tenant selected. Please select a tenant first.');
      });

      alertSpy.mockRestore();
    });
  });

  describe('Tenant-Aware API Calls', () => {
    it('uses tenant-aware API for fetching available years', async () => {
      await renderAndSettle(<BtwReport />);
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

      await renderAndSettle(<BtwReport />);
      
      const generateButton = screen.getByText('actions.generateReport');
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
    it('disables generate button when no tenant selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: ['GoodwinSolutions'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<BtwReport />);
      
      await waitFor(() => {
        const generateButton = screen.getByText('actions.generateReport');
        expect(generateButton).toBeDisabled();
      });
    });

    it('shows quarter selection dropdown', async () => {
      await renderAndSettle(<BtwReport />);
      
      // FilterPanel mock uses the raw label from t('filters.quarter') = 'filters.quarter'
      const quarterFilter = screen.getByTestId('filter-filters.quarter');
      expect(quarterFilter).toBeInTheDocument();
      expect(screen.getByTestId('filters.quarter-select')).toBeInTheDocument();
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

      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});

      await renderAndSettle(<BtwReport />);
      
      const generateButton = screen.getByText('actions.generateReport');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Failed to generate BTW report: Test error');
      });

      alertSpy.mockRestore();
    });

    it('handles network errors during report generation', async () => {
      mockTenantAwarePost.mockRejectedValueOnce(new Error('Network error'));

      const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

      await renderAndSettle(<BtwReport />);
      
      const generateButton = screen.getByText('actions.generateReport');
      fireEvent.click(generateButton);

      await waitFor(() => {
        expect(alertSpy).toHaveBeenCalledWith('Error generating BTW report: Error: Network error');
      });

      alertSpy.mockRestore();
      consoleSpy.mockRestore();
    });
  });

  describe('Component Structure', () => {
    it('renders all required UI elements', async () => {
      await renderAndSettle(<BtwReport />);
      
      expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      expect(screen.getByText('actions.generateReport')).toBeInTheDocument();
      // Quarter filter label from t('filters.quarter')
      expect(screen.getByText('filters.quarter')).toBeInTheDocument();
      // Instructions heading is hardcoded in the component
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

      await renderAndSettle(<BtwReport />);
      
      const generateButton = screen.getByText('actions.generateReport');
      fireEvent.click(generateButton);

      await waitFor(() => {
        // t('titles.btwReport') returns the key
        expect(screen.getByText('titles.btwReport')).toBeInTheDocument();
        // 'Transaction Preview' is hardcoded in the component
        expect(screen.getByText('Transaction Preview')).toBeInTheDocument();
        // Save button text: t('common:buttons.save') + ' & ' + t('export.download')
        expect(screen.getByText(/common:buttons.save/)).toBeInTheDocument();
      });
    });
  });
});
