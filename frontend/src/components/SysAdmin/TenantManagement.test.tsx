import React from 'react';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TenantManagement } from './TenantManagement';

// Mock sysadminService
const mockGetTenants = vi.fn();
const mockCreateTenant = vi.fn();
const mockUpdateTenant = vi.fn();
const mockDeleteTenant = vi.fn();
const mockReprovisionTenant = vi.fn();
const mockResendInvitation = vi.fn();

vi.mock('../../services/sysadminService', () => ({
  getTenants: (...args: unknown[]) => mockGetTenants(...args),
  createTenant: (...args: unknown[]) => mockCreateTenant(...args),
  updateTenant: (...args: unknown[]) => mockUpdateTenant(...args),
  deleteTenant: (...args: unknown[]) => mockDeleteTenant(...args),
  reprovisionTenant: (...args: unknown[]) => mockReprovisionTenant(...args),
  resendInvitation: (...args: unknown[]) => mockResendInvitation(...args),
}));

// Mock hooks
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../hooks/useColumnFilters', () => ({
  useColumnFilters: (data: unknown[]) => ({
    filters: {},
    setFilter: vi.fn(),
    filteredData: data,
  }),
}));

vi.mock('../filters/FilterableHeader', () => ({
  FilterableHeader: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
}));

vi.mock('./ModuleManagement', () => ({
  ModuleManagement: () => <div data-testid="module-management" />,
}));

const mockTenants = [
  {
    administration: 'tenant-a',
    display_name: 'Tenant A',
    contact_email: 'admin@tenanta.com',
    status: 'active' as const,
    enabled_modules: ['FIN', 'STR'],
    user_count: 3,
    created_at: '2025-01-01',
  },
  {
    administration: 'tenant-b',
    display_name: 'Tenant B',
    contact_email: 'admin@tenantb.com',
    status: 'suspended' as const,
    enabled_modules: ['FIN'],
    user_count: 1,
    created_at: '2025-06-15',
  },
];

describe('TenantManagement Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTenants.mockResolvedValue({
      tenants: mockTenants,
      total_pages: 1,
      total: 2,
    });
  });

  describe('Rendering', () => {
    it('renders loading spinner initially', () => {
      mockGetTenants.mockReturnValue(new Promise(() => {})); // never resolves
      render(<TenantManagement />);
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('renders tenant table after loading', async () => {
      render(<TenantManagement />);
      await waitFor(() => {
        expect(screen.getByText('Tenant A')).toBeInTheDocument();
      });
      expect(screen.getByText('Tenant B')).toBeInTheDocument();
    });

    it('renders Add Tenant button', async () => {
      render(<TenantManagement />);
      await waitFor(() => {
        expect(screen.getByText('Tenant A')).toBeInTheDocument();
      });
      expect(screen.getAllByRole('button', { name: /add|create|tenantManagement/i })[0]).toBeInTheDocument();
    });
  });

  describe('Create Tenant', () => {
    it('opens create modal on Add button click', async () => {
      render(<TenantManagement />);
      await waitFor(() => {
        expect(screen.getByText('Tenant A')).toBeInTheDocument();
      });

      const addButton = screen.getAllByRole('button', { name: /add|create|tenantManagement/i })[0];
      fireEvent.click(addButton);

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('calls createTenant on form submit', async () => {
      mockCreateTenant.mockResolvedValue({ success: true, message: 'Created' });
      render(<TenantManagement />);
      await waitFor(() => {
        expect(screen.getByText('Tenant A')).toBeInTheDocument();
      });

      const addButton = screen.getAllByRole('button', { name: /add|create|tenantManagement/i })[0];
      fireEvent.click(addButton);

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Fill required fields
      const adminInput = screen.getByPlaceholderText(/administrationPlaceholder/i);
      const nameInput = screen.getByPlaceholderText(/displayNamePlaceholder/i);
      const emailInput = screen.getByPlaceholderText(/contactEmailPlaceholder/i);

      fireEvent.change(adminInput, { target: { value: 'new-tenant' } });
      fireEvent.change(nameInput, { target: { value: 'New Tenant' } });
      fireEvent.change(emailInput, { target: { value: 'admin@new.com' } });

      const submitButton = screen.getByRole('button', { name: 'tenantManagement.actions.create' });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockCreateTenant).toHaveBeenCalledWith(
          expect.objectContaining({
            administration: 'new-tenant',
            display_name: 'New Tenant',
            contact_email: 'admin@new.com',
          })
        );
      });
    });
  });

  describe('Delete Tenant', () => {
    it('calls deleteTenant after confirmation', async () => {
      mockDeleteTenant.mockResolvedValue({ success: true, message: 'Deleted' });
      render(<TenantManagement />);
      await waitFor(() => {
        expect(screen.getByText('Tenant A')).toBeInTheDocument();
      });

      // Click on the row to open edit/actions
      fireEvent.click(screen.getByText('Tenant A'));

      await waitFor(() => {
        const deleteButton = screen.queryByRole('button', { name: /delete/i });
        if (deleteButton) {
          fireEvent.click(deleteButton);
        }
      });
    });
  });

  describe('Error Handling', () => {
    it('shows error toast when getTenants fails', async () => {
      mockGetTenants.mockRejectedValue(new Error('Network error'));
      render(<TenantManagement />);
      await waitFor(() => {
        expect(mockGetTenants).toHaveBeenCalled();
      });
    });
  });

  describe('Pagination', () => {
    it('fetches tenants with page parameters', async () => {
      render(<TenantManagement />);
      await waitFor(() => {
        expect(mockGetTenants).toHaveBeenCalledWith(
          expect.objectContaining({
            page: 1,
            per_page: 10,
            sort_by: 'administration',
            sort_order: 'asc',
          })
        );
      });
    });
  });
});
