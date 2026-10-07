/**
 * Component tests for the generic shared ViolinChart (charts/ViolinChart.tsx).
 *
 * Verifies the extracted violin component (spec `.kiro/specs/Members/member-analytics`
 * task 2.1; R3.2/R3.3/R3.4/R6.6):
 *   - groups `ViolinDatum[]` by `group` and renders one violin trace per group;
 *   - renders through the shared PlotlyChart Plot factory (mocked here, lazy + Suspense);
 *   - ALWAYS renders the quartile stats table when `showStats !== false` (R6.6);
 *   - hides the stats table only when `showStats={false}`;
 *   - renders a neutral empty state for empty data;
 *   - is exported from the charts barrel.
 */
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

// Mock Plotly: capture the traces handed to the Plot factory so we can assert on
// grouping without loading the ~1MB Plotly bundle. Matches the project's existing
// PlotlyChart mock pattern.
const plotCalls: any[] = [];
vi.mock('../PlotlyChart', () => ({
  default: function MockPlot(props: any) {
    plotCalls.push(props);
    return (
      <div data-testid="plotly-chart" data-trace-count={props.data?.length ?? 0} />
    );
  },
}));

// Mock the translation hook to echo keys, so assertions are stable regardless of
// locale content.
vi.mock('../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

import { render, screen, waitFor } from '@/test-utils';
import ViolinChart, { type ViolinDatum } from './ViolinChart';
import { ViolinChart as ViolinChartFromBarrel } from './index';

// A fixed dataset with hand-computable quartiles per group.
// group "A": [10,20,30,40,50,60,70,80] -> count 8, min 10, q1 30, median 45,
//            mean 45.0, q3 70, max 80, range 70.0
// group "B": [5] -> count 1, min 5, q1 5, median 5, mean 5.0, q3 5, max 5, range 0.0
const sampleData: ViolinDatum[] = [
  { group: 'A', value: 10 },
  { group: 'A', value: 20 },
  { group: 'A', value: 30 },
  { group: 'A', value: 40 },
  { group: 'A', value: 50 },
  { group: 'A', value: 60 },
  { group: 'A', value: 70 },
  { group: 'A', value: 80 },
  { group: 'B', value: 5 },
];

beforeEach(() => {
  plotCalls.length = 0;
});

describe('ViolinChart (shared, generic)', () => {
  it('is exported from the charts barrel', () => {
    expect(ViolinChartFromBarrel).toBe(ViolinChart);
  });

  it('renders one violin trace per group via the shared Plot factory', async () => {
    render(<ViolinChart data={sampleData} metricLabel="Age" groupLabel="Region" />);

    await waitFor(() => {
      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument();
    });

    // Two groups (A, B) => two traces.
    const lastCall = plotCalls[plotCalls.length - 1];
    expect(lastCall.data).toHaveLength(2);
    expect(lastCall.data.every((trace: any) => trace.type === 'violin')).toBe(true);
    // Groups sorted alphabetically: A then B.
    expect(lastCall.data.map((trace: any) => trace.name)).toEqual(['A', 'B']);
    // Trace y-values are the grouped values.
    expect(lastCall.data[0].y).toEqual([10, 20, 30, 40, 50, 60, 70, 80]);
    expect(lastCall.data[1].y).toEqual([5]);
  });

  it('always renders the quartile stats table by default (R6.6)', async () => {
    render(<ViolinChart data={sampleData} metricLabel="Age" groupLabel="Region" />);

    await waitFor(() => {
      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument();
    });

    // One header row + two data rows.
    const rows = document.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);

    // Group A row carries the computed quartiles.
    const groupARow = Array.from(rows).find((r) => r.textContent?.startsWith('A'));
    expect(groupARow).toBeDefined();
    const aCells = Array.from(groupARow!.querySelectorAll('td')).map(
      (c) => c.textContent
    );
    // [name, count, min, q1, median, mean(.1), q3, max, range(.1)]
    expect(aCells).toEqual(['A', '8', '10', '30', '45', '45.0', '70', '80', '70.0']);

    // Group B single-element row.
    const groupBRow = Array.from(rows).find((r) => r.textContent?.startsWith('B'));
    const bCells = Array.from(groupBRow!.querySelectorAll('td')).map(
      (c) => c.textContent
    );
    expect(bCells).toEqual(['B', '1', '5', '5', '5', '5.0', '5', '5', '0.0']);
  });

  it('presents the stats table as the non-visual alternative WHENEVER the chart renders (R6.6)', async () => {
    render(<ViolinChart data={sampleData} metricLabel="Age" groupLabel="Region" />);

    // The chart renders…
    await waitFor(() => {
      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument();
    });
    // …so its non-visual alternative — the quartile stats table — MUST be
    // present alongside it (not optional): the default omits `showStats`, so the
    // table is there. Every group the chart plots has a corresponding table row.
    const plottedGroups = plotCalls[plotCalls.length - 1].data.length;
    expect(document.querySelector('table')).toBeInTheDocument();
    expect(document.querySelectorAll('tbody tr')).toHaveLength(plottedGroups);
  });

  it('hides the stats table when showStats is false', async () => {
    render(
      <ViolinChart
        data={sampleData}
        metricLabel="Age"
        groupLabel="Region"
        showStats={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('plotly-chart')).toBeInTheDocument();
    });

    expect(document.querySelectorAll('tbody tr')).toHaveLength(0);
  });

  it('renders a neutral empty state for empty data', () => {
    render(<ViolinChart data={[]} metricLabel="Age" />);

    // No chart, no stats table — just the no-data message key.
    expect(screen.queryByTestId('plotly-chart')).not.toBeInTheDocument();
    expect(screen.getByText('charts.noData')).toBeInTheDocument();
  });
});
