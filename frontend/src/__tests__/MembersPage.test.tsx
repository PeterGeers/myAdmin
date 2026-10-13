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
import MembersPage from '../pages/MembersPage';
import * as membersApiService from '../services/membersApiService';
import type { Member, FieldConfig } from '../types/members';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';

vi.mock('../services/membersApiService');

// MembersPage renders the single generic table over the resolved field config's
// visible fields; the view-context dropdown was retired in Phase 2 step b
// (task 3.3). `useAuth().hasAnyRole` is stubbed permissive — role gating is not
// exercised by these table-focused tests.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockGetColumnPreferences = vi.mocked(membersApiService.getColumnPreferences);
const mockSaveColumnPreferences = vi.mocked(membersApiService.saveColumnPreferences);

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
    // `membership_type` + `status` are resolved fields too, so the global search
    // (which scans every candidate field) can match on them.
    { key: 'membership_type', label: 'Type', type: 'string', order: 3 },
    { key: 'status', label: 'Status', type: 'string', order: 4 },
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
 * Find the read-only region SCOPE cell for a value. The region renders as a
 * plain table cell (`<td>`) — the purple `<Badge>` was intentionally removed
 * (commit ea6e4ab). We pick the table-cell node for the value.
 */
const regionBadge = (value: string): HTMLElement => {
  const match = screen
    .getAllByText(value)
    .find((el) => el.tagName.toLowerCase() === 'td');
  if (!match) throw new Error(`No region cell <td> for "${value}"`);
  return match;
};

/**
 * Read the member-name column order from the rendered table body. The compact
 * table now leads with member_number (Lidnummer, commit 3dde030), so the name is
 * no longer the first cell — pick the cell whose text is one of the known member
 * names rather than assuming a fixed column index.
 */
