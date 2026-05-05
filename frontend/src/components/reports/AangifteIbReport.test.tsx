/**
 * AangifteIbReport Component Tests
 * 
 * Tests the Aangifte IB (Income Tax Declaration) report component with tenant handling.
 * Verifies tenant context integration, API calls, and user interactions.
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@/test-utils';
import '@testing-library/jest-dom';
import AangifteIbReport from './AangifteIbReport';
import { useTenant } from '../../context/TenantContext';
import { tenantAwareGet, tenantAwarePost, requireTenant } from '../../services/tenantApiService';
import { createMockResponse } from '@/test-utils/mockHelpers';

// Mock dependencies
vi.mock('../../context/TenantContext');
vi.mock('../../services/tenantApiService');

// Mock useTypedTranslation to return keys as-is (avoids needing full i18n setup)
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() }
  })
}));

vi.mock('../../config', () => ({
  buildApiUrl: vi.fn((path: string, params?: URLSearchParams) => {
    return params ? `${path}?${params.toString()}` : path;
  })
}));



// Mock FilterPanel
vi.mock('../filters/FilterPanel', () => {
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
vi.mock('../YearEndClosureSection', () => {
  return {
    default: function MockYearEndClosureSection() {
      return <div data-testid="year-end-closure-section">YearEndClosureSection</div>;
    },
  };
});

const mockUseTenant = vi.mocked(useTenant);
const mockTenantAwareGet = vi.mocked(tenantAwareGet);
const mockTenantAwarePost = vi.mocked(tenantAwarePost);
const mockRequireTenant = vi.mocked(requireTenant);

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
    vi.clearAllMocks();
    
    // Default mock implementations
    mockUseTenant.mockReturnValue({
      currentTenant: 'GoodwinSolutions',
      availableTenants: ['GoodwinSolutions', 'TestTenant'],
      setCurrentTenant: vi.fn(),
      hasMultipleTenants: true
    });

    mockTenantAwareGet.mockResolvedValue(createMockResponse({
      body: { 
        success: true, 
        data: [],
        available_years: ['2024', '2023'] 
      }
    }));

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
        setCurrentTenant: vi.fn(),
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
        setCurrentTenant: vi.fn(),
        hasMultipleTenants: false
      });

      render(<AangifteIbReport />);
      
      // Should show warning
      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
    });
  });
});
