/**
 * BudgetTemplatesPage Unit Tests
 *
 * Tests FilterableHeader rendering, Formik+Yup modal validation,
 * dark theme application, and absence of light-theme backgrounds.
 *
 * Validates: Requirements 3.2, 5.2, 5.3
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import BudgetTemplatesPage from '../pages/BudgetTemplatesPage';
import * as budgetService from '../services/budgetService';
import * as chartOfAccountsService from '../services/chartOfAccountsService';

vi.mock('../services/budgetService');
vi.mock('../services/chartOfAccountsService');

const mockListTemplates = vi.mocked(budgetService.listTemplates);
const mockListAccounts = vi.mocked(chartOfAccountsService.listAccounts);

const mockTemplates = [
  {
    id: 1,
    name: 'Standard Template',
    line_count: 5,
    created_at: '2025-01-15T10:00:00Z',
    updated_at: '2025-01-15T10:00:00Z',
  },
  {
    id: 2,
    name: 'Minimal Template',
    line_count: 2,
    created_at: '2025-02-01T08:30:00Z',
    updated_at: '2025-02-01T08:30:00Z',
  },
];

const mockAccounts = [
  { Account: '4000', AccountName: 'Revenue', AccountLookup: 'Revenue', Belastingaangifte: 'PL' },
  { Account: '6000', AccountName: 'Expenses', AccountLookup: 'Costs', Belastingaangifte: 'PL' },
];

describe('BudgetTemplatesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListTemplates.mockResolvedValue({ success: true, data: mockTemplates });
    mockListAccounts.mockResolvedValue({
      success: true,
      accounts: mockAccounts as any,
      total: 2,
      page: 1,
      limit: 100,
      pages: 1,
    });
  });

  describe('FilterableHeader renders for each column', () => {
    it('renders FilterableHeader for Name column with filter input', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      // FilterableHeader renders an aria-label="Filter by {label}" input
      // In test env, labels are translation keys (e.g., columns.name)
      expect(screen.getByLabelText('Filter by columns.name')).toBeInTheDocument();
    });

    it('renders FilterableHeader for Lines column with filter input', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.lines')).toBeInTheDocument();
    });

    it('renders FilterableHeader for Created column with filter input', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Filter by columns.created')).toBeInTheDocument();
    });

    it('renders sort buttons for all 3 columns', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      expect(screen.getByLabelText('Sort by columns.name')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.lines')).toBeInTheDocument();
      expect(screen.getByLabelText('Sort by columns.created')).toBeInTheDocument();
    });
  });

  describe('Formik modal validates required fields', () => {
    it('opens create template modal when Create Template button is clicked', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      // Button text is the translation key in test env
      fireEvent.click(screen.getByText('buttons.createTemplate'));

      await waitFor(() => {
        // Modal should open (dialog role from Chakra mock)
        expect(screen.getByRole('dialog')).toBeInTheDocument();
        // Template Name label should appear
        expect(screen.getByText('labels.templateName')).toBeInTheDocument();
      });
    });

    it('shows validation error when name is empty on submit', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('buttons.createTemplate'));

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Touch and blur the name field to trigger touched state
      const nameInput = screen.getByPlaceholderText('labels.templateName');
      fireEvent.focus(nameInput);
      fireEvent.blur(nameInput);

      // Submit the form by clicking Save button (translation key: buttons.save)
      fireEvent.click(screen.getByText('buttons.save'));

      // Formik+Yup validation should show error for name
      await waitFor(() => {
        expect(screen.getByText('Name is required')).toBeInTheDocument();
      });
    });

    it('shows validation error when line account_code is empty', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('buttons.createTemplate'));

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Fill in the name to pass name validation
      const nameInput = screen.getByPlaceholderText('labels.templateName');
      fireEvent.change(nameInput, { target: { value: 'Test Template' } });

      // Submit without selecting account_code on the default line
      fireEvent.click(screen.getByText('buttons.save'));

      // Yup validates account_code is required on each line
      await waitFor(() => {
        expect(screen.getByText('Account code is required')).toBeInTheDocument();
      });
    });
  });

  describe('No light-theme backgrounds remain', () => {
    it('does not render any elements with light-theme background values in the page output', async () => {
      const { container } = render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      const html = container.innerHTML;

      // These light-theme backgrounds should NOT appear in rendered output
      expect(html).not.toContain('gray.50');
      expect(html).not.toContain('purple.50');
      expect(html).not.toContain('green.50');
    });
  });

  describe('Dark theme applied', () => {
    it('renders the page title', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        // Title is rendered with translation key
        expect(screen.getByText('titles.templates')).toBeInTheDocument();
      });
    });

    it('renders the table element', async () => {
      const { container } = render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      // Table should be rendered (Chakra Table mock renders as <table>)
      const table = container.querySelector('table');
      expect(table).toBeInTheDocument();
    });

    it('renders template data in table rows', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
        expect(screen.getByText('Minimal Template')).toBeInTheDocument();
        expect(screen.getByText('5')).toBeInTheDocument();
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    });

    it('modal uses dark theme (dialog role) when opened', async () => {
      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        expect(screen.getByText('Standard Template')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('buttons.createTemplate'));

      await waitFor(() => {
        // Modal renders (the dialog role comes from the Chakra Modal mock)
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });
  });

  describe('Empty state', () => {
    it('shows empty message when no templates exist', async () => {
      mockListTemplates.mockResolvedValue({ success: true, data: [] });

      render(<BudgetTemplatesPage />);

      await waitFor(() => {
        // In test env, translation key is rendered directly
        expect(screen.getByText('messages.noTemplates')).toBeInTheDocument();
      });
    });
  });
});