const nameColumnOrder = (): string[] => {
  const rows = screen.getAllByRole('row');
  // row[0] is the header row; data rows follow.
  return rows
    .slice(1)
    .map(
      (r) =>
        within(r)
          .getAllByRole('cell')
          .map((c) => c.textContent ?? '')
          .find((t) => ['Jan', 'Piet', 'Marie'].includes(t)) ?? '',
    )
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
    // Column preferences (session-columns C8): a first-time user with no saved
    // columns → empty set, so these table-focused tests see the default columns.
    // Deterministic mocks avoid the C8 load effect hanging on an auto-mocked
    // undefined return.
    mockGetColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
    mockSaveColumnPreferences.mockResolvedValue({ sub: '', columns: [], updated_at: '' } as never);
  });

  describe('renders mocked rows (R7.5, R8.7)', () => {
    it('renders each member name returned by GET /members', async () => {
      render(<MembersPage />);
      await waitForRows();

      expect(screen.getByText('jan@h-dcn.example')).toBeInTheDocument();
      // Region values are shown as read-only cells (<td>), one per row.
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

      // The region FilterableHeader control (label is the raw i18n key) is the
      // standard free-text filter input, like every other column.
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

      // Region values render as read-only cells (<td>), one per row — the
      // scope indicator.
      expect(regionBadge('Noord')).toBeInTheDocument();
      expect(regionBadge('Zuid')).toBeInTheDocument();
      expect(regionBadge('West')).toBeInTheDocument();
    });

    it('renders the scope filter as the standard free-text input (Table Filter Framework v2)', async () => {
      render(<MembersPage />);
      await waitForRows();

      // The region column filter is the standard free-text <input>, exactly like
      // every other column — not an enum <select>. Even though the field config
      // carries a `region` scope dimension, the header no longer pre-fills enum
      // options; it uses the shared toolkit's default text filter.
      const regionFilter = screen.getByLabelText('Filter by filters.region');
      expect(regionFilter.tagName.toLowerCase()).toBe('input');
      expect(regionFilter.tagName.toLowerCase()).not.toBe('select');
    });

    it('typing a region value narrows the rows to that scope (client-side over already-scoped rows)', async () => {
      render(<MembersPage />);
      await waitForRows();

      const regionFilter = screen.getByLabelText('Filter by filters.region') as HTMLInputElement;
      fireEvent.change(regionFilter, { target: { value: 'Zuid' } });

      await waitFor(() => {
        expect(screen.getByText('Piet')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });

    it('renders a free-text region filter over the single generic table (applies regardless of render path)', async () => {
      // Phase 2 step b (task 3.3) retired the view-context explicit-columns path;
      // the single generic table renders over the resolved visible fields. The
      // region column (a fixed flat alias → legacy `filters.region` label) must
      // still carry the standard free-text input — the region filter behavior
      // never depended on a context.
      render(<MembersPage />);
      await waitForRows();

      const regionFilter = screen.getByLabelText('Filter by filters.region') as HTMLInputElement;
      expect(regionFilter.tagName.toLowerCase()).toBe('input');
      expect(regionFilter.tagName.toLowerCase()).not.toBe('select');

      // And typing a value narrows the rows.
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

  // The compact/full toggle was removed (findings): overlay columns are now
  // surfaced on demand via the ColumnChooser instead of a two-state switch.
  describe('surfacing an overlay column via the ColumnChooser', () => {
    it('shows the overlay column after it is checked, and hides it when unchecked', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Default (compact) view: the overlay header is absent.
      expect(screen.queryByText(OVERLAY_HEADER)).not.toBeInTheDocument();

      // Open the chooser and check the overlay field (motor_type).
      fireEvent.click(screen.getByTestId('members-column-chooser-button'));
      await waitFor(() => {
        expect(screen.getByTestId('column-chooser')).toBeInTheDocument();
      });
      const motorCheckbox = within(screen.getByTestId('column-chooser'))
        .getByTestId('column-chooser-motor_type')
        .querySelector('input[type="checkbox"]') as HTMLInputElement;
      fireEvent.click(motorCheckbox);

      // The overlay column header + value now render. (The value "BMW" is a table
      // cell, so it is unambiguous even with the chooser open — the header label
      // "Motorfiets" also appears as the chooser checkbox label, so assert on the
      // VALUE for presence.)
      await waitFor(() => {
        expect(screen.getByText('BMW')).toBeInTheDocument();
      });

      // Uncheck it again → the column is removed. Close the chooser first so the
      // chooser's own "Motorfiets" checkbox label can't satisfy the query; then
      // the only possible "BMW" would be a table cell, which must be gone.
      fireEvent.click(motorCheckbox);
      fireEvent.click(screen.getByTestId('column-chooser-close'));
      await waitFor(() => {
        expect(screen.queryByText('BMW')).not.toBeInTheDocument();
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

      const regionFilter = screen.getByLabelText('Filter by filters.region') as HTMLInputElement;
      fireEvent.change(regionFilter, { target: { value: 'Noord' } });

      // The stats strip follows `processedData`: total stays 3 (full scoped set),
      // filtered drops to the single matching row, regions collapses to 1.
      await waitFor(() => {
        expect(screen.getByTestId('stat-filtered')).toHaveTextContent('1');
      });
      expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      expect(screen.getByTestId('stat-regions')).toHaveTextContent('1');
    });

    it('keeps the strip correct when a column filter narrows the single table', async () => {
      // Phase 2 step b (task 3.3) retired the view-context dropdown; there is one
      // generic table rendering over the resolved visible fields. The strip must
      // stay correct as a column filter narrows `processedData` (the invariant
      // the former context-switch case exercised, now without a context to pick).
      render(<MembersPage />);
      await waitForRows();

      // Strip is present and reports the full scoped set.
      await waitFor(() => {
        expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      });
      expect(screen.getByTestId('stat-filtered')).toHaveTextContent('3');

      // Filtering the region column recomputes the strip (total stays the full
      // set; filtered + regions collapse to the single match).
      const regionFilter =
        screen.getByLabelText('Filter by filters.region') as HTMLInputElement;
      fireEvent.change(regionFilter, { target: { value: 'Zuid' } });

      await waitFor(() => {
        expect(screen.getByTestId('stat-filtered')).toHaveTextContent('1');
      });
      expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      expect(screen.getByTestId('stat-regions')).toHaveTextContent('1');
    });
  });

  // ── Global all-fields search (member-field-search Option 1) ──────────────────
  describe('global all-fields search (Option 1)', () => {
    it('narrows the rows by a visible field value (case-insensitive)', async () => {
      render(<MembersPage />);
      await waitForRows();

      const search = screen.getByTestId('members-global-search') as HTMLInputElement;
      fireEvent.change(search, { target: { value: 'piet' } });

      await waitFor(() => {
        expect(screen.getByText('Piet')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });

    it('matches a NON-visible field (overlay motor_type) in compact view — the hidden-field case', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Compact view: the motor_type column is NOT rendered, yet searching its
      // value still narrows the rows — Option 1 scans every candidate field.
      expect(screen.queryByText(OVERLAY_HEADER)).not.toBeInTheDocument();

      const search = screen.getByTestId('members-global-search') as HTMLInputElement;
      fireEvent.change(search, { target: { value: 'yamaha' } });

      await waitFor(() => {
        expect(screen.getByText('Marie')).toBeInTheDocument(); // the Yamaha rider
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Piet')).not.toBeInTheDocument();
      });
    });

    it('drives the stats strip (total stays full, filtered follows the search)', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Baseline: the stats strip is present and reports the full scoped set.
      // Wrapped in waitFor — the strip renders under `!loading`, which can settle
      // a tick after the row names appear.
      await waitFor(() => {
        expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
      });

      const search = screen.getByTestId('members-global-search') as HTMLInputElement;
      fireEvent.change(search, { target: { value: 'honda' } });

      await waitFor(() => {
        expect(screen.getByTestId('stat-filtered')).toHaveTextContent('1');
      });
      // Total stays the full scoped set; only the filtered figure narrows.
      expect(screen.getByTestId('stat-total')).toHaveTextContent('3');
    });

    it('clear button restores all rows', async () => {
      render(<MembersPage />);
      await waitForRows();

      const search = screen.getByTestId('members-global-search') as HTMLInputElement;
      fireEvent.change(search, { target: { value: 'yamaha' } });
      await waitFor(() => {
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('members-global-search-clear'));
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument();
        expect(screen.getByText('Piet')).toBeInTheDocument();
        expect(screen.getByText('Marie')).toBeInTheDocument();
      });
    });

    it('combines with a per-column filter (AND semantics)', async () => {
      render(<MembersPage />);
      await waitForRows();

      // Search narrows to the two 'regulier' riders by matching their shared
      // membership_type, then a region column filter narrows further.
      const search = screen.getByTestId('members-global-search') as HTMLInputElement;
      fireEvent.change(search, { target: { value: 'regulier' } });
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument();
        expect(screen.getByText('Marie')).toBeInTheDocument();
        expect(screen.queryByText('Piet')).not.toBeInTheDocument(); // erelid
      });

      // Resolve the region filter asynchronously (findBy retries) so a transient
      // re-render after the global-search step cannot flake the query — same
      // intent, just tolerant of the post-search render settling.
      const regionFilter =
        (await screen.findByLabelText('Filter by filters.region')) as HTMLInputElement;
      fireEvent.change(regionFilter, { target: { value: 'West' } });
      await waitFor(() => {
        expect(screen.getByText('Marie')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
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

  // ── Renders over visible_fields() with NO context dropdown + paginates by the ─
  //    precedence rule (Members config redesign Phase 2 step b — task 3.3) ───────
  //
  // Phase 2 step b retired the view-context dropdown: the single generic table
  // renders over the resolved `FieldConfig` visible fields directly, and the
  // rows-per-page is the precedence `userPreference ?? default_page_size ??
  // platformDefault` (resolver `resolvePageSize`, PLATFORM_DEFAULT_PAGE_SIZE =
  // 25). This block exercises the no-dropdown render + each pagination leg over
  // the REAL page (not the resolver unit, which `membersPagination.test.ts`
  // covers) by asserting the number of rendered table body rows.
  //
  // **Validates: Requirements 3.2, 2.2, 2.3, 2.4**
  describe('visible-fields render + pagination precedence (no view-context dropdown)', () => {
    // 30 members (> the platform default of 25) so a page-size cap is observable
    // as a cut in the rendered body-row count. Each carries a unique name so the
    // name column stays a stable per-row cell.
    const manyMembers: Member[] = Array.from({ length: 30 }, (_, i) => ({
      member_id: `mm-${i + 1}`,
      name: `Lid ${String(i + 1).padStart(2, '0')}`,
      email: `lid${i + 1}@h-dcn.example`,
      status: 'active',
      membership_type: 'regulier',
      region: 'Noord',
    }));

    /** Count rendered table BODY rows (all <tr> role=row minus the header row). */
    const bodyRowCount = (): number => screen.getAllByRole('row').length - 1;

    const waitForManyRows = async () => {
      await waitFor(() => {
        expect(screen.getByText('Lid 01')).toBeInTheDocument();
      });
    };

    beforeEach(() => {
      mockListMembers.mockResolvedValue(manyMembers as never);
      mockGetMember.mockResolvedValue(manyMembers[0] as never);
    });

    it('renders the single generic table over visible_fields() with no context dropdown', async () => {
      // A field config with a visible fixed field + a NOT-visible field: the table
      // renders only the visible field as a column (visible_fields()), and no
      // view-context dropdown is present (the surface was retired in step b).
      mockGetFieldConfig.mockResolvedValue({
        fields: [
          { key: 'name', label: 'Naam', compact: true, order: 1, visible: true },
          { key: 'email', label: 'E-mail', order: 2, visible: true },
          { key: 'secret_notes', label: 'Verborgen', order: 3, visible: false },
        ],
      } as never);

      render(<MembersPage />);
      await waitForManyRows();

      // NO view-context dropdown anywhere on the page.
      expect(screen.queryByLabelText('viewContext.label')).not.toBeInTheDocument();

      // The visible field's values render; the not-visible field never becomes a
      // column header (visible_fields() gate).
      expect(screen.getByText('lid1@h-dcn.example')).toBeInTheDocument();
      expect(screen.queryByText('Verborgen')).not.toBeInTheDocument();
    });

    it('paginates by the platform default (25) when neither user pref nor tenant default is set', async () => {
      // Default beforeEach: column prefs page_size absent, field config carries no
      // default_page_size → the resolver falls through to PLATFORM_DEFAULT (25).
      mockGetFieldConfig.mockResolvedValue({
        fields: [{ key: 'name', label: 'Naam', compact: true, order: 1 }],
      } as never);

      render(<MembersPage />);
      await waitForManyRows();

      // 30 rows available, capped to the platform default of 25.
      await waitFor(() => expect(bodyRowCount()).toBe(25));
    });

    it('paginates by the tenant default_page_size leg when no user preference is set', async () => {
      // No user page_size → the tenant field-config default (10) wins over the
      // platform default (middle tier of the precedence).
      mockGetFieldConfig.mockResolvedValue({
        fields: [{ key: 'name', label: 'Naam', compact: true, order: 1 }],
        default_page_size: 10,
      } as never);

      render(<MembersPage />);
      await waitForManyRows();

      await waitFor(() => expect(bodyRowCount()).toBe(10));
    });

    it('paginates by the per-user column_preferences page_size leg (highest precedence)', async () => {
      // A user preference (5) wins over BOTH the tenant default (10) and the
      // platform default (25) — the top tier of the precedence.
      mockGetFieldConfig.mockResolvedValue({
        fields: [{ key: 'name', label: 'Naam', compact: true, order: 1 }],
        default_page_size: 10,
      } as never);
      mockGetColumnPreferences.mockResolvedValue(
        { sub: 'u-1', columns: [], page_size: 5, updated_at: '2024-01-01T00:00:00Z' } as never,
      );

      render(<MembersPage />);
      await waitForManyRows();

      await waitFor(() => expect(bodyRowCount()).toBe(5));
    });
  });
});
