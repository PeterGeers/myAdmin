/**
 * BankingMutatiesTab export button render tests — task 1.5 (R1.1, R1.2, R1.3, R1.4).
 *
 * Lightweight render/interaction coverage for the "Export to CSV" control that
 * task 1.4 wired into the Transactions table view. The pure CSV helper
 * (buildTransactionsCsv / transactionsCsvColumns / transactionsCsvFilename) is
 * exhaustively unit-tested in `components/banking/transactionsCsv.test.ts`; here
 * we only assert the UI-presence/wiring criteria:
 *
 * - the button renders with its i18n label from the `banking` namespace and
 *   carries `data-testid="export-transactions-csv-button"` (R1.1, R1.3);
 * - it sits beside the existing "Add new record" control (R1.2 — sibling action);
 * - it is DISABLED when there are no rows (empty `mutaties` → empty
 *   `processedData`) (R1.1);
 * - clicking it with rows present triggers a CSV download via the shared
 *   `csvExport.downloadCsv` (asserted by spying on it) (R1.1, R2.1);
 * - no row-selection checkboxes were added to the table (R1.4).
 *
 * Mocking approach (matches the repo's render tests, e.g. MembersExport /
 * BankingProcessorTable):
 * - `@chakra-ui/react` is already aliased to the shared lightweight mock via
 *   vite.config.ts (Button → <button disabled={isDisabled}>, data-testid passed
 *   through), so no Chakra provider gymnastics are needed.
 * - `useTypedTranslation` is mocked to return raw i18n keys, so the label is
 *   asserted as the `banking`-namespace key `mutaties.export.exportToCsv`.
 * - `useTableConfig` is mocked to the banking_mutaties column defaults so the
 *   component renders synchronously without the async parameter fetch.
 * - the shared `downloadCsv` is spied/stubbed so clicking never touches jsdom
 *   Blob/anchor internals — we assert it was invoked with a transactions-*.csv
 *   filename.
 *
 * _Requirements: 1.1, 1.2, 1.3, 1.4_
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import BankingMutatiesTab, {
  BankingMutatiesTabProps,
} from '../components/banking/BankingMutatiesTab';
import * as csvExport from '../utils/csvExport';
import { render, screen, fireEvent, within } from '@/test-utils';

// t() returns the raw key, so the button label is asserted as the banking
// namespace key `mutaties.export.exportToCsv` (R1.3).
vi.mock('../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}));

// Return the banking_mutaties column defaults synchronously so the table
// renders without the async parameter fetch (useTableConfig otherwise calls
// getParameters in an effect).
vi.mock('../hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    columns: [
      'ID', 'TransactionNumber', 'TransactionDate', 'TransactionDescription',
      'TransactionAmount', 'Debet', 'Credit', 'ReferenceNumber',
      'Ref1', 'Ref2', 'Ref3', 'Ref4', 'Administration',
    ],
    filterableColumns: [
      'ID', 'TransactionNumber', 'TransactionDate', 'TransactionDescription',
      'TransactionAmount', 'Debet', 'Credit', 'ReferenceNumber',
      'Ref1', 'Ref2', 'Ref3', 'Ref4', 'Administration',
    ],
    defaultSort: { field: 'TransactionDate', direction: 'desc' },
    pageSize: 100,
    loading: false,
    error: null,
  }),
}));

// Spy on the shared CSV download so a click never touches jsdom Blob/anchor
// internals; we only assert that a download was triggered.
const downloadCsvSpy = vi
  .spyOn(csvExport, 'downloadCsv')
  .mockImplementation(() => {});

const sampleTransaction = {
  ID: 1,
  row_id: 1,
  TransactionNumber: '001',
  TransactionDate: '2026-01-15',
  TransactionDescription: 'PINBETALING HOOGVLIET',
  TransactionAmount: 45.5,
  Debet: '4000',
  Credit: '1300',
  ReferenceNumber: 'INV-001',
  Ref1: '',
  Ref2: '',
  Ref3: '',
  Ref4: '',
  Administration: 'TestTenant',
};

const baseProps: BankingMutatiesTabProps = {
  mutaties: [sampleTransaction],
  filterOptions: { years: ['2026'], administrations: ['TestTenant'] },
  mutatiesFilters: { years: [] },
  setMutatiesFilters: vi.fn(),
  openEditModal: vi.fn(),
  openInsertModal: vi.fn(),
  copyToClipboard: vi.fn(),
  handleRef3Click: vi.fn(),
};

const exportButton = () => screen.getByTestId('export-transactions-csv-button');

describe('BankingMutatiesTab export button (R1.1–R1.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    downloadCsvSpy.mockImplementation(() => {});
  });

  it('renders the export button with the banking-namespace label (R1.1, R1.3)', () => {
    render(<BankingMutatiesTab {...baseProps} />);

    const button = exportButton();
    expect(button).toBeInTheDocument();
    // Label resolves to the `banking` namespace i18n key.
    expect(button).toHaveTextContent('mutaties.export.exportToCsv');
  });

  it('places the export control beside the "Add new record" action (R1.2)', () => {
    render(<BankingMutatiesTab {...baseProps} />);

    const exportBtn = exportButton();
    const addBtn = screen.getByText('mutaties.addNewRecord');
    // Both actions share the same immediate container (the HStack of actions).
    expect(exportBtn.parentElement).toBe(addBtn.closest('button')?.parentElement);
  });

  it('is enabled when rows are present (R1.1)', () => {
    render(<BankingMutatiesTab {...baseProps} />);
    expect(exportButton()).toBeEnabled();
  });

  it('is disabled when there are no rows (R1.1)', () => {
    render(<BankingMutatiesTab {...baseProps} mutaties={[]} />);
    expect(exportButton()).toBeDisabled();
  });

  it('triggers a CSV download via the shared util when clicked with rows (R1.1, R2.1)', () => {
    render(<BankingMutatiesTab {...baseProps} />);

    fireEvent.click(exportButton());

    expect(downloadCsvSpy).toHaveBeenCalledTimes(1);
    // Downloaded with the transactions-YYYY-MM-DD.csv filename produced by the
    // export helper, and a non-empty CSV string as the first argument.
    const [csvContent, filename] = downloadCsvSpy.mock.calls[0];
    expect(typeof csvContent).toBe('string');
    expect((csvContent as string).length).toBeGreaterThan(0);
    expect(filename).toMatch(/^transactions-\d{4}-\d{2}-\d{2}\.csv$/);
  });

  it('does not add row-selection checkboxes to the table (R1.4)', () => {
    const { container } = render(<BankingMutatiesTab {...baseProps} />);

    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    // No checkbox inputs anywhere in the rendered table.
    expect(within(table as HTMLElement).queryAllByRole('checkbox')).toHaveLength(0);
    expect((table as HTMLElement).querySelectorAll('input[type="checkbox"]')).toHaveLength(0);
  });
});
