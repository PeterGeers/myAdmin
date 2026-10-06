/**
 * MemberAnalyticsPage (Member Analytics) Unit Tests — tasks 3.1 + 3.2
 *
 * Verifies the separate Analytics page/route for the Members module
 * (design C1; requirements R1.1, R1.2, R1.5, R5.1):
 *
 * Task 3.1 (shell + gate):
 * - the page is gated behind `members:read` — a caller WITHOUT a Members read
 *   capability (`Members_Read` / `Members_CRUD`) sees the no-permission notice
 *   and NOT the analytics frame (R1.2);
 * - a caller WITH `members:read` sees the analytics page frame (title + body),
 *   following the dark-theme / orange STR/FIN report pattern (R1.1);
 * - the page is read-only — it exposes no member add/edit/delete action.
 *
 * Task 3.2 (own fetch + own filter):
 * - on open the page fetches its OWN scope-authorized set via `listMembers()`
 *   and the field config via `getFieldConfig()` (R1.5), with a loading state
 *   while in flight and an error+retry state on a member-list load failure (R1.4);
 * - it mounts its OWN `useFilterableTable(memberRows)` instance (Option A,
 *   self-contained) and renders its own `FilterableHeader` filter controls over
 *   the SAME scope-authorized rows the table shows — narrowing further, never
 *   inventing scope (R5.1): typing a column filter shrinks the live count;
 * - a field-config miss degrades gracefully (the page still renders from the
 *   member set) rather than failing the whole page.
 *
 * Mocking/render approach matches the sibling members page tests: the service
 * layer is mocked with `vi.mock` + `vi.mocked(...)`; `useAuth` is stubbed via
 * `vi.mock`; the page is rendered with the shared `@/test-utils` `render`
 * helper (ChakraProvider). In the test env `useTypedTranslation` returns raw
 * i18n keys, so text is asserted by its raw key (the field-config-resolved
 * header labels, however, come through as the config's `{nl,en}`/string label).
 *
 * **Validates: Requirements R1.1, R1.2, R1.5, R5.1**
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import MemberAnalyticsPage from '../pages/MemberAnalyticsPage';
import * as membersApiService from '../services/membersApiService';
import type { Member, FieldConfig } from '../types/members';
import { render, screen, waitFor, fireEvent } from '@/test-utils';
import {
  measurePayloadBytes,
  LIMIT_BYTES,
  WARNING_THRESHOLD_BYTES,
} from '../components/members/analytics/dataVolumeGuard';

vi.mock('../services/membersApiService');

// The page reads `useAuth().user?.roles` for its `members:read` gate. A mutable
// `mockRoles` lets each test choose the caller's roles before rendering.
let mockRoles: string[] = [];
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { roles: mockRoles } }),
}));

const mockListMembers = vi.mocked(membersApiService.listMembers);
const mockGetFieldConfig = vi.mocked(membersApiService.getFieldConfig);

// A few FLAT members (as `listMembers` already flattens them), spanning regions —
// the page's own scope-authorized set.
const mockMembers: Member[] = [
  {
    member_id: 'm-1',
    name: 'Jan',
    email: 'jan@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
  },
  {
    member_id: 'm-2',
    name: 'Piet',
    email: 'piet@h-dcn.example',
    status: 'active',
    membership_type: 'erelid',
    region: 'Zuid',
  },
  {
    member_id: 'm-3',
    name: 'Marie',
    email: 'marie@h-dcn.example',
    status: 'active',
    membership_type: 'regulier',
    region: 'West',
  },
];

// A field config carrying bilingual labels for the filter columns + the analytics
// config block (so the page resolves header labels from the config, R6.4).
const mockFieldConfig: FieldConfig = {
  fields: [
    { key: 'name', label: { nl: 'Naam', en: 'Name' }, order: 1 },
    { key: 'email', label: { nl: 'E-mail', en: 'Email' }, order: 2 },
  ],
  dimensions: [
    { key: 'region', label: 'Regio', enabled: true, values: ['Noord', 'Zuid', 'West'] },
  ],
  analytics: { jubilee_rule: { multiple_of: 5 } },
};

/** Default happy-path service stubs; individual tests override as needed. */
const stubServices = () => {
  mockListMembers.mockResolvedValue(mockMembers as never);
  mockGetFieldConfig.mockResolvedValue(mockFieldConfig as never);
};

