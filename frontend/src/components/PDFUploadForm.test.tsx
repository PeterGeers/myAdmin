import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@/test-utils';

/**
 * PDFUploadForm tests
 *
 * Task 7.2 (spec `.kiro/specs/Common/Frameworks/lazy-select/`, Requirement 8.3):
 * These tests render the REAL `PDFUploadForm` with its hooks mocked so the new LazySelect
 * controls (Debet/Credit accounts + the Google-Drive folder picker that replaced the old
 * `<Input list>` + `<datalist>`) get real coverage, while preserving the previously asserted
 * intents (file accept types, folder selection, new-folder button, prepared-transaction fields,
 * approve/cancel buttons, upload button, tenant-missing vs present handling).
 *
 * LazySelect owns its own listbox (plain Chakra Boxes, not a Menu) so open/type/pick work under
 * the auto-mocked Chakra (steering 33). We assert on roles/values/labels — no i18n init needed.
 */

// --- API service (transitively imported by the real hooks; keep the network scanner happy) ---
vi.mock('../services/apiService', () => ({
  authenticatedGet: vi.fn(),
  authenticatedPost: vi.fn(),
  authenticatedFormData: vi.fn(),
}));

// --- Tenant context ---
const mockUseTenant = {
  currentTenant: 'tenant1' as string | null,
  availableTenants: ['tenant1', 'tenant2'],
  setCurrentTenant: vi.fn(),
  hasMultipleTenants: true,
};
vi.mock('../context/TenantContext', () => ({
  useTenant: () => mockUseTenant,
}));

// --- Tenant functions (drives the optional tabs; keep them off for a deterministic layout) ---
vi.mock('../hooks/useTenantFunctions', () => ({
  useTenantFunctions: () => ({ hasFunction: () => false, functions: [], loading: false, error: null }),
}));

// --- Chart of accounts feeding the Debet/Credit LazySelects ---
const mockChartAccounts = [
  { Account: '4000', AccountName: 'Sales' },
  { Account: '1300', AccountName: 'Debtors' },
];
vi.mock('../hooks/useAccountLookup', () => ({
  useAccountLookup: () => ({ accounts: mockChartAccounts, loading: false, error: null, refetch: vi.fn() }),
}));

// --- usePDFUpload: a controllable object so the real component is deterministic ---
import type { UsePDFUploadReturn, PreparedTransaction } from '../hooks/usePDFUpload';

const ALL_FOLDERS = ['General', 'Booking.com', 'Utilities'];

// One prepared transaction so the account LazySelects render. Debet is in the chart of accounts
// ('4000'); Credit is an out-of-list legacy value ('9999') to exercise tolerate-legacy.
const preparedTransaction: PreparedTransaction = {
  ID: 1,
  TransactionNumber: 'TXN001',
  ReferenceNumber: 'REF001',
  TransactionDate: '2023-01-15',
  TransactionDescription: 'Test Invoice',
  TransactionAmount: 100,
  Debet: '4000',
  Credit: '9999',
  Ref1: 'R1',
  Ref2: 'R2',
  Ref3: 'https://drive/file',
  Ref4: 'invoice.pdf',
  Administration: 'tenant1',
};

const handleSearch = vi.fn();
const setPreparedTransactions = vi.fn();
const approveTransactions = vi.fn();

function makeHook(overrides: Partial<UsePDFUploadReturn> = {}): UsePDFUploadReturn {
  return {
    loading: false,
    tenantSwitching: false,
    message: '',
    setMessage: vi.fn(),
    uploadProgress: 0,
    parsedData: null,
    vendorData: null,
    preparedTransactions: [],
    setPreparedTransactions,
    allFolders: ALL_FOLDERS,
    filteredFolders: ALL_FOLDERS,
    searchTerm: '',
    setSearchTerm: vi.fn(),
    showCreateFolder: false,
    setShowCreateFolder: vi.fn(),
    newFolderName: '',
    setNewFolderName: vi.fn(),
    showDuplicateDialog: false,
    duplicateInfo: null,
    duplicateLoading: false,
    handleSearch,
    handleSubmit: vi.fn(),
    approveTransactions,
    createFolder: vi.fn(),
    handleDuplicateContinue: vi.fn(),
    handleDuplicateCancel: vi.fn(),
    ...overrides,
  };
}

