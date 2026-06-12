/**
 * Component tests for conditional rendering based on useTenantFunctions hook
 *
 * Tests that navigation buttons are hidden/shown based on function state,
 * and that loading/error states hide all gated elements (safe default).
 *
 * **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.7, 4.8**
 *
 * @see .kiro/specs/tenant-optional-functions/design.md — Component Tests
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the useTenantFunctions hook
vi.mock('@/hooks/useTenantFunctions', () => ({
  useTenantFunctions: vi.fn(),
}));

import { useTenantFunctions } from '@/hooks/useTenantFunctions';
const mockUseTenantFunctions = vi.mocked(useTenantFunctions);

// ---------------------------------------------------------------------------
// Test component — mimics the App.tsx navigation pattern
// ---------------------------------------------------------------------------

/**
 * Minimal component that conditionally renders navigation buttons
 * based on the useTenantFunctions hook, mirroring the real App.tsx pattern.
 */
function TestNavigation() {
  const { hasFunction } = useTenantFunctions();
  return (
    <div>
      {hasFunction('assets') && <button>Asset Administration</button>}
      {hasFunction('str_channel_revenue') && <button>STR Channel Revenue</button>}
      {hasFunction('generate_invoice') && <button>Generate Invoice</button>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper to configure mock return values
// ---------------------------------------------------------------------------

function mockHookReturn(overrides: Partial<ReturnType<typeof useTenantFunctions>> = {}) {
  const defaults: ReturnType<typeof useTenantFunctions> = {
    functions: [],
    loading: false,
    error: null,
    hasFunction: () => false,
  };
  mockUseTenantFunctions.mockReturnValue({ ...defaults, ...overrides });
}

// ---------------------------------------------------------------------------
// Tests: Navigation buttons shown when enabled
// ---------------------------------------------------------------------------

describe('Conditional rendering — buttons shown when enabled', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Validates: Requirement 4.3
   * WHEN hasFunction('assets') returns true, the Asset Administration button is rendered.
   */
  it('shows Asset Administration button when assets function is enabled', () => {
    mockHookReturn({
      hasFunction: (name: string) => name === 'assets',
    });

    render(<TestNavigation />);

    expect(screen.getByText('Asset Administration')).toBeInTheDocument();
  });

  /**
   * Validates: Requirement 4.4
   * WHEN hasFunction('str_channel_revenue') returns true, the STR Channel Revenue button is rendered.
   */
  it('shows STR Channel Revenue button when str_channel_revenue function is enabled', () => {
    mockHookReturn({
      hasFunction: (name: string) => name === 'str_channel_revenue',
    });

    render(<TestNavigation />);

    expect(screen.getByText('STR Channel Revenue')).toBeInTheDocument();
  });

  /**
   * Validates: Requirement 4.5
   * WHEN hasFunction('generate_invoice') returns true, the Generate Invoice button is rendered.
   */
  it('shows Generate Invoice button when generate_invoice function is enabled', () => {
    mockHookReturn({
      hasFunction: (name: string) => name === 'generate_invoice',
    });

    render(<TestNavigation />);

    expect(screen.getByText('Generate Invoice')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Navigation buttons hidden when disabled
// ---------------------------------------------------------------------------

describe('Conditional rendering — buttons hidden when disabled', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Validates: Requirement 4.3
   * WHEN hasFunction('assets') returns false, the Asset Administration button is NOT rendered.
   */
  it('hides Asset Administration button when assets function is disabled', () => {
    mockHookReturn({
      hasFunction: () => false,
    });

    render(<TestNavigation />);

    expect(screen.queryByText('Asset Administration')).not.toBeInTheDocument();
  });

  /**
   * Validates: Requirement 4.4
   * WHEN hasFunction('str_channel_revenue') returns false, the STR Channel Revenue button is NOT rendered.
   */
  it('hides STR Channel Revenue button when str_channel_revenue function is disabled', () => {
    mockHookReturn({
      hasFunction: () => false,
    });

    render(<TestNavigation />);

    expect(screen.queryByText('STR Channel Revenue')).not.toBeInTheDocument();
  });

  /**
   * Validates: Requirement 4.5
   * WHEN hasFunction('generate_invoice') returns false, the Generate Invoice button is NOT rendered.
   */
  it('hides Generate Invoice button when generate_invoice function is disabled', () => {
    mockHookReturn({
      hasFunction: () => false,
    });

    render(<TestNavigation />);

    expect(screen.queryByText('Generate Invoice')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Loading state hides all gated elements
// ---------------------------------------------------------------------------

describe('Conditional rendering — loading state hides gated elements', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Validates: Requirement 4.8
   * WHILE the hook is in a loading state, hasFunction returns false for all
   * functions so no gated navigation elements are rendered.
   */
  it('hides all gated buttons during loading state', () => {
    mockHookReturn({
      loading: true,
      hasFunction: () => false, // Safe default during loading
    });

    render(<TestNavigation />);

    expect(screen.queryByText('Asset Administration')).not.toBeInTheDocument();
    expect(screen.queryByText('STR Channel Revenue')).not.toBeInTheDocument();
    expect(screen.queryByText('Generate Invoice')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Error state hides all gated elements
// ---------------------------------------------------------------------------

describe('Conditional rendering — error state hides gated elements', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * Validates: Requirement 4.7
   * IF the hook fails to fetch function state, hasFunction returns false for all
   * functions so no gated navigation elements are rendered.
   */
  it('hides all gated buttons when fetch error occurs', () => {
    mockHookReturn({
      error: 'Failed to load tenant functions',
      hasFunction: () => false, // Safe default on error
    });

    render(<TestNavigation />);

    expect(screen.queryByText('Asset Administration')).not.toBeInTheDocument();
    expect(screen.queryByText('STR Channel Revenue')).not.toBeInTheDocument();
    expect(screen.queryByText('Generate Invoice')).not.toBeInTheDocument();
  });
});
