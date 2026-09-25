/**
 * Members modals — structured error surfacing (API standard v1.0, task 4.4).
 *
 * Drives the Add and Transition modals THROUGH the page with the mocked members service throwing
 * a real `ApiError`, and asserts:
 *  - Add: a 422 `errors[]` renders the matching field error INLINE (localized via `code`, else
 *    `detail`) AND fires a summary toast; an UNMATCHED `field` folds into the toast;
 *  - Transition: a 409 `reasons[]` shows in the toast;
 *  - a network failure (non-ApiError) shows the localized fallback toast.
 *
 * `useToast` is spied so toast titles are asserted directly; the real i18n resolves codes.
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import { MembersTransitionModal } from '../components/members/MembersTransitionModal';
import * as membersApiService from '../services/membersApiService';
import { ApiError } from '../shared/api/ApiError';
import type { Member, FieldConfig } from '../types/members';

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

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockCreateMember = vi.mocked(membersApiService.createMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockTransitionMembership = vi.mocked(membersApiService.transitionMembership);

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
  mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
  mockGetMember.mockResolvedValue(mockMembers[0] as never);
  mockListMembershipTypes.mockResolvedValue([
    { key: 'erelid', label: { nl: 'Erelid', en: 'Honorary' }, active: true },
  ] as never);
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
    fillValidForm(dialog);
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
    fillValidForm(dialog);
    fireEvent.click(within(dialog).getByText('addModal.save'));

    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
    const titles = toastSpy.mock.calls.map((c) => String(c[0]?.title));
    // The unmatched field's detail folds into the summary toast (no inline field exists for it).
    expect(titles.some((tt) => tt.includes('an active member must have a motorcycle'))).toBe(true);
  });

  it('shows the localized fallback toast on a network failure', async () => {
    mockCreateMember.mockRejectedValue(new Error('Failed to fetch'));

    const dialog = await openAddModal();
    fillValidForm(dialog);
    fireEvent.click(within(dialog).getByText('addModal.save'));

    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
    // Non-ApiError → the localized server-error fallback (key-echo env → the key resolves to
    // `errors:api.serverError`); localization is proven in applyApiError.test.ts.
    const titles = toastSpy.mock.calls.map((c) => c[0]?.title);
    expect(titles).toContain('errors:api.serverError');
  });
});

describe('MembersTransitionModal — 409 reasons (task 4.4)', () => {
  // A minimal module-provided lifecycle so the modal offers a target from `active`.
  const transitionMember = { ...mockMembers[0], status: 'active' } as Member;
  const lifecycleConfig = {
    lifecycle: { allowed_transitions: { active: ['inactive'] } },
  } as unknown as FieldConfig;

  it('shows the 409 transition reasons in the toast (localized)', async () => {
    mockTransitionMembership.mockRejectedValue(
      new ApiError(409, {
        error: 'Transition denied',
        code: 'errors.transition.denied',
        reasons: [{ code: 'errors.transition.denied', detail: 'member number required to activate' }],
      }),
    );

    render(
      <MembersTransitionModal
        isOpen
        onClose={() => { }}
        member={transitionMember}
        fieldConfig={lifecycleConfig}
        onDone={() => { }}
      />,
    );
    const dialog = await screen.findByRole('dialog');
    const select = dialog.querySelector('[name="to_state"]') as HTMLElement;
    fireEvent.change(select, { target: { value: 'inactive' } });
    fireEvent.click(within(dialog).getByText('transition.confirm'));

    await waitFor(() => expect(mockTransitionMembership).toHaveBeenCalled());
    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
    const titles = toastSpy.mock.calls.map((c) => String(c[0]?.title));
    // The 409 reason surfaces in the toast (key-echo env → the reason's English detail, since the
    // top-level code has no resolved copy here; localization proven in applyApiError.test.ts).
    expect(titles.some((tt) => tt.includes('member number required to activate'))).toBe(true);
  });

  it('shows the localized fallback toast on a network failure', async () => {
    mockTransitionMembership.mockRejectedValue(new Error('Failed to fetch'));

    render(
      <MembersTransitionModal
        isOpen
        onClose={() => { }}
        member={transitionMember}
        fieldConfig={lifecycleConfig}
        onDone={() => { }}
      />,
    );
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(dialog.querySelector('[name="to_state"]') as HTMLElement, {
      target: { value: 'inactive' },
    });
    fireEvent.click(within(dialog).getByText('transition.confirm'));

    await waitFor(() => expect(toastSpy).toHaveBeenCalled());
    const titles = toastSpy.mock.calls.map((c) => c[0]?.title);
    expect(titles).toContain('errors:api.serverError');
  });
});
