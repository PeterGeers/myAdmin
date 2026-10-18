/**
 * MembersPage — applications-inbox preset END TO END (Member Application Form,
 * task 7.2, R8b.4/R8b.5/F3).
 *
 * Proves the staff applications inbox is the EXISTING member overview grid viewed
 * through the Table Filter Framework v2 — NOT a new grid — over the real
 * `MembersPage` + the shared filter framework + the unified column model + the
 * on-the-fly overlay flatten:
 *
 * - "Applications inbox" pins the one grid to `status = application`: only the
 *   application-status rows remain visible, active members drop out (R8b.4/F3).
 * - "Possible duplicates" / "Not auto-notified" narrow that inbox to the rows
 *   whose `overlay.additional_info` carries the stable `DUP` / `NO_NOTIFY` keyword
 *   the SAM create/notify path wrote (R8b.5) — resolved through the generic
 *   framework filter on the surfaced `additional_info` column, no bespoke grid.
 * - "Clear" restores the full overview.
 *
 * Mocking/render approach matches the established `MembersPage.test.tsx`
 * convention (service layer mocked with `vi.mock` + the shared `@/test-utils`
 * render; raw i18n keys in the test env).
 *
 * **Validates: Requirements 8b.4, 8b.5**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersPage from '../../pages/MembersPage';
import * as membersApiService from '../../services/membersApiService';
import type { Member, FieldConfig } from '../../types/members';
import { render, screen, waitFor, fireEvent } from '@/test-utils';

vi.mock('../../services/membersApiService');

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockGetColumnPreferences = vi.mocked(membersApiService.getColumnPreferences);
const mockSaveColumnPreferences = vi.mocked(membersApiService.saveColumnPreferences);

// A mix of statuses + overlay.additional_info keyword notes:
// - Dup Applicant: status=application + DUP note (possible duplicate).
// - NoNotify Applicant: status=application + NO_NOTIFY note (undeliverable staff mail).
// - Plain Applicant: status=application, no note.
// - Active Member: status=active (must drop out of the inbox view).
const mockMembers: Member[] = [
  {
    member_id: 'app-dup',
    name: 'Dup Applicant',
    email: 'dup@h-dcn.example',
    status: 'application',
    overlay: { additional_info: 'some leftover text DUP' },
  },
  {
    member_id: 'app-nonotify',
    name: 'NoNotify Applicant',
    email: 'nn@h-dcn.example',
    status: 'application',
    overlay: { additional_info: 'NO_NOTIFY' },
  },
  {
    member_id: 'app-plain',
    name: 'Plain Applicant',
    email: 'plain@h-dcn.example',
    status: 'application',
    overlay: { additional_info: '' },
  },
  {
    member_id: 'active-1',
    name: 'Active Member',
    email: 'active@h-dcn.example',
    status: 'active',
    overlay: { additional_info: '' },
  },
];

// Field config exposing `status` (compact, filterable) + the overlay
// `additional_info` field so the inbox can surface it as a keyword-filterable
// column.
const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'name', label: 'Naam', compact: true, order: 1 },
    { key: 'email', group: 'personal', label: 'E-mail', type: 'string', order: 2 },
    { key: 'status', label: 'Status', type: 'string', order: 3 },
    { key: 'additional_info', group: 'overlay', label: 'Aanvullende info', type: 'string', order: 20 },
  ],
};

const SETTLE = { timeout: 5000 };
const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('Dup Applicant')).toBeInTheDocument();
    expect(screen.getByText('Active Member')).toBeInTheDocument();
  }, SETTLE);
};

describe('MembersPage — applications inbox preset (task 7.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockListMembershipTypes.mockResolvedValue([] as never);
    mockGetColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
    mockSaveColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
  });

  it('renders the inbox preset bar as a view over the one overview (no new grid)', async () => {
    render(<MembersPage />);
    await waitForRows();

    // The preset bar is present; there is still exactly ONE members table.
    expect(screen.getByTestId('members-inbox-bar')).toBeInTheDocument();
    expect(screen.getAllByRole('table')).toHaveLength(1);
  });

  it('"Applications inbox" pins the grid to status=application (R8b.4/F3)', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(screen.getByTestId('members-inbox-activate'));

    // The three application rows stay; the active member drops out — a filtered
    // VIEW of the existing grid, not a separate table.
    await waitFor(() => {
      expect(screen.getByText('Dup Applicant')).toBeInTheDocument();
      expect(screen.getByText('NoNotify Applicant')).toBeInTheDocument();
      expect(screen.getByText('Plain Applicant')).toBeInTheDocument();
      expect(screen.queryByText('Active Member')).not.toBeInTheDocument();
    });
  });

  it('"Possible duplicates" narrows the inbox to the DUP-noted rows (R8b.5)', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(screen.getByTestId('members-inbox-dup'));

    // Only the DUP-noted application remains — keyword-filtered on
    // overlay.additional_info via the generic framework.
    await waitFor(() => {
      expect(screen.getByText('Dup Applicant')).toBeInTheDocument();
      expect(screen.queryByText('NoNotify Applicant')).not.toBeInTheDocument();
      expect(screen.queryByText('Plain Applicant')).not.toBeInTheDocument();
      expect(screen.queryByText('Active Member')).not.toBeInTheDocument();
    });
  });

  it('"Not auto-notified" narrows the inbox to the NO_NOTIFY-noted rows (R8b.5)', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(screen.getByTestId('members-inbox-no-notify'));

    await waitFor(() => {
      expect(screen.getByText('NoNotify Applicant')).toBeInTheDocument();
      expect(screen.queryByText('Dup Applicant')).not.toBeInTheDocument();
      expect(screen.queryByText('Plain Applicant')).not.toBeInTheDocument();
      expect(screen.queryByText('Active Member')).not.toBeInTheDocument();
    });
  });

  it('"Clear" restores the full overview', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(screen.getByTestId('members-inbox-dup'));
    await waitFor(() => {
      expect(screen.queryByText('Active Member')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('members-inbox-clear'));
    await waitFor(() => {
      expect(screen.getByText('Dup Applicant')).toBeInTheDocument();
      expect(screen.getByText('NoNotify Applicant')).toBeInTheDocument();
      expect(screen.getByText('Plain Applicant')).toBeInTheDocument();
      expect(screen.getByText('Active Member')).toBeInTheDocument();
    });
  });
});
