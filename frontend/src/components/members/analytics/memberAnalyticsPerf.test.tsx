/**
 * Cross-cutting memoization / performance pass for Member Analytics (task 11.2).
 *
 * This is a VERIFICATION test, not a new feature. It guards the three
 * performance claims the design pins to the analytics surface so an accidental
 * regression (a missing `useMemo`, an O(n^2) aggregation, an eagerly-mounted
 * inactive area) is caught by CI rather than discovered in the field:
 *
 *   1. Overview renders < ~1s after the rows load (R6.7 / design C2). We measure
 *      the Overview aggregation over a few-thousand-row synthetic `processedData`
 *      and assert it completes well under the budget. We ALSO assert the memo is
 *      stable: an unrelated prop change (same `processedData` REFERENCE) does NOT
 *      recompute the aggregation, and a new `processedData` reference DOES — the
 *      `useMemo` keyed on `processedData` is doing its job (R2.2).
 *
 *   2. Filter re-derive is cheap (< ~100ms beyond the debounce) (R7.6 / design
 *      C2–C4). We measure the pure aggregation path the areas use on every filter
 *      change — `mean` / `countExcluded` (Overview) and `executeMemberPivot`
 *      (Pivot Views) — over a few-thousand-row set and assert each completes well
 *      under the budget. Measuring the PURE functions keeps the timing
 *      deterministic (no React render/jsdom noise).
 *
 *   3. Only the VISIBLE area recomputes on a filter change (R1.6 / design C1).
 *      `MemberAnalyticsPanel` lazy-mounts ONE area at a time, so an inactive area
 *      is not in the tree and literally cannot recompute. We assert that changing
 *      `processedData` (a filter change) re-renders the active area but never
 *      mounts an inactive one.
 *
 * Thresholds are deliberately GENEROUS — the point is to catch a quadratic blow-up
 * or a dropped memo, not to microbenchmark. A correct linear pass over a few
 * thousand rows finishes in single-digit milliseconds; the budgets below are
 * orders of magnitude above that so the test is not CI-flaky.
 *
 * All data is synthetic (generated in-test). No production data, no I/O.
 *
 * @see .kiro/specs/Members/member-analytics (design C2/C3/C4; R6.7, R7.6, R1.6)
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// ---------------------------------------------------------------------------
// Timing budgets (generous — regression guard, not a microbenchmark).
// ---------------------------------------------------------------------------

/** Rows in the synthetic set — "a few thousand", the design's working ceiling. */
const ROW_COUNT = 4000;

/**
 * Overview aggregation budget. The spec says the Overview renders < ~1s after
 * rows load (R6.7). We measure just the aggregation (not the full jsdom render)
 * and allow a very generous 250ms — a linear pass over 4k rows is ~1ms, so this
 * only trips on an accidental O(n^2) or a parse blow-up.
 */
const OVERVIEW_AGG_BUDGET_MS = 250;

/**
 * Filter re-derive budget (R7.6): < ~100ms beyond the debounce. We measure the
 * pure helpers the areas call on every filter change. A linear derive over 4k
 * rows is a few ms; 100ms is the spec budget and comfortably clears real work.
 */
const REDERIVE_BUDGET_MS = 100;

// ---------------------------------------------------------------------------
// Synthetic data — a few thousand near-realistic member rows.
// ---------------------------------------------------------------------------

import type { FieldConfig, Member, MemberRow } from '../../../types/members';
import type { PivotConfig } from '../../../types/pivot';
import { mean, countExcluded } from './memberAggregations';
import { executeMemberPivot } from './memberPivotAdapter';

const REGIONS = ['Noord', 'Oost', 'Zuid', 'West', 'Midden'];
const TYPES = ['regular', 'student', 'senior', 'family', 'honorary'];

/**
 * Build `n` synthetic member rows. `age` / `years_member` are string-typed
 * (as the Members module serializes its calculated fields), with a sprinkling of
 * absent/invalid values so the excluded-count path is exercised too.
 */
function makeRows(n: number): MemberRow[] {
  const rows: MemberRow[] = [];
  for (let i = 0; i < n; i += 1) {
    // ~5% of rows carry an absent/invalid age so exclusion logic runs.
    const badAge = i % 20 === 0;
    rows.push({
      member_id: `m-${i}`,
      age: badAge ? (i % 40 === 0 ? '' : 'n/a') : String(20 + (i % 60)),
      years_member: String(1 + (i % 45)),
      region: REGIONS[i % REGIONS.length],
      membership_type: TYPES[i % TYPES.length],
    } as unknown as MemberRow);
  }
  return rows;
}

