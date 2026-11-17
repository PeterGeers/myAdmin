/**
 * TenantAdminDashboard — registry-driven rendering (Properties 5/7/9).
 *
 * Feature: admin-surface-registry
 * The dashboard renders EXACTLY the surfaces the backend derives — no extra
 * hardcoded tabs, no per-module conditionals. A fetch failure degrades to the
 * baseline surfaces + a toast; an unknown id renders a visible error panel.
 *
 * Validates: Requirements 5.1–5.6, 8.2, 8.3
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen } from '../../../test-utils';

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 't-1' }),
}));

function makeIdToken(tenants: string[]): string {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ 'custom:tenants': JSON.stringify(tenants) }));
  return `${header}.${payload}.sig`;
}

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(() =>
    Promise.resolve({
      tokens: { idToken: { toString: () => makeIdToken(['t-1']) } },
    }),
  ),
}));

const mockToast = vi.fn();
vi.mock('@chakra-ui/react', async () => {
  const actual = await vi.importActual('@chakra-ui/react');
  return { ...actual, useToast: () => mockToast };
});

vi.mock('../../../services/apiService', () => ({
  buildEndpoint: (endpoint: string) => endpoint,
  authenticatedGet: vi.fn((endpoint: string) => {
    if (endpoint.startsWith('/api/auth/me')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ roles: ['Tenant_Admin'] }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ tenant: 't-1', available_modules: [] }),
    });
  }),
}));

// Configurable surface state for the hook.
type Surface = {
  id: string;
  kind: 'always' | 'module' | 'capability' | 'role';
  order: number;
  label_key: string;
};
let mockSurfaces: Surface[] = [];
let mockSurfacesError: string | null = null;

vi.mock('../../../hooks/useTenantAdminSurfaces', () => ({
  useTenantAdminSurfaces: () => ({
    surfaces: mockSurfaces,
    fallbackSurfaceIds: ['users', 'tenant-info', 'sender', 'landing'],
    loading: false,
    error: mockSurfacesError,
  }),
}));

vi.mock('../adminSurfaceComponents', () => ({
  SurfaceComponent: ({ surface }: { surface: Surface }) =>
    surface.id === 'users' || surface.id === 'tenant-info' || surface.id === 'sender' ||
    surface.id === 'landing' ? (
      <div data-testid={`stub-${surface.id}`} />
    ) : surface.id === 'unknown' ? (
      <div data-testid="unknown-panel">Unknown admin surface: {surface.id}</div>
    ) : (
      <div data-testid={`stub-${surface.id}`} />
    ),
}));

import { TenantAdminDashboard } from '../TenantAdminDashboard';

const surface = (id: string, kind: Surface['kind'] = 'always', order = 10): Surface => ({
  id,
  kind,
  order,
  label_key: `tenantAdmin.tabs.${id}`,
});

beforeEach(() => {
  mockSurfaces = [];
  mockSurfacesError = null;
  vi.clearAllMocks();
});

describe('TenantAdminDashboard — registry-driven rendering', () => {
  it('renders exactly the surfaces the backend derived (no extras)', async () => {
    mockSurfaces = [surface('users'), surface('financial', 'module', 100)];
    render(<TenantAdminDashboard />);

    await screen.findByTestId('stub-users');
    expect(screen.getByTestId('stub-financial')).toBeInTheDocument();
    // A surface NOT returned by the backend must not appear.
    expect(screen.queryByTestId('stub-members')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stub-storage')).not.toBeInTheDocument();
  });

  it('renders a Members-only tenant with the members panel and no financial tab', async () => {
    mockSurfaces = [surface('users'), surface('members', 'module', 110)];
    render(<TenantAdminDashboard />);
    await screen.findByTestId('stub-users');
    expect(screen.getByTestId('stub-members')).toBeInTheDocument();
    expect(screen.queryByTestId('stub-financial')).not.toBeInTheDocument();
  });

  it('renders a dual tenant with both panels and one storage surface', async () => {
    mockSurfaces = [
      surface('users'),
      surface('financial', 'module', 100),
      surface('members', 'module', 110),
      surface('storage', 'capability', 200),
    ];
    render(<TenantAdminDashboard />);
    await screen.findByTestId('stub-users');
    expect(screen.getByTestId('stub-financial')).toBeInTheDocument();
    expect(screen.getByTestId('stub-members')).toBeInTheDocument();
    expect(screen.getAllByTestId('stub-storage')).toHaveLength(1);
  });

  it('falls back to the baseline surfaces and toasts when the fetch failed', async () => {
    mockSurfaces = [];
    mockSurfacesError = 'Failed to load tenant admin surfaces';
    render(<TenantAdminDashboard />);

    await screen.findByTestId('stub-users');
    expect(screen.getByTestId('stub-tenant-info')).toBeInTheDocument();
    expect(screen.getByTestId('stub-sender')).toBeInTheDocument();
    expect(screen.getByTestId('stub-landing')).toBeInTheDocument();
    // Module/capability surfaces must NOT appear on failure.
    expect(screen.queryByTestId('stub-financial')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stub-members')).not.toBeInTheDocument();
    expect(mockToast).toHaveBeenCalled();
  });

  it('renders a visible error panel for an unknown surface id (no silent drop)', async () => {
    mockSurfaces = [surface('users'), surface('unknown')];
    render(<TenantAdminDashboard />);
    await screen.findByTestId('stub-users');
    expect(screen.getByTestId('unknown-panel')).toHaveTextContent(
      'Unknown admin surface: unknown',
    );
  });
});
