/**
 * MembersEditModal + MembersDeleteConfirm Unit Tests — s5c task 4.4 (BROADENED from the s5b
 * task 19.2/19.3 tests) + delete confirm (unchanged behavior).
 *
 * The edit modal is now BROADENED over the RESOLVED field set (design C-SURFACE): it renders
 * WHATEVER `GET /members/field-config` resolves, SECTIONED by `functional_group` (R4.9),
 * PRE-FILLED from the selected member's nested record, and shapes the module's NESTED update
 * body by each field's STORAGE group. These tests verify (R5.5/R4.9, R8.2/Property 2):
 *
 * EDIT:
 * - the view-modal footer "Edit" opens the edit modal, pre-filled from the member;
 * - the resolved fields render as inputs; a calculated (read-only) field is disabled (R4.4);
 * - submitting calls `updateMember(memberId, body)` with the storage-group-shaped nested body
 *   and NO tenant field (Property 2);
 * - a validation error (required field cleared) blocks submit;
 * - a successful update closes the modal and refreshes the list.
 *
 * DELETE (unchanged): the footer "Delete" opens a CONFIRM step naming the member; confirming
 * deletes + refreshes; cancelling does not delete.
 *
 * The service layer is mocked with `vi.mock`; `useTypedTranslation` returns raw i18n keys.
 *
 * _Requirements: R5.5, R4.9, R4.4, R8.2, R7.9_
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import type { Member, FieldConfig } from '../types/members';

vi.mock('../services/membersApiService');

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true, user: { roles: ['Members_CRUD'] } }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockUpdateMember = vi.mocked(membersApiService.updateMember);
const mockDeleteMember = vi.mocked(membersApiService.deleteMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);

// The active membership-type catalog the page feeds the membership_type dropdown from via
// listMembershipTypes(true) (R5.8, task 4.7). Keys match the field's embedded options so the
// dropdown offers `gewoon`/`erelid` (pre-fill lands on `gewoon`; edits can select `erelid`).
const mockMembershipTypes = [
  { key: 'gewoon', label: { nl: 'Gewoon lid', en: 'Ordinary' }, active: true },
  { key: 'erelid', label: { nl: 'Erelid', en: 'Honorary' }, active: true },
];

// The flat table row (list view).
const mockRow: Member = {
  member_id: 'm-1',
  name: 'Jan',
  email: 'jan@h-dcn.example',
  status: 'active',
  membership_type: 'gewoon',
  region: 'Noord',
};

// The full nested record `getMember` returns (drives the edit pre-fill by storage group).
const mockFullMember: Member = {
  member_id: 'm-1',
  name: 'Jan',
  region: 'Noord',
  personal: { first_name: 'Jan', last_name: 'de Vries', email: 'jan@h-dcn.example' },
  membership: { membership_type: 'gewoon', status: 'active' },
} as Member;

const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'first_name', group: 'personal', label: { nl: 'Voornaam', en: 'First name' }, type: 'string', required: true, functional_group: 'personal', order: 10 },
    { key: 'last_name', group: 'personal', label: { nl: 'Achternaam', en: 'Last name' }, type: 'string', required: true, functional_group: 'personal', order: 20 },
    { key: 'email', group: 'personal', label: { nl: 'E-mail', en: 'Email' }, type: 'string', required: true, functional_group: 'personal', order: 30 },
    {
      key: 'membership_type', group: 'membership', label: { nl: 'Type', en: 'Type' }, type: 'reference', required: true,
      functional_group: 'membership', order: 40,
      options: [
        { value: 'gewoon', label: { nl: 'Gewoon lid', en: 'Ordinary' } },
        { value: 'erelid', label: { nl: 'Erelid', en: 'Honorary' } },
      ],
    },
    { key: 'display_name', group: 'personal', label: { nl: 'Weergavenaam', en: 'Display name' }, type: 'string', origin: 'calculated', read_only: true, functional_group: 'personal', order: 15 },
    { key: 'region', group: 'membership', label: { nl: 'Regio', en: 'Region' }, type: 'reference', functional_group: 'membership', order: 60 },
  ],
  functional_groups: [
    { key: 'personal', label: { nl: 'Persoonlijk', en: 'Personal' }, order: 1 },
    { key: 'membership', label: { nl: 'Lidmaatschap', en: 'Membership' }, order: 2 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'Oost', 'West'] },
  ],
};

const openViewModal = async () => {
  render(<MembersPage />);
  await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());
  fireEvent.click(screen.getByText('Jan'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  await waitFor(() => expect(mockGetMember).toHaveBeenCalledWith('m-1'));
  return screen.getByRole('dialog');
};

const openEditModal = async () => {
  const view = await openViewModal();
  fireEvent.click(within(view).getByText('actions.edit'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  return screen.getByRole('dialog');
};

const fillByName = (dialog: HTMLElement, name: string, value: string) => {
  const control = dialog.querySelector(`[name="${name}"]`) as HTMLElement | null;
  if (!control) throw new Error(`No form control with name="${name}"`);
  fireEvent.change(control, { target: { value } });
};

describe('MembersEditModal — broadened over the resolved field set', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue([mockRow] as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockFullMember as never);
    mockUpdateMember.mockResolvedValue({ member_id: 'm-1' } as never);
    mockListMembershipTypes.mockResolvedValue(mockMembershipTypes as never);
  });

  describe('opening + pre-fill (R8.2, R4.9)', () => {
    it('opens the edit modal from the view-modal footer, pre-filled from the nested member', async () => {
      const dialog = await openEditModal();
      expect(within(dialog).getByText('editModal.title')).toBeInTheDocument();
      expect((dialog.querySelector('[name="first_name"]') as HTMLInputElement).value).toBe('Jan');
      expect((dialog.querySelector('[name="last_name"]') as HTMLInputElement).value).toBe('de Vries');
      expect((dialog.querySelector('[name="email"]') as HTMLInputElement).value).toBe('jan@h-dcn.example');
      expect((dialog.querySelector('[name="membership_type"]') as HTMLSelectElement).value).toBe('gewoon');
      expect((dialog.querySelector('[name="region"]') as HTMLSelectElement).value).toBe('Noord');
    });
  });

  describe('field-level read-only (R4.4)', () => {
    it('renders a calculated field disabled (never editable)', async () => {
      const dialog = await openEditModal();
      const displayName = dialog.querySelector('[name="display_name"]') as HTMLInputElement | null;
      expect(displayName).toBeTruthy();
      expect(displayName!.disabled).toBe(true);
    });
  });

  describe('valid submit (R8.2, Property 2)', () => {
    it('calls updateMember with the storage-group-shaped nested body (NO tenant)', async () => {
      const dialog = await openEditModal();
      fillByName(dialog, 'first_name', 'Jan Jansen');
      fillByName(dialog, 'membership_type', 'erelid');
      fillByName(dialog, 'region', 'Zuid');

      fireEvent.click(within(dialog).getByText('editModal.save'));
      await waitFor(() => expect(mockUpdateMember).toHaveBeenCalledTimes(1));

      const [memberId, body] = mockUpdateMember.mock.calls[0] as [string, Record<string, unknown>];
      expect(memberId).toBe('m-1');
      expect(body).toEqual({
        personal: { first_name: 'Jan Jansen', last_name: 'de Vries', email: 'jan@h-dcn.example' },
        membership: { membership_type: 'erelid' },
        scope_values: { region: ['Zuid'] },
      });
      expect(body).not.toHaveProperty('tenant');
      expect(body).not.toHaveProperty('tenant_id');
    });
  });

  describe('validation blocks submit', () => {
    it('does not call updateMember when a required field is cleared', async () => {
      const dialog = await openEditModal();
      fillByName(dialog, 'first_name', '');
      fireEvent.click(within(dialog).getByText('editModal.save'));
      await waitFor(() => {
        expect(within(dialog).getByText('addModal.validation.required')).toBeInTheDocument();
      });
      expect(mockUpdateMember).not.toHaveBeenCalled();
    });
  });

  describe('success closes the modal and refreshes the list', () => {
    it('closes the edit modal and reloads members after a successful update', async () => {
      const dialog = await openEditModal();
      const callsBeforeSubmit = mockListMembers.mock.calls.length;
      fillByName(dialog, 'first_name', 'Jan Jansen');
      fireEvent.click(within(dialog).getByText('editModal.save'));

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      await waitFor(() =>
        expect(mockListMembers.mock.calls.length).toBeGreaterThan(callsBeforeSubmit),
      );
    });
  });
});

describe('MembersDeleteConfirm (task 19.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue([mockRow] as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockFullMember as never);
    mockDeleteMember.mockResolvedValue({} as never);
    mockListMembershipTypes.mockResolvedValue(mockMembershipTypes as never);
  });

  const openDeleteConfirm = async () => {
    const view = await openViewModal();
    fireEvent.click(within(view).getByText('actions.delete'));
    await waitFor(() => expect(screen.getByRole('alertdialog')).toBeInTheDocument());
    return screen.getByRole('alertdialog');
  };

  describe('confirm step names the member (R8.2)', () => {
    it('shows a confirm dialog naming the member — not a one-click delete', async () => {
      const dialog = await openDeleteConfirm();
      expect(within(dialog).getByText('deleteConfirm.title')).toBeInTheDocument();
      expect(within(dialog).getByText('Jan')).toBeInTheDocument();
      expect(mockDeleteMember).not.toHaveBeenCalled();
    });
  });

  describe('confirming deletes + refreshes (R8.2)', () => {
    it('calls deleteMember and reloads the list on confirm', async () => {
      const dialog = await openDeleteConfirm();
      const callsBeforeConfirm = mockListMembers.mock.calls.length;
      fireEvent.click(within(dialog).getByText('deleteConfirm.confirm'));

      await waitFor(() => expect(mockDeleteMember).toHaveBeenCalledWith('m-1'));
      await waitFor(() =>
        expect(mockListMembers.mock.calls.length).toBeGreaterThan(callsBeforeConfirm),
      );
      await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    });
  });

  describe('cancelling does NOT delete', () => {
    it('does not call deleteMember when the confirm is cancelled', async () => {
      const dialog = await openDeleteConfirm();
      fireEvent.click(within(dialog).getByText('deleteConfirm.cancel'));
      await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
      expect(mockDeleteMember).not.toHaveBeenCalled();
    });
  });
});
