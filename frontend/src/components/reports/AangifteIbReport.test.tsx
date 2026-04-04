/**
 * AangifteIbReport Component Tests
 * 
 * Tests the Aangifte IB (Income Tax Declaration) report component with tenant handling.
 * Verifies tenant context integration, API calls, and user interactions.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import AangifteIbReport from './AangifteIbReport';
import { useTenant } from '../../context/TenantContext';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';

// Mock dependencies
jest.mock('../../context/TenantContext');
jest.mock('../../services/tenantApiService');

// Mock useTypedTranslation to return keys as-is (avoids needing full i18n setup)
jest.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: jest.fn() }
  })
}));

jest.mock('../../config', () => ({
  buildApiUrl: jest.fn((path: string, params?: URLSearchParams) => {
    return params ? `${path}?${params.toString()}` : path;
  })
}));

// Mock Chakra UI components with proper prop destructuring (strip colorScheme, bg, etc.)
jest.mock('@chakra-ui/react', () => ({
  VStack: ({ children, ...props }: any) => <div data-testid="vstack" {...props}>{children}</div>,
  Alert: ({ children, status, ...props }: any) => <div data-testid="alert" {...props}>{children}</div>,
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  Card: ({ children, bg, ...props }: any) => <div data-testid="card" {...props}>{children}</div>,
  CardBody: ({ children, ...props }: any) => <div data-testid="card-body" {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: any) => <div data-testid="card-header" {...props}>{children}</div>,
  Heading: ({ children, ...props }: any) => <h2 data-testid="heading" {...props}>{children}</h2>,
  HStack: ({ children, ...props }: any) => <div data-testid="hstack" {...props}>{children}</div>,
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
  Progress: ({ value, colorScheme, bg, ...props }: any) => <div data-testid="progress" data-value={value} {...props} />,
  Table: ({ children, ...props }: any) => <table data-testid="table" {...props}>{children}</table>,
  TableContainer: ({ children, ...props }: any) => <div data-testid="table-container" {...props}>{children}</div>,
  Tbody: ({ children, ...props }: any) => <tbody data-testid="tbody" {...props}>{children}</tbody>,
  Td: ({ children, isNumeric, ...props }: any) => <td data-testid="td" {...props}>{children}</td>,
  Th: ({ children, isNumeric, ...props }: any) => <th data-testid="th" {...props}>{children}</th>,
  Thead: ({ children, ...props }: any) => <thead data-testid="thead" {...props}>{children}</thead>,
  Tr: ({ children, bg, _hover, ...props }: any) => <tr data-testid="tr" {...props}>{children}</tr>,
  useToast: () => jest.fn(),
}));

// Mock FilterPanel
jest.mock('../filters/FilterPanel', () => {
  return {
    FilterPanel: function MockFilterPanel(props: any) {
      return (
        <div data-testid="filter-panel">
          {props.filters.map((filter: any, index: number) => (
            <div key={index} data-testid={`filter-${filter.label}`}>
              <label>{filter.label}</label>
            </div>
          ))}
        </div>
      );
    }
  };
});

// Mock YearEndClosureSection to avoid its internal Chakra dependencies
jest.mock('../YearEndClosureSection', () => {
  return function MockYearEndClosureSection() {
    return <div data-testid="year-end-closure-section">YearEndClosureSection</div>;
  };
});

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockTenantAwareGet = tenantAwareGet as jest.MockedFunction<typeof tenantAwareGet>;
const mockTenantAwarePost = tenantAwarePost as jest.MockedFunction<typeof tenantAwarePost>;
const mockRequireTenant = requireTenant as jest.MockedFunction<typeof requireTenant>;

// Helper to render and wait for async mount effects (fetchAangifteIbData)
async function renderAndSettle(ui: React.ReactElement) {
  const result = render(ui);
  await waitFor(() => {
    expect(mockTenantAwareGet).toHaveBeenCalled();
  });
  return result;
}

describe('AangifteIbReport', () => {
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
      json: () => Promise.resolve({ 
        success: true, 
        data: [],
        available_years: ['2024', '2023'] 
      })
    } as Response);

    mockRequireTenant.mockReturnValue('GoodwinSolutions');
  });

  describe('Tenant Context Integration', () => {
    it('uses useTenant hook for tenant context', async () => {
      await renderAndSettle(<AangifteIbReport />);
      expect(mockUseTenant).toHaveBeenCalled();
    });

    it('shows warning when no tenant is selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: ['GoodwinSolutions'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<AangifteIbReport />);
      // With mocked t(), the key is returned as-is
      await waitFor(() => {
        expect(screen.getByText('common:messages.noTenantSelected')).toBeInTheDocument();
      });
    });
  });

  describe('Component Structure', () => {
    it('renders all required UI elements', async () => {
      await renderAndSettle(<AangifteIbReport />);
      
      expect(screen.getByTestId('filter-panel')).toBeInTheDocument();
      // t('actions.generateReport') returns the key
      expect(screen.getByText('actions.generateReport')).toBeInTheDocument();
      // t('export.exportToExcel') returns the key
      expect(screen.getByText('export.exportToExcel')).toBeInTheDocument();
      // t('titles.aangifteIb') returns the key
      expect(screen.getByText('titles.aangifteIb')).toBeInTheDocument();
    });
  });

  describe('Security Requirements', () => {
    it('follows tenant isolation principles', async () => {
      await renderAndSettle(<AangifteIbReport />);
      
      // Component should use tenant context
      expect(mockUseTenant).toHaveBeenCalled();
      
      // Should have tenant validation in place
      expect(mockTenantAwareGet).toHaveBeenCalled();
    });

    it('disables functionality when no tenant selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: ['GoodwinSolutions'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<AangifteIbReport />);
      
      // Should show warning
      await waitFor(() => {
        expect(screen.getByTestId('alert')).toBeInTheDocument();
      });
    });
  });
});
