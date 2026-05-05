/**
 * ProfitLossReport Component Tests
 *
 * Tests: hierarchical table, expand ledger → ReferenceNumber rows, drill-down level,
 * pivot view toggle, split charts, Update Data cache invalidation.
 */

import { vi } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import '@testing-library/jest-dom';
import ProfitLossReport from '../ProfitLossReport';
import { useTenant } from '../../../context/TenantContext';
import { authenticatedGet } from '../../../services/apiService';
import { invalidateAndFetch } from '../../../utils/financialReportUtils';
import { createMockResponse } from '@/test-utils/mockHelpers';

// --- Mocks ---

vi.mock('../../../context/TenantContext');
vi.mock('../../../services/apiService', async () => {
  const actual = await vi.importActual('../../../services/apiService');
  return {
    ...actual,
    authenticatedGet: vi.fn(),
    authenticatedPost: vi.fn().mockResolvedValue({ json: () => Promise.resolve({ success: true }) }),
  };
});
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));
vi.mock('../../../utils/financialReportUtils', async () => {
  const actual = await vi.importActual('../../../utils/financialReportUtils');
  return {
    ...actual,
    invalidateAndFetch: vi.fn(async (fn: () => Promise<void>) => fn()),
  };
});

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));
vi.mock('../../filters/YearFilter', () => ({
  YearFilter: () => <div data-testid="year-filter" />,
}));

// --- Test data ---

const mockUseTenant = vi.mocked(useTenant);
const mockAuthGet = vi.mocked(authenticatedGet);

const plResponse = {
  success: true,
  data: [
    { Parent: '4000 Costs', Reknum: '4010', AccountName: 'Office', jaar: 2024, kwartaal: 1, maand: 1, Amount: 500 },
    { Parent: '4000 Costs', Reknum: '4010', AccountName: 'Office', jaar: 2024, kwartaal: 2, maand: 4, Amount: 300 },
    { Parent: '8000 Revenue', Reknum: '8010', AccountName: 'Sales', jaar: 2024, kwartaal: 1, maand: 1, Amount: 5000 },
    { Parent: '8000 Revenue', Reknum: '8010', AccountName: 'Sales', jaar: 2025, kwartaal: 1, maand: 1, Amount: 6000 },
  ],
};

const refResponse = {
  success: true,
  data: [
    { Parent: '4000 Costs', Reknum: '4010', AccountName: 'Office', jaar: 2024, kwartaal: 1, maand: 1, Amount: 250, ReferenceNumber: 'INV-001' },
    { Parent: '4000 Costs', Reknum: '4010', AccountName: 'Office', jaar: 2024, kwartaal: 1, maand: 1, Amount: 250, ReferenceNumber: 'INV-002' },
  ],
};

const defaultProps = {
  selectedYears: ['2024', '2025'],
  displayFormat: '2dec' as const,
  availableYears: ['2023', '2024', '2025'],
  onYearsChange: vi.fn(),
  onDisplayFormatChange: vi.fn(),
};

const tenantCtx = {
  currentTenant: 'TestTenant',
  availableTenants: ['TestTenant'],
  setCurrentTenant: vi.fn(),
  hasMultipleTenants: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseTenant.mockReturnValue(tenantCtx);
  mockAuthGet.mockImplementation((url: string) => {
    if (url?.includes('includeRef=true')) {
      return Promise.resolve(createMockResponse({ body: refResponse }));
    }
    return Promise.resolve(createMockResponse({ body: plResponse }));
  });
});

// --- Tests ---

describe('ProfitLossReport', () => {
  it('renders parent rows in hierarchical table', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText('4000 Costs')).toBeInTheDocument();
      expect(screen.getByText('8000 Revenue')).toBeInTheDocument();
    });
  });

  it('expands parent to show ledger rows', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => expect(screen.getByText('4000 Costs')).toBeInTheDocument());

    fireEvent.click(screen.getAllByText('+')[0]);
    await waitFor(() => {
      expect(screen.getByText('4010 Office')).toBeInTheDocument();
    });
  });

  it('expands ledger to show ReferenceNumber rows', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => expect(screen.getByText('4000 Costs')).toBeInTheDocument());

    // Expand parent
    fireEvent.click(screen.getAllByText('+')[0]);
    await waitFor(() => expect(screen.getByText('4010 Office')).toBeInTheDocument());

    // Expand ledger
    fireEvent.click(screen.getAllByText('+')[0]);
    await waitFor(() => {
      expect(screen.getByText('INV-001')).toBeInTheDocument();
      expect(screen.getByText('INV-002')).toBeInTheDocument();
    });
  });

  it('renders column headers matching drill-down level', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText('2024')).toBeInTheDocument();
      expect(screen.getByText('2025')).toBeInTheDocument();
    });
  });

  it('renders grand total row', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText('actuals.total')).toBeInTheDocument();
    });
  });

  it('renders two separate bar charts (revenue + costs)', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => {
      const charts = screen.getAllByTestId('bar-chart');
      expect(charts.length).toBe(2);
    });
  });

  it('shows Standard/Pivot toggle buttons', () => {
    render(<ProfitLossReport {...defaultProps} />);
    expect(screen.getByText('actuals.standardView')).toBeInTheDocument();
    expect(screen.getByText('actuals.pivotView')).toBeInTheDocument();
  });

  it('pivot view shows accounts as column headers', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => expect(screen.getByText('4000 Costs')).toBeInTheDocument());

    fireEvent.click(screen.getByText('actuals.pivotView'));
    await waitFor(() => {
      // In pivot view, accounts move to column headers (with +/- prefix)
      expect(screen.getByText(/4000 Costs/)).toBeInTheDocument();
      expect(screen.getByText(/8000 Revenue/)).toBeInTheDocument();
      // Rows should now be time periods
      expect(screen.getByText('2024')).toBeInTheDocument();
      expect(screen.getByText('2025')).toBeInTheDocument();
    });
  });

  it('Update Data button triggers invalidateAndFetch', async () => {
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => expect(screen.getByText('actuals.refresh')).toBeInTheDocument());

    fireEvent.click(screen.getByText('actuals.refresh'));
    await waitFor(() => {
      expect(invalidateAndFetch).toHaveBeenCalled();
    });
  });

  it('shows drill-down level buttons', () => {
    render(<ProfitLossReport {...defaultProps} />);
    expect(screen.getByText(/actuals\.year/)).toBeInTheDocument();
    expect(screen.getByText(/actuals\.quarter/)).toBeInTheDocument();
    expect(screen.getByText(/actuals\.month/)).toBeInTheDocument();
  });

  it('shows error on API failure', async () => {
    mockAuthGet.mockRejectedValue(new Error('fail'));
    render(<ProfitLossReport {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText('actuals.errorLoadingData')).toBeInTheDocument();
    });
  });
});