let hookValue: UsePDFUploadReturn = makeHook();
vi.mock('../hooks/usePDFUpload', () => ({
  usePDFUpload: () => hookValue,
}));

import PDFUploadForm from './PDFUploadForm';

beforeEach(() => {
  vi.clearAllMocks();
  mockUseTenant.currentTenant = 'tenant1';
  hookValue = makeHook();
});

describe('PDFUploadForm - file + folder + buttons (real component)', () => {
  it('renders the file input with correct accept types', () => {
    const { container } = render(<PDFUploadForm />);
    // FormLabel/FormControl in the Chakra mock does not wire htmlFor/id, so query the input directly.
    const fileInput = container.querySelector('input[type="file"]');
    expect(fileInput).toBeInTheDocument();
    expect(fileInput).toHaveAttribute('accept', '.pdf,.jpg,.jpeg,.png,.mhtml,.eml');
    expect(screen.getByText(/select file/i)).toBeInTheDocument();
  });

  it('shows the new-folder button', () => {
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /\+ new/i })).toBeInTheDocument();
  });

  it('shows the upload button', () => {
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /upload & process/i })).toBeInTheDocument();
  });
});

describe('PDFUploadForm - folder LazySelect', () => {
  it('renders the folder picker as a combobox named "Select Folder"', () => {
    render(<PDFUploadForm />);
    expect(screen.getByRole('combobox', { name: 'Select Folder' })).toBeInTheDocument();
  });

  it('lists all folders as options when opened (typeahead over the long external list)', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Select Folder' }));

    const optionTexts = screen.getAllByRole('option').map((o) => o.textContent);
    expect(optionTexts).toEqual(expect.arrayContaining(ALL_FOLDERS));
  });

  it('picking a folder calls setFieldValue(folderId, folder) via handleSearch', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Select Folder' }));

    const utilities = screen.getAllByRole('option').find((o) => o.textContent === 'Utilities')!;
    expect(utilities).toBeTruthy();
    fireEvent.mouseDown(utilities);

    // onChange -> setFieldValue('folderId', 'Utilities') then handleSearch('Utilities', setFieldValue).
    expect(handleSearch).toHaveBeenCalledWith('Utilities', expect.any(Function));
  });

  it('offers only the known folders (a name not in allFolders is never a selectable option)', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Select Folder' }));
    // The folder set is exactly allFolders; a legacy/unknown name is never injected as an option.
    expect(screen.queryAllByRole('option').some((o) => o.textContent === 'LegacyFolder')).toBe(false);
    // (The at-rest tolerate-legacy display is covered against the account LazySelects below, where
    // a preset out-of-list value flows in via preparedTransactions.)
  });
});

describe('PDFUploadForm - upload gate', () => {
  it('enables Upload when exactly one folder is resolved (gate open)', () => {
    hookValue = makeHook({ filteredFolders: ['General'] });
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /upload & process/i })).not.toBeDisabled();
  });

  it('disables Upload when more than one folder matches (gate closed)', () => {
    hookValue = makeHook({ filteredFolders: ALL_FOLDERS });
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /upload & process/i })).toBeDisabled();
  });

  it('disables Upload when no tenant is selected even with one folder resolved', () => {
    mockUseTenant.currentTenant = null;
    hookValue = makeHook({ filteredFolders: ['General'] });
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /upload & process/i })).toBeDisabled();
  });

  it('disables Upload while the tenant is switching', () => {
    hookValue = makeHook({ filteredFolders: ['General'], tenantSwitching: true });
    render(<PDFUploadForm />);
    // While switching, the submit button shows its loadingText ("Switching tenant...") and is disabled.
    expect(screen.getByRole('button', { name: /switching tenant/i })).toBeDisabled();
  });
});

