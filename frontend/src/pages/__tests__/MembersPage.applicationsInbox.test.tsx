/**
 * MembersPage — applications inbox REMOVED (members-overview-tweaks, task 8.1,
 * Req 6.1).
 *
 * The applications inbox used to live on the Members Overview page as a preset
 * bar over the one grid. members-overview-tweaks Req 6.1 relocates it OFF this
 * page ("THE Members_Overview_Page SHALL exclude the Applications_Inbox") and
 * into a tenant-administrator members > mail route (task 8.2). Task 8.1 removes
 * the inbox usage from `MembersPage` — the page is now toolbar → stats →
 * pagination → table.
 *
 * This file (which previously proved the inbox preset end to end on this page)
 * is realigned to the new behavior per the change-with-tests contract: it
 * asserts the inbox bar + its preset controls are NO LONGER rendered on
 * `MembersPage`, while the one members table still renders. The relocated inbox
 * and its own behavior are covered by the hook test
 * (`useApplicationsInbox.test.ts`, unchanged — the hook is reused verbatim) and
 * the new members-mail route tests (task 8.2 / 8.5).
 *
 * **Validates: Requirements 6.1**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersPage from '../../pages/MembersPage';
import * as membersApiService from '../../services/membersApiService';
import type { Member, FieldConfig } from '../../types/members';
import { render, screen, waitFor } from '@/test-utils';

vi.mock('../../services/membersApiService');

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

// MembersPage reads `useTenant().currentTenant` for the export filename
// (members-overview-tweaks Req 5.1/5.4). Stub the tenant context so the page
// does not require a real TenantProvider in this inbox-removal test.
vi.mock('../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'h-dcn' }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockGetColumnPreferences = vi.mocked(membersApiService.getColumnPreferences);
const mockSaveColumnPreferences = vi.mocked(membersApiService.saveColumnPreferences);

// A mix of statuses + overlay.additional_info keyword notes — the same fixtures
// the inbox preset once filtered. They still render in the plain overview; the
// point of this file now is that the INBOX CONTROLS are gone, not the rows.
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

describe('MembersPage — applications inbox removed (task 8.1, Req 6.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    // The Members table loads ONE DynamoDB cursor page via `listMembersPage`
    // (Req 25). Return all mock rows as a single final page (no next cursor).
    vi.mocked(membersApiService.listMembersPage).mockResolvedValue(
      { items: mockMembers, cursor: null } as never,
    );
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockGetColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
    mockSaveColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
  });

  it('no longer renders the applications inbox bar on the Members Overview page (Req 6.1)', async () => {
    render(<MembersPage />);
    await waitForRows();

    // The inbox preset bar and each of its controls are relocated off this page.
    expect(screen.queryByTestId('members-inbox-bar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-inbox-activate')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-inbox-dup')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-inbox-no-notify')).not.toBeInTheDocument();
    expect(screen.queryByTestId('members-inbox-clear')).not.toBeInTheDocument();
  });

  it('still renders exactly one members table with every member row (inbox removal only)', async () => {
    render(<MembersPage />);
    await waitForRows();

    // Removing the inbox preset leaves the one overview grid intact: all rows,
    // regardless of status, are present (no status pin applied on the page).
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(screen.getByText('Dup Applicant')).toBeInTheDocument();
    expect(screen.getByText('NoNotify Applicant')).toBeInTheDocument();
    expect(screen.getByText('Plain Applicant')).toBeInTheDocument();
    expect(screen.getByText('Active Member')).toBeInTheDocument();
  });
});
