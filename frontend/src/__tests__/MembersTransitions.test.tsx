/**
 * MembersTransitionModal + MembersBulkTransitionModal Unit Tests — tasks 20.3 + 20.4
 *
 * Verifies the single + bulk lifecycle-transition actions wired into the Members
 * Overzicht page (C9, R8.5/R8.6/R7.9):
 *
 * SINGLE (20.3, R8.5):
 * - clicking a row opens the view modal (fetches `getMember`), whose footer
 *   carries a "Change status" (`actions.transition`) action that opens the
 *   single-transition modal;
 * - the target-state options are DERIVED FROM THE MODULE RESPONSE (the resolved
 *   field config's `lifecycle`), NOT a hardcoded status list — only the states
 *   reachable from the member's CURRENT state are offered;
 * - confirming calls `transitionMembership(memberId, membershipId, { to_state })`
 *   for the selected member's primary membership;
 * - a successful transition refreshes the list;
 * - a DENIED (rejected) transition surfaces the error without crashing.
 *
 * BULK (20.4, R8.6):
 * - each row carries a selection checkbox; selecting ≥1 row enables the bulk
 *   action (a header "Bulk: change status" affordance);
 * - the header select-all checkbox selects ALL visible (`processedData`) rows;
 * - confirming the bulk modal calls `bulkTransition({ member_ids, to_state })`
 *   with EXACTLY the selected ids;
 * - a successful bulk transition clears the selection + refreshes the list.
 *
 * Mocking/render approach matches the sibling `MembersPage.test.tsx` /
 * `MembersEditDelete.test.tsx`: the service layer is mocked with `vi.mock` +
 * `vi.mocked(...)`, the page is rendered with the shared `@/test-utils` `render`
 * helper (ChakraProvider), and `useTypedTranslation` returns raw i18n keys so
 * buttons/labels are asserted by their raw keys.
 *
 * _Requirements: R8.5, R8.6, R7.9, R10.7_
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import type { Member, FieldConfig } from '../types/members';

vi.mock('../services/membersApiService');

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockTransitionMembership = vi.mocked(membersApiService.transitionMembership);
const mockBulkTransition = vi.mocked(membersApiService.bulkTransition);

// Flat members spanning regions. `m-1` is active with a primary membership id so
// the single-transition action can target it.
const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    membership_id: 'ms-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
  },
  {
    member_id: 'm-2',
    membership_id: 'ms-2',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
  },
  {
    member_id: 'm-3',
    membership_id: 'ms-3',
    name: 'Marie',
    email: 'marie@h-dcn.example',
    status: 'pending',
    membership_type: 'regulier',
    region: 'West',
  },
];

// Field config carrying the MODULE-PROVIDED lifecycle (design C2). The allowed
// transition targets the SPA offers are read from this — never hardcoded.
// From "active": suspended / lapsed / left. From "pending": active / left.
const mockFieldConfig: FieldConfig = {
  fields: [{ key: 'name', label: 'Naam', compact: true, order: 1 }],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'Oost', 'West'] },
  ],
  lifecycle: {
    allowed_states: ['application', 'pending', 'active', 'suspended', 'lapsed', 'left'],
    initial_state: 'application',
    allowed_transitions: {
      application: ['pending'],
      pending: ['active', 'left'],
      active: ['suspended', 'lapsed', 'left'],
      suspended: ['active', 'left'],
      lapsed: ['active', 'left'],
    },
  },
};

const setup = () => {
  vi.clearAllMocks();
  mockListMembers.mockResolvedValue(mockMembers as never);
  mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
  // getMember returns the same flat record the row carries (incl. membership_id).
  mockGetMember.mockImplementation((id: string) =>
    Promise.resolve(mockMembers.find(m => m.member_id === id) as never),
  );
  mockTransitionMembership.mockResolvedValue({} as never);
  mockBulkTransition.mockResolvedValue({} as never);
};

/** Wait for the table to render the mocked rows. */
const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('Jan')).toBeInTheDocument();
    expect(screen.getByText('Piet')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
  });
};

/** Open the read-only view modal by clicking a member's row. */
const openViewModal = async (name: string, memberId: string) => {
  fireEvent.click(screen.getByText(name));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  await waitFor(() => expect(mockGetMember).toHaveBeenCalledWith(memberId));
  return screen.getByRole('dialog');
};

/** Open the view modal, then click its "Change status" footer action. */
const openTransitionModal = async (name: string, memberId: string) => {
  const view = await openViewModal(name, memberId);
  fireEvent.click(within(view).getByText('actions.transition'));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  return screen.getByRole('dialog');
};

