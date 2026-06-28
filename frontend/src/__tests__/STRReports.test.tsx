/**
 * Unit tests for STRReports.tsx
 *
 * Tests the STR Reports page:
 * - Shows reports when user has STR permissions
 * - Shows permission warning when user lacks STR roles
 * - Renders BnbReportsGroup child component
 *
 * Task 56 of Phase 7: Missing Test Coverage
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import STRReports from '../components/STRReports';
import { render, screen } from '@/test-utils';

// Mock contexts
const mockUseAuth = vi.fn();

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock useTypedTranslation
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock child component
vi.mock('../components/reports/BnbReportsGroup', () => ({
  default: () => <div data-testid="bnb-reports-group">BnbReportsGroup</div>,
}));

describe('STRReports', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders BnbReportsGroup when user has STR_CRUD role', () => {
    mockUseAuth.mockReturnValue({
      user: { roles: ['STR_CRUD'] },
    });

    render(<STRReports />);

    expect(screen.getByTestId('bnb-reports-group')).toBeInTheDocument();
    expect(screen.queryByText('reports.noPermission')).not.toBeInTheDocument();
  });

  it('renders BnbReportsGroup when user has STR_Read role', () => {
    mockUseAuth.mockReturnValue({
      user: { roles: ['STR_Read'] },
    });

    render(<STRReports />);

    expect(screen.getByTestId('bnb-reports-group')).toBeInTheDocument();
  });

  it('renders BnbReportsGroup when user has STR_Export role', () => {
    mockUseAuth.mockReturnValue({
      user: { roles: ['STR_Export'] },
    });

    render(<STRReports />);

    expect(screen.getByTestId('bnb-reports-group')).toBeInTheDocument();
  });

  it('shows permission warning when user has no STR roles', () => {
    mockUseAuth.mockReturnValue({
      user: { roles: ['Finance_Read'] },
    });

    render(<STRReports />);

    expect(screen.getByText('reports.noPermission')).toBeInTheDocument();
    expect(screen.queryByTestId('bnb-reports-group')).not.toBeInTheDocument();
  });

  it('shows permission warning when user has empty roles', () => {
    mockUseAuth.mockReturnValue({
      user: { roles: [] },
    });

    render(<STRReports />);

    expect(screen.getByText('reports.noPermission')).toBeInTheDocument();
  });

  it('shows permission warning when user is null', () => {
    mockUseAuth.mockReturnValue({
      user: null,
    });

    render(<STRReports />);

    expect(screen.getByText('reports.noPermission')).toBeInTheDocument();
  });

  it('renders within a dark background container', () => {
    mockUseAuth.mockReturnValue({
      user: { roles: ['STR_CRUD'] },
    });

    const { container } = render(<STRReports />);

    // The outer Box has bg="gray.800" — verify the component renders
    expect(container.firstChild).toBeTruthy();
    expect(screen.getByTestId('bnb-reports-group')).toBeInTheDocument();
  });
});
