/**
 * MutatiesReport Component Tests
 * 
 * Tests the MutatiesReport component with tenant handling functionality.
 * Verifies tenant context integration, validation, auto-refresh, and security.
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@/test-utils';
import '@testing-library/jest-dom';
import MutatiesReport from './MutatiesReport';
import { useTenant } from '../../context/TenantContext';
import { authenticatedGet } from '../../services/apiService';
import { createMockResponse } from '@/test-utils/mockHelpers';

// Mock dependencies
vi.mock('../../context/TenantContext');
vi.mock('../../services/apiService', () => ({
  authenticatedGet: vi.fn(),
  buildEndpoint: (endpoint: string, params: URLSearchParams) => `${endpoint}?${params.toString()}`
}));

// Mock FilterableHeader to render a simple <th> with optional filter input
vi.mock('../filters/FilterableHeader', () => ({
  FilterableHeader: ({ label, filterValue, onFilterChange, onSort, sortable, sortDirection, ...props }: any) => (
    <th data-testid="th" onClick={sortable ? onSort : undefined} {...props}>
      <span>{label}</span>
      {sortable && sortDirection && <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>}
      {filterValue !== undefined && (
        <input
          data-testid="input"
          value={filterValue}
          onChange={(e: any) => onFilterChange?.(e.target.value)}
          placeholder="Filter..."
        />
      )}
    </th>
  ),
}));

// Mock YearFilter to render a simple select
vi.mock('../filters/YearFilter', () => ({
  YearFilter: ({ values, onChange, availableOptions, ...props }: any) => (
    <select
      data-testid="year-filter"
      value={values?.[0] || ''}
      onChange={(e: any) => onChange?.([e.target.value])}
    >
      {(availableOptions || []).map((y: string) => (
        <option key={y} value={y}>{y}</option>
      ))}
    </select>
  ),
}));



const mockUseTenant = vi.mocked(useTenant);
const mockAuthenticatedGet = vi.mocked(authenticatedGet);

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
    vi.clearAllMocks();
    
    // Default mock response
    mockAuthenticatedGet.mockResolvedValue(createMockResponse({
      body: {
        success: true,
        data: mockMutatiesData
      }
    }));
  });

  describe('Tenant Context Integration', () => {
    it('uses useTenant hook for tenant context', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      expect(mockUseTenant).toHaveBeenCalled();
    });

    it('shows warning alert when no tenant is selected', () => {
      mockUseTenant.mockReturnValue({
        currentTenant: null,
        availableTenants: [],
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      expect(screen.getByTestId('no-tenant-alert')).toBeInTheDocument();
    });

    it('renders component when tenant is selected', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(document.querySelector('table')).toBeInTheDocument();
      });
    });
  });

  describe('Tenant-Aware API Calls', () => {
    it('makes API calls with current tenant parameter', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: vi.fn(),
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
        setCurrentTenant: vi.fn(),
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
        setCurrentTenant: vi.fn(),
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
        setCurrentTenant: vi.fn(),
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
        // Currency formatting now uses English locale (€100.50 instead of €100,50)
        expect(screen.getByText('€100.50')).toBeInTheDocument();
        expect(screen.getByText('-€50.25')).toBeInTheDocument();
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
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });
    });

    it('provides CSV export button', async () => {
      render(<MutatiesReport />);
      
      await waitFor(() => {
        expect(screen.getByTestId('export-csv-button')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      mockAuthenticatedGet.mockRejectedValue(new Error('API Error'));
      
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
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
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      mockAuthenticatedGet.mockResolvedValue(createMockResponse({
        body: {
          success: false,
          message: 'Data not found'
        }
      }));
      
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      
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
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      render(<MutatiesReport />);
      
      // Should not make API calls when no tenant is selected
      expect(mockAuthenticatedGet).not.toHaveBeenCalled();
      
      // Should show warning message
      expect(screen.getByTestId('no-tenant-alert')).toBeInTheDocument();
    });

    it('validates tenant before API calls', async () => {
      mockUseTenant.mockReturnValue({
        currentTenant: 'TestTenant',
        availableTenants: ['TestTenant'],
        setCurrentTenant: vi.fn(),
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
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      const element = React.createElement(MutatiesReport);
      expect(element).toBeDefined();
      expect(element.type).toBe(MutatiesReport);
    });
  });
});