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

// MembersPage reads `useAuth().hasAnyRole` to gate the view-context dropdown
// (task 3.3). These page tests exercise the default (all-visible-fields) context,
// so a permissive stub keeps every context available and the dropdown hidden
// (single/default-only context) — leaving the existing assertions unchanged.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);

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
    // `email` is a resolved field so the (now parameter-driven) read-only view modal
    // surfaces it (s5c task 4.4 — the view is sectioned over the resolved field set).
    { key: 'email', group: 'personal', label: 'E-mail', type: 'string', order: 2 },
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

/**
 * Find the read-only region SCOPE BADGE (<span>) for a value. A region value now
 * appears twice — as a Badge <span> in the row AND as an <option> in the scope
 * enum-filter — so we disambiguate by tag.
 */
const regionBadge = (value: string): HTMLElement => {
  const match = screen
    .getAllByText(value)
    .find((el) => el.tagName.toLowerCase() === 'span');
  if (!match) throw new Error(`No region badge <span> for "${value}"`);
  return match;
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
    // The membership-type catalog feed (R5.8) — the page fetches it for the modals'
    // dropdown; an empty active list keeps these table-focused tests unaffected.
    mockListMembershipTypes.mockResolvedValue([] as never);
  });

  describe('renders mocked rows (R7.5, R8.7)', () => {
    it('renders each member name returned by GET /members', async () => {
      render(<MembersPage />);
      await waitForRows();

      expect(screen.getByText('jan@h-dcn.example')).toBeInTheDocument();
      // Region values are shown as read-only Badges (<span>). They ALSO appear as
      // options in the scope enum-filter, so assert on the badge <span> node.
      expect(regionBadge('Noord')).toBeInTheDocument();
      expect(regionBadge('Zuid')).toBeInTheDocument();
      expect(regionBadge('West')).toBeInTheDocument();
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

      // The region FilterableHeader control (label is the raw i18n key). With a
      // configured scope dimension it is an enum-select (task 4.2).
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

  // ── Scope badge + scope pre-filter (task 4.2, design C-SCOPE; R5.3, R5.4) ──────
  describe('scope badge + scope pre-filter (R5.3, R5.4, C-SCOPE)', () => {
    it('surfaces each region as a read-only scope Badge (the scope indicator)', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Region values render as read-only Badges (<span>), one per row — the
      // scope indicator. (They also appear as enum-filter options; regionBadge
      // disambiguates by picking the <span>.)
      expect(regionBadge('Noord')).toBeInTheDocument();
      expect(regionBadge('Zuid')).toBeInTheDocument();
      expect(regionBadge('West')).toBeInTheDocument();
    });

    it('renders the scope filter as an enum-select drawn from the config#scope dimension values', async () => {
      render(<MembersPage />);
      await waitForRows();

      // The region column filter is a <select> (combobox), not a free-text box,
      // because the field config carries a `region` scope dimension with values.
      const regionFilter = screen.getByLabelText('Filter by filters.region');
      expect(regionFilter.tagName.toLowerCase()).toBe('select');

      // Its options are EXACTLY the dimension's authored values (+ the empty
      // "clear" option) — never invented client-side.
      const options = within(regionFilter as HTMLSelectElement)
        .getAllByRole('option') as HTMLOptionElement[];
      const values = options.map((o) => o.value).filter((v) => v !== '');
      expect(values).toEqual(['Noord', 'Zuid', 'Oost', 'West']);
    });

    it('selecting a scope value narrows the rows to that scope (client-side over already-scoped rows)', async () => {
      render(<MembersPage />);
      await waitForRows();

      const regionFilter = screen.getByLabelText('Filter by filters.region') as HTMLSelectElement;
      fireEvent.change(regionFilter, { target: { value: 'Zuid' } });

      await waitFor(() => {
        expect(screen.getByText('Piet')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });

    it('applies the scope enum-filter in an explicit-columns view context too (applies regardless of context)', async () => {
      // A view context whose explicit columns include `region` drives the
      // explicit-columns render path (design C-VIEW). The scope pre-filter must
      // still be the enum-select drawn from the dimension values there — a
      // context chooses columns, never the scope machinery.
      mockGetFieldConfig.mockResolvedValue({
        ...mockFieldConfig,
        // The explicit-columns path resolves each column key against `fields`, so
        // `region` must be a visible field descriptor there to render.
        fields: [
          ...mockFieldConfig.fields,
          { key: 'region', label: 'Regio', order: 5 },
        ],
        view_contexts: [
          { key: 'ctx-scoped', label: { nl: 'Regio', en: 'Region' }, columns: ['name', 'region'] },
        ],
      } as never);

      render(<MembersPage />);
      await waitForRows();

      // In the explicit-columns path the header label is the resolved FIELD label
      // (here "Regio"), so the aria-label is "Filter by Regio".
      const regionFilter = screen.getByLabelText('Filter by Regio') as HTMLSelectElement;
      expect(regionFilter.tagName.toLowerCase()).toBe('select');
      const values = within(regionFilter)
        .getAllByRole('option')
        .map((o) => (o as HTMLOptionElement).value)
        .filter((v) => v !== '');
      expect(values).toEqual(['Noord', 'Zuid', 'Oost', 'West']);

      // And selecting a value narrows the rows in this context as well.
      fireEvent.change(regionFilter, { target: { value: 'West' } });
      await waitFor(() => {
        expect(screen.getByText('Marie')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Piet')).not.toBeInTheDocument();
      });
    });

    it('falls back to a free-text filter when the tenant configured no scope dimension', async () => {
      // A field config with NO dimensions → no enum options → the region column
      // keeps the shared toolkit's default free-text filter (never crashes).
      mockGetFieldConfig.mockResolvedValue({
        fields: [{ key: 'name', label: 'Naam', compact: true, order: 1 }],
      } as never);

      render(<MembersPage />);
      await waitForRows();

      const regionFilter = screen.getByLabelText('Filter by filters.region');
      expect(regionFilter.tagName.toLowerCase()).toBe('input');
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

  // ── Live statistics strip (task 4.3, design C-SURFACE; R5.4) ──────────────────
  describe('live statistics strip (R5.4, C-SURFACE)', () => {
    it('renders a stats strip reflecting the total scoped rows', async () => {
      render(<MembersPage />);
      await waitForRows();

      // The strip is present and reports the full scoped set (3 rows).
      expect(screen.getByTestId('members-stats-strip')).toBeInTheDocument();
      expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      // Nothing filtered yet → filtered count equals total.
      expect(screen.getByTestId('stat-filtered')).toHaveTextContent('3');
      // All three fixtures are `active`.
      expect(screen.getByTestId('stat-active')).toHaveTextContent('3');
      // Three distinct regions among the visible rows.
      expect(screen.getByTestId('stat-regions')).toHaveTextContent('3');
    });

    it('recomputes the filtered count from the shared toolkit when a filter narrows rows', async () => {
      render(<MembersPage />);
      await waitForRows();

      const regionFilter = screen.getByLabelText('Filter by filters.region') as HTMLSelectElement;
      fireEvent.change(regionFilter, { target: { value: 'Noord' } });

      // The stats strip follows `processedData`: total stays 3 (full scoped set),
      // filtered drops to the single matching row, regions collapses to 1.
      await waitFor(() => {
        expect(screen.getByTestId('stat-filtered')).toHaveTextContent('1');
      });
      expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      expect(screen.getByTestId('stat-regions')).toHaveTextContent('1');
    });

    it('follows a view-context switch (stats + filters recompute per selected context)', async () => {
      // Two authored contexts open to everyone (the AuthContext stub grants all
      // roles), so the context dropdown renders and a switch is observable. Both
      // feed the SAME shared toolkit + `processedData`, so the strip must stay
      // correct across the selection.
      mockGetFieldConfig.mockResolvedValue({
        ...mockFieldConfig,
        fields: [
          ...mockFieldConfig.fields,
          { key: 'email', label: 'E-mail', order: 2 },
          { key: 'status', label: 'Status', order: 3 },
          { key: 'region', label: 'Regio', order: 5 },
        ],
        view_contexts: [
          { key: 'ctx-a', label: { nl: 'Overzicht', en: 'Overview' }, columns: ['name', 'email'] },
          {
            key: 'ctx-b',
            label: { nl: 'Regio', en: 'Region' },
            columns: ['name', 'region'],
            default_sort: { field: 'name', direction: 'desc' },
          },
        ],
      } as never);

      render(<MembersPage />);
      await waitForRows();

      // Strip is present and correct in the first context.
      expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      expect(screen.getByTestId('stat-filtered')).toHaveTextContent('3');

      // Switch to the second context via the dropdown.
      const dropdown = screen.getByLabelText('viewContext.label') as HTMLSelectElement;
      fireEvent.change(dropdown, { target: { value: 'ctx-b' } });

      // Stats still reflect the full processed set after the context switch, and a
      // filter applied in the new context recomputes the strip. The switch to the
      // explicit-columns context (`ctx-b`) re-renders asynchronously, so wait for
      // its `region` header filter (label "Regio") to settle before driving it —
      // `findByLabelText` retries until the post-switch render is stable.
      await waitFor(() => {
        expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      });

      const regionFilter =
        (await screen.findByLabelText('Filter by Regio')) as HTMLSelectElement;
      fireEvent.change(regionFilter, { target: { value: 'Zuid' } });

      await waitFor(() => {
        expect(screen.getByTestId('stat-filtered')).toHaveTextContent('1');
      });
      expect(screen.getByTestId('stat-regions')).toHaveTextContent('1');
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
