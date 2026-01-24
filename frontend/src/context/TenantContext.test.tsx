/**
 * Tests for TenantContext
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { TenantProvider, useTenant } from './TenantContext';
import { AuthProvider } from './AuthContext';

// Mock AuthContext
jest.mock('./AuthContext', () => ({
  ...jest.requireActual('./AuthContext'),
  useAuth: () => ({
    user: {
      username: 'testuser',
      email: 'test@example.com',
      roles: ['Finance_CRUD'],
      tenants: ['GoodwinSolutions', 'PeterPrive'],
      sub: 'test-sub'
    },
    loading: false,
    isAuthenticated: true,
    logout: jest.fn(),
    refreshUserRoles: jest.fn(),
    hasRole: jest.fn(),
    hasAnyRole: jest.fn(),
    hasAllRoles: jest.fn(),
    validateRoles: jest.fn()
  })
}));

// Test component that uses tenant context
function TestComponent() {
  const { currentTenant, availableTenants, hasMultipleTenants } = useTenant();
  
  return (
    <div>
      <div data-testid="current-tenant">{currentTenant || 'none'}</div>
      <div data-testid="available-tenants">{availableTenants.join(',')}</div>
      <div data-testid="has-multiple">{hasMultipleTenants ? 'yes' : 'no'}</div>
    </div>
  );
}

describe('TenantContext', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('should provide tenant context', async () => {
    render(
      <TenantProvider>
        <TestComponent />
      </TenantProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('current-tenant')).toHaveTextContent('GoodwinSolutions');
    });

    expect(screen.getByTestId('available-tenants')).toHaveTextContent('GoodwinSolutions,PeterPrive');
    expect(screen.getByTestId('has-multiple')).toHaveTextContent('yes');
  });

  it('should restore tenant from localStorage', async () => {
    localStorage.setItem('selectedTenant', 'PeterPrive');

    render(
      <TenantProvider>
        <TestComponent />
      </TenantProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('current-tenant')).toHaveTextContent('PeterPrive');
    });
  });
});
