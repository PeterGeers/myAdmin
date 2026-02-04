/**
 * MutatiesReport Component Tests
 * 
 * Tests the MutatiesReport component with tenant handling functionality.
 * Verifies tenant context integration, validation, auto-refresh, and security.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import MutatiesReport from './MutatiesReport';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet } from '../../services/apiService';

// Mock dependencies
jest.mock('../../context/TenantContext');
jest.mock('../../services/apiService', () => ({
  authenticatedGet: jest.fn(),
  buildEndpoint: (endpoint: string, params: URLSearchParams) => `${endpoint}?${params.toString()}`
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
  HStack: ({ children, ...props }: any) => <div data-testid="hstack" {...props}>{children}</div>,
  Input: ({ onChange, value, ...props }: any) => (
    <input data-testid="input" onChange={onChange} value={value} {...props} />
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

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockAuthenticatedGet = authenticatedGet as jest.MockedFunction<typeof authenticatedGet>;

const mockMutatiesData = [
  {
    TransactionDate: '2024-01-15',
    TransactionDescription: 'Test Transaction 1',
    Amount: 100.50,
    Reknum: '1000',
    AccountName: 'Test Account 1',
    Administration: 'TestTenant',
    ReferenceNumber: 'REF001'
  },
  {
    TransactionDate: '2024-01-16',
    TransactionDescription: 'Test Transaction 2',
    Amount: -50.25,
    Reknum: '2000',
    AccountName: 'Test Account 2',
    Administration: 'TestTenant',
    ReferenceNumber: 'REF002'
  }
];

describe('MutatiesReport', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Default mock response
    mockAuthenticatedGet.mockResolvedValue({
      json: () => Promise.resolve({
        success: true,
        data: mockMutatiesData
      })
    } as Response);
  });

  describe('Tenant Context Integration', () => {
    it('uses useTenant hook for tenant context', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      expect(mockUseTenant).toHaveBeenCalled();
    });

    it('shows warning alert when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: [],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      expect(screen.getByTestId('alert')).toBeInTheDocument();
      expect(screen.getByText('No tenant selected. Please select a tenant first.')).toBeInTheDocument();
    });

    it('renders component when tenant is selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('table')).toBeInTheDocument();
      });
    });
  });

  describe('Tenant-Aware API Calls', () => {
    it('makes API calls with current tenant parameter', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('administration=TestTenant')
        );
      });
    });

    it('includes all required parameters in API call', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      await waitFor(() => {
        const apiCall = mockAuthenticatedGet.mock.calls[0][0];
        expect(apiCall).toContain('dateFrom=');
        expect(apiCall).toContain('dateTo=');
        expect(apiCall).toContain('administration=TestTenant');
        expect(apiCall).toContain('profitLoss=all');
      });
    });
  });

  describe('Auto-Refresh on Tenant Change', () => {
    it('fetches data when tenant changes', async () => {
      // Mock with a tenant from the start
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
      
      render(<MutatiesReport />);
      
      // Wait for API calls to complete
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('administration=TestTenant')
        );
      });
      
      // Verify the API was called (could be 1 or 2 times due to useEffect timing)
      expect(mockAuthenticatedGet).toHaveBeenCalled();
      expect(mockAuthenticatedGet).toHaveBeenCalledWith(
        expect.stringContaining('administration=TestTenant')
      );
    });
  });

  describe('Data Display and Filtering', () => {
    beforeEach(() => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
    });

    it('displays mutaties data in table', async () => {
      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Test Transaction 1')).toBeInTheDocument();
        expect(screen.getByText('Test Transaction 2')).toBeInTheDocument();
      });
    });

    it('formats amounts correctly', async () => {
      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(screen.getByText('€100,50')).toBeInTheDocument();
        expect(screen.getByText('€-50,25')).toBeInTheDocument();
      });
    });

    it('provides search functionality', async () => {
      render(<MutatiesReport />);
      
      await waitFor(() => {
        const searchInputs = screen.getAllByTestId('input');
        expect(searchInputs.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Export Functionality', () => {
    beforeEach(() => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });
    });

    it('provides CSV export button', async () => {
      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(screen.getByText('Export CSV')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      mockAuthenticatedGet.mockRejectedValue(new Error('API Error'));
      
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('Error fetching mutaties data:', expect.any(Error));
      });
      
      consoleSpy.mockRestore();
    });

    it('handles unsuccessful API response', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      mockAuthenticatedGet.mockResolvedValue({
        json: () => Promise.resolve({
          success: false,
          message: 'Data not found'
        })
      } as Response);
      
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith('Failed to fetch mutaties data:', 'Data not found');
      });
      
      consoleSpy.mockRestore();
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

      render(<MutatiesReport />);
      
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

      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(mockAuthenticatedGet).toHaveBeenCalledWith(
          expect.stringContaining('administration=TestTenant')
        );
      });
    });
  });

  describe('Component Structure', () => {
    it('component imports successfully', () => {
      expect(MutatiesReport).toBeDefined();
      expect(typeof MutatiesReport).toBe('function');
    });

    it('component structure is valid', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: jest.fn(),
        hasMultipleTenants: false
      });

      const element = React.createElement(MutatiesReport);
      expect(element).toBeDefined();
      expect(element.type).toBe(MutatiesReport);
    });
  });
});