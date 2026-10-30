/**
 * Members modals — structured error surfacing (API standard v1.0, task 4.4).
 *
 * Drives the Add modal THROUGH the page with the mocked members service throwing a real
 * `ApiError`, and asserts:
 *  - Add: a 422 `errors[]` renders the matching field error INLINE (localized via `code`, else
 *    `detail`) AND fires a summary toast; an UNMATCHED `field` folds into the toast;
 *  - a network failure (non-ApiError) shows the localized fallback toast.
 *
 * (retire-members-status-lifecycle-engine, design D/F: the Transition-modal half of this file
 * was removed with the SPA transition surface — the modal + `transitionMembership` no longer
 * exist. Status is now a plain field edit via the member edit modal.)
 *
 * `useToast` is spied so toast titles are asserted directly; the real i18n resolves codes.
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import { ApiError } from '../shared/api/ApiError';
import type { Member, FieldConfig } from '../types/members';
import { pickLazySelectOption, pickMembershipType } from './helpers/lazySelect';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';

vi.mock('../services/membersApiService');

// Spy on Chakra's useToast so we can read toast titles.
const toastSpy = vi.fn();
vi.mock('@chakra-ui/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@chakra-ui/react')>();
  return { ...actual, useToast: () => toastSpy };
});

let currentRoles: string[] = ['Members_CRUD'];
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    hasAnyRole: (roles: string[]) => roles.some((r) => currentRoles.includes(r)),
    user: { roles: currentRoles },
  }),
}));

// MembersPage reads the active tenant for the export filename (members-overview-tweaks Req 5.1);
// this test renders the page without a TenantProvider, so stub useTenant to a fixed tenant.
vi.mock('../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'h-dcn' }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockCreateMember = vi.mocked(membersApiService.createMember);

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

const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'first_name', group: 'personal', label: { nl: 'Voornaam', en: 'First name' }, type: 'string', required: true, functional_group: 'personal', order: 10 },
    { key: 'last_name', group: 'personal', label: { nl: 'Achternaam', en: 'Last name' }, type: 'string', required: true, functional_group: 'personal', order: 20 },
    { key: 'email', group: 'personal', label: { nl: 'E-mail', en: 'Email' }, type: 'string', required: true, functional_group: 'personal', order: 30 },
    { key: 'membership_type', group: 'membership', label: { nl: 'Type', en: 'Type' }, type: 'reference', required: true, functional_group: 'membership', order: 40, options: [{ value: 'erelid', label: { nl: 'Erelid', en: 'Honorary' } }] },
    { key: 'region', group: 'membership', label: { nl: 'Regio', en: 'Region' }, type: 'reference', functional_group: 'membership', order: 60 },
  ],
  functional_groups: [
    { key: 'personal', label: { nl: 'Persoonlijk', en: 'Personal' }, order: 1 },
    { key: 'membership', label: { nl: 'Lidmaatschap', en: 'Membership' }, order: 2 },
  ],
  dimensions: [{ key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid'] }],
} as unknown as FieldConfig;

const openAddModal = async () => {
  render(<MembersPage />);
  await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());
  fireEvent.click(screen.getByText('actions.add'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  return screen.getByRole('dialog');
};

// first_name / last_name / email are plain text Inputs → still addressable by `name`.
const fillByName = (dialog: HTMLElement, name: string, value: string) => {
  const control = dialog.querySelector(`[name="${name}"]`) as HTMLElement | null;
  if (!control) throw new Error(`No form control with name="${name}"`);
  fireEvent.change(control, { target: { value } });
};

// membership_type (eager field options) + region (eager scope dimension) route through the shared
// LazySelect combobox — open then pick so Formik `setFieldValue` fires. Labels resolve to `nl`
// (this suite does not init i18n). The field carries a single membership_type option (Erelid).
const fillValidForm = async (dialog: HTMLElement) => {
  fillByName(dialog, 'first_name', 'Piet');
  fillByName(dialog, 'last_name', 'de Nieuwe');
  fillByName(dialog, 'email', 'piet@h-dcn.example');
  await pickMembershipType('Erelid', undefined, dialog);
  await pickLazySelectOption('region', 'Zuid', { container: dialog });
};

// NOTE: this file deliberately does NOT initialize i18n — like the sibling MembersAddModal test,
// `t` echoes keys here (labels asserted by key). The LOCALIZATION of codes → copy is proven
// exhaustively by applyApiError.test.ts against the real i18n; this file proves the WIRING: a
// thrown ApiError reaches applyApiError, producing the inline field error (its English `detail`
// fallback when no copy resolves) + a summary toast.

beforeEach(() => {
  vi.clearAllMocks();
  currentRoles = ['Members_CRUD'];
  toastSpy.mockReset();
  mockListMembers.mockResolvedValue(mockMembers as never);
  vi.mocked(membersApiService.listMembersPage).mockResolvedValue(
    { items: mockMembers, cursor: null } as never,
  );
  mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
  mockGetMember.mockResolvedValue(mockMembers[0] as never);
});

describe('MembersAddModal — 422 field errors (task 4.4)', () => {
  it('renders a matched field error INLINE and fires a summary toast', async () => {
    mockCreateMember.mockRejectedValue(
      new ApiError(422, {
        error: 'Validation failed',
        code: 'errors.validation.failed',
        errors: [
          {
            field: 'personal.first_name',
            code: 'errors.validation.mustNotBeBlank',
            detail: 'must not be blank',
          },
        ],
      }),
    );

    const dialog = await openAddModal();
    await fillValidForm(dialog);
    fireEvent.click(within(dialog).getByText('addModal.save'));

    await waitFor(() => expect(mockCreateMember).toHaveBeenCalledTimes(1));
    // The field error is rendered INLINE on the matched (first_name) field — proving
    // applyApiError → setFieldError wired through. (Key-echo env → the English `detail` shows;
    // localization of the code is covered by applyApiError.test.ts.)
    await waitFor(() =>
      expect(within(dialog).getByText('must not be blank')).toBeInTheDocument(),
    );
    // A summary toast fires too (additive to the inline error).
    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
  });

  it('folds an UNMATCHED field into the summary toast', async () => {
    mockCreateMember.mockRejectedValue(
      new ApiError(422, {
        error: 'Validation failed',
        errors: [
          {
            field: 'overlay.motor',
            code: 'no.copy.code',
            detail: 'an active member must have a motorcycle',
          },
        ],
      }),
    );

    const dialog = await openAddModal();
    await fillValidForm(dialog);
    fireEvent.click(within(dialog).getByText('addModal.save'));

    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
    const titles = toastSpy.mock.calls.map((c) => String(c[0]?.title));
    // The unmatched field's detail folds into the summary toast (no inline field exists for it).
    expect(titles.some((tt) => tt.includes('an active member must have a motorcycle'))).toBe(true);
  });

  it('shows the localized fallback toast on a network failure', async () => {
    mockCreateMember.mockRejectedValue(new Error('Failed to fetch'));

    const dialog = await openAddModal();
    await fillValidForm(dialog);
    fireEvent.click(within(dialog).getByText('addModal.save'));

    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
    // Non-ApiError → the localized server-error fallback (key-echo env → the key resolves to
    // `errors:api.serverError`); localization is proven in applyApiError.test.ts.
    const titles = toastSpy.mock.calls.map((c) => c[0]?.title);
    expect(titles).toContain('errors:api.serverError');
  });
});

// retire-members-status-lifecycle-engine (design D/F): the `MembersTransitionModal — 409 reasons`
// suite was removed with the SPA transition surface (the modal + `transitionMembership` are
// gone). Status is now an ordinary field edit via the member edit modal; its error surfacing is
// the same `createMember`/`updateMember` ApiError path the Add-modal suite above already covers.
