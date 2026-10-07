/**
 * MembersPage — session columns (user column chooser) integration tests
 * (session-columns task 5.1; design C3/C4/C6/C8).
 *
 * Exercises the user-chosen-column behavior END TO END on the real
 * `MembersPage`, over the shared Table Filter Framework + the unified column
 * model + the on-the-fly flatten + the per-user persistence wiring. Covers:
 *
 *  - surfacing a NESTED field → its filter narrows by the RESOLVED value
 *    (nested-aware via `valueFor`) — R2.2.
 *  - type-correct sort: a `number` field sorts numerically (9 before 12, not
 *    lexically) and a `date` field sorts chronologically — R2.3.
 *  - AND-composition: a chosen-column filter composes with another column filter
 *    AND with the Option-1 global search — R2.4.
 *  - no flat-alias collision: surfacing a field never clobbers an existing flat
 *    alias (region/name) value — R3.4.
 *  - member_number is always first + not removable — R7.1.
 *  - the OQ-1 context-switch rule: a user with a saved column list keeps it
 *    across a view-context switch — R3.3.
 *  - the persistence round-trip: `getColumnPreferences` seeds columns on load; a
 *    chooser change calls `saveColumnPreferences` with the FULL ordered list —
 *    R6.5 / C8.
 *  - empty-default: a first-time user (no saved columns) → the admin/compact
 *    default columns render — R6.4.
 *  - dangling-key-skip: a stored key absent from the field config is skipped on
 *    load (no column, no crash) — R6.4 / R6.6.
 *
 * Mocking/render approach matches the sibling MembersPage specs: the service
 * layer is mocked with `vi.mock` + `vi.mocked(...)` (so `getColumnPreferences` /
 * `saveColumnPreferences` can be stubbed per test and the save call asserted);
 * the page is rendered with the shared `@/test-utils` `render` helper
 * (ChakraProvider); `useTypedTranslation` returns raw i18n keys so labels/buttons
 * are asserted by their raw keys. `useAuth` is permissive so every context is
 * selectable.
 *
 * HARNESS NOTE — the centralized Chakra mock (`src/__mocks__/chakra-ui-react.tsx`)
 * renders `Checkbox` WITHOUT honoring `isDisabled` (the prop is stripped by the
 * prop filter and the mock ignores it). So the always-on `member_number`
 * checkbox is CHECKED but not actually `disabled` in the test DOM — these tests
 * assert the always-on CHECKED state (R7.1), never the DOM `disabled` attribute.
 *
 * **Validates: Requirements 2.2, 2.3, 2.4, 3.3, 3.4, 6.4, 6.5, 7.1, 5.2**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MembersPage from '../MembersPage';
import * as membersApiService from '../../services/membersApiService';
import type { Member, FieldConfig } from '../../types/members';
import { render, screen, waitFor, fireEvent, within } from '@/test-utils';

vi.mock('../../services/membersApiService');

// Permissive auth so every view context is selectable (the dropdown renders
// only when ≥2 contexts are available — exercised by the context-switch test).
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ hasAnyRole: () => true }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);
const mockGetMember = vi.mocked(membersApiService.getMember);
const mockListMembershipTypes = vi.mocked(membersApiService.listMembershipTypes);
const mockGetColumnPreferences = vi.mocked(membersApiService.getColumnPreferences);
const mockSaveColumnPreferences = vi.mocked(membersApiService.saveColumnPreferences);

// ── Fixtures ─────────────────────────────────────────────────────────────────
// Member rows carry NESTED storage buckets (`membership.*`) alongside the flat
// convenience aliases `listMembers` already promotes (member_number, name,
// email, status, membership_type, region). `valueFor(row, 'membership', key)`
// reads the nested bucket first, so a surfaced nested field resolves its real
// value. The nested `years_member` values (9 / 12 / 3) and `joined_date` values
// are chosen so a numeric/chronological sort differs from a lexical string sort
// ("12" < "9" lexically; the ISO dates likewise interleave).
const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    member_number: 'M00001',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    membership: { years_member: 9, joined_date: '2015-03-01' },
  } as unknown as Member,
  {
    member_id: 'm-2',
    member_number: 'M00002',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
    membership: { years_member: 12, joined_date: '2012-11-20' },
  } as unknown as Member,
  {
    member_id: 'm-3',
    member_number: 'M00003',
    name: 'Marie',
    email: 'marie@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'West',
    membership: { years_member: 3, joined_date: '2021-07-10' },
  } as unknown as Member,
];

// A field config carrying the fixed compact fields + the region dimension + two
// NESTED candidate fields (a number + a date, grouped under `membership`). The
// nested fields are the ones a user surfaces via the chooser; their field-config
// labels ("Jaren lid" / "Ingangsdatum") drive the rendered header + the
// `Filter by <label>` / `Sort by <label>` aria-labels.
const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'member_number', label: 'Lidnummer', order: 0 },
    { key: 'name', label: 'Naam', compact: true, order: 1 },
    { key: 'email', group: 'personal', label: 'E-mail', type: 'string', order: 2 },
    { key: 'membership_type', label: 'Type', type: 'string', order: 3 },
    { key: 'status', label: 'Status', type: 'string', order: 4 },
    { key: 'region', label: 'Regio', order: 5 },
    // The surfaceable NESTED fields (storage group `membership`).
    {
      key: 'years_member',
      group: 'membership',
      functional_group: 'membership',
      label: 'Jaren lid',
      type: 'number',
      order: 10,
    },
    {
      key: 'joined_date',
      group: 'membership',
      functional_group: 'membership',
      label: 'Ingangsdatum',
      type: 'date',
      order: 11,
    },
  ],
  functional_groups: [
    { key: 'membership', label: { nl: 'Lidmaatschap', en: 'Membership' }, order: 1 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'West'] },
  ],
};

/** Resolved field-config header labels for the surfaced nested columns. */
const YEARS_LABEL = 'Jaren lid';
const DATE_LABEL = 'Ingangsdatum';

