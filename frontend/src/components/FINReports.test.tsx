/**
 * Tests for FINReports Component
 * 
 * Tests tenant handling implementation including:
 * - Tenant context integration
 * - Pre-processing validation
 * - Auto-refresh on tenant change
 * - Graceful tenant switching
 * - Clear error messages
 * - Security requirements
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@/test-utils';
import FINReports from './FINReports';

// Mock the contexts
const mockUseAuth = vi.fn();
const mockUseTenant = vi.fn();

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockUseAuth()
}));

vi.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant()
}));

// Mock the FinancialReportsGroup component
vi.mock('./reports/FinancialReportsGroup', () => {
  return {
    default: function MockFinancialReportsGroup() {
      return <div data-testid="financial-reports-group">Financial Reports Group</div>;
    },
  };
});


describe('FINReports Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Clear console.log mock
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Tenant Context Integration', () => {
    it('should use useTenant hook for tenant context', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(mockUseTenant).toHaveBeenCalled();
    });
  });

  describe('Pre-processing Validation', () => {
    it('should show error when no tenant is selected', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('No tenant selected')).toBeInTheDocument();
      expect(screen.getByText(/Please select a tenant from the dropdown menu/)).toBeInTheDocument();
    });

    it('should show error when user lacks finance permissions', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Other_Role'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.getByText(/Required permissions: Finance_CRUD, Finance_Read, or Finance_Export/)).toBeInTheDocument();
    });

    it('should allow access with Finance_CRUD permission', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_CRUD'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert - wait for loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });
    });

    it('should allow access with Finance_Read permission', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert - wait for loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });
    });

    it('should allow access with Finance_Export permission', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Export'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert - wait for loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });
    });
  });

  describe('Auto-refresh on Tenant Change', () => {
    it('should log tenant change when tenant changes', () => {
      // Arrange
      const consoleSpy = vi.spyOn(console, 'log');
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(consoleSpy).toHaveBeenCalledWith('FIN Reports: Tenant changed to GoodwinSolutions');
    });

    it('should re-render when tenant context changes', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      
      // Initial render with first tenant
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });
      const { rerender } = render(<FINReports />);
      
      // Wait for initial loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });

      // Change tenant
      mockUseTenant.mockReturnValue({
        currentTenant: 'PeterPrive'
      });

      // Act
      rerender(<FINReports />);

      // Assert - should show loading state first, then the reports
      expect(screen.getByRole('status')).toBeInTheDocument();
      
      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });
    });
  });

  describe('Graceful Tenant Switching', () => {
    it('should show loading state during tenant switching', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert - should show loading state briefly
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByText('Switching to GoodwinSolutions...')).toBeInTheDocument();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
      }, { timeout: 200 });

      expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
    });

    it('should handle tenant switching with proper loading states', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      
      // Initial state - no tenant
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });
      const { rerender } = render(<FINReports />);
      expect(screen.getByText('No tenant selected')).toBeInTheDocument();

      // Switch to tenant
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      rerender(<FINReports />);

      // Assert - should show loading state
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByText('Switching to GoodwinSolutions...')).toBeInTheDocument();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
      }, { timeout: 200 });

      expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
    });
  });

  describe('Clear Error Messages', () => {
    it('should provide detailed error message for no tenant selected', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByText('No tenant selected')).toBeInTheDocument();
      expect(screen.getByText(/Financial data is organized by tenant for security and compliance/)).toBeInTheDocument();
    });

    it('should provide detailed error message for insufficient permissions', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Other_Role'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
      expect(screen.getByText(/Required permissions: Finance_CRUD, Finance_Read, or Finance_Export/)).toBeInTheDocument();
      expect(screen.getByText(/Please contact your administrator to request access/)).toBeInTheDocument();
    });
  });

  describe('Security Requirements', () => {
    it('should block access when no user is present', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: null
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });

    it('should block access when user has no roles', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: [] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });

    it('should block access when user has undefined roles', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: undefined }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });

    it('should enforce tenant selection before showing financial data', () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: null
      });

      // Act
      render(<FINReports />);

      // Assert
      expect(screen.queryByTestId('financial-reports-group')).not.toBeInTheDocument();
      expect(screen.getByText('No tenant selected')).toBeInTheDocument();
    });
  });

  describe('Component Integration', () => {
    it('should render FinancialReportsGroup when all conditions are met', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert - wait for loading to complete
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });
    });

    it('should pass tenant context to child components through provider', async () => {
      // Arrange
      mockUseAuth.mockReturnValue({
        user: { roles: ['Finance_Read'] }
      });
      mockUseTenant.mockReturnValue({
        currentTenant: 'GoodwinSolutions'
      });

      // Act
      render(<FINReports />);

      // Assert - FinancialReportsGroup should be rendered, indicating tenant context is available
      await waitFor(() => {
        expect(screen.getByTestId('financial-reports-group')).toBeInTheDocument();
      }, { timeout: 200 });
    });
  });
});