/** Field config exposing both calculated metrics (so both Overview cards render). */
const fieldConfig = {
  fields: [
    { key: 'age', origin: 'calculated', label: { nl: 'Leeftijd', en: 'Age' } },
    { key: 'years_member', origin: 'calculated', label: { nl: 'Lidjaren', en: 'Years-member' } },
    { key: 'region', origin: 'variable', group: undefined, label: { nl: 'Regio', en: 'Region' } },
    {
      key: 'membership_type',
      origin: 'fixed',
      group: undefined,
      label: { nl: 'Type', en: 'Type' },
    },
  ],
} as unknown as FieldConfig;

/** Time a synchronous callback in milliseconds (monotonic clock). */
function timeMs(fn: () => void): number {
  const start = performance.now();
  fn();
  return performance.now() - start;
}

// ===========================================================================
// 2. Filter re-derive is cheap — pure functions, deterministic timing (R7.6).
// ===========================================================================

describe('Member Analytics perf — filter re-derive is cheap (R7.6)', () => {
  const rows = makeRows(ROW_COUNT);

  it(`Overview aggregation over ${ROW_COUNT} rows completes under the budget`, () => {
    const ages = rows.map((r) => r.age);
    const years = rows.map((r) => r.years_member);

    let avgAge: number | null = null;
    let excluded = 0;
    const elapsed = timeMs(() => {
      // The exact work MemberOverviewStats does inside its memo.
      avgAge = mean(ages);
      excluded = countExcluded(ages);
      mean(years);
      countExcluded(years);
    });

    // Sanity: the aggregation actually produced the figures (not short-circuited).
    expect(avgAge).not.toBeNull();
    expect(excluded).toBeGreaterThan(0); // ~5% of rows carry an absent/invalid age
    expect(elapsed).toBeLessThan(OVERVIEW_AGG_BUDGET_MS);
  });

  it(`executeMemberPivot (aggregate) over ${ROW_COUNT} rows re-derives under ~100ms`, () => {
    const config: PivotConfig = {
      dataSource: 'members',
      groupColumns: ['membership_type'],
      aggregateMeasures: [
        { function: 'COUNT', column: '*' },
        { function: 'AVG', column: 'years_member' },
      ],
      filters: {},
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };

    let rowCount = -1;
    const elapsed = timeMs(() => {
      const result = executeMemberPivot(rows, config, fieldConfig);
      rowCount = result.row_count;
    });

    // One result row per membership type → bounded, correct grouping.
    expect(rowCount).toBe(TYPES.length);
    expect(elapsed).toBeLessThan(REDERIVE_BUDGET_MS);
  });

  it(`executeMemberPivot (filtered list) over ${ROW_COUNT} rows re-derives under ~100ms`, () => {
    const config: PivotConfig = {
      dataSource: 'members',
      groupColumns: [],
      aggregateMeasures: [],
      filters: {},
      columnPivot: null,
      columnNestLevels: [],
      displayMode: 'flat',
    };

    let rowCount = -1;
    const elapsed = timeMs(() => {
      const result = executeMemberPivot(rows, config, fieldConfig);
      rowCount = result.row_count;
    });

    // Filtered-list mode is one output row per input member (no widening/dropping).
    expect(rowCount).toBe(ROW_COUNT);
    expect(elapsed).toBeLessThan(REDERIVE_BUDGET_MS);
  });
});

// ===========================================================================
// 1. Overview memo: stable across unrelated re-render, recomputes on new data.
// ===========================================================================