/** Build a column-preferences record (the GET load-seed shape). */
const prefs = (columns: string[]) => ({ sub: 'u-1', columns, updated_at: '2024-01-01T00:00:00Z' });

const waitForRows = async () => {
  await waitFor(() => {
    expect(screen.getByText('Jan')).toBeInTheDocument();
    expect(screen.getByText('Piet')).toBeInTheDocument();
    expect(screen.getByText('Marie')).toBeInTheDocument();
  });
};

/**
 * Is `value` present as a table CELL (`<td>`)? Scopes a value assertion to the
 * table body so a surfaced numeric cell (e.g. years_member `3`) is not confused
 * with the live stats-strip figures (which also render plain numbers like `3`).
 */
const hasCell = (value: string): boolean =>
  screen.getAllByText(value).some((el) => el.tagName.toLowerCase() === 'td');

/**
 * Wait for a surfaced column (seeded from `getColumnPreferences`) to render. The
 * seed is applied asynchronously AFTER the rows first render (the load effect
 * resolves the preferences, then seeds `chosenKeys`), so a column assertion /
 * interaction must wait for the column header to appear rather than reading it
 * synchronously right after `waitForRows`.
 */
const waitForColumn = async (label: string) => {
  await waitFor(() => {
    expect(screen.getByText(label)).toBeInTheDocument();
  });
};

/**
 * Read the member-name column order from the rendered table body. member_number
 * leads every row, so the name is not the first cell — pick the cell whose text
 * is one of the known member names.
 */
