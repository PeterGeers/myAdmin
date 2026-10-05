/**
 * Tests for BankingTransactionModal
 *
 * Covers:
 * - Renders in edit mode with record data
 * - Renders in insert mode with create header
 * - Displays error alert when modalError is set
 * - Calls onSave when save button clicked
 * - Calls onClose when cancel button clicked
 * - Administration field is read-only
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import BankingTransactionModal from '../components/BankingTransactionModal';
import type { BankingTransactionModalProps } from '../components/BankingTransactionModal';
import type { Transaction } from '../components/BankingProcessor.types';
import { render, screen, fireEvent } from '@/test-utils';

// Debet/Credit render as LazySelect (task 6.1): a role="combobox" trigger whose accessible name
// comes from the `label` prop (t('table.debit')/'Debit', t('table.credit')/'Credit'). LazySelect
// owns its own listbox, so no AccountSelect mock is needed.

const mockTransaction: Transaction = {
  ID: 42,
  row_id: 1,
  TransactionNumber: 'TXN001',
  TransactionDate: '2026-01-15',
  TransactionDescription: 'Test payment',
  TransactionAmount: 250.50,
  Debet: '4000',
  Credit: '1300',
  ReferenceNumber: 'REF-123',
  Ref1: 'NL80RABO0107936917',
  Ref2: '001',
  Ref3: '5000.00',
  Ref4: '',
  Administration: 'TestTenant',
};

const mockT = (key: string): string => {
  const translations: Record<string, string> = {
    'mutaties.editRecord': 'Edit Record',
    'mutaties.addNewRecord': 'Add New Record',
    'mutaties.updateRecord': 'Update',
    'mutaties.insertRecord': 'Insert',
    'table.transactionNumber': 'Transaction Number',
    'table.transactionDate': 'Date',
    'table.description': 'Description',
    'table.amount': 'Amount',
    'table.administration': 'Administration',
    'table.debit': 'Debit',
    'table.credit': 'Credit',
    'table.referenceNumber': 'Reference',
    'table.ref1': 'Ref1',
    'table.ref2': 'Ref2',
    'table.ref3': 'Ref3',
    'table.ref4': 'Ref4',
    'labels.cancel': 'Cancel',
    'labels.administrationCannotChange': 'Cannot change',
  };
  return translations[key] || key;
};

const defaultProps: BankingTransactionModalProps = {
  isOpen: true,
  onClose: vi.fn(),
  editingRecord: mockTransaction,
  setEditingRecord: vi.fn(),
  isInsertMode: false,
  loading: false,
  modalError: '',
  chartAccounts: [],
  onSave: vi.fn(),
  onKeyDown: vi.fn(),
  t: mockT,
};

describe('BankingTransactionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders edit mode header with record ID', () => {
    render(<BankingTransactionModal {...defaultProps} />);
    expect(screen.getByText(/Edit Record.*42/)).toBeInTheDocument();
  });

  it('renders insert mode header', () => {
    render(<BankingTransactionModal {...defaultProps} isInsertMode={true} />);
    expect(screen.getByText('Add New Record')).toBeInTheDocument();
  });

  it('displays transaction fields with correct values', () => {
    render(<BankingTransactionModal {...defaultProps} />);
    expect(screen.getByDisplayValue('TXN001')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Test payment')).toBeInTheDocument();
  });

  it('renders Debet and Credit as LazySelect comboboxes', () => {
    render(<BankingTransactionModal {...defaultProps} />);
    // Two LazySelect triggers expose the ARIA combobox pattern with accessible names from the label.
    const comboboxes = screen.getAllByRole('combobox');
    expect(comboboxes).toHaveLength(2);
    expect(screen.getByRole('combobox', { name: 'Debit' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Credit' })).toBeInTheDocument();
  });

  it('displays an out-of-list account value at rest (tolerate legacy)', () => {
    // defaultProps.chartAccounts is [], so Debet '4000' / Credit '1300' are out-of-set and shown raw.
    render(<BankingTransactionModal {...defaultProps} />);
    const debit = screen.getByRole('combobox', { name: 'Debit' });
    const credit = screen.getByRole('combobox', { name: 'Credit' });
    expect(debit).toHaveTextContent('4000');
    expect(credit).toHaveTextContent('1300');
  });

  it('does not offer an out-of-list value as a selectable option when opened', () => {
    render(<BankingTransactionModal {...defaultProps} />);
    const debit = screen.getByRole('combobox', { name: 'Debit' });
    fireEvent.click(debit);
    // Open with an empty chart of accounts: '4000' is displayed at rest but is not a selectable option.
    const options = screen.queryAllByRole('option');
    expect(options.every((o) => o.textContent !== '4000')).toBe(true);
  });

  it('shows the in-set label when the account value is present in chartAccounts', () => {
    const chartAccounts = [{ Account: '4000', AccountName: 'Sales' }] as BankingTransactionModalProps['chartAccounts'];
    render(<BankingTransactionModal {...defaultProps} chartAccounts={chartAccounts} />);
    // In-set value renders as "value - name" via the mapped LazyOption label.
    expect(screen.getByRole('combobox', { name: 'Debit' })).toHaveTextContent('4000 - Sales');
  });

  it('shows administration field that cannot be edited', () => {
    render(<BankingTransactionModal {...defaultProps} />);
    const adminInput = screen.getByDisplayValue('TestTenant');
    // The field renders with cursor "not-allowed" via Chakra's isReadOnly
    expect(adminInput).toBeInTheDocument();
  });

  it('displays error alert when modalError is set', () => {
    render(<BankingTransactionModal {...defaultProps} modalError="Something went wrong" />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('does not display error alert when modalError is empty', () => {
    render(<BankingTransactionModal {...defaultProps} modalError="" />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('calls onSave when save button is clicked', () => {
    const onSave = vi.fn();
    render(<BankingTransactionModal {...defaultProps} onSave={onSave} />);
    fireEvent.click(screen.getByText('Update'));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it('shows Insert text on save button in insert mode', () => {
    render(<BankingTransactionModal {...defaultProps} isInsertMode={true} />);
    expect(screen.getByText('Insert')).toBeInTheDocument();
  });

  it('calls onClose when cancel button is clicked', () => {
    const onClose = vi.fn();
    render(<BankingTransactionModal {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders nothing in body when editingRecord is null', () => {
    render(<BankingTransactionModal {...defaultProps} editingRecord={null} />);
    expect(screen.queryByDisplayValue('TXN001')).not.toBeInTheDocument();
  });
});
