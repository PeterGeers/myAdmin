/**
 * MembersPage — controls-above-the-table ordering (members-overview-tweaks,
 * task 1.2, Req 1.1–1.4).
 *
 * Task 1.1 reordered `MembersPage.tsx` so the JSX document order is
 * toolbar (action controls) → stats strip → `MembersPaginationBar`
 * (pagination controls) → `MembersTable`. These interaction tests pin that
 * structural contract and the unchanged paging behaviour:
 *
 * - With ZERO rows AND with MANY rows: the action controls (the toolbar) and
 *   the pagination bar both precede the members table in DOM document order.
 *   The pagination bar renders in that position REGARDLESS of row count — its
 *   only early return is `loading`, never an empty page (Req 1.1, 1.2, 1.3).
 * - Clicking "next" walks the DynamoDB cursor: `listMembersPage` is called
 *   again with the cursor the previous page returned, and the rendered rows
 *   update to the next page. `useMembersCursorPaging` wiring is unchanged, so
 *   paging behaviour is identical to before the reorder (Req 1.4).
 *
 * Mocking approach mirrors the sibling MembersPage tests
 * (`MembersPage.applicationsInbox.test.tsx`, `MembersExport.test.tsx`): the
 * service layer is mocked with `vi.mock`, `AuthContext` + `TenantContext` are
 * stubbed (the shared `@/test-utils` render helper wraps only ChakraProvider,
 * not a TenantProvider), and the one members table loads a DynamoDB cursor page
 * via `listMembersPage` (Req 25).
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersPage from '../../pages/MembersPage';
import * as membersApiService from '../../services/membersApiService';
import type { Member, FieldConfig } from '../../types/members';
import { render, screen, waitFor, fireEvent } from '@/test-utils';

vi.mock('../../services/membersApiService');

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

// MembersPage reads `useTenant().currentTenant` for the export filename
// (members-overview-tweaks Req 5.1/5.4). The shared `@/test-utils` render helper
// wraps only ChakraProvider, so stub the tenant context with a fixed active
// tenant (mirrors the sibling MembersPage tests).
vi.mock('../../context/TenantContext', () => ({
  useTenant: () => ({ currentTenant: 'h-dcn' }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockListMembersPage = vi.mocked(membersApiService.listMembersPage);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockGetColumnPreferences = vi.mocked(membersApiService.getColumnPreferences);
const mockSaveColumnPreferences = vi.mocked(membersApiService.saveColumnPreferences);

// A single-row "many" page is enough to exercise the ordering + paging
// contract; the DOM-order assertion does not depend on the row count.
const pageOne: Member[] = [
  {
    member_id: 'm-1',
    member_number: 'M01001',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    motor_type: 'BMW',
  },
  {
    member_id: 'm-2',
    member_number: 'M01002',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
    motor_type: 'Honda',
  },
];

// The SECOND cursor page — distinct rows so we can observe the table update
// after a "next" cursor walk.
const pageTwo: Member[] = [
  {
    member_id: 'm-3',
    member_number: 'M01003',
    name: 'Marie',
    email: 'marie@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'West',
    motor_type: 'Yamaha',
  },
];

const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'member_number', label: 'Lidnummer', type: 'string', order: 1 },
    { key: 'name', label: 'Naam', compact: true, order: 2 },
    { key: 'motor_type', label: 'Motorfiets', type: 'string', order: 10 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'Oost', 'West'] },
  ],
};

/** The action controls (toolbar) are identified by the overview title (raw key in test env). */
const toolbarTitle = () => screen.getByText('overview.title');
/** The pagination bar's "next" cursor control. */
const nextButton = () => screen.getByTestId('members-pagination-next');
/** The one members table. */
const membersTable = () => screen.getByRole('table');

/**
 * Assert that `before` precedes `after` in DOM document order.
 * `Node.DOCUMENT_POSITION_FOLLOWING` (4) is set on the result when the argument
 * node follows the reference node.
 */
const assertPrecedes = (before: Element, after: Element) => {
  const position = before.compareDocumentPosition(after);
  expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
};

describe('MembersPage — controls above the table (task 1.2, Req 1.1–1.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(pageOne as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(pageOne[0] as never);
    mockListMembershipTypes.mockResolvedValue([] as never);
    mockGetColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
    mockSaveColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
  });

  it('renders the action controls and pagination bar before the table with MANY rows (Req 1.1–1.3)', async () => {
    // A non-empty page with a next-page cursor.
    mockListMembersPage.mockResolvedValue({ items: pageOne, cursor: 'CUR-2' } as never);

    render(<MembersPage />);
    await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());

    // Action controls (toolbar) precede the table.
    assertPrecedes(toolbarTitle(), membersTable());
    // Pagination bar (its "next" control) precedes the table.
    assertPrecedes(nextButton(), membersTable());
    // And the toolbar precedes the pagination bar (toolbar → pagination → table).
    assertPrecedes(toolbarTitle(), nextButton());
  });

  it('renders the action controls and pagination bar before the table with ZERO rows (Req 1.3)', async () => {
    // An empty final page: no rows, no next cursor. The pagination bar must
    // still render above the table — its only early return is `loading`.
    mockListMembersPage.mockResolvedValue({ items: [], cursor: null } as never);

    render(<MembersPage />);
    // Wait for loading to settle: the empty-state row renders once loading ends.
    await waitFor(() => expect(membersTable()).toBeInTheDocument());

    // No data rows, yet the controls + pagination bar precede the (empty) table.
    assertPrecedes(toolbarTitle(), membersTable());
    assertPrecedes(nextButton(), membersTable());
    assertPrecedes(toolbarTitle(), nextButton());
  });

  it('clicking "next" walks the cursor and updates the rows (paging unchanged, Req 1.4)', async () => {
    // Route by cursor so the result is deterministic regardless of how many
    // times the initial-mount effect settles: the first page (null cursor)
    // returns a next-page cursor; fetching WITH that cursor returns the final
    // page (no further cursor).
    mockListMembersPage.mockImplementation((({ cursor }: { cursor: string | null }) =>
      Promise.resolve(
        cursor === 'CUR-2'
          ? { items: pageTwo, cursor: null }
          : { items: pageOne, cursor: 'CUR-2' },
      )) as never);

    render(<MembersPage />);

    // Page one rendered; the first fetch used the first-page (null) cursor.
    await waitFor(() => expect(screen.getByText('Jan')).toBeInTheDocument());
    expect(mockListMembersPage).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: null }),
    );

    // Baseline the call count right before the click so the assertion does not
    // depend on how many times the initial-mount effect settled.
    const callsBeforeNext = mockListMembersPage.mock.calls.length;

    // Activate the "next" pagination control above the table.
    fireEvent.click(nextButton());

    // The cursor walk fires: `listMembersPage` is called again with the cursor
    // the previous page returned (Req 1.4 — paging behaviour unchanged).
    await waitFor(() =>
      expect(mockListMembersPage.mock.calls.length).toBeGreaterThan(callsBeforeNext),
    );
    expect(mockListMembersPage).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: 'CUR-2' }),
    );

    // The rendered rows update to the next page.
    await waitFor(() => expect(screen.getByText('Marie')).toBeInTheDocument());
    expect(screen.queryByText('Jan')).not.toBeInTheDocument();
    expect(screen.queryByText('Piet')).not.toBeInTheDocument();
  });
});