describe('PDFUploadForm - account LazySelects (Debet/Credit)', () => {
  beforeEach(() => {
    hookValue = makeHook({ preparedTransactions: [preparedTransaction] });
  });

  it('renders Debet and Credit as combobox controls', () => {
    render(<PDFUploadForm />);
    expect(screen.getByRole('combobox', { name: 'Debet' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Credit' })).toBeInTheDocument();
  });

  it('shows the in-set account "Account - Name" label at rest', () => {
    render(<PDFUploadForm />);
    // Debet '4000' is in the chart of accounts -> "4000 - Sales".
    expect(screen.getByRole('combobox', { name: 'Debet' })).toHaveTextContent('4000 - Sales');
  });

  it('shows an out-of-list account value at rest (tolerate legacy)', () => {
    render(<PDFUploadForm />);
    // Credit '9999' is not in the chart of accounts -> shown raw, never blanked.
    expect(screen.getByRole('combobox', { name: 'Credit' })).toHaveTextContent('9999');
  });

  it('does not offer the out-of-list account value as a selectable option', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Credit' }));
    expect(screen.queryAllByRole('option').some((o) => o.textContent === '9999')).toBe(false);
  });

  it('offers the in-set accounts as options when opened', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Debet' }));
    const optionTexts = screen.getAllByRole('option').map((o) => o.textContent);
    expect(optionTexts).toEqual(expect.arrayContaining(['4000 - Sales', '1300 - Debtors']));
  });

  it('picking an account emits exactly that account value and updates the prepared transaction', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('combobox', { name: 'Debet' }));
    const debtors = screen.getAllByRole('option').find((o) => o.textContent === '1300 - Debtors')!;
    fireEvent.mouseDown(debtors);

    expect(setPreparedTransactions).toHaveBeenCalledTimes(1);
    const updated = setPreparedTransactions.mock.calls[0][0] as PreparedTransaction[];
    expect(updated[0].Debet).toBe('1300');
  });
});

describe('PDFUploadForm - prepared transactions + approve/cancel', () => {
  beforeEach(() => {
    hookValue = makeHook({ preparedTransactions: [preparedTransaction] });
  });

  it('displays the prepared transaction record and its editable fields', () => {
    render(<PDFUploadForm />);
    expect(screen.getByText('New Transaction Records (Ready for Approval)')).toBeInTheDocument();
    expect(screen.getByText(/Record 1 \(ID: 1\)/)).toBeInTheDocument();
    expect(screen.getByDisplayValue('TXN001')).toBeInTheDocument();
    expect(screen.getByDisplayValue('REF001')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Test Invoice')).toBeInTheDocument();
  });

  it('shows approve and cancel buttons and cancel clears the prepared transactions', () => {
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /approve & save to database/i })).toBeInTheDocument();

    const cancel = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancel);
    expect(setPreparedTransactions).toHaveBeenCalledWith([]);
  });

  it('approve button triggers approveTransactions', () => {
    render(<PDFUploadForm />);
    fireEvent.click(screen.getByRole('button', { name: /approve & save to database/i }));
    expect(approveTransactions).toHaveBeenCalledTimes(1);
  });
});

describe('PDFUploadForm - parsed + vendor data display', () => {
  it('displays parsed PDF data when present', () => {
    hookValue = makeHook({
      parsedData: {
        name: 'test-invoice.pdf',
        url: '/uploads/test-invoice.pdf',
        folder: 'General',
        txt: 'Invoice #12345',
      },
    });
    render(<PDFUploadForm />);
    expect(screen.getByText('Parsed PDF Data')).toBeInTheDocument();
    expect(screen.getByText('test-invoice.pdf')).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Invoice #12345/)).toBeInTheDocument();
  });

  it('displays vendor data when present', () => {
    hookValue = makeHook({
      parsedData: { name: 'f.pdf', url: '/u/f.pdf', folder: 'General', txt: '' },
      vendorData: {
        date: '2023-01-15',
        total_amount: '100.00',
        vat_amount: '21.00',
        description: 'Test Invoice',
      },
    });
    render(<PDFUploadForm />);
    expect(screen.getByText('Parsed Vendor Data')).toBeInTheDocument();
    expect(screen.getByText('2023-01-15')).toBeInTheDocument();
    expect(screen.getByText('Test Invoice')).toBeInTheDocument();
  });
});

describe('PDFUploadForm - tenant handling', () => {
  it('shows an upload message from the hook (e.g. tenant-missing error)', () => {
    hookValue = makeHook({ message: 'Error: No tenant selected. Please select a tenant first.' });
    render(<PDFUploadForm />);
    expect(screen.getByText(/No tenant selected/)).toBeInTheDocument();
  });

  it('disables the +New folder button when no tenant is selected', () => {
    mockUseTenant.currentTenant = null;
    render(<PDFUploadForm />);
    expect(screen.getByRole('button', { name: /\+ new/i })).toBeDisabled();
  });
});
