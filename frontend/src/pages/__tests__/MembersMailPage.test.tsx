/**
 * MembersMailPage — relocated applications inbox renders in the tenant-admin
 * members > mail area (members-overview-tweaks, task 8.5, Req 6.2).
 *
 * Req 6.1 (the inbox is GONE from the Members Overview page) is proved by the
 * sibling `MembersPage.applicationsInbox.test.tsx` (task 8.1) — it asserts the
 * inbox bar and every one of its preset controls are no longer rendered on
 * `MembersPage`. This file covers the OTHER half of the relocation: Req 6.2 —
 * "THE Members_Mail_Area SHALL present the Applications_Inbox under tenant
 * administrator > members > mail".
 *
 * `MembersMailPage` (task 8.2) hosts the relocated inbox by COMPOSING the same
 * machinery the overview grid used: `useMembersData` (field config / prefs),
 * `useMembersCursorPaging` (one DynamoDB cursor page via `listMembersPage`),
 * `useMembersColumns` + `useFilterableTable` (the one grid), `MembersInboxBar` +
 * `useApplicationsInbox` (the preset, reused verbatim), and `getMember` for the
 * row-click view modal. Every one of those resolves through
 * `services/membersApiService`, so mocking that single module (mirroring the
 * sibling MembersPage tests) is enough to render the page.
 *
 * These assertions stay at the render / wiring level: the inbox bar + its preset
 * controls render (Req 6.2) and the members table renders. The status-pin and
 * keyword-filter INVARIANTS have dedicated property tests (tasks 8.3 / 8.4), so
 * this file does not re-derive them — it only checks that a preset control is
 * wired (activating it re-pins the grid without crashing and the table survives).
 *
 * **Validates: Requirements 6.2**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersMailPage from '../../pages/MembersMailPage';
import * as membersApiService from '../../services/membersApiService';
import type { Member, FieldConfig } from '../../types/members';
import { render, screen, waitFor, fireEvent } from '@/test-utils';

vi.mock('../../services/membersApiService');

const mockListMembersPage = vi.mocked(membersApiService.listMembersPage);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockGetColumnPreferences = vi.mocked(membersApiService.getColumnPreferences);
const mockSaveColumnPreferences = vi.mocked(membersApiService.saveColumnPreferences);

// A single application-status page: the mail area OPENS on the applications
// inbox (pinned `status = application` on mount), so these are the rows the
// relocated inbox surfaces. Overlay notes carry the DUP / NO_NOTIFY keyword
// tokens the quick-filters narrow by (their filtering is covered by the 8.3/8.4
// property tests; here we only need rows for the table to render).
const applicationRows: Member[] = [
  {
    member_id: 'app-dup',
    member_number: 'A00001',
    name: 'Dup Applicant',
    email: 'dup@h-dcn.example',
    status: 'application',
    overlay: { additional_info: 'leftover text DUP' },
  },
  {
    member_id: 'app-nonotify',
    member_number: 'A00002',
    name: 'NoNotify Applicant',
    email: 'nn@h-dcn.example',
    status: 'application',
    overlay: { additional_info: 'NO_NOTIFY' },
  },
  {
    member_id: 'app-plain',
    member_number: 'A00003',
    name: 'Plain Applicant',
    email: 'plain@h-dcn.example',
    status: 'application',
    overlay: { additional_info: '' },
  },
];

const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'member_number', label: 'Lidnummer', type: 'string', order: 1 },
    { key: 'name', label: 'Naam', compact: true, order: 2 },
    { key: 'status', label: 'Status', type: 'string', order: 3 },
    { key: 'additional_info', group: 'overlay', label: 'Aanvullende info', type: 'string', order: 20 },
  ],
};

const SETTLE = { timeout: 5000 };
// The mail area opens on the applications inbox, which surfaces the
// `additional_info` note column (task 8.2) rather than the full overview column
// set — so the table shows each row's `member_number` + note, not the `name`.
// Key row assertions off the stable `member_number` values, which always render.
const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('A00001')).toBeInTheDocument();
  }, SETTLE);
};

describe('MembersMailPage — relocated applications inbox (task 8.5, Req 6.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // The grid loads ONE DynamoDB cursor page via `listMembersPage` (Req 25).
    // Return the application rows as a single final page (no next cursor).
    mockListMembersPage.mockResolvedValue({ items: applicationRows, cursor: null } as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(applicationRows[0] as never);
    mockListMembershipTypes.mockResolvedValue([] as never);
    mockGetColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
    mockSaveColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
  });

  it('renders the applications inbox preset bar and all its controls (Req 6.2)', async () => {
    render(<MembersMailPage />);
    await waitForRows();

    // The relocated inbox preset bar is present on the members-mail route...
    expect(screen.getByTestId('members-inbox-bar')).toBeInTheDocument();
    // ...with every preset control: activate (pins status=application), the DUP
    // and NO_NOTIFY keyword quick-filters (Req 6.4), and clear.
    expect(screen.getByTestId('members-inbox-activate')).toBeInTheDocument();
    expect(screen.getByTestId('members-inbox-dup')).toBeInTheDocument();
    expect(screen.getByTestId('members-inbox-no-notify')).toBeInTheDocument();
    expect(screen.getByTestId('members-inbox-clear')).toBeInTheDocument();
  });

  it('renders a members table with the application rows (Req 6.2)', async () => {
    render(<MembersMailPage />);
    await waitForRows();

    // The inbox is a VIEW over one member grid — exactly one table renders with
    // the application-status rows the mail area opens on (keyed by the always-
    // rendered `member_number` column).
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(screen.getByText('A00001')).toBeInTheDocument();
    expect(screen.getByText('A00002')).toBeInTheDocument();
    expect(screen.getByText('A00003')).toBeInTheDocument();
  });

  it('wires a preset control: activating the inbox keeps the grid rendered (Req 6.2)', async () => {
    render(<MembersMailPage />);
    await waitForRows();

    // Activating the "Applications" preset re-pins status=application. The
    // status-pin INVARIANT itself is covered by the 8.3 property test; here we
    // only confirm the control is wired and the grid survives the interaction.
    fireEvent.click(screen.getByTestId('members-inbox-activate'));

    await waitFor(() => {
      expect(screen.getByTestId('members-inbox-bar')).toBeInTheDocument();
      expect(screen.getAllByRole('table')).toHaveLength(1);
    }, SETTLE);
    expect(screen.getByText('A00001')).toBeInTheDocument();
  });
});
