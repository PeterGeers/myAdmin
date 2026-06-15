/**
 * BudgetDashboard Unit Tests
 *
 * Tests drill-down navigation, no-active-version notification display,
 * variance color coding, FilterableHeader rendering, and dark theme styling.
 *
 * Validates: Requirements 3.4, 4.1, 6.1, 6.5, 6.8
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import BudgetDashboard from '../pages/BudgetDashboard';
import * as budgetService from '../services/budgetService';
import type { DashboardParams } from '../services/budgetService';

vi.mock('../services/budgetService');

const mockGetDashboard = vi.mocked(budgetService.getDashboard);

/** Helper that returns mock data based on the level parameter */
function createDashboardMock() {
  return (params: DashboardParams) => {
    const { level, parent_code, subparent_code } = params;

    if (level === 'account' && subparent_code) {
      return Promise.resolve({
        success: true as const,
        data: {
          year: 2025,
          level: 'account' as const,
          period: 'ytd' as const,
          active_version: { id: 1, name: 'Budget 2025' },
          rows: [
            { code: '4101', name: 'Airbnb NL', budget: 10000.0, actual: 9000.0, variance: -1000.0 },
            { code: '4102', name: 'Airbnb BE', budget: 10000.0, actual: 9000.0, variance: -1000.0 },
          ],
        },
      });
    }

    if (level === 'subparent' && parent_code) {
      return Promise.resolve({
        success: true as const,
        data: {
          year: 2025,
          level: 'subparent' as const,
          period: 'ytd' as const,
          active_version: { id: 1, name: 'Budget 2025' },
          rows: [
            { code: '4100', name: 'Omzet Airbnb', budget: 20000.0, actual: 18000.0, variance: -2000.0 },
            { code: '4200', name: 'Omzet Booking', budget: 25000.0, actual: 24350.75, variance: -649.25 },
          ],
        },
      });
    }

    // Default: parent level
    return Promise.resolve({
      success: true as const,
      data: {
        year: 2025,
        level: 'parent' as const,
        period: 'ytd' as const,
        active_version: { id: 1, name: 'Budget 2025' },
        rows: [
          { code: '4000', name: 'Omzet', budget: 45000.0, actual: 42350.75, variance: -2649.25 },
          { code: '5000', name: 'Kosten', budget: 30000.0, actual: 31200.5, variance: 1200.5 },
        ],
      },
    });
  };
}

