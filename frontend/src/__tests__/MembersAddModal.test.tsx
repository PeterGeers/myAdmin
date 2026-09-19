/**
 * MembersAddModal (Members Add / application modal) Unit Tests — task 20.1
 *
 * Verifies the add-member modal wired into the Members Overzicht page
 * (C9, R8.3/R7.7/R7.9):
 * - clicking the header "Nieuw lid" (`actions.add`) action opens the modal;
 * - the membership-type dropdown is populated from `listMembershipTypes(true)` —
 *   the ACTIVE-ONLY catalog (R7.7): the test asserts the wrapper was called with
 *   `true`, and that only the active entries render as options;
 * - submitting a VALID form calls `createMember` with the module's NESTED create
 *   body (`personal.name` / `personal.contact` / `membership.membership_type` /
 *   `scope_values.region`) and NO `tenant` field (the module stamps the tenant —
 *   Property 2);
 * - a validation error (empty required field) BLOCKS submit (`createMember` is
 *   never called);
 * - a successful create closes the modal and triggers a list refresh
 *   (`listMembers` is called again after the create).
 *
 * Mocking/render approach matches the sibling `MembersPage.test.tsx`: the service
 * layer is mocked with `vi.mock` + `vi.mocked(...)`, and the page is rendered with
 * the shared `@/test-utils` `render` helper (ChakraProvider). In the test env
 * `useTypedTranslation` returns raw i18n keys, so buttons/labels are asserted by
 * their raw keys.
 *
 * The modal is exercised THROUGH the page (rather than in isolation) so the full
 * open → fill → submit → close + refresh wiring is covered end-to-end.
 *
 * _Requirements: R8.3, R7.7, R7.9, R10.7_
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
const mockCreateMember = vi.mocked(membersApiService.createMember);

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

/** Open the add modal from the page header and wait for it to render. */
const openAddModal = async () => {
  render(<MembersPage />);
  await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());

  fireEvent.click(screen.getByText('actions.add'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  return screen.getByRole('dialog');
};

/**
 * Fill a form field by its `name` attribute. Chakra's `FormControl` associates
 * labels via generated ids only when the field carries one; the modal renders
 * plain labels, so the tests target the underlying control by `name` (a stable,
 * intentional attribute of the Formik field).
 */
const fillByName = (dialog: HTMLElement, name: string, value: string) => {
  const control = dialog.querySelector(`[name="${name}"]`) as HTMLElement | null;
  if (!control) throw new Error(`No form control with name="${name}"`);
  fireEvent.change(control, { target: { value } });
};

/** Fill the full valid form (name/email/type/region). */
const fillValidForm = (dialog: HTMLElement) => {
  fillByName(dialog, 'name', 'Nieuwe Piet');
  fillByName(dialog, 'email', 'piet@h-dcn.example');
  fillByName(dialog, 'membership_type', 'erelid');
  fillByName(dialog, 'region', 'Zuid');
};

describe('MembersAddModal (Add / application)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockListMembershipTypes.mockResolvedValue(mockMembershipTypes as never);
    mockCreateMember.mockResolvedValue({ member_id: 'm-new' } as never);
  });

  describe('opening the modal (R8.3)', () => {
    it('opens the modal when the header "Nieuw lid" action is clicked', async () => {
      const dialog = await openAddModal();
      expect(within(dialog).getByText('addModal.title')).toBeInTheDocument();
    });
  });

  describe('membership-type dropdown is active-only (R7.7)', () => {
    it('requests the ACTIVE-ONLY catalog and renders its entries as options', async () => {
      const dialog = await openAddModal();

      // The active-only catalog must be requested with `true`.
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      // Both active entries render as <option>s.
      await waitFor(() => {
        expect(within(dialog).getByRole('option', { name: 'Gewoon lid' })).toBeInTheDocument();
        expect(within(dialog).getByRole('option', { name: 'Erelid' })).toBeInTheDocument();
      });
    });
  });

  describe('valid submit (R8.3, Property 2)', () => {
    it('calls createMember with the nested body and NO tenant field', async () => {
      const dialog = await openAddModal();
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      fillValidForm(dialog);

      fireEvent.click(within(dialog).getByText('addModal.save'));

      await waitFor(() => expect(mockCreateMember).toHaveBeenCalledTimes(1));

      const body = mockCreateMember.mock.calls[0][0] as Record<string, unknown>;
      expect(body).toEqual({
        personal: { name: 'Nieuwe Piet', contact: 'piet@h-dcn.example' },
        membership: { membership_type: 'erelid' },
        scope_values: { region: ['Zuid'] },
      });
      // The body MUST NOT carry a tenant field (the module stamps it — Property 2).
      expect(body).not.toHaveProperty('tenant');
      expect(body).not.toHaveProperty('tenant_id');
    });
  });

  describe('validation blocks submit', () => {
    it('does not call createMember when a required field is empty', async () => {
      const dialog = await openAddModal();
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      // Submit with everything blank → Yup validation blocks the submit.
      fireEvent.click(within(dialog).getByText('addModal.save'));

      await waitFor(() => {
        expect(within(dialog).getByText('addModal.validation.nameRequired')).toBeInTheDocument();
      });
      expect(mockCreateMember).not.toHaveBeenCalled();
    });
  });

  describe('success closes the modal and refreshes the list', () => {
    it('closes the modal and reloads members after a successful create', async () => {
      const dialog = await openAddModal();
      await waitFor(() => expect(mockListMembershipTypes).toHaveBeenCalledWith(true));

      // Capture how many times the list was loaded before the create.
      const callsBeforeSubmit = mockListMembers.mock.calls.length;

      fillValidForm(dialog);

      fireEvent.click(within(dialog).getByText('addModal.save'));

      // The modal closes.
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      // And the list is refreshed (onSaved → loadMembers fires again after create).
      await waitFor(() =>
        expect(mockListMembers.mock.calls.length).toBeGreaterThan(callsBeforeSubmit),
      );
    });
  });
});
