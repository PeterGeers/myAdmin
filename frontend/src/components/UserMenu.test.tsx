import React from 'react';
import { render, screen, fireEvent, within } from '@/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import UserMenu from './UserMenu';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock TenantContext
const mockUseTenant = vi.fn();
vi.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant(),
}));

// Default mock values
const defaultUser = {
  username: 'user-123-abc',
  email: 'john@example.com',
  name: 'John Doe',
  roles: ['Administrators', 'Finance'],
  tenants: ['tenant-a', 'tenant-b'],
  sub: 'sub-123',
};

const defaultTenantContext = {
  currentTenant: 'tenant-a',
  availableTenants: ['tenant-a', 'tenant-b'],
  setCurrentTenant: vi.fn(),
  hasMultipleTenants: true,
};

describe('UserMenu Component', () => {
  const mockOnLogout = vi.fn();
  const mockOnSettings = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: defaultUser });
    mockUseTenant.mockReturnValue(defaultTenantContext);
  });

  describe('Rendering', () => {
    it('renders the trigger button with user display name', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      // The trigger button contains the display name
      const button = screen.getByRole('button', { name: /John Doe/i });
      expect(button).toBeInTheDocument();
    });

    it('renders null when no user is present', () => {
      mockUseAuth.mockReturnValue({ user: null });
      const { container } = render(<UserMenu onLogout={mockOnLogout} />);
      expect(container.firstChild).toBeNull();
    });

    it('displays email as fallback when name is not available', () => {
      mockUseAuth.mockReturnValue({
        user: { ...defaultUser, name: null },
      });
      render(<UserMenu onLogout={mockOnLogout} />);
      const button = screen.getByRole('button', { name: /john@example.com/i });
      expect(button).toBeInTheDocument();
    });

    it('displays username as fallback when name and email are not available', () => {
      mockUseAuth.mockReturnValue({
        user: { ...defaultUser, name: null, email: null },
      });
      render(<UserMenu onLogout={mockOnLogout} />);
      const button = screen.getByRole('button', { name: /user-123-abc/i });
      expect(button).toBeInTheDocument();
    });
  });

  describe('Popover Content', () => {
    it('shows user information header', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('User Information')).toBeInTheDocument();
    });

    it('shows user name in the details section', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('Name')).toBeInTheDocument();
      // "John Doe" appears both in trigger and body
      const allJohnDoe = screen.getAllByText('John Doe');
      expect(allJohnDoe.length).toBe(2);
    });

    it('shows user email', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('Email')).toBeInTheDocument();
      expect(screen.getByText('john@example.com')).toBeInTheDocument();
    });

    it('shows N/A for email when not available', () => {
      mockUseAuth.mockReturnValue({
        user: { ...defaultUser, email: null },
      });
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('N/A')).toBeInTheDocument();
    });

    it('shows user ID when username differs from email', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('User ID')).toBeInTheDocument();
      expect(screen.getByText('user-123-abc')).toBeInTheDocument();
    });

    it('hides user ID when username equals email', () => {
      mockUseAuth.mockReturnValue({
        user: { ...defaultUser, username: 'john@example.com' },
      });
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.queryByText('User ID')).not.toBeInTheDocument();
    });

    it('displays user roles as badges', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('Administrators')).toBeInTheDocument();
      expect(screen.getByText('Finance')).toBeInTheDocument();
    });

    it('shows no roles message when roles array is empty', () => {
      mockUseAuth.mockReturnValue({
        user: { ...defaultUser, roles: [] },
      });
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('No roles assigned')).toBeInTheDocument();
    });

    it('displays available tenants', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('tenant-a')).toBeInTheDocument();
      expect(screen.getByText('tenant-b')).toBeInTheDocument();
    });

    it('marks the current tenant', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('(current)')).toBeInTheDocument();
    });

    it('shows no tenants message when tenants list is empty', () => {
      mockUseTenant.mockReturnValue({
        ...defaultTenantContext,
        availableTenants: [],
      });
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.getByText('No tenants assigned')).toBeInTheDocument();
    });
  });

  describe('Mode Display', () => {
    it('shows Test mode badge when mode is Test', () => {
      render(<UserMenu onLogout={mockOnLogout} mode="Test" />);
      expect(screen.getByText('Environment')).toBeInTheDocument();
      expect(screen.getByText(/Test/)).toBeInTheDocument();
      expect(screen.getByText(/Mode/)).toBeInTheDocument();
    });

    it('shows Production mode badge when mode is Production', () => {
      render(<UserMenu onLogout={mockOnLogout} mode="Production" />);
      expect(screen.getByText('Environment')).toBeInTheDocument();
      expect(screen.getByText(/Production/)).toBeInTheDocument();
    });

    it('does not show environment section when mode is not provided', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.queryByText('Environment')).not.toBeInTheDocument();
    });
  });

  describe('Actions', () => {
    it('calls onLogout when logout button is clicked', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      fireEvent.click(screen.getByText('Logout'));
      expect(mockOnLogout).toHaveBeenCalledTimes(1);
    });

    it('shows settings button when onSettings is provided', () => {
      render(<UserMenu onLogout={mockOnLogout} onSettings={mockOnSettings} />);
      expect(screen.getByText('⚙️ Settings')).toBeInTheDocument();
    });

    it('calls onSettings when settings button is clicked', () => {
      render(<UserMenu onLogout={mockOnLogout} onSettings={mockOnSettings} />);
      fireEvent.click(screen.getByText('⚙️ Settings'));
      expect(mockOnSettings).toHaveBeenCalledTimes(1);
    });

    it('does not show settings button when onSettings is not provided', () => {
      render(<UserMenu onLogout={mockOnLogout} />);
      expect(screen.queryByText('⚙️ Settings')).not.toBeInTheDocument();
    });
  });
});
