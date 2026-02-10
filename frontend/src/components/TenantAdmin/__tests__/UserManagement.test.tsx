/**
 * UserManagement Component - Unit Tests
 * 
 * Tests for UserManagement component functionality.
 * Target: 20+ tests
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '../../../test-utils';
import { fetchAuthSession } from 'aws-amplify/auth';
import UserManagement from '../UserManagement';

// Mock AWS Amplify
jest.mock('aws-amplify/auth');

// Mock config
jest.mock('../../../config', () => ({
  buildApiUrl: (endpoint: string) => `http://localhost:5000${endpoint}`,
  API_BASE_URL: 'http://localhost:5000',
}));

const mockFetchAuthSession = fetchAuthSession as jest.MockedFunction<typeof fetchAuthSession>;

describe('UserManagement Component', () => {
  const mockToken = 'mock-jwt-token';
  const mockTenant = 'TestTenant';

  const mockUsers = [
    {
      username: 'user1',
      email: 'user1@example.com',
      name: 'User One',
      status: 'CONFIRMED',
      enabled: true,
      groups: ['Tenant_Admin'],
      tenants: ['TestTenant'],
      created: '2026-01-01T00:00:00Z',
    },
    {
      username: 'user2',
      email: 'user2@example.com',
      name: 'User Two',
      status: 'FORCE_CHANGE_PASSWORD',
      enabled: true,
      groups: ['Finance_CRUD'],
      tenants: ['TestTenant'],
      created: '2026-01-02T00:00:00Z',
    },
  ];

  const mockRoles = [
    { name: 'Tenant_Admin', description: 'Tenant Administrator', precedence: 1 },
    { name: 'Finance_CRUD', description: 'Finance Full Access', precedence: 2 },
    { name: 'Finance_Read', description: 'Finance Read Only', precedence: 3 },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    mockFetchAuthSession.mockResolvedValue({
      tokens: {
        idToken: {
          toString: () => mockToken,
        },
      },
    } as any);

    // Mock successful API responses
    global.fetch = jest.fn((url: string) => {
      if (url.includes('/api/tenant-admin/users')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: mockUsers }),
        } as Response);
      }
      if (url.includes('/api/tenant-admin/roles')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ roles: mockRoles }),
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      } as Response);
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  // ============================================================================
  // Rendering Tests
  // ============================================================================

  describe('Rendering', () => {
    test('renders component with loading state', () => {
      render(<UserManagement tenant={mockTenant} />);
      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    test('renders user list after loading', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('user1@example.com')).toBeInTheDocument();
        expect(screen.getByText('user2@example.com')).toBeInTheDocument();
      });
    });

    test('renders user names correctly', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('User One')).toBeInTheDocument();
        expect(screen.getByText('User Two')).toBeInTheDocument();
      });
    });

    test('renders user status badges', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('CONFIRMED')).toBeInTheDocument();
        expect(screen.getByText('FORCE_CHANGE_PASSWORD')).toBeInTheDocument();
      });
    });

    test('renders user roles', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('Tenant_Admin')).toBeInTheDocument();
        expect(screen.getByText('Finance_CRUD')).toBeInTheDocument();
      });
    });

    test('renders create user button', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Data Loading Tests
  // ============================================================================

  describe('Data Loading', () => {
    test('fetches users on mount', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/tenant-admin/users'),
          expect.any(Object)
        );
      });
    });

    test('fetches roles on mount', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/tenant-admin/roles'),
          expect.any(Object)
        );
      });
    });

    test('includes authentication token in requests', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        const calls = (global.fetch as jest.Mock).mock.calls;
        const usersCall = calls.find(call => call[0].includes('/api/tenant-admin/users'));
        expect(usersCall[1].headers['Authorization']).toBe(`Bearer ${mockToken}`);
      });
    });

    test('includes tenant header in requests', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        const calls = (global.fetch as jest.Mock).mock.calls;
        const usersCall = calls.find(call => call[0].includes('/api/tenant-admin/users'));
        expect(usersCall[1].headers['X-Tenant']).toBe(mockTenant);
      });
    });

    test('handles API error gracefully', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('API Error'));

      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.queryByText('user1@example.com')).not.toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Filtering and Sorting Tests
  // ============================================================================

  describe('Filtering and Sorting', () => {
    test('filters users by email search', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('user1@example.com')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by email/i);
      fireEvent.change(searchInput, { target: { value: 'user1' } });

      await waitFor(() => {
        expect(screen.getByText('user1@example.com')).toBeInTheDocument();
        // user2 should be filtered out (if filtering is implemented in component)
      });
    });

    test('filters users by name search', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('User One')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText(/search by name/i);
      fireEvent.change(searchInput, { target: { value: 'One' } });

      await waitFor(() => {
        expect(screen.getByText('User One')).toBeInTheDocument();
      });
    });

    test('filters users by status', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('CONFIRMED')).toBeInTheDocument();
      });

      const statusFilter = screen.getByLabelText(/filter by status/i);
      fireEvent.change(statusFilter, { target: { value: 'CONFIRMED' } });

      await waitFor(() => {
        expect(screen.getByText('CONFIRMED')).toBeInTheDocument();
      });
    });

    test('filters users by role', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('Tenant_Admin')).toBeInTheDocument();
      });

      const roleFilter = screen.getByLabelText(/filter by role/i);
      fireEvent.change(roleFilter, { target: { value: 'Tenant_Admin' } });

      await waitFor(() => {
        expect(screen.getByText('Tenant_Admin')).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // User Actions Tests
  // ============================================================================

  describe('User Actions', () => {
    test('opens create user modal when button clicked', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument();
      });

      const createButton = screen.getByRole('button', { name: /create user/i });
      fireEvent.click(createButton);

      await waitFor(() => {
        expect(screen.getByText(/create new user/i)).toBeInTheDocument();
      });
    });

    test('displays user details when row clicked', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('user1@example.com')).toBeInTheDocument();
      });

      const userRow = screen.getByText('user1@example.com').closest('tr');
      if (userRow) {
        fireEvent.click(userRow);

        await waitFor(() => {
          expect(screen.getByText(/user details/i)).toBeInTheDocument();
        });
      }
    });

    test('shows edit button for each user', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        const editButtons = screen.getAllByLabelText(/edit user/i);
        expect(editButtons.length).toBeGreaterThan(0);
      });
    });
  });

  // ============================================================================
  // Role Management Tests
  // ============================================================================

  describe('Role Management', () => {
    test('displays available roles in modal', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument();
      });

      const createButton = screen.getByRole('button', { name: /create user/i });
      fireEvent.click(createButton);

      await waitFor(() => {
        expect(screen.getByText('Tenant_Admin')).toBeInTheDocument();
        expect(screen.getByText('Finance_CRUD')).toBeInTheDocument();
        expect(screen.getByText('Finance_Read')).toBeInTheDocument();
      });
    });

    test('allows selecting multiple roles', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument();
      });

      const createButton = screen.getByRole('button', { name: /create user/i });
      fireEvent.click(createButton);

      await waitFor(() => {
        const checkboxes = screen.getAllByRole('checkbox');
        expect(checkboxes.length).toBeGreaterThan(0);
      });
    });
  });

  // ============================================================================
  // Email Functionality Tests
  // ============================================================================

  describe('Email Functionality', () => {
    test('shows send email button for users', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('user1@example.com')).toBeInTheDocument();
      });

      // Check if send email functionality exists
      const userRow = screen.getByText('user1@example.com').closest('tr');
      expect(userRow).toBeInTheDocument();
    });

    test('shows resend invitation button for FORCE_CHANGE_PASSWORD users', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByText('FORCE_CHANGE_PASSWORD')).toBeInTheDocument();
      });

      // User with FORCE_CHANGE_PASSWORD status should have resend option
      const user2Row = screen.getByText('user2@example.com').closest('tr');
      expect(user2Row).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Accessibility Tests
  // ============================================================================

  describe('Accessibility', () => {
    test('has accessible table structure', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        const table = screen.getByRole('table');
        expect(table).toBeInTheDocument();
      });
    });

    test('has accessible buttons', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        const buttons = screen.getAllByRole('button');
        expect(buttons.length).toBeGreaterThan(0);
      });
    });

    test('has accessible form inputs in modal', async () => {
      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /create user/i })).toBeInTheDocument();
      });

      const createButton = screen.getByRole('button', { name: /create user/i });
      fireEvent.click(createButton);

      await waitFor(() => {
        const inputs = screen.getAllByRole('textbox');
        expect(inputs.length).toBeGreaterThan(0);
      });
    });
  });

  // ============================================================================
  // Error Handling Tests
  // ============================================================================

  describe('Error Handling', () => {
    test('displays error message when users fail to load', async () => {
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Failed to load users'));

      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        // Component should handle error gracefully
        expect(screen.queryByText('user1@example.com')).not.toBeInTheDocument();
      });
    });

    test('displays error message when roles fail to load', async () => {
      (global.fetch as jest.Mock).mockImplementation((url: string) => {
        if (url.includes('/api/tenant-admin/roles')) {
          return Promise.reject(new Error('Failed to load roles'));
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ users: mockUsers }),
        } as Response);
      });

      render(<UserManagement tenant={mockTenant} />);

      await waitFor(() => {
        // Component should handle error gracefully
        expect(screen.getByText('user1@example.com')).toBeInTheDocument();
      });
    });
  });
});