/** Wait for the fetch to settle and the live count strip to appear. */
const waitForLoaded = async () => {
  await waitFor(() => {
    expect(screen.getByTestId('analytics-count-strip')).toBeInTheDocument();
  });
};

/**
 * A synthetic member set whose serialized byte length is at least
 * `targetBytes` — member-shaped rows padded with a filler string, inflated
 * until `measurePayloadBytes` (the guard's own measurement) crosses the target.
 * Shared by the data-volume-guard tests (task 10.2) and the accessibility pass
 * (task 11.3), both of which need the warning/exceeded banners on screen.
 */
const syntheticMembers = (targetBytes: number): Member[] => {
  const filler = 'x'.repeat(1024);
  const makeRow = (i: number): Member => ({
    member_id: `m-${i}`,
    name: `Member ${i}`,
    email: `member${i}@example.test`,
    status: 'active',
    membership_type: 'regulier',
    region: 'Noord',
    filler,
  } as unknown as Member);

  // Size the array from a ONE-row estimate (O(1)), then top up if needed —
  // never re-measure the whole array per push (that is O(n²) and stalls on the
  // multi-MiB exceeded case).
  const perRow = measurePayloadBytes([makeRow(0)]);
  const estRows = Math.ceil(targetBytes / Math.max(perRow, 1)) + 2;
  const rows: Member[] = [];
  for (let i = 0; i < estRows; i++) rows.push(makeRow(i));
  while (measurePayloadBytes(rows) < targetBytes) {
    for (let b = 0; b < 64; b++) rows.push(makeRow(rows.length));
  }
  return rows;
};