describe('MembersTransitionModal — single transition (task 20.3, R8.5)', () => {
  beforeEach(setup);

  it('offers ONLY the module-derived targets for the member current state', async () => {
    render(<MembersPage />);
    await waitForRows();

    const dialog = await openTransitionModal('Jan', 'm-1'); // current state: active

    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    const optionValues = Array.from(select.options)
      .map(o => o.value)
      .filter(v => v !== ''); // drop the placeholder

    // From "active" the module allows suspended / lapsed / left — and nothing else.
    expect(optionValues).toEqual(['suspended', 'lapsed', 'left']);
    // The hardcoded-forbidden states (e.g. "application") are NOT offered.
    expect(optionValues).not.toContain('application');
    expect(optionValues).not.toContain('active');
  });

  it('calls transitionMembership(memberId, membershipId, { to_state }) on confirm', async () => {
    render(<MembersPage />);
    await waitForRows();

    const dialog = await openTransitionModal('Jan', 'm-1');

    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'suspended' } });

    fireEvent.click(within(dialog).getByText('transition.confirm'));

    await waitFor(() => expect(mockTransitionMembership).toHaveBeenCalledTimes(1));
    const [memberId, membershipId, body] =
      mockTransitionMembership.mock.calls[0] as [string, string, Record<string, unknown>];
    expect(memberId).toBe('m-1');
    expect(membershipId).toBe('ms-1');
    expect(body).toEqual({ to_state: 'suspended' });
  });

  it('refreshes the list after a successful transition', async () => {
    render(<MembersPage />);
    await waitForRows();

    const dialog = await openTransitionModal('Jan', 'm-1');
    const callsBefore = mockListMembers.mock.calls.length;

    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'left' } });
    fireEvent.click(within(dialog).getByText('transition.confirm'));

    await waitFor(() => expect(mockTransitionMembership).toHaveBeenCalled());
    await waitFor(() =>
      expect(mockListMembers.mock.calls.length).toBeGreaterThan(callsBefore),
    );
  });

  it('surfaces a denied transition error without crashing', async () => {
    setup();
    mockTransitionMembership.mockRejectedValueOnce(
      new Error('transition denied: application must be approved'),
    );

    render(<MembersPage />);
    await waitForRows();

    const dialog = await openTransitionModal('Jan', 'm-1');
    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'suspended' } });
    fireEvent.click(within(dialog).getByText('transition.confirm'));

    await waitFor(() => expect(mockTransitionMembership).toHaveBeenCalled());
    // The page still shows its rows — the rejection was handled (toast), no crash.
    await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());
  });
});

describe('MembersBulkTransitionModal — bulk transition (task 20.4, R8.6)', () => {
  beforeEach(setup);

  /** All checkboxes on the page (header select-all + per-row). */
  const allCheckboxes = () => screen.getAllByRole('checkbox');

  it('does not show the bulk action until a row is selected', async () => {
    render(<MembersPage />);
    await waitForRows();

    expect(screen.queryByText('bulkTransition.barLabel')).not.toBeInTheDocument();

    // Select the first data row (checkbox[0] is the header select-all).
    fireEvent.click(allCheckboxes()[1]);

    await waitFor(() =>
      expect(screen.getByText('bulkTransition.barLabel')).toBeInTheDocument(),
    );
  });

  /** The checkbox inside the table row that renders `name`. */
  const rowCheckbox = (name: string): HTMLElement => {
    const cell = screen.getByText(name);
    const row = cell.closest('tr');
    if (!row) throw new Error(`No row for ${name}`);
    const box = row.querySelector('input[type="checkbox"]');
    if (!box) throw new Error(`No checkbox in row for ${name}`);
    return box as HTMLElement;
  };

  it('bulkTransition is called with EXACTLY the selected ids', async () => {
    render(<MembersPage />);
    await waitForRows();

    // Select Jan (m-1) and Marie (m-3) by their row checkbox (stable across the
    // re-render that shows the bulk bar — we re-query the row each time).
    fireEvent.click(rowCheckbox('Jan'));
    await waitFor(() =>
      expect(screen.getByText('bulkTransition.barLabel')).toBeInTheDocument(),
    );
    fireEvent.click(rowCheckbox('Marie'));

    fireEvent.click(screen.getByText('bulkTransition.barLabel'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    const dialog = screen.getByRole('dialog');
    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'left' } });
    fireEvent.click(within(dialog).getByText('bulkTransition.confirm'));

    await waitFor(() => expect(mockBulkTransition).toHaveBeenCalledTimes(1));
    const [body] = mockBulkTransition.mock.calls[0] as [Record<string, unknown>];
    expect(body.to_state).toBe('left');
    // Default sort is name asc → rows are Jan(m-1), Marie(m-3), Piet(m-2).
    expect(body.member_ids).toEqual(['m-1', 'm-3']);
  });

  it('select-all selects every visible row', async () => {
    render(<MembersPage />);
    await waitForRows();

    // Header select-all is the first checkbox.
    fireEvent.click(allCheckboxes()[0]);

    await waitFor(() =>
      expect(screen.getByText('bulkTransition.barLabel')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByText('bulkTransition.barLabel'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    const dialog = screen.getByRole('dialog');
    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'left' } });
    fireEvent.click(within(dialog).getByText('bulkTransition.confirm'));

    await waitFor(() => expect(mockBulkTransition).toHaveBeenCalledTimes(1));
    const [body] = mockBulkTransition.mock.calls[0] as [Record<string, unknown>];
    expect((body.member_ids as string[]).slice().sort()).toEqual(['m-1', 'm-2', 'm-3']);
  });

  it('clears the selection and refreshes after a successful bulk transition', async () => {
    render(<MembersPage />);
    await waitForRows();

    fireEvent.click(allCheckboxes()[1]); // select one row
    await waitFor(() =>
      expect(screen.getByText('bulkTransition.barLabel')).toBeInTheDocument(),
    );

    const callsBefore = mockListMembers.mock.calls.length;

    fireEvent.click(screen.getByText('bulkTransition.barLabel'));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    const dialog = screen.getByRole('dialog');
    const select = dialog.querySelector('[name="to_state"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'left' } });
    fireEvent.click(within(dialog).getByText('bulkTransition.confirm'));

    await waitFor(() => expect(mockBulkTransition).toHaveBeenCalled());
    // Selection cleared → the bulk bar disappears again.
    await waitFor(() =>
      expect(screen.queryByText('bulkTransition.barLabel')).not.toBeInTheDocument(),
    );
    // List refreshed.
    await waitFor(() =>
      expect(mockListMembers.mock.calls.length).toBeGreaterThan(callsBefore),
    );
  });
});