const nameColumnOrder = (): string[] => {
  const rows = screen.getAllByRole('row');
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

describe('MembersPage — session columns (user column chooser)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListMembers.mockResolvedValue(mockMembers as never);
    mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
    mockGetMember.mockResolvedValue(mockMembers[0] as never);
    mockListMembershipTypes.mockResolvedValue([] as never);
    // Default: a first-time user with no saved columns. Individual tests override
    // the GET to seed a saved list.
    mockGetColumnPreferences.mockResolvedValue(prefs([]) as never);
    mockSaveColumnPreferences.mockResolvedValue(prefs([]) as never);
  });

  // ── Surface a nested field → its filter narrows by the resolved value ────────
  describe('surfacing a nested field makes it filterable (R2.2)', () => {
    it('renders the surfaced nested column + value, and its filter narrows by the resolved nested value', async () => {
      // Seed a saved list surfacing the nested `years_member` field on load (C8).
      // A saved list REPLACES the admin default columns with the user's own, so
      // `name` is included to keep each row identifiable by its name cell.
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // The surfaced nested column renders its header + each row's RESOLVED
      // nested value (membership.years_member), proving the on-the-fly flatten.
      // Scope the value checks to table cells (<td>) so the surfaced numbers are
      // not confused with the live stats-strip figures (which also render `3`).
      expect(screen.getByText(YEARS_LABEL)).toBeInTheDocument();
      expect(hasCell('9')).toBe(true);
      expect(hasCell('12')).toBe(true);
      expect(hasCell('3')).toBe(true);

      // The surfaced column is filterable identically to a fixed one: typing the
      // nested value narrows to the matching row (R2.2 — resolved, nested-aware).
      const yearsFilter = screen.getByLabelText(`Filter by ${YEARS_LABEL}`) as HTMLInputElement;
      fireEvent.change(yearsFilter, { target: { value: '12' } });

      await waitFor(() => {
        expect(screen.getByText('Piet')).toBeInTheDocument(); // years_member = 12
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });
  });

  // ── Type-correct sort (number + date fixtures) ───────────────────────────────
  describe('type-correct sort on a surfaced column (R2.3)', () => {
    it('sorts a number column numerically (9 before 12, not lexically)', async () => {
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // Sort ascending on the numeric column. A lexical sort would order the
      // string forms "12" < "3" < "9" (Piet, Marie, Jan); numeric order is
      // 3 < 9 < 12 (Marie, Jan, Piet).
      fireEvent.click(screen.getByLabelText(`Sort by ${YEARS_LABEL}`));

      await waitFor(() => {
        expect(nameColumnOrder()).toEqual(['Marie', 'Jan', 'Piet']);
      });
    });

    it('sorts a date column chronologically (not lexically on the raw value)', async () => {
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'joined_date']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(DATE_LABEL);

      // joined_date: Jan 2015-03-01, Piet 2012-11-20, Marie 2021-07-10.
      // Chronological asc → Piet (2012), Jan (2015), Marie (2021).
      fireEvent.click(screen.getByLabelText(`Sort by ${DATE_LABEL}`));

      await waitFor(() => {
        expect(nameColumnOrder()).toEqual(['Piet', 'Jan', 'Marie']);
      });
    });
  });

  // ── AND-composition: chosen filter × column filter × global search ───────────
  describe('AND-composition of a chosen-column filter (R2.4)', () => {
    it('composes a chosen-column filter with another column filter', async () => {
      // A user with a saved list REPLACES the default columns with their own, so
      // both the compose-with column (membership_type) and the surfaced nested
      // field (years_member) must be in the chosen list to be present + filterable.
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'membership_type', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // Narrow by membership_type (shared by Jan + Marie), then AND the chosen
      // years_member filter to a single row. membership_type is a fixed flat
      // alias, so even when user-chosen it keeps its legacy label (`filters.type`).
      const typeFilter = screen.getByLabelText('Filter by filters.type') as HTMLInputElement;
      fireEvent.change(typeFilter, { target: { value: 'regulier' } });
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument();
        expect(screen.getByText('Marie')).toBeInTheDocument();
        expect(screen.queryByText('Piet')).not.toBeInTheDocument();
      });

      // Resolve the surfaced-column filter asynchronously (findBy retries) so a
      // transient re-render after the first filter step cannot flake the query.
      const yearsFilter =
        (await screen.findByLabelText(`Filter by ${YEARS_LABEL}`)) as HTMLInputElement;
      fireEvent.change(yearsFilter, { target: { value: '3' } });
      await waitFor(() => {
        expect(screen.getByText('Marie')).toBeInTheDocument(); // regulier + years_member 3
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
      });
    });

    it('composes a chosen-column filter with the global all-fields search', async () => {
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // Global search narrows to the two 'regulier' riders (Jan + Marie) by their
      // shared membership_type; the chosen years_member filter ANDs to one.
      const search = screen.getByTestId('members-global-search') as HTMLInputElement;
      fireEvent.change(search, { target: { value: 'regulier' } });
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument();
        expect(screen.getByText('Marie')).toBeInTheDocument();
        expect(screen.queryByText('Piet')).not.toBeInTheDocument();
      });

      // Resolve the surfaced-column filter asynchronously (findBy retries) so a
      // transient re-render after the global-search step cannot flake the query.
      const yearsFilter =
        (await screen.findByLabelText(`Filter by ${YEARS_LABEL}`)) as HTMLInputElement;
      fireEvent.change(yearsFilter, { target: { value: '9' } });
      await waitFor(() => {
        expect(screen.getByText('Jan')).toBeInTheDocument(); // regulier + years_member 9
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });
  });

  // ── No flat-alias collision (R3.4) ───────────────────────────────────────────
  describe('no flat-alias collision (R3.4)', () => {
    it('surfacing a nested field never clobbers an existing flat alias (region) value', async () => {
      // Surface the nested years_member AND the flat alias `region`. The flatten
      // skips the alias (shouldFlatten === false), so region's real value is
      // preserved and still filterable by its own value.
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member', 'region']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // Each flat-alias region value survives (not overwritten by a flatten).
      expect(hasCell('Noord')).toBe(true);
      expect(hasCell('Zuid')).toBe(true);
      expect(hasCell('West')).toBe(true);

      // And the surfaced nested value renders alongside, uncorrupted.
      expect(hasCell('9')).toBe(true);

      // The region alias filter still narrows by the alias value (proving it was
      // not clobbered to the nested field's value). region is a fixed flat alias,
      // so even when user-chosen it keeps its legacy label (`filters.region`).
      const regionFilter = screen.getByLabelText('Filter by filters.region') as HTMLInputElement;
      fireEvent.change(regionFilter, { target: { value: 'Zuid' } });
      await waitFor(() => {
        expect(screen.getByText('Piet')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
        expect(screen.queryByText('Marie')).not.toBeInTheDocument();
      });
    });
  });

  // ── member_number always first + not removable (R7.1) ────────────────────────
  describe('member_number is always first + not removable (R7.1)', () => {
    it('renders member_number as the leading column even with a saved chosen list', async () => {
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // The FIRST header cell is the member_number column (its legacy i18n label
      // `columns.memberNumber`), and the first body cell of each row is the
      // member_number value.
      const headerRow = screen.getAllByRole('row')[0];
      const headerCells = within(headerRow).getAllByRole('columnheader');
      expect(headerCells[0]).toHaveTextContent('columns.memberNumber');

      const firstDataRow = screen.getAllByRole('row')[1];
      const firstCell = within(firstDataRow).getAllByRole('cell')[0];
      expect(firstCell).toHaveTextContent('M00001');
    });

    it('presents member_number in the chooser as always-on (checked) and not a removable candidate', async () => {
      // Even if a (defensive) stored list includes member_number, it is never a
      // toggleable candidate — the chooser locks it on (R7.1/R7.3).
      mockGetColumnPreferences.mockResolvedValue(prefs(['member_number', 'name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();

      // Open the chooser.
      fireEvent.click(screen.getByTestId('members-column-chooser-button'));
      await waitFor(() => {
        expect(screen.getByTestId('column-chooser')).toBeInTheDocument();
      });

      // The member_number checkbox is rendered CHECKED (always-on). The Chakra
      // mock does not honor `isDisabled`, so we assert the checked state (the
      // always-on signal), not the DOM `disabled` attribute (HARNESS NOTE).
      const chooser = within(screen.getByTestId('column-chooser'));
      const memberNumberCheckbox = chooser
        .getByTestId('column-chooser-member_number')
        .querySelector('input[type="checkbox"]') as HTMLInputElement;
      expect(memberNumberCheckbox).toBeInTheDocument();
      expect(memberNumberCheckbox.checked).toBe(true);
    });
  });

  // ── OQ-1 context switch retains a saved column list (R3.3) ────────────────────
  describe('context switch retains a saved column list (OQ-1, R3.3)', () => {
    it('keeps the user chosen columns after switching the view context', async () => {
      // Two contexts open to everyone → the dropdown renders. Each defines its
      // own columns, but a user WITH a saved list keeps that list across the
      // switch (the context only drives default_sort / filterable_columns /
      // page_size, not the column set).
      mockGetFieldConfig.mockResolvedValue({
        ...mockFieldConfig,
        view_contexts: [
          { key: 'ctx-a', label: { nl: 'Overzicht', en: 'Overview' }, columns: ['name', 'email'] },
          { key: 'ctx-b', label: { nl: 'Financieel', en: 'Financial' }, columns: ['name', 'status'] },
        ],
      } as never);
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // The saved chosen column is shown in the first context.
      expect(screen.getByText(YEARS_LABEL)).toBeInTheDocument();

      // Switch context.
      const dropdown = screen.getByLabelText('viewContext.label') as HTMLSelectElement;
      fireEvent.change(dropdown, { target: { value: 'ctx-b' } });

      // The chosen column is RETAINED (not rebuilt from the new context). The
      // context switch re-renders asynchronously, so wait for the retained
      // column's filter to settle (findBy retries) before driving it.
      await waitFor(() => {
        expect(screen.getByText(YEARS_LABEL)).toBeInTheDocument();
      });
      // Its filter still works post-switch (the column is still wired).
      const yearsFilter =
        (await screen.findByLabelText(`Filter by ${YEARS_LABEL}`)) as HTMLInputElement;
      fireEvent.change(yearsFilter, { target: { value: '12' } });
      await waitFor(() => {
        expect(screen.getByText('Piet')).toBeInTheDocument();
        expect(screen.queryByText('Jan')).not.toBeInTheDocument();
      });
    });
  });

  // ── Persistence round-trip (R6.5 / C8) ───────────────────────────────────────
  describe('persistence round-trip (R6.5, C8)', () => {
    it('seeds columns from getColumnPreferences on load (they render)', async () => {
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member', 'joined_date']) as never);

      render(<MembersPage />);
      await waitForRows();

      // Both seeded columns render — the load-seed round-trip half.
      await waitFor(() => {
        expect(screen.getByText(YEARS_LABEL)).toBeInTheDocument();
        expect(screen.getByText(DATE_LABEL)).toBeInTheDocument();
      });
      expect(mockGetColumnPreferences).toHaveBeenCalled();
    });

    it('a chooser toggle calls saveColumnPreferences with the FULL ordered list', async () => {
      // Start from a saved list; toggling another field appends it and persists
      // the full ordered list (full replace, R6.5).
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member']) as never);

      render(<MembersPage />);
      await waitForRows();
      // Wait for the seed to apply so the chooser's current selection is the
      // saved list — the toggle then appends to it (full-list emit).
      await waitForColumn(YEARS_LABEL);

      fireEvent.click(screen.getByTestId('members-column-chooser-button'));
      await waitFor(() => {
        expect(screen.getByTestId('column-chooser')).toBeInTheDocument();
      });

      // Toggle ON the second nested field via its checklist checkbox.
      const chooser = within(screen.getByTestId('column-chooser'));
      const joinedCheckbox = chooser
        .getByTestId('column-chooser-joined_date')
        .querySelector('input[type="checkbox"]') as HTMLInputElement;
      fireEvent.click(joinedCheckbox);

      // The save wrapper is called with the FULL ordered list (never
      // member_number — it is implied/pinned, R7.3).
      await waitFor(() => {
        expect(mockSaveColumnPreferences).toHaveBeenCalledWith(['name', 'years_member', 'joined_date']);
      });
    });

    it('toggling OFF a surfaced column persists the full remaining list', async () => {
      mockGetColumnPreferences.mockResolvedValue(prefs(['name', 'years_member', 'joined_date']) as never);

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      fireEvent.click(screen.getByTestId('members-column-chooser-button'));
      await waitFor(() => {
        expect(screen.getByTestId('column-chooser')).toBeInTheDocument();
      });

      const chooser = within(screen.getByTestId('column-chooser'));
      const yearsCheckbox = chooser
        .getByTestId('column-chooser-years_member')
        .querySelector('input[type="checkbox"]') as HTMLInputElement;
      fireEvent.click(yearsCheckbox);

      await waitFor(() => {
        expect(mockSaveColumnPreferences).toHaveBeenCalledWith(['name', 'joined_date']);
      });
    });
  });

  // ── Empty-default + dangling-key-skip (R6.4 / R6.6) ───────────────────────────
  describe('empty-default + dangling-key-skip (R6.4, R6.6)', () => {
    it('a first-time user (no saved columns) sees the admin/compact default columns', async () => {
      // Default beforeEach GET returns an empty list → the first-time default:
      // the compact fixed columns render, and NO surfaced nested column appears.
      mockGetColumnPreferences.mockResolvedValue(prefs([]) as never);

      render(<MembersPage />);
      await waitForRows();

      // The compact default renders the fixed columns (name/email values present)
      // but not the non-default nested columns.
      expect(screen.getByText('jan@h-dcn.example')).toBeInTheDocument();
      expect(screen.queryByText(YEARS_LABEL)).not.toBeInTheDocument();
      expect(screen.queryByText(DATE_LABEL)).not.toBeInTheDocument();
    });

    it('skips a stored key that is not in the field config (no column, no crash)', async () => {
      // A saved list mixing a resolvable nested key with a DANGLING key (a field
      // removed/hidden from the config). The dangling key is skipped on load; the
      // resolvable one still renders — the page never crashes.
      mockGetColumnPreferences.mockResolvedValue(
        prefs(['name', 'years_member', 'ghost_field_gone']) as never,
      );

      render(<MembersPage />);
      await waitForRows();
      await waitForColumn(YEARS_LABEL);

      // The resolvable column renders.
      expect(screen.getByText(YEARS_LABEL)).toBeInTheDocument();
      // The dangling key produces no header/column and does not crash the page.
      expect(screen.queryByText('ghost_field_gone')).not.toBeInTheDocument();
      // All rows still present (no crash).
      expect(nameColumnOrder()).toHaveLength(mockMembers.length);
    });
  });
});
