/**
 * Unit tests for BudgetPage.tsx
 *
 * Tests the budget preparation page:
 * - Version selector rendering
 * - Lines table rendering
 * - Status bar with contextual actions
 *
 * Task 56 of Phase 7: Missing Test Coverage
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import * as chakra from '@chakra-ui/react';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import BudgetPage from '../pages/BudgetPage';
import * as budgetService from '../services/budgetService';

vi.mock('../services/budgetService');

// Stabilize useToast
const stableToast = vi.fn() as unknown as ReturnType<typeof chakra.useToast>;
vi.spyOn(chakra, 'useToast').mockReturnValue(stableToast);

// Mock sub-components to keep tests fast
vi.mock('../pages/BudgetLineModal', () => ({
  default: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="line-modal">Line Modal</div> : null,
}));

vi.mock('../pages/BudgetNewVersionModal', () => ({
  default: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="new-version-modal">New Version Modal</div> : null,
}));

const mockListVersions = vi.mocked(budgetService.listVersions);
const mockListLines = vi.mocked(budgetService.listLines);

const mockVersions = [
  {
    id: 1,
    name: 'Budget 2025',
    fiscal_year: 2025,
    status: 'Draft' as const,
    is_active: false,
    status_changed_at: null,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
];

const mockLines = [
  {
    id: 10,
    version_id: 1,
    account_code: '4000',
    period_mode: 'Monthly' as const,
    detail_dimension_type: null,
    detail_dimension_value: null,
    month_01: 1000, month_02: 1200, month_03: 1100, month_04: 950,
    month_05: 1300, month_06: 1250, month_07: 1400, month_08: 1350,
    month_09: 1200, month_10: 1150, month_11: 1050, month_12: 1500,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
];

describe('BudgetPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListVersions.mockResolvedValue({ success: true, data: mockVersions });
    mockListLines.mockResolvedValue({ success: true, data: mockLines });
  });

  it('renders version selector after loading', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText(/Budget 2025/)).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders Create Version button', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('buttons.createVersion')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders Draft status badge for draft version', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('Draft')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('shows Approve button for Draft version', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('buttons.approve')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders lines table with account code', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('4000')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders Add Line button for Draft version', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('buttons.addLine')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('opens New Version modal on button click', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('buttons.createVersion')).toBeInTheDocument();
    }, { timeout: 5000 });

    fireEvent.click(screen.getByText('buttons.createVersion'));

    await waitFor(() => {
      expect(screen.getByTestId('new-version-modal')).toBeInTheDocument();
    });
  });

  it('handles empty versions list', async () => {
    mockListVersions.mockResolvedValue({ success: true, data: [] });
    mockListLines.mockResolvedValue({ success: true, data: [] });

    render(<BudgetPage />);

    await waitFor(() => {
      // The select should show no version placeholder
      expect(screen.getByText('messages.noVersions')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders Delete button for Draft version', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(screen.getByText('buttons.delete')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('calls listVersions on mount', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(mockListVersions).toHaveBeenCalled();
    });
  });

  it('calls listLines when a version is selected', async () => {
    render(<BudgetPage />);

    await waitFor(() => {
      expect(mockListLines).toHaveBeenCalledWith(1);
    }, { timeout: 5000 });
  });
});
