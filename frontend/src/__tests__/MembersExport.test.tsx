/**
 * MembersPage export action tests — task 4.5 (R5.6, R8.7).
 *
 * Verifies the header-right "Exporteren" action is wired to the AUTHORITATIVE
 * `export_members` module action (NOT a client-only CSV of the visible rows):
 * - clicking it calls `membersApiService.exportMembers()` (GET /members/export),
 *   whose rows are scope-narrowed SERVER-side (R8.7: the SPA never invents scope);
 * - the action's returned rows are serialized via the shared `csvExport.ts`
 *   helper and handed to a browser download;
 * - because the export source is the server action — not the client-filtered
 *   `processedData` — a client column filter does NOT change what is exported;
 * - the empty case (action returns []) is handled gracefully (info toast, no
 *   download), and an action failure surfaces an error toast with no download.
 *
 * Mocking approach (matches `MembersPage.test.tsx` + the repo's export tests):
 * the service layer is mocked with `vi.mock`, and the browser download is
 * captured by spying on `generateCsv` (the CSV string builder) from the shared
 * `csvExport.ts` util — the same util ZZP/pivot exports use — plus stubbing
 * `downloadCsv` so it never touches jsdom internals. In the test env
 * `useTypedTranslation` returns raw i18n keys, so the button/toast are asserted
 * by their raw keys.
 *
 * **Validates: Requirements 5.6, 8.7**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import * as csvExport from '../utils/csvExport';
import type { Member, FieldConfig } from '../types/members';

vi.mock('../services/membersApiService');

// MembersPage reads `useAuth().hasAnyRole` for the view-context dropdown (task
// 3.3). A permissive stub keeps the default context available (dropdown hidden).
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockExportMembers = vi.mocked(membersApiService.exportMembers);

// Spy on the shared CSV builder + download so we can assert what gets exported
// without depending on jsdom Blob/anchor internals.
const generateCsvSpy = vi.spyOn(csvExport, 'generateCsv');
const downloadCsvSpy = vi
  .spyOn(csvExport, 'downloadCsv')
  .mockImplementation(() => { });

const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    motor_type: 'BMW',
  },
  {
    member_id: 'm-2',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
    motor_type: 'Honda',
  },
  {
    member_id: 'm-3',
    name: 'Marie',
    email: 'marie@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'West',
    motor_type: 'Yamaha',
  },
];

const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'name', label: 'Naam', compact: true, order: 1 },
    { key: 'motor_type', label: 'Motorfiets', type: 'string', order: 10 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'Oost', 'West'] },
  ],
};

/** Wait for the mocked rows to render. */
const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('Jan')).toBeInTheDocument();
    expect(screen.getByText('Piet')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
  });
};

/** The export button (label is the raw i18n key in the test env). */
const exportButton = () => screen.getByRole('button', { name: /actions\.export/ });

describe('MembersPage export action (R5.6, R8.7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    // The authoritative export action returns the scope-narrowed rows server-side.
    mockExportMembers.mockResolvedValue(mockMembers as never);
    // Re-establish the download stub after clearAllMocks.
    downloadCsvSpy.mockImplementation(() => { });
  });

  it('calls the authoritative export_members action and downloads its rows', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(exportButton());

    // The export is sourced from the AUTHORITATIVE module action, not a
    // client-only CSV of the visible rows (R5.6).
    await waitFor(() => expect(mockExportMembers).toHaveBeenCalledTimes(1));

    // The shared CSV builder is invoked with the action's rows and a download
    // is triggered.
    await waitFor(() => expect(downloadCsvSpy).toHaveBeenCalledTimes(1));
    expect(generateCsvSpy).toHaveBeenCalledTimes(1);

    // The generated CSV string carries every row the action returned.
    const csv = generateCsvSpy.mock.results[0].value as string;
    expect(csv).toContain('Jan');
    expect(csv).toContain('jan@h-dcn.example');
    expect(csv).toContain('m-1');
    expect(csv).toContain('Noord');
    expect(csv).toContain('Piet');
    expect(csv).toContain('Marie');
    // The overlay column value is included too.
    expect(csv).toContain('BMW');

    // The download filename is date-stamped (leden-YYYY-MM-DD.csv).
    const filename = downloadCsvSpy.mock.calls[0][1];
    expect(filename).toMatch(/^leden-\d{4}-\d{2}-\d{2}\.csv$/);
  });

  it('exports the action result, not the client-filtered rows (scope is server-side, R8.7)', async () => {
    render(<MembersPage />);
    await waitForRows();

    // Narrow the VISIBLE table to region "Noord" — only Jan remains on screen.
    // The export must NOT follow this client filter: it exports whatever the
    // scope-narrowed server action returns (here: all three mock rows). This
    // proves the SPA does not invent scope client-side (R8.7).
    const regionFilter = screen.getByLabelText('Filter by filters.region');
    fireEvent.change(regionFilter, { target: { value: 'Noord' } });
    await waitFor(() => {
      expect(screen.getByText('Jan')).toBeInTheDocument();
      expect(screen.queryByText('Piet')).not.toBeInTheDocument();
      expect(screen.queryByText('Marie')).not.toBeInTheDocument();
    });

    fireEvent.click(exportButton());

    await waitFor(() => expect(mockExportMembers).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(downloadCsvSpy).toHaveBeenCalledTimes(1));

    const lastIdx = generateCsvSpy.mock.results.length - 1;
    const csv = generateCsvSpy.mock.results[lastIdx].value as string;
    // All three action rows are serialized despite the client filter hiding two.
    expect(csv).toContain('Jan');
    expect(csv).toContain('Piet');
    expect(csv).toContain('Marie');
  });

  it('handles an empty action result gracefully — no CSV built, no download', async () => {
    mockExportMembers.mockResolvedValue([] as never);
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(exportButton());

    // The action is still called, but with no rows nothing is serialized and no
    // download is triggered (the empty guard fires an info toast instead).
    await waitFor(() => expect(mockExportMembers).toHaveBeenCalledTimes(1));
    expect(generateCsvSpy).not.toHaveBeenCalled();
    expect(downloadCsvSpy).not.toHaveBeenCalled();
  });

  it('surfaces an error and skips the download when the action fails', async () => {
    mockExportMembers.mockRejectedValue(new Error('export failed') as never);
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(exportButton());

    // The action was attempted; on failure no CSV is built and no download runs
    // (the catch fires an error toast).
    await waitFor(() => expect(mockExportMembers).toHaveBeenCalledTimes(1));
    expect(generateCsvSpy).not.toHaveBeenCalled();
    expect(downloadCsvSpy).not.toHaveBeenCalled();
  });
});
