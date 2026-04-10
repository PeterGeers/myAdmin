/**
 * ProfitLossReport Component Tests
 *
 * Tests: hierarchical table, expand ledger → ReferenceNumber rows, drill-down level,
 * pivot view toggle, split charts, Update Data cache invalidation.
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProfitLossReport from '../ProfitLossReport';
import { useTenant } from '../../../context/TenantContext';
import { authenticatedGet } from '../../../services/apiService';

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
jest.mock('@chakra-ui/react', () => ({
  Alert: ({ children }: any) => <div data-testid="alert">{children}</div>,
  AlertIcon: () => <span>!</span>,
  Button: ({ children, onClick, isLoading, ...p }: any) => (
    <button onClick={onClick} data-loading={isLoading} {...p}>{children}</button>
  ),
  ButtonGroup: ({ children }: any) => <div data-testid="button-group">{children}</div>,
  Card: ({ children }: any) => <div>{children}</div>,
  CardBody: ({ children }: any) => <div>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  Grid: ({ children }: any) => <div>{children}</div>,
  GridItem: ({ children }: any) => <div>{children}</div>,
  HStack: ({ children }: any) => <div>{children}</div>,
  Heading: ({ children, size }: any) => <h2 data-size={size}>{children}</h2>,
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
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));
jest.mock('../../filters/YearFilter', () => ({
  YearFilter: () => <div data-testid="year-filter" />,
}));

// --- Test data ---

const mockUseTenant = useTenant as jest.MockedFunction<typeof useTenant>;
const mockAuthGet = authenticatedGet as jest.MockedFunction<typeof authenticatedGet>;

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
  onYearsChange: jest.fn(),
  onDisplayFormatChange: jest.fn(),
};

const tenantCtx = {
  currentTenant: 'TestTenant',
  availableTenants: ['TestTenant'],
  setCurrentTenant: jest.fn(),
  hasMultipleTenants: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockUseTenant.mockReturnValue(tenantCtx);
  mockAuthGet.mockImplementation((url: string) => {
    if (url?.includes('includeRef=true')) {
      return Promise.resolve({ json: () => Promise.resolve(refResponse) } as Response);
    }
    return Promise.resolve({ json: () => Promise.resolve(plResponse) } as Response);
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
    const { invalidateAndFetch } = require('../../../utils/financialReportUtils');
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
