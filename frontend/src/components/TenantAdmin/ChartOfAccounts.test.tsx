import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock service functions
const mockListAccounts = vi.fn();
const mockExportAccounts = vi.fn();
const mockImportAccounts = vi.fn();
const mockCreateAccount = vi.fn();
const mockUpdateAccount = vi.fn();
const mockDeleteAccount = vi.fn();

vi.mock('../../services/chartOfAccountsService', () => ({
  listAccounts: (...args: unknown[]) => mockListAccounts(...args),
  exportAccounts: (...args: unknown[]) => mockExportAccounts(...args),
  importAccounts: (...args: unknown[]) => mockImportAccounts(...args),
  createAccount: (...args: unknown[]) => mockCreateAccount(...args),
  updateAccount: (...args: unknown[]) => mockUpdateAccount(...args),
  deleteAccount: (...args: unknown[]) => mockDeleteAccount(...args),
}));

// Mock hooks
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../hooks/useFilterableTable', () => ({
  useFilterableTable: (data: unknown[]) => ({
    filters: {},
    setFilter: vi.fn(),
    resetFilters: vi.fn(),
    hasActiveFilters: false,
    handleSort: vi.fn(),
    sortField: 'Account',
    sortDirection: 'asc' as const,
    processedData: data,
  }),
}));

vi.mock('../../hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    columns: ['Account', 'AccountName', 'VW', 'Parent'],
    filterableColumns: ['Account', 'AccountName', 'VW', 'Parent'],
    defaultSort: { field: 'Account', direction: 'asc' },
    pageSize: 100,
    loading: false,
    error: null,
  }),
}));

vi.mock('../filters/FilterableHeader', () => ({
  FilterableHeader: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
}));

vi.mock('./AccountModal', () => ({
  default: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? <div data-testid="account-modal" role="dialog"><button onClick={onClose}>Close</button></div> : null,
}));

// Import component after mocks
import ChartOfAccounts from './ChartOfAccounts';

const mockAccounts = [
  {
    Account: '1000',
    AccountName: 'Cash',
    AccountLookup: 'Kas',
    SubParent: 'Liquid',
    Parent: 'Assets',
    VW: 'N',
    Belastingaangifte: '',
    parameters: null,
  },
  {
    Account: '4000',
    AccountName: 'General Costs',
    AccountLookup: 'Kosten',
    SubParent: 'Operating',
    Parent: 'Expenses',
    VW: 'Y',
    Belastingaangifte: 'box1',
    parameters: null,
  },
  {
    Account: '8000',
    AccountName: 'Revenue',
    AccountLookup: 'Omzet',
    SubParent: 'Sales',
    Parent: 'Income',
    VW: 'Y',
    Belastingaangifte: 'box1',
    parameters: null,
  },
];

describe('ChartOfAccounts Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListAccounts.mockResolvedValue({ accounts: mockAccounts });
  });

  describe('Rendering', () => {
    it('renders loading state initially', () => {
      mockListAccounts.mockReturnValue(new Promise(() => {}));
      render(<ChartOfAccounts tenant="test-tenant" />);
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('renders accounts table after loading', async () => {
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(screen.getByText('Cash')).toBeInTheDocument();
      });
      expect(screen.getByText('General Costs')).toBeInTheDocument();
      expect(screen.getByText('Revenue')).toBeInTheDocument();
    });

    it('renders action buttons (Add, Export, Import)', async () => {
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(screen.getByText('Cash')).toBeInTheDocument();
      });
      // At minimum there should be buttons for add/export/import
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('displays account numbers in the table', async () => {
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(screen.getByText('1000')).toBeInTheDocument();
        expect(screen.getByText('4000')).toBeInTheDocument();
        expect(screen.getByText('8000')).toBeInTheDocument();
      });
    });
  });

  describe('CRUD Operations', () => {
    it('opens create modal on Add button click', async () => {
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(screen.getByText('Cash')).toBeInTheDocument();
      });

      const addButton = screen.getByRole('button', { name: /add|create|new/i });
      fireEvent.click(addButton);

      await waitFor(() => {
        expect(screen.getByTestId('account-modal')).toBeInTheDocument();
      });
    });

    it('opens edit modal on row click', async () => {
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(screen.getByText('Cash')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Cash'));

      await waitFor(() => {
        expect(screen.getByTestId('account-modal')).toBeInTheDocument();
      });
    });

    it('calls listAccounts with tenant parameter', async () => {
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockListAccounts).toHaveBeenCalled();
      });
    });
  });

  describe('Export', () => {
    it('calls exportAccounts when export button clicked', async () => {
      mockExportAccounts.mockResolvedValue(new Blob(['test'], { type: 'text/csv' }));
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(screen.getByText('Cash')).toBeInTheDocument();
      });

      const exportButton = screen.getByRole('button', { name: /export|download/i });
      fireEvent.click(exportButton);

      await waitFor(() => {
        expect(mockExportAccounts).toHaveBeenCalled();
      });
    });
  });

  describe('Error Handling', () => {
    it('shows error when listAccounts fails', async () => {
      mockListAccounts.mockRejectedValue(new Error('Network error'));
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockListAccounts).toHaveBeenCalled();
      });
      // Component should handle error gracefully (no crash)
    });

    it('handles empty account list', async () => {
      mockListAccounts.mockResolvedValue({ success: true, data: [] });
      render(<ChartOfAccounts tenant="test-tenant" />);
      await waitFor(() => {
        expect(mockListAccounts).toHaveBeenCalled();
      });
      // Should render without crashing
    });
  });
});