describe('Member Analytics perf — Overview memoization + render budget (R6.7, R2.2)', () => {
  // Spy on the aggregation so we can PROVE the memo gates recomputation. We spy
  // on the module the component imports from, so a call means the memo re-ran.
  it('renders under ~1s and the memo recomputes only on a new processedData reference', async () => {
    const aggMod = await import('./memberAggregations');
    const meanSpy = vi.spyOn(aggMod, 'mean');
    const excludedSpy = vi.spyOn(aggMod, 'countExcluded');

    // Import AFTER spying so the component binds the spied exports.
    const { render, screen } = await import('@/test-utils');
    const { default: MemberOverviewStats } = await import('./MemberOverviewStats');

    const rows = makeRows(ROW_COUNT);

    const baseProps = {
      members: rows as unknown as Member[],
      fieldConfig,
      hasAnalyticsConfig: true,
      language: 'en',
      capabilities: { canExport: false },
    };

    // (a) Initial render over 4k rows is well under the ~1s budget (R6.7).
    const start = performance.now();
    const { rerender } = render(
      <MemberOverviewStats processedData={rows} {...baseProps} />,
    );
    // The count card is always rendered — wait for the first paint.
    await screen.findByTestId('overview-stat-count-value');
    const renderMs = performance.now() - start;
    expect(renderMs).toBeLessThan(1000);

    // Figures are correct over the big set (both average cards present).
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent(
      String(ROW_COUNT),
    );
    expect(screen.getByTestId('overview-stat-avg-age-value')).toBeInTheDocument();

    const callsAfterInitial = meanSpy.mock.calls.length;
    expect(callsAfterInitial).toBeGreaterThan(0); // the memo ran at least once

    // (b) Unrelated prop change, SAME processedData reference → memo must NOT
    // recompute. Changing `language` re-renders but the memo is keyed on
    // processedData + resolved fields, so the aggregation does not re-run.
    excludedSpy.mockClear();
    meanSpy.mockClear();
    rerender(<MemberOverviewStats processedData={rows} {...baseProps} language="nl" />);
    await screen.findByTestId('overview-stat-count-value');
    expect(meanSpy).not.toHaveBeenCalled();
    expect(excludedSpy).not.toHaveBeenCalled();

    // (c) New processedData reference (a filter change) → memo MUST recompute.
    const narrowed = rows.slice(0, ROW_COUNT / 2);
    meanSpy.mockClear();
    rerender(<MemberOverviewStats processedData={narrowed} {...baseProps} language="nl" />);
    await screen.findByTestId('overview-stat-count-value');
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent(
      String(ROW_COUNT / 2),
    );
    expect(meanSpy).toHaveBeenCalled();

    meanSpy.mockRestore();
    excludedSpy.mockRestore();
  });
});

// ===========================================================================
// 3. Only the VISIBLE area recomputes on a filter change (R1.6).
// ===========================================================================

// Record each area mount + each render so we can prove an inactive area never
// mounts (so it cannot recompute) when processedData changes.
const mounts: string[] = [];
const renders: Record<string, number> = {};

function makeAreaMock(name: string) {
  return {
    default: function MockArea(props: any) {
      renders[name] = (renders[name] ?? 0) + 1;
      React.useEffect(() => {
        mounts.push(name);
      }, []);
      return (
        <div data-testid={`mock-area-${name}`} data-row-count={props.processedData?.length}>
          {name}
        </div>
      );
    },
  };
}

vi.mock('./areas/OverviewArea', () => makeAreaMock('overview'));
vi.mock('./areas/DistributionsArea', () => makeAreaMock('distributions'));
vi.mock('./areas/PivotViewsArea', () => makeAreaMock('pivotViews'));

vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

describe('Member Analytics perf — only the visible area recomputes on filter change (R1.6)', () => {
  beforeEach(() => {
    mounts.length = 0;
    for (const key of Object.keys(renders)) delete renders[key];
  });

  it('a filter change (new processedData) re-renders only the active area; inactive areas never mount', async () => {
    const { render, screen } = await import('@/test-utils');
    const { default: MemberAnalyticsPanel } = await import('./MemberAnalyticsPanel');

    const members = makeRows(ROW_COUNT) as unknown as Member[];
    const first = makeRows(ROW_COUNT);

    const { rerender } = render(
      <MemberAnalyticsPanel
        processedData={first}
        members={members}
        fieldConfig={fieldConfig}
        hasAnalyticsConfig
        language="en"
        capabilities={{ canExport: true }}
      />,
    );

    // Only Overview (the default landing area) is mounted — inactive areas are
    // not in the tree, so they cannot compute (R1.6).
    await screen.findByTestId('mock-area-overview');
    expect(mounts).toEqual(['overview']);
    expect(screen.queryByTestId('mock-area-distributions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mock-area-pivotViews')).not.toBeInTheDocument();

    const overviewRendersBefore = renders.overview;

    // A filter change hands the panel a NEW processedData reference.
    const filtered = makeRows(ROW_COUNT / 2);
    rerender(
      <MemberAnalyticsPanel
        processedData={filtered}
        members={members}
        fieldConfig={fieldConfig}
        hasAnalyticsConfig
        language="en"
        capabilities={{ canExport: true }}
      />,
    );

    // The active (Overview) area re-rendered with the new row count …
    await screen.findByTestId('mock-area-overview');
    expect(renders.overview).toBeGreaterThan(overviewRendersBefore);
    expect(screen.getByTestId('mock-area-overview')).toHaveAttribute(
      'data-row-count',
      String(ROW_COUNT / 2),
    );

    // … and the inactive areas STILL never mounted — the filter change could not
    // have triggered a recompute in an area that isn't in the tree (R1.6).
    expect(mounts).toEqual(['overview']);
    expect(renders.distributions).toBeUndefined();
    expect(renders.pivotViews).toBeUndefined();
  });
});
