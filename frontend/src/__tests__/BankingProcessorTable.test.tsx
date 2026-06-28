/**
 * Unit tests for BankingProcessorTable.tsx
 *
 * Tests the transaction review table component:
 * - Renders nothing when no transactions
 * - Renders table headers and rows
 * - Calls callbacks on button clicks
 * - Shows pattern results card when patterns available
 *
 * Task 55 of Phase 7: Missing Test Coverage
 */

import { vi, describe, it, expect } from 'vitest';
import BankingProcessorTable, {
  BankingProcessorTableProps,
  PatternResults,
} from '../components/BankingProcessorTable';
import type { Transaction } from '../components/BankingProcessor';
import { render, screen, fireEvent } from '@/test-utils';

// Mock FieldHelp to avoid complex tooltip rendering
vi.mock('../components/help', () => ({
  FieldHelp: () => <span data-testid="field-help" />,
}));

// Mock AccountSelect
vi.mock('../components/common/AccountSelect', () => ({
  default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <input data-testid="account-select" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

const mockT = (key: string, opts?: Record<string, unknown>) => {
  if (opts?.count !== undefined) return `${key} (${opts.count})`;
  return key;
};

const baseProps: BankingProcessorTableProps = {
  transactions: [],
  chartAccounts: [],
  loading: false,
  patternResults: null,
  updateTransaction: vi.fn(),
  onApplyPatterns: vi.fn(),
  onSaveTransactions: vi.fn(),
  getPatternFieldStyle: () => ({}),
  t: mockT,
};

const sampleTransaction: Transaction = {
  row_id: 1,
  TransactionNumber: '001',
  TransactionDate: '2025-06-15',
  TransactionDescription: 'PINBETALING HOOGVLIET',
  TransactionAmount: 45.50,
  Debet: '4000',
  Credit: '1300',
  ReferenceNumber: 'INV-001',
  Ref1: 'groceries',
  Ref2: '',
  Ref3: '',
  Administration: 'TestTenant',
  pattern_filled: { Debet: true, Credit: false },
};

describe('BankingProcessorTable', () => {
  it('renders nothing when transactions is empty', () => {
    const { container } = render(<BankingProcessorTable {...baseProps} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders table with transactions', () => {
    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
      />
    );

    // Heading with transaction count
    expect(screen.getByText('fileProcessing.reviewTransactions (1)')).toBeInTheDocument();
    // Action buttons
    expect(screen.getByText('fileProcessing.applyPatterns')).toBeInTheDocument();
    expect(screen.getByText('fileProcessing.saveTransactions')).toBeInTheDocument();
  });

  it('calls onApplyPatterns when Apply Patterns clicked', () => {
    const onApplyPatterns = vi.fn();
    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
        onApplyPatterns={onApplyPatterns}
      />
    );

    fireEvent.click(screen.getByText('fileProcessing.applyPatterns'));
    expect(onApplyPatterns).toHaveBeenCalledTimes(1);
  });

  it('calls onSaveTransactions when Save clicked', () => {
    const onSaveTransactions = vi.fn();
    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
        onSaveTransactions={onSaveTransactions}
      />
    );

    fireEvent.click(screen.getByText('fileProcessing.saveTransactions'));
    expect(onSaveTransactions).toHaveBeenCalledTimes(1);
  });

  it('renders pattern results card when patternResults is provided', () => {
    const patternResults: PatternResults = {
      patterns_found: 5,
      predictions_made: { debet: 3, credit: 2, reference: 1 },
      confidence_scores: [0.9, 0.8, 0.7],
      average_confidence: 0.8,
    };

    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
        patternResults={patternResults}
      />
    );

    expect(screen.getByText('labels.patternResultsTitle')).toBeInTheDocument();
  });

  it('does not render pattern results card when null', () => {
    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
        patternResults={null}
      />
    );

    expect(screen.queryByText('labels.patternResultsTitle')).not.toBeInTheDocument();
  });

  it('renders table headers', () => {
    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
      />
    );

    expect(screen.getByText('labels.trxNumber')).toBeInTheDocument();
    expect(screen.getByText('labels.date')).toBeInTheDocument();
    expect(screen.getByText('table.description')).toBeInTheDocument();
    expect(screen.getByText('table.amount')).toBeInTheDocument();
    expect(screen.getByText('table.debit')).toBeInTheDocument();
    expect(screen.getByText('table.credit')).toBeInTheDocument();
  });

  it('shows loading state on buttons', () => {
    render(
      <BankingProcessorTable
        {...baseProps}
        transactions={[sampleTransaction]}
        loading={true}
      />
    );

    // Loading text shown on buttons
    expect(screen.getByText('fileProcessing.applyingPatterns')).toBeInTheDocument();
    expect(screen.getByText('fileProcessing.saving')).toBeInTheDocument();
  });
});
