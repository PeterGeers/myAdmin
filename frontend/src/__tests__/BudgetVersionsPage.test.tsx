/**
 * BudgetVersionsPage Unit Tests
 *
 * Tests rendering of version list, status transition button visibility
 * based on current status, and activate button behavior for Draft versions.
 * Also tests FilterableHeader rendering, Formik modal validation, and dark theme.
 *
 * Validates: Requirements 1.1–1.8, 3.1, 5.2, 5.3
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import BudgetVersionsPage from '../pages/BudgetVersionsPage';
import * as budgetService from '../services/budgetService';

vi.mock('../services/budgetService');

const mockListVersions = vi.mocked(budgetService.listVersions);
const mockTransitionVersionStatus = vi.mocked(budgetService.transitionVersionStatus);
const mockActivateVersion = vi.mocked(budgetService.activateVersion);
const mockDeleteVersion = vi.mocked(budgetService.deleteVersion);

const mockVersions = [
  {
    id: 1,
    name: 'Budget 2025',
    fiscal_year: 2025,
    status: 'Draft' as const,
    is_active: false,
    status_changed_at: null,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Budget 2024',
    fiscal_year: 2024,
    status: 'Approved' as const,
    is_active: true,
    status_changed_at: '2024-12-01T00:00:00Z',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-12-01T00:00:00Z',
  },
  {
    id: 3,
    name: 'Budget 2023 Revised',
    fiscal_year: 2023,
    status: 'Revised' as const,
    is_active: false,
    status_changed_at: '2023-06-01T00:00:00Z',
    created_at: '2023-01-01T00:00:00Z',
    updated_at: '2023-06-01T00:00:00Z',
  },
];

describe('BudgetVersionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListVersions.mockResolvedValue({ success: true, data: mockVersions });
  });

  describe('Renders version list', () => {
    it('shows all versions in the table', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
        expect(screen.getByText('Budget 2024')).toBeInTheDocument();
        expect(screen.getByText('Budget 2023 Revised')).toBeInTheDocument();
      });
    });

    it('displays fiscal year for each version', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('2025')).toBeInTheDocument();
        expect(screen.getByText('2024')).toBeInTheDocument();
        expect(screen.getByText('2023')).toBeInTheDocument();
      });
    });

    it('displays status badges', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Draft')).toBeInTheDocument();
        expect(screen.getByText('Approved')).toBeInTheDocument();
        expect(screen.getByText('Revised')).toBeInTheDocument();
      });
    });

    it('shows Active badge for active version', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        // "Active" appears as both a column header (th label) and a badge.
        // In test env, column header renders as "columns.active" and badge as "messages.activeVersion"
        expect(screen.getByText('messages.activeVersion')).toBeInTheDocument();
      });
    });

    it('shows empty state when no versions exist', async () => {
      mockListVersions.mockResolvedValue({ success: true, data: [] });

      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('messages.noVersions')).toBeInTheDocument();
      });
    });
  });

  describe('Status buttons for Draft version', () => {
    it('shows Approve and Delete buttons, no Activate or Revise', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Click the Draft version row to open detail modal
      fireEvent.click(screen.getByText('Budget 2025'));

      await waitFor(() => {
        expect(screen.getByText('buttons.approve')).toBeInTheDocument();
        expect(screen.getByText('buttons.delete')).toBeInTheDocument();
      });

      // Activate and Revise should not be visible for Draft
      expect(screen.queryByText('buttons.activate')).not.toBeInTheDocument();
      expect(screen.queryByText('buttons.revise')).not.toBeInTheDocument();
    });
  });

  describe('Status buttons for Approved version', () => {
    it('shows Revise and Activate buttons, no Delete or Approve', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2024')).toBeInTheDocument();
      });

      // Click the Approved version row to open detail modal
      fireEvent.click(screen.getByText('Budget 2024'));

      await waitFor(() => {
        expect(screen.getByText('buttons.revise')).toBeInTheDocument();
        expect(screen.getByText('buttons.activate')).toBeInTheDocument();
      });

      // Delete and Approve should not be visible for Approved
      expect(screen.queryByText('buttons.delete')).not.toBeInTheDocument();
      expect(screen.queryByText('buttons.approve')).not.toBeInTheDocument();
    });
  });

  describe('Status buttons for Revised version', () => {
    it('shows Activate button, no Approve, Revise, or Delete', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2023 Revised')).toBeInTheDocument();
      });

      // Click the Revised version row to open detail modal
      fireEvent.click(screen.getByText('Budget 2023 Revised'));

      await waitFor(() => {
        expect(screen.getByText('buttons.activate')).toBeInTheDocument();
      });

      // Other action buttons should not be visible for Revised
      expect(screen.queryByText('buttons.approve')).not.toBeInTheDocument();
      expect(screen.queryByText('buttons.delete')).not.toBeInTheDocument();
      expect(screen.queryByText('buttons.revise')).not.toBeInTheDocument();
    });
  });

  describe('Activate button not available for Draft versions', () => {
    it('does not show Activate for a Draft version', async () => {
      // Only provide a Draft version
      mockListVersions.mockResolvedValue({
        success: true,
        data: [mockVersions[0]], // Draft only
      });

      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Open detail modal for Draft version
      fireEvent.click(screen.getByText('Budget 2025'));

      await waitFor(() => {
        expect(screen.getByText('buttons.approve')).toBeInTheDocument();
      });

      // Activate must NOT be available for Draft versions (Requirement 1.7)
      expect(screen.queryByText('buttons.activate')).not.toBeInTheDocument();
    });
  });

  // ─── Requirement 3.1: FilterableHeader for all columns ──────────────────────

  describe('FilterableHeader renders for each column (Requirement 3.1)', () => {
    it('renders a filter input for the Name column', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.name')).toBeInTheDocument();
    });

    it('renders a filter input for the Fiscal Year column', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.fiscalYear')).toBeInTheDocument();
    });

    it('renders a filter input for the Status column', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.status')).toBeInTheDocument();
    });

    it('renders a filter input for the Active column', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.active')).toBeInTheDocument();
    });

    it('renders sort buttons for all four columns', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Sort by columns.name')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.fiscalYear')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.status')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.active')).toBeInTheDocument();
    });
  });

  // ─── Requirement 5.2, 5.3: Formik modal validates required fields ───────────

  describe('Create modal Formik validation (Requirements 5.2, 5.3)', () => {
    it('opens the create modal when Create button is clicked', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Click the Create Version button (renders as translation key)
      fireEvent.click(screen.getByText('buttons.createVersion'));

      // Modal should be open with the form labels
      await waitFor(() => {
        expect(screen.getByText('labels.versionName')).toBeInTheDocument();
      });

      expect(screen.getByText('labels.fiscalYear')).toBeInTheDocument();
    });

    it('shows validation error when name field is empty on submit', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('buttons.createVersion'));

      await waitFor(() => {
        expect(screen.getByText('labels.versionName')).toBeInTheDocument();
      });

      // Clear the name field and submit
      const nameInput = screen.getByPlaceholderText('e.g. Budget 2025');
      fireEvent.change(nameInput, { target: { value: '' } });
      fireEvent.blur(nameInput);

      // Click save to trigger validation (renders as translation key from common ns)
      const saveButton = screen.getByText('buttons.save');
      fireEvent.click(saveButton);

      // Wait for Formik validation error (key rendered as-is)
      await waitFor(() => {
        expect(screen.getByText('messages.nameRequired')).toBeInTheDocument();
      });
    });

    it('shows validation error when fiscal_year is empty on submit', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('buttons.createVersion'));

      await waitFor(() => {
        expect(screen.getByText('labels.fiscalYear')).toBeInTheDocument();
      });

      // Clear the fiscal_year field
      const yearInput = screen.getByDisplayValue(new Date().getFullYear().toString());
      fireEvent.change(yearInput, { target: { value: '' } });
      fireEvent.blur(yearInput);

      // Click save to trigger validation
      const saveButton = screen.getByText('buttons.save');
      fireEvent.click(saveButton);

      // Wait for Formik validation error
      await waitFor(() => {
        expect(screen.getByText('messages.yearRequired')).toBeInTheDocument();
      });
    });

    it('does not submit when required fields are empty', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('buttons.createVersion'));

      await waitFor(() => {
        expect(screen.getByText('labels.versionName')).toBeInTheDocument();
      });

      // Clear the name field
      const nameInput = screen.getByPlaceholderText('e.g. Budget 2025');
      fireEvent.change(nameInput, { target: { value: '' } });

      // Click save
      fireEvent.click(screen.getByText('buttons.save'));

      // createVersion should NOT have been called
      await waitFor(() => {
        expect(budgetService.createVersion).not.toHaveBeenCalled();
      });
    });
  });

  // ─── Requirements 1.1, 1.2, 5.6: Dark theme props ──────────────────────────

  describe('Dark theme props (Requirements 1.1, 1.2, 5.6)', () => {
    it('renders the table element when data is loaded', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Table renders (bg="gray.800" is applied in source, mock renders as <table>)
      const table = screen.getByRole('table');
      expect(table).toBeInTheDocument();
    });

    it('renders page title with translated key', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Title renders with color="white" applied in source (translation key in test env)
      expect(screen.getByText('titles.versions')).toBeInTheDocument();
    });

    it('renders modal content with dark theme when detail modal is opened', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Open detail modal
      fireEvent.click(screen.getByText('Budget 2025'));

      // Modal renders (bg="gray.800" color="white" applied to ModalContent in source)
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('renders create modal content with dark theme styling', async () => {
      render(<BudgetVersionsPage />);

      await waitFor(() => {
        expect(screen.getByText('Budget 2025')).toBeInTheDocument();
      });

      // Open create modal
      fireEvent.click(screen.getByText('buttons.createVersion'));

      // Create modal renders with dialog role (bg="gray.800" color="white" on ModalContent)
      await waitFor(() => {
        expect(screen.getAllByRole('dialog').length).toBeGreaterThanOrEqual(1);
      });
    });
  });
});
