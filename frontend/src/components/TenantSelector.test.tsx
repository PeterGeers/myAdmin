/**
 * Tests for TenantSelector Component
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen } from '@/test-utils';
import TenantSelector from './TenantSelector';

// Mock the tenant context
const mockUseTenant = vi.fn();

vi.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant()
}));


describe('TenantSelector', () => {
  it('should render tenant selector for users with multiple tenants', () => {
    mockUseTenant.mockReturnValue({
      currentTenant: 'GoodwinSolutions',
      availableTenants: ['GoodwinSolutions', 'PeterPrive'],
      setCurrentTenant: vi.fn(),
      hasMultipleTenants: true
    });

    render(<TenantSelector />);

    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('should not render for users with single tenant', () => {
    mockUseTenant.mockReturnValue({
      currentTenant: 'GoodwinSolutions',
      availableTenants: ['GoodwinSolutions'],
      setCurrentTenant: vi.fn(),
      hasMultipleTenants: false
    });

    const { container } = render(<TenantSelector />);

    // Should not render anything
    expect(container.firstChild).toBeNull();
  });
});