describe('MemberAnalyticsPage (Member Analytics)', () => {
  beforeEach(() => {
    mockRoles = [];
    vi.clearAllMocks();
    stubServices();
  });

  // ── Task 3.1: capability gate (R1.2) ──────────────────────────────────────
  describe('members:read gate (R1.2)', () => {
    it('denies access when the caller holds no Members capability', () => {
      mockRoles = ['Finance_Read'];
      render(<MemberAnalyticsPage />);

      expect(screen.getByText('analytics.noPermission')).toBeInTheDocument();
      expect(screen.queryByText('analytics.title')).not.toBeInTheDocument();
      // No data fetch happens behind the gate.
      expect(mockListMembers).not.toHaveBeenCalled();
    });

    it('grants access with Members_Read (the members:read capability)', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);

      expect(screen.getByText('analytics.title')).toBeInTheDocument();
      expect(screen.queryByText('analytics.noPermission')).not.toBeInTheDocument();
      await waitForLoaded();
    });

    it('grants access with Members_CRUD', async () => {
      mockRoles = ['Members_CRUD'];
      render(<MemberAnalyticsPage />);

      expect(screen.getByText('analytics.title')).toBeInTheDocument();
      await waitForLoaded();
    });
  });

  // ── Task 3.1: page shell (R1.1) ───────────────────────────────────────────
  describe('page shell (R1.1)', () => {
    it('renders the analytics title and subtitle frame for an authorized caller', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);

      expect(screen.getByText('analytics.title')).toBeInTheDocument();
      expect(screen.getByText('analytics.subtitle')).toBeInTheDocument();
      await waitForLoaded();
    });

    it('is read-only — exposes no member add/edit/delete action', async () => {
      mockRoles = ['Members_CRUD'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      expect(screen.queryByText('actions.add')).not.toBeInTheDocument();
      expect(screen.queryByText('actions.edit')).not.toBeInTheDocument();
      expect(screen.queryByText('actions.delete')).not.toBeInTheDocument();
    });
  });

  // ── Task 3.2: own fetch (R1.5) ────────────────────────────────────────────
  describe('own data fetch (R1.5)', () => {
    it('fetches the scope-authorized set and field config on open', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // The page fetches BOTH its own member set and the field config (R1.5),
      // reusing the same seam the table uses so the rows are the scope-narrowed
      // GET /members set.
      expect(mockListMembers).toHaveBeenCalledTimes(1);
      expect(mockGetFieldConfig).toHaveBeenCalledTimes(1);
    });

    it('shows a loading state while the member set is in flight', async () => {
      mockRoles = ['Members_Read'];
      // A never-resolving listMembers keeps the page in its loading state.
      let resolve!: (v: Member[]) => void;
      mockListMembers.mockReturnValue(
        new Promise<Member[]>((r) => { resolve = r; }) as never,
      );

      render(<MemberAnalyticsPage />);
      expect(screen.getByTestId('analytics-loading')).toBeInTheDocument();

      resolve(mockMembers);
      await waitForLoaded();
      expect(screen.queryByTestId('analytics-loading')).not.toBeInTheDocument();
    });

    it('renders an error + retry state when the member-list load fails, then recovers', async () => {
      mockRoles = ['Members_Read'];
      mockListMembers.mockRejectedValueOnce(new Error('network'));

      render(<MemberAnalyticsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('analytics-load-error')).toBeInTheDocument();
      });
      expect(screen.getByText('analytics.states.loadError')).toBeInTheDocument();

      // Retry succeeds (the default stub resolves) → the error clears and the
      // filtered dataset renders.
      fireEvent.click(screen.getByText('analytics.states.retry'));
      await waitForLoaded();
      expect(screen.queryByTestId('analytics-load-error')).not.toBeInTheDocument();
    });

    it('still renders the member set when the field config load fails (graceful degrade)', async () => {
      mockRoles = ['Members_Read'];
      mockGetFieldConfig.mockRejectedValueOnce(new Error('no config'));

      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // A field-config miss does NOT fail the page — the filter bar + count still
      // render from the member set. The region filter header falls back to its
      // `columns.region` i18n key (no field-config label).
      expect(screen.getByTestId('analytics-filter-bar')).toBeInTheDocument();
      expect(screen.getByTestId('analytics-row-count')).toHaveTextContent('3');
    });
  });

  // ── Task 3.2: own filter wiring (R1.5 / R5.1) ─────────────────────────────
  describe('own self-contained filter (Option A, R5.1)', () => {
    it('mounts its own filter bar and reflects the full scope-authorized count initially', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      expect(screen.getByTestId('analytics-filter-bar')).toBeInTheDocument();
      // All three mocked rows present → count 3 (the page's own processedData).
      expect(screen.getByTestId('analytics-row-count')).toHaveTextContent('3');
    });

    it('resolves filter-column labels from the field config (bilingual), not raw keys', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // `name`/`email` carry field-config labels → resolved for the active
      // language (the test env defaults to `nl`); columns without a config label
      // fall back to their `columns.*` i18n key (raw in the test env). The
      // config-resolved header proves the field-config label path (not hardcoded).
      expect(screen.getByText('Naam')).toBeInTheDocument();
      expect(screen.getByText('E-mail')).toBeInTheDocument();
      // The un-labelled columns fall back to their bilingual i18n key.
      expect(screen.getByText('columns.region')).toBeInTheDocument();
    });

    it('narrows the live count when a column filter is typed (own filter, R5.1)', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      expect(screen.getByTestId('analytics-row-count')).toHaveTextContent('3');

      // Filter the name column to "Jan" → only one row remains in the page's own
      // filtered dataset. The region/name/etc. filters are standard free-text
      // inputs from the reused FilterableHeader. The name header resolves its
      // label from the field config → `Naam` in the test env's `nl` language.
      const nameFilter = screen.getByLabelText('Filter by Naam');
      fireEvent.change(nameFilter, { target: { value: 'Jan' } });

      await waitFor(() => {
        expect(screen.getByTestId('analytics-row-count')).toHaveTextContent('1');
      });
    });

    it('shows the neutral empty state when the filter narrows to zero rows', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      const nameFilter = screen.getByLabelText('Filter by Naam');
      fireEvent.change(nameFilter, { target: { value: 'ZZZ-no-match' } });

      await waitFor(() => {
        expect(screen.getByTestId('analytics-row-count')).toHaveTextContent('0');
      });
      expect(screen.getByTestId('analytics-empty')).toBeInTheDocument();
    });
  });

  // ── Task 3.4: the THREE non-happy states rendered DISTINCTLY (R1.4) ────────
  describe('three distinct non-happy states (task 3.4, R1.4)', () => {
    it('STATE 1 — empty set renders the NEUTRAL empty state, distinct from the error state', async () => {
      mockRoles = ['Members_Read'];
      // An empty (but successful) scope-authorized set.
      mockListMembers.mockResolvedValue([] as never);
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // Neutral empty state is shown…
      const empty = screen.getByTestId('analytics-empty');
      expect(empty).toBeInTheDocument();
      expect(empty).toHaveAttribute('role', 'status'); // neutral, not an alert
      expect(screen.getByText('analytics.states.empty')).toBeInTheDocument();
      // …and it is NOT the error state and NOT the analytics panel.
      expect(screen.queryByTestId('analytics-load-error')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analytics-panel')).not.toBeInTheDocument();
    });

    it('STATE 2 — no analytics config: areas still render, config-dependent sets degrade (not an error)', async () => {
      mockRoles = ['Members_Read'];
      // Field config present but WITHOUT an analytics block → "no analytics config".
      mockGetFieldConfig.mockResolvedValue({ fields: [] } as never);
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // The analytics panel (fixed/calculated areas) still renders — no error,
      // no empty state. The config-dependent degradation reason surfaces inside
      // the Pivot Views area (asserted in the PivotViewsArea test); here we prove
      // the page did NOT fall into the empty/error states.
      expect(screen.getByTestId('analytics-panel')).toBeInTheDocument();
      expect(screen.queryByTestId('analytics-load-error')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analytics-empty')).not.toBeInTheDocument();
    });

    it('STATE 3 — load failure renders the ERROR + retry state, distinct from the empty state', async () => {
      mockRoles = ['Members_Read'];
      mockListMembers.mockRejectedValueOnce(new Error('network'));
      render(<MemberAnalyticsPage />);

      await waitFor(() => {
        expect(screen.getByTestId('analytics-load-error')).toBeInTheDocument();
      });
      // Error state carries the error message + a retry affordance…
      expect(screen.getByText('analytics.states.loadError')).toBeInTheDocument();
      expect(screen.getByText('analytics.states.retry')).toBeInTheDocument();
      // …and it is NOT the neutral empty state and NOT the analytics panel.
      expect(screen.queryByTestId('analytics-empty')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analytics-panel')).not.toBeInTheDocument();
    });
  });

  // ── Task 10.2: the data-volume guard (C8, R7.1/R7.3/R7.4) ──────────────────
  // The page measures the SERIALIZED byte length of the scope-authorized
  // `GET /members` response (the full `members` set) against the 6 MiB Lambda
  // ceiling, and renders the warning banner (≥ 80%) / exceeded state (≥ 100%,
  // NO aggregation) accordingly. We drive the boundaries with a SYNTHETIC large
  // member payload measured the SAME way the guard measures it.
  describe('data-volume guard (task 10.2, R7.1/R7.3/R7.4)', () => {
    it('BELOW 80% — normal: no warning banner, no exceeded state, panel renders', async () => {
      mockRoles = ['Members_Read'];
      // The default 3-row stub is tiny (well under 80%).
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      expect(screen.queryByTestId('analytics-over-limit-warning')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analytics-over-limit-exceeded')).not.toBeInTheDocument();
      // The analytics panel (aggregation) renders normally.
      expect(screen.getByTestId('analytics-panel')).toBeInTheDocument();
    });

    it('AT/≥ 80% but < 100% — WARNING banner shows AND the panel still renders (aggregation runs)', async () => {
      mockRoles = ['Members_Read'];
      // Cross 80% of 6 MiB but stay under the limit.
      const payload = syntheticMembers(WARNING_THRESHOLD_BYTES + 50 * 1024);
      // Sanity: the synthetic set is in the warning band.
      expect(measurePayloadBytes(payload)).toBeGreaterThanOrEqual(WARNING_THRESHOLD_BYTES);
      expect(measurePayloadBytes(payload)).toBeLessThan(LIMIT_BYTES);
      mockListMembers.mockResolvedValue(payload as never);

      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // User-visible warning banner (bilingual key)…
      const banner = await screen.findByTestId('analytics-over-limit-warning');
      expect(banner).toBeInTheDocument();
      expect(screen.getByText('analytics.overLimit.warning')).toBeInTheDocument();
      // …but aggregation STILL runs (panel present), and it is NOT the exceeded state.
      expect(screen.getByTestId('analytics-panel')).toBeInTheDocument();
      expect(screen.queryByTestId('analytics-over-limit-exceeded')).not.toBeInTheDocument();
    });

    it('AT/OVER 100% — EXCEEDED state shows, the panel does NOT render (no partial aggregation)', async () => {
      mockRoles = ['Members_Read'];
      // Cross the 6 MiB limit.
      const payload = syntheticMembers(LIMIT_BYTES + 100 * 1024);
      expect(measurePayloadBytes(payload)).toBeGreaterThanOrEqual(LIMIT_BYTES);
      mockListMembers.mockResolvedValue(payload as never);

      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // Explicit "dataset too large" state (bilingual key)…
      const exceeded = await screen.findByTestId('analytics-over-limit-exceeded');
      expect(exceeded).toBeInTheDocument();
      expect(screen.getByText('analytics.overLimit.exceeded')).toBeInTheDocument();
      // …and NO aggregation: the analytics panel does not mount its areas, and
      // the warning banner is not shown instead (exceeded supersedes warning).
      expect(screen.queryByTestId('analytics-panel')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analytics-over-limit-warning')).not.toBeInTheDocument();
    });
  });

  // ── Task 11.3: accessibility pass (R6.6) ──────────────────────────────────
  // Cross-cutting A11Y verification over the page-owned surface: controls are
  // keyboard-navigable, and the degradation/over-limit/error states carry a
  // NON-COLOUR signal (an icon + text), never colour alone. (The view-switch
  // tablist, the pivot set dropdown / Execute / export+mail buttons, and the
  // violin stats-table alternative are covered in their own component tests —
  // MemberAnalyticsPanel.test, MemberPivotViews.test, ViolinChart.test.)
  describe('accessibility pass (task 11.3, R6.6)', () => {
    it('the load-error state carries icon + text (non-colour signal) and a keyboard-focusable retry button', async () => {
      mockRoles = ['Members_Read'];
      mockListMembers.mockRejectedValueOnce(new Error('network'));
      render(<MemberAnalyticsPage />);

      const alert = await screen.findByTestId('analytics-load-error');
      // Non-colour signal: the <AlertIcon> renders an icon element alongside the
      // text, so the error is conveyed by icon + text, not just the red hue.
      expect(alert.querySelector('[data-testid="alert-icon"]')).toBeInTheDocument();
      expect(screen.getByText('analytics.states.loadError')).toBeInTheDocument();

      // The retry affordance is a native, keyboard-navigable button (focusable,
      // Enter/Space activate it natively).
      const retry = screen.getByText('analytics.states.retry').closest('button');
      expect(retry).not.toBeNull();
      retry!.focus();
      expect(retry).toHaveFocus();
    });

    it('the WARNING data-volume banner carries icon + text, not colour alone', async () => {
      mockRoles = ['Members_Read'];
      const payload = syntheticMembers(WARNING_THRESHOLD_BYTES + 50 * 1024);
      mockListMembers.mockResolvedValue(payload as never);

      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      const banner = await screen.findByTestId('analytics-over-limit-warning');
      // Icon + bilingual text — the warning is not signalled by colour alone.
      expect(banner.querySelector('[data-testid="alert-icon"]')).toBeInTheDocument();
      expect(screen.getByText('analytics.overLimit.warning')).toBeInTheDocument();
    });

    it('the EXCEEDED "dataset too large" state carries icon + text, not colour alone', async () => {
      mockRoles = ['Members_Read'];
      const payload = syntheticMembers(LIMIT_BYTES + 100 * 1024);
      mockListMembers.mockResolvedValue(payload as never);

      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      const exceeded = await screen.findByTestId('analytics-over-limit-exceeded');
      expect(exceeded.querySelector('[data-testid="alert-icon"]')).toBeInTheDocument();
      expect(screen.getByText('analytics.overLimit.exceeded')).toBeInTheDocument();
    });

    it('the own filter inputs are keyboard-navigable native inputs with discernible labels', async () => {
      mockRoles = ['Members_Read'];
      render(<MemberAnalyticsPage />);
      await waitForLoaded();

      // Each FilterableHeader exposes a labelled native <input> (accessible name
      // from the resolved field-config label), so the filter controls are
      // reachable + operable by keyboard.
      const nameFilter = screen.getByLabelText('Filter by Naam') as HTMLInputElement;
      expect(nameFilter.tagName).toBe('INPUT');
      nameFilter.focus();
      expect(nameFilter).toHaveFocus();
    });
  });
});
