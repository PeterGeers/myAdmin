/**
 * MembersPage export action tests — task 20.2 (R8.4, R8.7).
 *
 * Verifies the header-right "Exporteren" action:
 * - clicking it produces a CSV containing the loaded rows' values, serialized via
 *   the shared `csvExport.ts` helper and handed to a browser download;
 * - the export reflects only the loaded, scoped rows — and, when a column filter
 *   narrows the visible set, exactly that filtered subset (R8.7: the page never
 *   invents scope; it exports what the module returned / what the list shows);
 * - the empty case is handled gracefully (an info toast, no download).
 *
 * Mocking approach (matches `MembersPage.test.tsx` + the repo's export tests):
 * the service layer is mocked with `vi.mock`, and the browser download is
 * captured by spying on `generateCsv` (the CSV string builder) from the shared
 * `csvExport.ts` util — the same util ZZP/pivot exports use — plus stubbing
 * `URL.createObjectURL` / anchor `click` so `downloadCsv` never touches jsdom
 * internals. In the test env `useTypedTranslation` returns raw i18n keys, so the
 * button/toast are asserted by their raw keys.
 *
 * **Validates: Requirements 8.4, 8.7**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import * as csvExport from '../utils/csvExport';
import type { Member, FieldConfig } from '../types/members';

vi.mock('../services/membersApiService');

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);

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

describe('MembersPage export action (R8.4, R8.7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    // Re-establish the download stub after clearAllMocks.
    downloadCsvSpy.mockImplementation(() => { });
  });

  it('produces a CSV of the loaded rows and triggers a download', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(exportButton());

    // The shared CSV builder is invoked and a download is triggered.
    expect(generateCsvSpy).toHaveBeenCalledTimes(1);
    expect(downloadCsvSpy).toHaveBeenCalledTimes(1);

    // The generated CSV string carries every loaded row's values.
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

  it('exports only the filtered subset when a column filter is active (R8.7)', async () => {
    render(<MembersPage />);
    await waitForRows();

    // Narrow to region "Noord" — only Jan should remain visible. The shared
    // filter framework debounces, so wait until the non-matching rows drop out
    // of the DOM before exporting (that is when `processedData` is narrowed).
    const regionFilter = screen.getByLabelText('Filter by filters.region');
    fireEvent.change(regionFilter, { target: { value: 'Noord' } });
    await waitFor(() => {
      expect(screen.getByText('Jan')).toBeInTheDocument();
      expect(screen.queryByText('Piet')).not.toBeInTheDocument();
      expect(screen.queryByText('Marie')).not.toBeInTheDocument();
    });

    fireEvent.click(exportButton());

    // Assert against the CSV from the most recent (this test's) export call.
    await waitFor(() => expect(downloadCsvSpy).toHaveBeenCalledTimes(1));
    const lastIdx = generateCsvSpy.mock.results.length - 1;
    const csv = generateCsvSpy.mock.results[lastIdx].value as string;
    // Only the filtered row is serialized.
    expect(csv).toContain('Jan');
    expect(csv).not.toContain('Piet');
    expect(csv).not.toContain('Marie');
  });

  it('handles the empty case gracefully — no CSV built, no download', async () => {
    mockListMembers.mockResolvedValue([] as never);
    render(<MembersPage />);

    // Wait for the empty-table message to confirm loading finished.
    await waitFor(() => {
      expect(screen.getByText('table.empty')).toBeInTheDocument();
    });

    fireEvent.click(exportButton());

    // Nothing is serialized and no download is triggered (the empty guard fires
    // an info toast instead — asserted by the absence of a CSV build/download,
    // the meaningful, portal-independent behavior).
    expect(generateCsvSpy).not.toHaveBeenCalled();
    expect(downloadCsvSpy).not.toHaveBeenCalled();
  });
});
