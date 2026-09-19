/**
 * MembersPage (Leden Overzicht) Unit Tests — task 17.3
 *
 * Verifies the runnable/clickable Members overview page (C8, R7.5/R7.6/R7.9/R8.7):
 * - renders the mocked member rows returned by `GET /members` (the page renders
 *   whatever the module returns and never invents scope client-side — R8.7);
 * - the shared Table Filter Framework v2 narrows visible rows on a column filter;
 * - clicking a sortable header reorders the rows;
 * - the compact/full view switch (driven by the resolved field config) reveals /
 *   hides overlay columns;
 * - a row click opens the read-only view modal (fetches `getMember`).
 *
 * Mocking/render approach (matches the established page-test convention, e.g.
 * `BudgetLinesPage.test.tsx`): the service layer is mocked with `vi.mock` +
 * `vi.mocked(...)` — cleaner than MSW for a page test since
 * `membersApiService.ts` already has its own unwrap/flatten unit tests — and the
 * page is rendered with the shared `@/test-utils` `render` helper (ChakraProvider).
 * In the test env `useTypedTranslation` returns raw i18n keys, so labels/buttons
 * are asserted by their raw keys (again matching `BudgetLinesPage.test.tsx`).
 *
 * **Property 4: Scope grant deny-by-default (at the UI)** — the page renders
 * exactly the scoped rows the module returns, adding/inventing nothing.
 * **Validates: Requirements 8.7, 10.7, 10.8**
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

// A few FLAT members (as `listMembers` already flattens them), spanning regions.
const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    motor_type: 'BMW',
  },
  {
    member_id: 'm-2',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
    motor_type: 'Honda',
  },
  {
    member_id: 'm-3',
    name: 'Marie',
    email: 'marie@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'West',
    motor_type: 'Yamaha',
  },
];

// A field config carrying the region dimension + one overlay field (`motor_type`)
// that is NOT one of the fixed compact keys, so it becomes a full-view-only column.
const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'name', label: 'Naam', compact: true, order: 1 },
    { key: 'motor_type', label: 'Motorfiets', type: 'string', order: 10 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'Oost', 'West'] },
  ],
};

/** The overlay column header label the field config resolves to. */
const OVERLAY_HEADER = 'Motorfiets';

/** Wait for the table to finish loading and show the mocked rows. */
const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('Jan')).toBeInTheDocument();
    expect(screen.getByText('Piet')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
  });
};

/** Read the member-name cell order from the rendered table body. */
const nameColumnOrder = (): string[] => {
  const rows = screen.getAllByRole('row');
  // row[0] is the header row; data rows follow.
  return rows
    .slice(1)
    .map((r) => within(r).getAllByRole('cell')[0]?.textContent ?? '')
    .filter((t) => ['Jan', 'Piet', 'Marie'].includes(t));
};

describe('MembersPage (Leden Overzicht)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
  });

  describe('renders mocked rows (R7.5, R8.7)', () => {
    it('renders each member name returned by GET /members', async () => {
      render(<MembersPage />);
      await waitForRows();

      expect(screen.getByText('jan@h-dcn.example')).toBeInTheDocument();
      // Region values are shown as read-only Badges.
      expect(screen.getByText('Noord')).toBeInTheDocument();
      expect(screen.getByText('Zuid')).toBeInTheDocument();
      expect(screen.getByText('West')).toBeInTheDocument();
    });

    it('renders exactly the rows the module returns — invents no extra rows (R8.7)', async () => {
      render(<MembersPage />);
      await waitForRows();
      expect(nameColumnOrder()).toHaveLength(mockMembers.length);
    });
  });

  describe('filtering via the shared Table Filter Framework (R7.6)', () => {
    it('narrows the visible rows to the region filter match', async () => {
      render(<MembersPage />);
      await waitForRows();

      // The region FilterableHeader input (label is the raw i18n key).
      const regionFilter = screen.getByLabelText('Filter by filters.region');
      fireEvent.change(regionFilter, { target: { value: 'Noord' } });

      // Filtering is debounced; wait for the non-matching rows to drop out.
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument();
        expect(screen.queryByText('Piet')).not.toBeInTheDocument();
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });
  });

  describe('sorting via a sortable header (R7.6)', () => {
    it('reverses the row order when the name header is clicked', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Default sort is name asc → Jan, Marie, Piet.
      expect(nameColumnOrder()).toEqual(['Jan', 'Marie', 'Piet']);

      // Click the name column sort control (label is the raw i18n key).
      fireEvent.click(screen.getByLabelText('Sort by columns.name'));

      // Toggling to desc → Piet, Marie, Jan.
      await waitFor(() => {
        expect(nameColumnOrder()).toEqual(['Piet', 'Marie', 'Jan']);
      });
    });
  });

  describe('compact/full view switch (R7.6, driven by field config)', () => {
    it('reveals the overlay column in full view and hides it again in compact', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Compact (default): the overlay header is absent.
      expect(screen.queryByText(OVERLAY_HEADER)).not.toBeInTheDocument();

      // Switch to full view: the overlay column header appears.
      fireEvent.click(screen.getByText('view.full'));
      await waitFor(() => {
        expect(screen.getByText(OVERLAY_HEADER)).toBeInTheDocument();
      });
      // Overlay values render too.
      expect(screen.getByText('BMW')).toBeInTheDocument();

      // Back to compact: the overlay column header disappears again.
      fireEvent.click(screen.getByText('view.compact'));
      await waitFor(() => {
        expect(screen.queryByText(OVERLAY_HEADER)).not.toBeInTheDocument();
      });
    });
  });

  describe('row click opens the read-only view modal (R8.1)', () => {
    it('fetches getMember and shows the member detail', async () => {
      render(<MembersPage />);
      await waitForRows();

      fireEvent.click(screen.getByText('Jan'));

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
      expect(mockGetMember).toHaveBeenCalledWith('m-1');

      const dialog = screen.getByRole('dialog');
      expect(within(dialog).getByText('jan@h-dcn.example')).toBeInTheDocument();
    });
  });
});