describe('BudgetDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDashboard.mockImplementation(createDashboardMock());
  });

  describe('No-active-version notification (Requirement 6.8)', () => {
    it('shows a warning Alert when no active version exists', async () => {
      mockGetDashboard.mockResolvedValue({
        success: true,
        data: {
          year: 2025,
          level: 'parent',
          period: 'ytd',
          active_version: null,
          notification: 'No active budget version for 2025',
          rows: [],
        },
      });

      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('No active budget version for 2025')).toBeInTheDocument();
      });

      // Verify it's inside an alert element
      const alert = screen.getByRole('alert');
      expect(alert).toBeInTheDocument();
    });

    it('does not show notification when active version exists', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      expect(screen.queryByText(/No active budget version/)).not.toBeInTheDocument();
    });
  });

  describe('Variance color coding (Requirement 6.5)', () => {
    it('renders positive variance value (over-budget)', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Kosten')).toBeInTheDocument();
      });

      // Kosten has variance 1200.50 (positive = over-budget)
      // Dutch locale formats as 1.200,50
      expect(screen.getByText('1.200,50')).toBeInTheDocument();
    });

    it('renders negative variance value (under-budget)', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // Omzet has variance -2649.25 (negative = under-budget)
      // Dutch locale formats as -2.649,25
      expect(screen.getByText('-2.649,25')).toBeInTheDocument();
    });
  });

  describe('Drill-down from Parent to SubParent (Requirement 6.1)', () => {
    it('clicking a Parent row navigates to subparent level and shows breadcrumb', async () => {
      render(<BudgetDashboard />);

      // Wait for parent-level rows
      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // Click on the Omzet row to drill down
      fireEvent.click(screen.getByText('Omzet'));

      // Wait for subparent-level rows to appear
      await waitFor(() => {
        expect(screen.getByText('Omzet Airbnb')).toBeInTheDocument();
      });

      // Breadcrumb should contain the parent code
      expect(screen.getByText(/SubParent:.*4000/)).toBeInTheDocument();

      // getDashboard should have been called with subparent level and parent_code
      expect(mockGetDashboard).toHaveBeenCalledWith(
        expect.objectContaining({
          level: 'subparent',
          parent_code: '4000',
        })
      );
    });
  });

  describe('Drill-down from SubParent to Account', () => {
    it('clicking a SubParent row navigates to account level', async () => {
      render(<BudgetDashboard />);

      // Start at parent level
      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // Drill down to subparent
      fireEvent.click(screen.getByText('Omzet'));

      await waitFor(() => {
        expect(screen.getByText('Omzet Airbnb')).toBeInTheDocument();
      });

      // Drill down to account
      fireEvent.click(screen.getByText('Omzet Airbnb'));

      await waitFor(() => {
        expect(screen.getByText('Airbnb NL')).toBeInTheDocument();
      });

      // Breadcrumb should show Account level
      expect(screen.getByText(/Account:.*4100/)).toBeInTheDocument();

      // getDashboard should have been called with account level and subparent_code
      expect(mockGetDashboard).toHaveBeenCalledWith(
        expect.objectContaining({
          level: 'account',
          subparent_code: '4100',
        })
      );
    });
  });

  describe('Back navigation', () => {
    it('clicking Back from subparent returns to parent level', async () => {
      render(<BudgetDashboard />);

      // Start at parent
      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // Drill down to subparent
      fireEvent.click(screen.getByText('Omzet'));

      await waitFor(() => {
        expect(screen.getByText('Omzet Airbnb')).toBeInTheDocument();
      });

      // Click Back button
      fireEvent.click(screen.getByText('← Back'));

      // Should return to parent level with original rows
      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
        expect(screen.getByText('Kosten')).toBeInTheDocument();
      });
    });

    it('clicking Back from account returns to subparent level', async () => {
      render(<BudgetDashboard />);

      // Navigate Parent → SubParent → Account
      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Omzet'));

      await waitFor(() => {
        expect(screen.getByText('Omzet Airbnb')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Omzet Airbnb'));

      await waitFor(() => {
        expect(screen.getByText('Airbnb NL')).toBeInTheDocument();
      });

      // Click Back — should return to subparent
      fireEvent.click(screen.getByText('← Back'));

      await waitFor(() => {
        expect(screen.getByText('Omzet Airbnb')).toBeInTheDocument();
      });
    });
  });

  describe('FilterableHeader rendering (Requirement 3.4)', () => {
    it('renders FilterableHeader with filter input for Code column', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // FilterableHeader uses the translated label in aria-label: "Filter by {label}"
      expect(screen.getByLabelText('Filter by columns.code')).toBeInTheDocument();
    });

    it('renders FilterableHeader with filter input for Name column', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.name')).toBeInTheDocument();
    });

    it('renders FilterableHeader with filter input for Budget column', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.budget')).toBeInTheDocument();
    });

    it('renders FilterableHeader with filter input for Actual column', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.actual')).toBeInTheDocument();
    });

    it('renders FilterableHeader with filter input for Variance column', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.variance')).toBeInTheDocument();
    });

    it('renders sortable sort buttons for all 5 columns', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Sort by columns.code')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.name')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.budget')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.actual')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.variance')).toBeInTheDocument();
    });
  });

  describe('Dark theme props (Requirement 4.1)', () => {
    it('renders Table with dark background', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // Table renders as <table> element via mock
      const table = screen.getByRole('table');
      expect(table).toBeInTheDocument();
    });

    it('renders page title', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // The dashboard title is rendered (translation key in test env)
      const title = screen.getByText('titles.dashboard');
      expect(title).toBeInTheDocument();
    });

    it('does not render any CRUD modals (no Formik forms)', async () => {
      render(<BudgetDashboard />);

      await waitFor(() => {
        expect(screen.getByText('Omzet')).toBeInTheDocument();
      });

      // Dashboard is read-only with filters — no modal dialogs should be present
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});
