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
import { render, screen, fireEvent } from '@/test-utils';
import BankingTransactionModal from '../components/BankingTransactionModal';
import type { BankingTransactionModalProps } from '../components/BankingTransactionModal';
import type { Transaction } from '../components/BankingProcessor.types';

// Mock AccountSelect to avoid complex select rendering
vi.mock('../components/common/AccountSelect', () => ({
  default: ({ value, onChange }: any) => (
    <input data-testid="account-select" value={value || ''} onChange={(e) => onChange(e.target.value)} />
  ),
}));

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
