/**
 * MembershipTypesManager + MembershipTypeModal component tests
 * (membership-type-catalog-admin-ui, task 2.5 — the paired test for tasks 2.1–2.4).
 *
 * The TenantAdmin "Lidmaatschapstypes" management surface wired to the EXISTING SAM
 * membership-type CRUD routes through the task-1 service wrapper. These assert the
 * observable behaviour of the list surface (`MembershipTypesManager`) and the create/
 * edit/retire modal (`MembershipTypeModal`) it owns, covering the spec's Properties 1–3
 * and the R1/R2 acceptance criteria.
 *
 * House pattern (NOT a literal MSW worker — the convention for these component tests is to
 * MOCK THE SERVICE LAYER, mirroring the sibling TenantAdmin/Members tests):
 *   - the service wrapper (`services/members/membersConfigApi`) is mocked with `vi.mock` +
 *     `vi.mocked(...)`, so each scenario drives `listMembershipTypes` and asserts the right
 *     write function (`createMembershipType` / `updateMembershipType` / `deactivateMembershipType`)
 *     is called with the right args, and that the list re-loads (refresh, R2.6) after a mutation;
 *   - the `members:admin` capability gate is driven by stubbing `useAuth().user.roles` via
 *     `vi.mock` (mirroring `MemberAnalyticsPage.test.tsx`): `['Tenant_Admin']` for the admin
 *     path, `['Members_Read']` for the non-admin (read-only) path;
 *   - rendered through the project's `@/test-utils` `render` (ChakraProvider) wrapped in the
 *     real i18n provider pinned to `en`, so the manager's `useTranslation()` language is
 *     deterministic (the modal receives `lang="en"` from the manager).
 *
 * Scenarios (Properties 1–3 + R1.1–R1.4, R2.1–R2.4, R2.6):
 *   1. LIST incl. retired, sorted by (order, type_code)           — R1.2, Property 1 read side
 *   2. EMPTY STATE with a create action for an admin               — R1.4
 *   3. CREATE → right body + list refresh                          — R2.1, R2.6, Property 1
 *   4. EDIT → type_code locked + update(typeCode, body) + refresh  — R2.2, Property 3
 *   5. RETIRE → confirm → deactivate(typeCode) + refresh           — R2.3, Property 2
 *   6. VALIDATION (blank nl / `#` in code) blocks the service call — R2.4
 *   7. SERVER ERROR (409) surfaced readably, list not corrupted    — R2.4
 *   8. CAPABILITY GATE — non-admin: no create, rows non-mutating   — R1.3
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.6**
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { render, screen, within, fireEvent, waitFor } from '../../../../test-utils';
import i18n from '../../../../i18n';
import { MembershipTypesManager } from '../MembershipTypesManager';
import { ApiError } from '../../../../shared/api/ApiError';
import type { MembershipType } from '../../../../types/members';

/* ------------------------------------------------------------------ */
/*  Service-layer mock — the data edge both the manager + modal use.  */
/* ------------------------------------------------------------------ */
vi.mock('../../../../services/members/membersConfigApi', () => ({
  listMembershipTypes: vi.fn(),
  createMembershipType: vi.fn(),
  updateMembershipType: vi.fn(),
  deactivateMembershipType: vi.fn(),
}));

import {
  listMembershipTypes,
  createMembershipType,
  updateMembershipType,
  deactivateMembershipType,
} from '../../../../services/members/membersConfigApi';

const mockList = vi.mocked(listMembershipTypes);
const mockCreate = vi.mocked(createMembershipType);
const mockUpdate = vi.mocked(updateMembershipType);
const mockDeactivate = vi.mocked(deactivateMembershipType);

/* ------------------------------------------------------------------ */
/*  Auth mock — drives the `members:admin` UX gate (R1.3).            */
/*  `Tenant_Admin` satisfies members:admin (task 2.4).                */
/* ------------------------------------------------------------------ */
let mockRoles: string[] = [];
vi.mock('../../../../context/AuthContext', () => ({
  useAuth: () => ({ user: { roles: mockRoles } }),
}));

/* ------------------------------------------------------------------ */
/*  Fixtures — a mix of ACTIVE + RETIRED entries, intentionally        */
/*  UNORDERED so the (order, type_code) sort is exercised (R1.2).      */
/* ------------------------------------------------------------------ */
const CATALOG: MembershipType[] = [
  { type_code: 'erelid', label: { nl: 'Erelid', en: 'Honorary' }, active: true, order: 2 },
  { type_code: 'regulier', label: { nl: 'Regulier', en: 'Regular' }, active: true, order: 1 },
  { type_code: 'oud', label: { nl: 'Oud lid', en: 'Former' }, active: false, order: 3 },
];

