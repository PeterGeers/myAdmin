/**
 * BalanceReport Component Tests
 *
 * Tests the BalanceReport component: year-column rendering, closed/open indicators,
 * expand/collapse, grand totals, Update Data cache invalidation, and loading state.
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import BalanceReport from '../BalanceReport';
import { useTenant } from '../../../context/TenantContext';
import { authenticatedGet } from '../../../services/apiService';
import { getClosedYears } from '../../../services/yearEndClosureService';

// --- Mocks ---

jest.mock('../../../context/TenantContext');
jest.mock('../../../services/apiService', () => {
  const actual = jest.requireActual('../../../services/apiService');
  return {
    ...actual,
    authenticatedGet: jest.fn(),
    authenticatedPost: jest.fn().mockResolvedValue({ json: () => Promise.resolve({ success: true }) }),
  };
});
jest.mock('../../../services/yearEndClosureService');
jest.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: jest.fn() },
  }),
}));

jest.mock('../../../utils/financialReportUtils', () => {
  const actual = jest.requireActual('../../../utils/financialReportUtils');
  return {
    ...actual,
    invalidateAndFetch: jest.fn(async (fn: () => Promise<void>) => fn()),
  };
});

// Mock Chakra UI
jest.mock('@chakra-ui/react', () => ({
  Alert: ({ children, ...p }: any) => <div data-testid="alert" {...p}>{children}</div>,
  AlertIcon: () => <span data-testid="alert-icon">!</span>,
  Button: ({ children, onClick, isLoading, ...p }: any) => (
    <button onClick={onClick} data-loading={isLoading} {...p}>{children}</button>
  ),
  Card: ({ children }: any) => <div>{children}</div>,
  CardBody: ({ children }: any) => <div>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  Grid: ({ children }: any) => <div>{children}</div>,
  GridItem: ({ children }: any) => <div>{children}</div>,
  HStack: ({ children }: any) => <div>{children}</div>,
  Heading: ({ children }: any) => <h2>{children}</h2>,
  Select: ({ children, onChange, value }: any) => (
    <select onChange={onChange} value={value} data-testid="select">{children}</select>
  ),
  Table: ({ children }: any) => <table>{children}</table>,
  TableContainer: ({ children }: any) => <div>{children}</div>,
  Tbody: ({ children }: any) => <tbody>{children}</tbody>,
  Td: ({ children }: any) => <td>{children}</td>,
  Text: ({ children }: any) => <span>{children}</span>,
  Th: ({ children }: any) => <th>{children}</th>,
  Thead: ({ children }: any) => <thead>{children}</thead>,
  Tr: ({ children }: any) => <tr>{children}</tr>,
  VStack: ({ children }: any) => <div>{children}</div>,
  useToast: () => jest.fn(),
}));

jest.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div data-testid="responsive-container">{children}</div>,
  PieChart: ({ children }: any) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  Tooltip: () => <div data-testid="tooltip" />,
}));

jest.mock('../../filters/YearFilter', () => ({
  YearFilter: (props: any) => <div data-testid="year-filter" />,
}));

// --- Test data ---

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockAuthGet = authenticatedGet as jest.MockedFunction<typeof authenticatedGet>;
const mockGetClosedYears = getClosedYears as jest.MockedFunction<typeof getClosedYears>;

const mockBalanceResponse = {
  success: true,
  data: [
    { Parent: '1000 Assets', Reknum: '1010', AccountName: 'Bank', jaar: 2024, Amount: 25000 },
    { Parent: '1000 Assets', Reknum: '1020', AccountName: 'Cash', jaar: 2024, Amount: 5000 },
    { Parent: '1000 Assets', Reknum: '1010', AccountName: 'Bank', jaar: 2025, Amount: 30000 },
    { Parent: '2000 Liabilities', Reknum: '2010', AccountName: 'Loan', jaar: 2024, Amount: -10000 },
    { Parent: '2000 Liabilities', Reknum: '2010', AccountName: 'Loan', jaar: 2025, Amount: -8000 },
  ],
  closedYears: [2024],
};

const defaultProps = {
  selectedYears: ['2024', '2025'],
  displayFormat: '2dec' as const,
  availableYears: ['2023', '2024', '2025'],
  onYearsChange: jest.fn(),
  onDisplayFormatChange: jest.fn(),
};

const tenantCtx = {
  currentTenant: 'TestTenant',
  availableTenants: ['TestTenant'],
  setCurrentTenant: jest.fn(),
  hasMultipleTenants: false,
};

// --- Setup ---

beforeEach(() => {
  jest.clearAllMocks();
  mockUseTenant.mockReturnValue(tenantCtx);
  mockGetClosedYears.mockResolvedValue([
    { year: 2024, closed_date: '2025-01-15', closed_by: 'admin',
      closure_transaction_number: 'YC2024', opening_balance_transaction_number: 'OB2025', notes: '' },
  ]);
  mockAuthGet.mockResolvedValue({
    json: () => Promise.resolve(mockBalanceResponse),
  } as Response);
});

// --- Tests ---

describe('BalanceReport', () => {
  it('renders year columns with closed/open indicators', async () => {
    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      // 2024 is closed → 🔒, 2025 is open → 🔓
      expect(screen.getByText(/2024.*🔒/)).toBeInTheDocument();
      expect(screen.getByText(/2025.*🔓/)).toBeInTheDocument();
    });
  });

  it('renders parent rows', async () => {
    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('1000 Assets')).toBeInTheDocument();
      expect(screen.getByText('2000 Liabilities')).toBeInTheDocument();
    });
  });

  it('expands parent to show ledger detail', async () => {
    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('1000 Assets')).toBeInTheDocument();
    });

    // Click expand button (first '+')
    const expandButtons = screen.getAllByText('+');
    fireEvent.click(expandButtons[0]);

    await waitFor(() => {
      expect(screen.getByText('1010 Bank')).toBeInTheDocument();
      expect(screen.getByText('1020 Cash')).toBeInTheDocument();
    });
  });

  it('renders grand total row', async () => {
    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('actuals.total')).toBeInTheDocument();
    });
  });

  it('calls API with per_year=true and correct tenant', async () => {
    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(mockAuthGet).toHaveBeenCalledWith(
        expect.stringContaining('per_year=true')
      );
      expect(mockAuthGet).toHaveBeenCalledWith(
        expect.stringContaining('administration=TestTenant')
      );
    });
  });

  it('Update Data button triggers invalidateAndFetch', async () => {
    const { invalidateAndFetch } = require('../../../utils/financialReportUtils');

    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('actuals.refresh')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('actuals.refresh'));

    await waitFor(() => {
      expect(invalidateAndFetch).toHaveBeenCalled();
    });
  });

  it('renders pie chart', async () => {
    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
    });
  });

  it('shows warning when no tenant selected', () => {
    mockUseTenant.mockReturnValue({
      currentTenant: null as any,
      availableTenants: [],
      setCurrentTenant: jest.fn(),
      hasMultipleTenants: false,
    });

    render(<BalanceReport {...defaultProps} />);

    expect(screen.getByText('actuals.noTenantSelected')).toBeInTheDocument();
    expect(mockAuthGet).not.toHaveBeenCalled();
  });

  it('shows error on API failure', async () => {
    mockAuthGet.mockRejectedValue(new Error('Network error'));

    render(<BalanceReport {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('actuals.errorLoadingData')).toBeInTheDocument();
    });
  });

  it('renders year filter', () => {
    render(<BalanceReport {...defaultProps} />);
    expect(screen.getByTestId('year-filter')).toBeInTheDocument();
  });
});
