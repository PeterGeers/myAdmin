/**
 * MembersAddModal (Members Add / application modal) Unit Tests — s5c task 4.4 (BROADENED
 * from the s5b task 20.1 tests).
 *
 * The add modal is now BROADENED over the RESOLVED field set (design C-SURFACE): it renders
 * WHATEVER `GET /members/field-config` resolves — the fixed base ⊕ tenant overlay ⊕ calculated
 * — SECTIONED by each field's `functional_group` (R4.9), and shapes the module's NESTED create
 * body by each field's STORAGE group (`personal.*` / `membership.*` / overlay). These tests
 * verify (C-SURFACE, R5.5/R4.9/R4.12, R8.3/Property 2):
 * - clicking the header "Nieuw lid" (`actions.add`) opens the modal;
 * - the resolved fields render as inputs grouped into their functional-group sections;
 * - a role-restricted enum option is filtered OUT of the dropdown for a caller lacking the role
 *   (R4.12 convenience filtering; the domain is authoritative);
 * - submitting a VALID form calls `createMember` with the nested body shaped by storage group
 *   and NO tenant field (Property 2);
 * - a validation error (empty required field) BLOCKS submit;
 * - a successful create closes the modal and refreshes the list.
 *
 * The service layer is mocked with `vi.mock`; the modal is exercised THROUGH the page. In the
 * test env `useTypedTranslation` returns raw i18n keys, so labels/buttons are asserted by key.
 *
 * _Requirements: R5.5, R4.9, R4.12, R8.3, R7.9_
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import type { Member, FieldConfig } from '../types/members';

vi.mock('../services/membersApiService');

// The current user's roles back both the view-context dropdown gate and the value-level enum
// option filtering (R4.12). A mutable set lets a test drive the role-restricted-option case.
let currentRoles: string[] = ['Members_CRUD'];
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    hasAnyRole: (roles: string[]) => roles.some((r) => currentRoles.includes(r)),
    user: { roles: currentRoles },
  }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockCreateMember = vi.mocked(membersApiService.createMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);

const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'gewoon',
    region: 'Noord',
  },
];

// A resolved field config carrying: the fixed base (grouped by functional_group), the
// membership_type reference field with its catalog options, a role-gated overlay enum, the
// functional-group catalog, and the region scope dimension.
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
    {
      key: 'tier', group: 'overlay', label: { nl: 'Niveau', en: 'Tier' }, type: 'enum', required: false,
      functional_group: 'membership', order: 50,
      options: [
        { value: 'standard', label: { nl: 'Standaard', en: 'Standard' } },
        { value: 'premium', label: { nl: 'Premium', en: 'Premium' }, roles: ['Members_CRUD'] },
      ],
    },
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

const openAddModal = async () => {
  render(<MembersPage />);
  await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());
  fireEvent.click(screen.getByText('actions.add'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  return screen.getByRole('dialog');
};

const fillByName = (dialog: HTMLElement, name: string, value: string) => {
  const control = dialog.querySelector(`[name="${name}"]`) as HTMLElement | null;
  if (!control) throw new Error(`No form control with name="${name}"`);
  fireEvent.change(control, { target: { value } });
};

const fillValidForm = (dialog: HTMLElement) => {
  fillByName(dialog, 'first_name', 'Piet');
  fillByName(dialog, 'last_name', 'de Nieuwe');
  fillByName(dialog, 'email', 'piet@h-dcn.example');
  fillByName(dialog, 'membership_type', 'erelid');
  fillByName(dialog, 'region', 'Zuid');
};

describe('MembersAddModal (Add / application) — broadened over the resolved field set', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentRoles = ['Members_CRUD'];
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockCreateMember.mockResolvedValue({ member_id: 'm-new' } as never);
    // The page feeds the membership_type dropdown from the ACTIVE catalog via
    // listMembershipTypes(true) (R5.8, task 4.7). Mirror the real wiring: stub the active
    // catalog to the same keys as the field's embedded membership_type options so the dropdown
    // offers `gewoon`/`erelid` and fillValidForm (which selects `erelid`) can set it.
    mockListMembershipTypes.mockResolvedValue([
      { key: 'gewoon', label: { nl: 'Gewoon lid', en: 'Ordinary' }, active: true },
      { key: 'erelid', label: { nl: 'Erelid', en: 'Honorary' }, active: true },
    ] as never);
  });

  describe('opening + sectioned rendering (R8.3, R4.9)', () => {
    it('opens the modal and renders the resolved fields in functional-group sections', async () => {
      const dialog = await openAddModal();
      expect(within(dialog).getByText('addModal.title')).toBeInTheDocument();
      // Section headings from the functional_groups catalog.
      expect(within(dialog).getByText('Persoonlijk')).toBeInTheDocument();
      expect(within(dialog).getByText('Lidmaatschap')).toBeInTheDocument();
      // Resolved fields render as controls (by their stable name attribute).
      expect(dialog.querySelector('[name="first_name"]')).toBeTruthy();
      expect(dialog.querySelector('[name="email"]')).toBeTruthy();
      expect(dialog.querySelector('[name="membership_type"]')).toBeTruthy();
    });
  });

  describe('value-level role-restricted enum options (R4.12)', () => {
    it('renders a role-restricted option for a caller holding the role', async () => {
      currentRoles = ['Members_CRUD'];
      const dialog = await openAddModal();
      expect(within(dialog).getByRole('option', { name: 'Premium' })).toBeInTheDocument();
    });

    it('hides a role-restricted option for a caller lacking the role', async () => {
      currentRoles = ['Members_Read'];
      const dialog = await openAddModal();
      // The open option is still there…
      expect(within(dialog).getByRole('option', { name: 'Standaard' })).toBeInTheDocument();
      // …but the gated one is filtered out (convenience; the domain is authoritative).
      expect(within(dialog).queryByRole('option', { name: 'Premium' })).not.toBeInTheDocument();
    });
  });

  describe('valid submit (R8.3, Property 2)', () => {
    it('calls createMember with the storage-group-shaped nested body and NO tenant field', async () => {
      const dialog = await openAddModal();
      fillValidForm(dialog);
      fireEvent.click(within(dialog).getByText('addModal.save'));

      await waitFor(() => expect(mockCreateMember).toHaveBeenCalledTimes(1));

      const body = mockCreateMember.mock.calls[0][0] as Record<string, unknown>;
      expect(body).toEqual({
        personal: { first_name: 'Piet', last_name: 'de Nieuwe', email: 'piet@h-dcn.example' },
        membership: { membership_type: 'erelid' },
        scope_values: { region: ['Zuid'] },
      });
      expect(body).not.toHaveProperty('tenant');
      expect(body).not.toHaveProperty('tenant_id');
    });
  });

  describe('validation blocks submit', () => {
    it('does not call createMember when a required field is empty', async () => {
      const dialog = await openAddModal();
      fireEvent.click(within(dialog).getByText('addModal.save'));
      await waitFor(() => {
        // Multiple required fields surface the error; assert at least one shows.
        expect(within(dialog).getAllByText('addModal.validation.required').length).toBeGreaterThan(0);
      });
      expect(mockCreateMember).not.toHaveBeenCalled();
    });
  });

  describe('success closes the modal and refreshes the list', () => {
    it('closes the modal and reloads members after a successful create', async () => {
      const dialog = await openAddModal();
      const callsBeforeSubmit = mockListMembers.mock.calls.length;
      fillValidForm(dialog);
      fireEvent.click(within(dialog).getByText('addModal.save'));

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      await waitFor(() =>
        expect(mockListMembers.mock.calls.length).toBeGreaterThan(callsBeforeSubmit),
      );
    });
  });
});
