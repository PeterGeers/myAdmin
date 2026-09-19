/**
 * MembersEditModal + MembersDeleteConfirm Unit Tests — tasks 19.2 + 19.3
 *
 * Verifies the edit + delete actions wired into the Members Overzicht page
 * through the read-only view modal (C9, R8.2/R7.7/R7.9):
 *
 * EDIT (19.2):
 * - clicking a row opens the view modal (fetches `getMember`), whose footer
 *   carries an "Edit" (`actions.edit`) action that opens the edit modal;
 * - the edit modal is PRE-FILLED from the selected member (name/email/type/region
 *   + overlay scalars);
 * - the membership-type dropdown is populated from `listMembershipTypes(true)` —
 *   the ACTIVE-ONLY catalog (R7.7);
 * - submitting calls `updateMember(memberId, body)` with the module's NESTED
 *   update body (`personal.name`/`personal.contact`/`membership.membership_type`/
 *   `scope_values.region`) and NO `tenant` field (the module stamps it — Property 2);
 * - a successful update closes the modal and triggers a list refresh.
 *
 * DELETE (19.3):
 * - the view-modal footer carries a "Delete" (`actions.delete`) action that opens
 *   a CONFIRM step (Chakra `AlertDialog`) NAMING the member — never a one-click delete;
 * - confirming calls `deleteMember(memberId)` and refreshes the list;
 * - cancelling does NOT call `deleteMember`.
 *
 * Mocking/render approach matches the sibling `MembersPage.test.tsx` /
 * `MembersAddModal.test.tsx`: the service layer is mocked with `vi.mock` +
 * `vi.mocked(...)`, the page is rendered with the shared `@/test-utils` `render`
 * helper (ChakraProvider), and `useTypedTranslation` returns raw i18n keys so
 * buttons/labels are asserted by their raw keys.
 *
 * _Requirements: R8.2, R7.7, R7.9, R10.7_
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import type { Member, FieldConfig, MembershipType } from '../types/members';

vi.mock('../services/membersApiService');

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockUpdateMember = vi.mocked(membersApiService.updateMember);
const mockDeleteMember = vi.mocked(membersApiService.deleteMember);

const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'gewoon_lid',
    region: 'Noord',
  },
];

// Field config carrying the region dimension with its allowed values (drives the
// region dropdown) — matches the projected `config#scope` shape.
const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'name', label: 'Naam', compact: true, order: 1 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'Oost', 'West'] },
  ],
};

// Active-only catalog (as `listMembershipTypes(true)` returns it).
const mockMembershipTypes: MembershipType[] = [
  { key: 'gewoon_lid', label: 'Gewoon lid', active: true },
  { key: 'erelid', label: 'Erelid', active: true },
];

/** Open the read-only view modal by clicking the member's row. */
const openViewModal = async () => {
  render(<MembersPage />);
  await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());

  fireEvent.click(screen.getByText('Jan'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  await waitFor(() => expect(mockGetMember).toHaveBeenCalledWith('m-1'));
  return screen.getByRole('dialog');
};

/** Open the view modal, then click its "Edit" footer action → edit modal. */
const openEditModal = async () => {
  const view = await openViewModal();
  fireEvent.click(within(view).getByText('actions.edit'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  return screen.getByRole('dialog');
};

/** Fill a form field by its `name` attribute (matches MembersAddModal.test). */
const fillByName = (dialog: HTMLElement, name: string, value: string) => {
  const control = dialog.querySelector(`[name="${name}"]`) as HTMLElement | null;
  if (!control) throw new Error(`No form control with name="${name}"`);
  fireEvent.change(control, { target: { value } });
};

describe('MembersEditModal (task 19.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockListMembershipTypes.mockResolvedValue(mockMembershipTypes as never);
    mockUpdateMember.mockResolvedValue({ member_id: 'm-1' } as never);
  });

  describe('opening + pre-fill (R8.2, R7.9)', () => {
    it('opens the edit modal from the view-modal footer, pre-filled from the member', async () => {
      const dialog = await openEditModal();

      expect(within(dialog).getByText('editModal.title')).toBeInTheDocument();

      // Pre-populated from the selected member.
      expect((dialog.querySelector('[name="name"]') as HTMLInputElement).value).toBe('Jan');
      expect((dialog.querySelector('[name="email"]') as HTMLInputElement).value)
        .toBe('jan@h-dcn.example');
      expect((dialog.querySelector('[name="membership_type"]') as HTMLSelectElement).value)
        .toBe('gewoon_lid');
      expect((dialog.querySelector('[name="region"]') as HTMLSelectElement).value)
        .toBe('Noord');
    });
  });

  describe('membership-type dropdown is active-only (R7.7)', () => {
    it('requests the ACTIVE-ONLY catalog and renders its entries as options', async () => {
      const dialog = await openEditModal();

      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      await waitFor(() => {
        expect(within(dialog).getByRole('option', { name: 'Gewoon lid' })).toBeInTheDocument();
        expect(within(dialog).getByRole('option', { name: 'Erelid' })).toBeInTheDocument();
      });
    });
  });

  describe('valid submit (R8.2, Property 2)', () => {
    it('calls updateMember with the nested body (NO tenant) for the selected member', async () => {
      const dialog = await openEditModal();
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      // Change a couple of fields.
      fillByName(dialog, 'name', 'Jan Jansen');
      fillByName(dialog, 'membership_type', 'erelid');
      fillByName(dialog, 'region', 'Zuid');

      fireEvent.click(within(dialog).getByText('editModal.save'));

      await waitFor(() => expect(mockUpdateMember).toHaveBeenCalledTimes(1));

      const [memberId, body] = mockUpdateMember.mock.calls[0] as [string, Record<string, unknown>];
      expect(memberId).toBe('m-1');
      expect(body).toEqual({
        personal: { name: 'Jan Jansen', contact: 'jan@h-dcn.example' },
        membership: { membership_type: 'erelid' },
        scope_values: { region: ['Zuid'] },
      });
      // The body MUST NOT carry a tenant field (the module stamps it — Property 2).
      expect(body).not.toHaveProperty('tenant');
      expect(body).not.toHaveProperty('tenant_id');
    });
  });

  describe('validation blocks submit', () => {
    it('does not call updateMember when a required field is cleared', async () => {
      const dialog = await openEditModal();
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      // Clear the required name field → Yup validation blocks submit.
      fillByName(dialog, 'name', '');
      fireEvent.click(within(dialog).getByText('editModal.save'));

      await waitFor(() => {
        expect(within(dialog).getByText('editModal.validation.nameRequired')).toBeInTheDocument();
      });
      expect(mockUpdateMember).not.toHaveBeenCalled();
    });
  });

  describe('success closes the modal and refreshes the list', () => {
    it('closes the edit modal and reloads members after a successful update', async () => {
      const dialog = await openEditModal();
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      const callsBeforeSubmit = mockListMembers.mock.calls.length;

      fillByName(dialog, 'name', 'Jan Jansen');
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
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockListMembershipTypes.mockResolvedValue(mockMembershipTypes as never);
    mockDeleteMember.mockResolvedValue({} as never);
  });

  /** Open the view modal then click its "Delete" footer action → confirm dialog. */
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
      // The dialog names the member being deleted.
      expect(within(dialog).getByText('Jan')).toBeInTheDocument();
      // No delete has happened just by opening the confirm.
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
      // The confirm dialog closes after a successful delete.
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
