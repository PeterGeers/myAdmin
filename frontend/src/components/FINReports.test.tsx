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

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import FINReports from './FINReports';

// Mock the contexts
const mockUseAuth = jest.fn();
const mockUseTenant = jest.fn();

jest.mock('../context/AuthContext', () => ({
  useAuth: () => mockUseAuth()
}));

jest.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant()
}));

// Mock the FinancialReportsGroup component
jest.mock('./reports/FinancialReportsGroup', () => {
  return function MockFinancialReportsGroup() {
    return <div data-testid="financial-reports-group">Financial Reports Group</div>;
  };
});

// Mock Chakra UI components
jest.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...props }: any) => {
    // Filter out Chakra-specific props to avoid DOM warnings
    const { bg, minH, p, display, alignItems, justifyContent, ...domProps } = props;
    return <div data-testid="box" {...domProps}>{children}</div>;
  },
  VStack: ({ children, ...props }: any) => {
    const { spacing, align, ...domProps } = props;
    return <div data-testid="vstack" {...domProps}>{children}</div>;
  },
  Alert: ({ children, status, ...props }: any) => <div data-testid="alert" data-status={status} {...props}>{children}</div>,
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  Spinner: ({ size, color, ...props }: any) => <div data-testid="spinner" data-size={size} data-color={color} {...props}>Loading...</div>,
  Text: ({ children, fontWeight, fontSize, color, ...props }: any) => (
    <span data-testid="text" data-font-weight={fontWeight} data-font-size={fontSize} data-color={color} {...props}>
      {children}
    </span>
  )
}));

describe('FINReports Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Clear console.log mock
    jest.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
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
      expect(screen.getByTestId('alert')).toHaveAttribute('data-status', 'warning');
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
      expect(screen.getByTestId('alert')).toHaveAttribute('data-status', 'error');
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
      const consoleSpy = jest.spyOn(console, 'log');
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
      expect(screen.getByTestId('spinner')).toBeInTheDocument();
      
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
      expect(screen.getByTestId('spinner')).toBeInTheDocument();
      expect(screen.getByText('Switching to GoodwinSolutions...')).toBeInTheDocument();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByTestId('spinner')).not.toBeInTheDocument();
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
      expect(screen.getByTestId('spinner')).toBeInTheDocument();
      expect(screen.getByText('Switching to GoodwinSolutions...')).toBeInTheDocument();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByTestId('spinner')).not.toBeInTheDocument();
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
      expect(screen.getByTestId('alert')).toHaveAttribute('data-status', 'error');
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
      expect(screen.getByTestId('alert')).toHaveAttribute('data-status', 'error');
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
      expect(screen.getByTestId('alert')).toHaveAttribute('data-status', 'error');
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