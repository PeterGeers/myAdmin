/**
 * Tests for TenantSelector Component
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import TenantSelector from './TenantSelector';

// Mock the tenant context
const mockUseTenant = jest.fn();

jest.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant()
}));

// Mock Chakra UI components to avoid dependency issues
jest.mock('@chakra-ui/react', () => ({
  HStack: ({ children }: any) => <div data-testid="hstack">{children}</div>,
  Text: ({ children }: any) => <span>{children}</span>,
  Select: ({ children, value, onChange }: any) => (
    <select data-testid="tenant-select" value={value} onChange={onChange}>
      {children}
    </select>
  )
}));

describe('TenantSelector', () => {
  it('should render tenant selector for users with multiple tenants', () => {
    mockUseTenant.mockReturnValue({
      currentTenant: 'GoodwinSolutions',
      availableTenants: ['GoodwinSolutions', 'PeterPrive'],
      setCurrentTenant: jest.fn(),
      hasMultipleTenants: true
    });

    render(<TenantSelector />);

    expect(screen.getByTestId('tenant-select')).toBeInTheDocument();
  });

  it('should not render for users with single tenant', () => {
    mockUseTenant.mockReturnValue({
      currentTenant: 'GoodwinSolutions',
      availableTenants: ['GoodwinSolutions'],
      setCurrentTenant: jest.fn(),
      hasMultipleTenants: false
    });

    const { container } = render(<TenantSelector />);

    // Should not render anything
    expect(container.firstChild).toBeNull();
  });
});