/** Render the manager wrapped in the real i18n provider pinned to `en` (deterministic labels). */
function renderManager() {
  i18n.changeLanguage('en');
  return render(
    <I18nextProvider i18n={i18n}>
      <MembershipTypesManager tenant="t-1" />
    </I18nextProvider>,
  );
}

/** Wait for the initial `load()` to settle (table present). */
async function waitForTable() {
  await screen.findByTestId('membership-types-table');
}

beforeEach(() => {
  mockRoles = [];
  vi.clearAllMocks();
  // Default happy-path: the full catalog. Individual tests override.
  mockList.mockResolvedValue(CATALOG as never);
  mockCreate.mockResolvedValue({} as never);
  mockUpdate.mockResolvedValue({} as never);
  mockDeactivate.mockResolvedValue({} as never);
});

/* ================================================================== */
/*  1. LIST incl. retired, sorted by (order, type_code) — R1.2        */
/* ================================================================== */
describe('list surface (R1.1/R1.2, Property 1 read side)', () => {
  it('lists ALL entries incl. retired, sorted by (order, type_code), with code/label/status/order', async () => {
    mockRoles = ['Tenant_Admin'];
    renderManager();
    await waitForTable();

    // The list is fetched with NO active filter (ALL entries incl. retired — R1.2).
    expect(mockList).toHaveBeenCalledTimes(1);
    expect(mockList).toHaveBeenLastCalledWith(); // no active-only argument

    // Every entry renders — including the RETIRED one (not filtered out).
    expect(screen.getByTestId('membership-types-row-regulier')).toBeInTheDocument();
    expect(screen.getByTestId('membership-types-row-erelid')).toBeInTheDocument();
    const retiredRow = screen.getByTestId('membership-types-row-oud');
    expect(retiredRow).toBeInTheDocument();

    // Rows are ordered by (order, type_code): regulier(1) → erelid(2) → oud(3).
    const rows = screen.getAllByTestId(/^membership-types-row-/);
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual([
      'membership-types-row-regulier',
      'membership-types-row-erelid',
      'membership-types-row-oud',
    ]);

    // Each row shows its code, (en) label, status badge and order.
    const regular = screen.getByTestId('membership-types-row-regulier');
    expect(within(regular).getByText('regulier')).toBeInTheDocument();
    expect(within(regular).getByText('Regular')).toBeInTheDocument();
    expect(within(regular).getByText('Active')).toBeInTheDocument();

    // The retired entry is SHOWN with a Retired status (not dropped).
    expect(within(retiredRow).getByText('oud')).toBeInTheDocument();
    expect(within(retiredRow).getByText('Former')).toBeInTheDocument();
    expect(within(retiredRow).getByText('Retired')).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  2. EMPTY STATE — R1.4                                              */
/* ================================================================== */
describe('empty state (R1.4)', () => {
  it('renders the empty state with a create action for an admin when the catalog is empty', async () => {
    mockRoles = ['Tenant_Admin'];
    mockList.mockResolvedValue([] as never);
    renderManager();

    const empty = await screen.findByTestId('membership-types-empty');
    expect(empty).toBeInTheDocument();
    // No crash, no table.
    expect(screen.queryByTestId('membership-types-table')).not.toBeInTheDocument();
    // Admin sees a create action in the empty state.
    expect(screen.getByTestId('membership-types-empty-create')).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  3. CREATE — R2.1, R2.6, Property 1                                 */
/* ================================================================== */
describe('create (R2.1, R2.6, Property 1)', () => {
  it('creates an entry with the right body and refreshes the list on success', async () => {
    mockRoles = ['Tenant_Admin'];
    renderManager();
    await waitForTable();
    expect(mockList).toHaveBeenCalledTimes(1); // initial load

    // Open the create modal.
    fireEvent.click(screen.getByTestId('membership-types-create'));
    const modal = await screen.findByTestId('membership-type-modal');

    // Fill code + nl/en label + order.
    fireEvent.change(within(modal).getByTestId('membership-type-modal-code'), {
      target: { value: 'student' },
    });
    fireEvent.change(within(modal).getByTestId('membership-type-modal-label-nl'), {
      target: { value: 'Student' },
    });
    fireEvent.change(within(modal).getByTestId('membership-type-modal-label-en'), {
      target: { value: 'Student' },
    });
    fireEvent.change(within(modal).getByTestId('membership-type-modal-order'), {
      target: { value: '5' },
    });

    fireEvent.click(within(modal).getByTestId('membership-type-modal-save'));

    // createMembershipType called with the parsed body (no `active` — server defaults it).
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate).toHaveBeenCalledWith({
      type_code: 'student',
      label: { nl: 'Student', en: 'Student' },
      order: 5,
    });

    // The list re-loads after success (refresh — R2.6): a SECOND listMembershipTypes call.
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
  });
});

/* ================================================================== */
/*  4. EDIT — R2.2, Property 3 (immutable id)                          */
/* ================================================================== */
describe('edit (R2.2, Property 3)', () => {
  it('locks type_code, updates label/order/active and refreshes', async () => {
    mockRoles = ['Tenant_Admin'];
    renderManager();
    await waitForTable();

    // Row-click opens the edit modal pre-filled with the entry.
    fireEvent.click(screen.getByTestId('membership-types-row-regulier'));
    const modal = await screen.findByTestId('membership-type-modal');

    // `type_code` is the stable id — the input is locked (readonly/disabled) on edit (Property 3).
    const codeInput = within(modal).getByTestId('membership-type-modal-code') as HTMLInputElement;
    expect(codeInput).toBeDisabled();
    expect(codeInput.value).toBe('regulier');

    // Change label / order / active.
    fireEvent.change(within(modal).getByTestId('membership-type-modal-label-nl'), {
      target: { value: 'Regulier lid' },
    });
    fireEvent.change(within(modal).getByTestId('membership-type-modal-order'), {
      target: { value: '9' },
    });
    fireEvent.click(within(modal).getByTestId('membership-type-modal-active')); // true → false

    fireEvent.click(within(modal).getByTestId('membership-type-modal-save'));

    // updateMembershipType(typeCode, body) — the id is the path arg, NEVER in the body (Property 3).
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    const [typeCode, body] = mockUpdate.mock.calls[0];
    expect(typeCode).toBe('regulier');
    expect(body).toEqual({
      label: { nl: 'Regulier lid', en: 'Regular' },
      active: false,
      order: 9,
    });
    expect(body).not.toHaveProperty('type_code');

    // Refresh after success (R2.6).
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
  });
});

/* ================================================================== */
/*  5. RETIRE — R2.3, Property 2 (non-destructive soft-delete)        */
/* ================================================================== */
describe('retire (R2.3, Property 2)', () => {
  it('soft-deletes via deactivateMembershipType after confirm and refreshes', async () => {
    mockRoles = ['Tenant_Admin'];
    renderManager();
    await waitForTable();

    fireEvent.click(screen.getByTestId('membership-types-row-erelid'));
    const modal = await screen.findByTestId('membership-type-modal');

    // Retire → confirm step.
    fireEvent.click(within(modal).getByTestId('membership-type-modal-retire'));
    const confirm = await screen.findByTestId('membership-type-retire-confirm');
    fireEvent.click(within(confirm).getByTestId('membership-type-retire-confirm-button'));

    // deactivateMembershipType(typeCode) — a soft-delete, never a hard delete (Property 2).
    await waitFor(() => expect(mockDeactivate).toHaveBeenCalledTimes(1));
    expect(mockDeactivate).toHaveBeenCalledWith('erelid');

    // Refresh after success (R2.6).
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
  });
});

/* ================================================================== */
/*  6. VALIDATION — R2.4 (client pre-submit blocks the service call)  */
/* ================================================================== */
describe('client-side validation (R2.4)', () => {
  it('blocks create when the nl label is blank (Save disabled, service NOT called), then unblocks once a label is typed', async () => {
    mockRoles = ['Tenant_Admin'];
    renderManager();
    await waitForTable();

    fireEvent.click(screen.getByTestId('membership-types-create'));
    const modal = await screen.findByTestId('membership-type-modal');

    // A code but a BLANK nl label → the coarse Save gate holds Save disabled (the non-blank nl
    // rule, R2.4), so a click cannot reach the service with an invalid form.
    fireEvent.change(within(modal).getByTestId('membership-type-modal-code'), {
      target: { value: 'ok-code' },
    });
    const save = within(modal).getByTestId('membership-type-modal-save') as HTMLButtonElement;
    expect(save).toBeDisabled();
    fireEvent.click(save);
    expect(mockCreate).not.toHaveBeenCalled();

    // Typing a non-blank nl label satisfies the rule → Save enables (the block was the nl label).
    fireEvent.change(within(modal).getByTestId('membership-type-modal-label-nl'), {
      target: { value: 'Student' },
    });
    await waitFor(() => expect(save).not.toBeDisabled());
  });

  it('blocks create when the code contains `#`, showing an inline code error and NOT calling the service', async () => {
    mockRoles = ['Tenant_Admin'];
    renderManager();
    await waitForTable();

    fireEvent.click(screen.getByTestId('membership-types-create'));
    const modal = await screen.findByTestId('membership-type-modal');

    // A code with the `#` sort-key separator the domain rejects, plus a valid nl label so the
    // coarse Save gate is open and the full `validate()` rule (no `#`) is what blocks submit.
    fireEvent.change(within(modal).getByTestId('membership-type-modal-code'), {
      target: { value: 'bad#code' },
    });
    fireEvent.change(within(modal).getByTestId('membership-type-modal-label-nl'), {
      target: { value: 'Label' },
    });
    fireEvent.click(within(modal).getByTestId('membership-type-modal-save'));

    expect(
      await within(modal).findByTestId('membership-type-modal-code-error'),
    ).toBeInTheDocument();
    expect(mockCreate).not.toHaveBeenCalled();
  });
});

/* ================================================================== */
/*  7. SERVER ERROR — R2.4 (409 surfaced readably, list intact)       */
/* ================================================================== */
describe('server error surfacing (R2.4)', () => {
  it('surfaces a 409 duplicate readably and does not corrupt the list', async () => {
    mockRoles = ['Tenant_Admin'];
    // The create rejects with a structured 409 duplicate ApiError (matched to the code field).
    mockCreate.mockRejectedValueOnce(
      new ApiError(409, {
        error: 'Type code already exists',
        code: 'errors.validation.duplicate',
        errors: [
          {
            field: 'type_code',
            code: 'errors.validation.duplicate',
            detail: 'Type code already exists',
          },
        ],
      }) as never,
    );
    renderManager();
    await waitForTable();

    fireEvent.click(screen.getByTestId('membership-types-create'));
    const modal = await screen.findByTestId('membership-type-modal');
    fireEvent.change(within(modal).getByTestId('membership-type-modal-code'), {
      target: { value: 'regulier' },
    });
    fireEvent.change(within(modal).getByTestId('membership-type-modal-label-nl'), {
      target: { value: 'Regulier' },
    });
    fireEvent.click(within(modal).getByTestId('membership-type-modal-save'));

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));

    // The 409 surfaces readably as an inline error on the code field (via applyApiError);
    // the modal stays open (no refresh fired) and the underlying list is not corrupted.
    expect(
      await within(modal).findByTestId('membership-type-modal-code-error'),
    ).toBeInTheDocument();
    // Only the initial load happened — a failed create does NOT refresh the list.
    expect(mockList).toHaveBeenCalledTimes(1);
    // The pre-existing rows remain intact behind the open modal.
    expect(screen.getByTestId('membership-types-row-regulier')).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  8. CAPABILITY GATE — R1.3 (non-admin: read-only, no mutations)    */
/* ================================================================== */
describe('capability gate (R1.3)', () => {
  it('a non-admin sees the read-only list but NO create button and non-mutating rows', async () => {
    mockRoles = ['Members_Read']; // not Tenant_Admin → no members:admin
    renderManager();
    await waitForTable();

    // The list is still visible (read-only) — every entry, incl. retired.
    expect(screen.getByTestId('membership-types-row-regulier')).toBeInTheDocument();
    expect(screen.getByTestId('membership-types-row-oud')).toBeInTheDocument();

    // The create affordance is ABSENT (hidden, not just disabled).
    expect(screen.queryByTestId('membership-types-create')).not.toBeInTheDocument();

    // A row-click does NOT open the mutation modal for a non-admin.
    fireEvent.click(screen.getByTestId('membership-types-row-regulier'));
    expect(screen.queryByTestId('membership-type-modal')).not.toBeInTheDocument();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('the empty-state create action is absent for a non-admin', async () => {
    mockRoles = [];
    mockList.mockResolvedValue([] as never);
    renderManager();

    const empty = await screen.findByTestId('membership-types-empty');
    expect(empty).toBeInTheDocument();
    expect(screen.queryByTestId('membership-types-empty-create')).not.toBeInTheDocument();
    expect(screen.queryByTestId('membership-types-create')).not.toBeInTheDocument();
  });
});
