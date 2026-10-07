/**
 * Component tests for MemberDistributions (analytics/MemberDistributions.tsx).
 *
 * Verifies task 5.1 (R3.1, R3.5, R3.6):
 *   - renders ONE shared ViolinChart per metric (age + years_member) when each
 *     metric has enough parsed points;
 *   - feeds a single UNGROUPED distribution by default (R3.3) — every datum
 *     carries one shared group key, so ViolinChart draws one violin;
 *   - parses string-typed calculated-field values via `toNumber` and SKIPS rows
 *     that don't parse (R3.5), never coercing to zero;
 *   - renders a NEUTRAL empty state (not a chart) for a metric below the minimum
 *     point threshold (R3.6);
 *   - uses the bilingual metric label i18n keys (no hardcoded English);
 *   - is exported from the analytics barrel.
 *
 * Verifies task 5.2 (R3.3, R6.1):
 *   - the group-by selector offers ONLY dimensions DISCOVERED from fieldConfig
 *     (region / membership_type / gender present as fields) — never hardcoded;
 *   - no selector is shown when the config exposes none of the candidates;
 *   - the default is a single UNGROUPED distribution (no groupLabel);
 *   - selecting a dimension produces GROUPED data (one group per distinct value)
 *     and passes the bilingual groupLabel to ViolinChart;
 *   - the selector is a keyboard-accessible combobox with a bilingual aria-label,
 *     and every option label is an i18n key (no hardcoded English).
 *
 * The shared ViolinChart is mocked with a lightweight component that records the
 * props it received, so grouping/label assertions don't load the ~1MB Plotly
 * bundle (mirrors charts/ViolinChart.test.tsx's Plot mock pattern).
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import type { ViolinDatum } from '../../charts';

// Capture every ViolinChart render so we can assert on how many charts render
// and the data/labels each got — without the real Plotly-backed chart.
const chartCalls: Array<{ data: ViolinDatum[]; metricLabel: string; groupLabel?: string }> = [];
vi.mock('../../charts', () => ({
  ViolinChart: function MockViolinChart(props: {
    data: ViolinDatum[];
    metricLabel: string;
    groupLabel?: string;
  }) {
    chartCalls.push({ data: props.data, metricLabel: props.metricLabel, groupLabel: props.groupLabel });
    return (
      <div
        data-testid="mock-violin-chart"
        data-metric-label={props.metricLabel}
        data-group-label={props.groupLabel ?? ''}
        data-point-count={props.data.length}
      />
    );
  },
}));

// Echo i18n keys so assertions are locale-independent (keys prove no hardcoding).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({ t: (key: string) => key }),
}));

import { render, screen, fireEvent } from '@/test-utils';
import MemberDistributions, {
  MIN_DISTRIBUTION_POINTS,
  buildMetricData,
  discoverGroupByDimensions,
} from './MemberDistributions';
import { MemberDistributions as DistributionsFromBarrel } from './index';
import type { Member, MemberRow, FieldConfig, FieldConfigField } from '../../../types/members';

/** Build N rows carrying string-typed `age` and `years_member` values. */
function rowsWithMetrics(ages: unknown[], yearsMember: unknown[]): MemberRow[] {
  const n = Math.max(ages.length, yearsMember.length);
  const rows: MemberRow[] = [];
  for (let i = 0; i < n; i += 1) {
    rows.push({
      member_id: String(i),
      age: ages[i],
      years_member: yearsMember[i],
    } as unknown as MemberRow);
  }
  return rows;
}

/** A field config exposing exactly the given field keys. */
function fieldConfigWithKeys(keys: string[]): FieldConfig {
  return {
    fields: keys.map((key) => ({ key } as FieldConfigField)),
  } as FieldConfig;
}

const emptyFieldConfig = { fields: [] } as unknown as FieldConfig;

function renderDistributions(processedData: MemberRow[], fieldConfig: FieldConfig = emptyFieldConfig) {
  return render(
    <MemberDistributions
      processedData={processedData}
      members={processedData as unknown as Member[]}
      fieldConfig={fieldConfig}
      hasAnalyticsConfig={false}
      language="en"
      capabilities={{ canExport: false }}
    />
  );
}

beforeEach(() => {
  chartCalls.length = 0;
});

describe('MemberDistributions', () => {
  it('is exported from the analytics barrel', () => {
    expect(DistributionsFromBarrel).toBe(MemberDistributions);
  });

  it('renders one chart per metric when both have enough points (R3.1)', () => {
    // Calculated fields are string-typed by the module — pass numeric strings.
    const ages = ['20', '30', '40', '50', '60', '70'];
    const years = ['1', '2', '3', '4', '5', '6'];
    renderDistributions(rowsWithMetrics(ages, years));

    // Two metrics -> two charts.
    expect(screen.getAllByTestId('mock-violin-chart')).toHaveLength(2);
    expect(chartCalls).toHaveLength(2);

    // Each chart carries its bilingual metric-label key (no hardcoded English).
    const labels = chartCalls.map((c) => c.metricLabel);
    expect(labels).toEqual([
      'analytics.distributions.metrics.age',
      'analytics.distributions.metrics.yearsMember',
    ]);
  });

  it('feeds a single ungrouped distribution per metric by default (R3.3)', () => {
    const ages = ['20', '30', '40', '50', '60', '70'];
    const years = ['1', '2', '3', '4', '5', '6'];
    renderDistributions(rowsWithMetrics(ages, years));

    // Age chart: all six values present, one shared group (ungrouped default).
    const ageChart = chartCalls[0];
    expect(ageChart.data).toHaveLength(6);
    expect(ageChart.data.map((d) => d.value)).toEqual([20, 30, 40, 50, 60, 70]);
    const groups = new Set(ageChart.data.map((d) => d.group));
    expect(groups.size).toBe(1); // ungrouped -> exactly one violin
    // No group-by label on the default (grouping is opt-in).
    expect(ageChart.groupLabel).toBeUndefined();
  });

  it('parses numeric strings and skips rows that do not parse (R3.5)', () => {
    // Mix valid numeric strings with absent / non-numeric values that must be
    // skipped (never coerced to 0), leaving >= MIN points so a chart still renders.
    const ages = ['20', '', '30', 'abc', '40', null, '50', undefined, '60'];
    const years = ['1', '2', '3', '4', '5', '6', '7', '8', '9'];
    renderDistributions(rowsWithMetrics(ages, years));

    const ageChart = chartCalls[0];
    // Only the five valid values survive; the four bad inputs are dropped.
    expect(ageChart.data.map((d) => d.value)).toEqual([20, 30, 40, 50, 60]);
  });

  it('renders a neutral empty state for a metric below the point threshold (R3.6)', () => {
    // age has 2 points (< MIN); years_member has enough -> chart.
    const ages = ['20', '30'];
    const years = ['1', '2', '3', '4', '5', '6'];
    renderDistributions(rowsWithMetrics(ages, years));

    // age: neutral empty notice, no chart for it.
    const ageEmpty = screen.getByTestId('distribution-age-empty');
    expect(ageEmpty).toBeInTheDocument();
    expect(ageEmpty).toHaveAttribute('data-notice-kind', 'empty');
    expect(ageEmpty).toHaveTextContent('analytics.states.notEnoughPoints');

    // Exactly one chart rendered (years_member only).
    expect(screen.getAllByTestId('mock-violin-chart')).toHaveLength(1);
    expect(chartCalls).toHaveLength(1);
    expect(chartCalls[0].metricLabel).toBe('analytics.distributions.metrics.yearsMember');
  });

  it('renders empty states for both metrics when the set is empty', () => {
    renderDistributions([]);

    expect(screen.getByTestId('distribution-age-empty')).toBeInTheDocument();
    expect(screen.getByTestId('distribution-years_member-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('mock-violin-chart')).not.toBeInTheDocument();
  });
});

describe('MemberDistributions — group-by selector (task 5.2)', () => {
  // Six rows with region / membership_type / gender so grouping has >= MIN
  // points per metric and distinct group values to split on.
  function groupableRows(): MemberRow[] {
    const ages = ['20', '30', '40', '50', '60', '70'];
    const years = ['1', '2', '3', '4', '5', '6'];
    const regions = ['North', 'South', 'North', 'South', 'North', 'South'];
    const types = ['Regular', 'Regular', 'Student', 'Student', 'Regular', 'Student'];
    const genders = ['F', 'M', 'F', 'M', 'F', 'M'];
    return ages.map(
      (age, i) =>
        ({
          member_id: String(i),
          age,
          years_member: years[i],
          region: regions[i],
          membership_type: types[i],
          gender: genders[i],
        }) as unknown as MemberRow,
    );
  }

  it('shows no selector when the config exposes none of the candidate dimensions (R6.1)', () => {
    renderDistributions(groupableRows(), fieldConfigWithKeys([]));
    expect(screen.queryByTestId('distributions-group-by')).not.toBeInTheDocument();
  });

  it('offers ONLY the dimensions discovered from fieldConfig (R6.1, not hardcoded)', () => {
    // Config exposes region + gender but NOT membership_type.
    renderDistributions(groupableRows(), fieldConfigWithKeys(['region', 'gender']));

    const select = screen.getByRole('combobox', {
      name: 'analytics.distributions.groupBy.label',
    });

    // Option values are: '' (none) + the discovered dimension keys only.
    const values = Array.from(select.querySelectorAll('option')).map((o) => o.getAttribute('value'));
    expect(values).toEqual(['', 'region', 'gender']);

    // membership_type is NOT offered because the config did not expose it.
    expect(values).not.toContain('membership_type');

    // Option labels are i18n keys (no hardcoded English).
    const labels = Array.from(select.querySelectorAll('option')).map((o) => o.textContent);
    expect(labels).toEqual([
      'analytics.distributions.groupBy.none',
      'analytics.distributions.groupBy.region',
      'analytics.distributions.groupBy.gender',
    ]);
  });

  it('defaults to an ungrouped distribution (R3.3)', () => {
    renderDistributions(groupableRows(), fieldConfigWithKeys(['region']));

    // Default selection is the ungrouped sentinel ('').
    const select = screen.getByRole('combobox', {
      name: 'analytics.distributions.groupBy.label',
    }) as HTMLSelectElement;
    expect(select.value).toBe('');

    // Each chart gets one shared group and no groupLabel.
    const ageChart = chartCalls[0];
    expect(new Set(ageChart.data.map((d) => d.group)).size).toBe(1);
    expect(ageChart.groupLabel).toBeUndefined();
  });

  it('produces grouped data and a bilingual groupLabel when a dimension is selected (R3.3)', () => {
    renderDistributions(groupableRows(), fieldConfigWithKeys(['region', 'membership_type', 'gender']));

    const select = screen.getByRole('combobox', {
      name: 'analytics.distributions.groupBy.label',
    });

    // Reset captures from the initial (ungrouped) render, then select region.
    chartCalls.length = 0;
    fireEvent.change(select, { target: { value: 'region' } });

    // Both metrics re-rendered grouped by region (two distinct values).
    const ageChart = chartCalls.find((c) => c.metricLabel === 'analytics.distributions.metrics.age');
    expect(ageChart).toBeDefined();
    expect(new Set(ageChart!.data.map((d) => d.group))).toEqual(new Set(['North', 'South']));

    // Bilingual group label passed through (the region option's i18n key).
    expect(ageChart!.groupLabel).toBe('analytics.distributions.groupBy.region');
  });
});

describe('discoverGroupByDimensions', () => {
  it('returns [] for a null or fieldless config', () => {
    expect(discoverGroupByDimensions(null)).toEqual([]);
    expect(discoverGroupByDimensions({} as FieldConfig)).toEqual([]);
  });

  it('keeps only candidate dimensions present in the config, in canonical order', () => {
    // Config lists gender before region, plus an unrelated field — output order
    // follows the canonical candidate order (region, membership_type, gender).
    const config = fieldConfigWithKeys(['gender', 'email', 'region']);
    expect(discoverGroupByDimensions(config).map((d) => d.key)).toEqual(['region', 'gender']);
  });
});

describe('buildMetricData', () => {
  it('tags every parsed value with one shared group when ungrouped, skipping bad rows', () => {
    const rows = [
      { age: '10' },
      { age: 'x' },
      { age: '20' },
      { age: null },
      { age: 30 },
    ] as unknown as Record<string, unknown>[];

    const data = buildMetricData(rows, 'age');
    expect(data.map((d) => d.value)).toEqual([10, 20, 30]);
    expect(new Set(data.map((d) => d.group)).size).toBe(1);
  });

  it('tags each value with its group-by value when a group key is given (R3.3)', () => {
    const rows = [
      { age: '10', region: 'North' },
      { age: '20', region: 'South' },
      { age: '30', region: 'North' },
      { age: 'x', region: 'South' }, // skipped (non-numeric), not grouped
    ] as unknown as Record<string, unknown>[];

    const data = buildMetricData(rows, 'age', 'region');
    expect(data).toEqual([
      { group: 'North', value: 10 },
      { group: 'South', value: 20 },
      { group: 'North', value: 30 },
    ]);
  });

  it('falls back to a neutral group for rows with an absent/blank group value', () => {
    const rows = [
      { age: '10', region: 'North' },
      { age: '20', region: '' },
      { age: '30' },
    ] as unknown as Record<string, unknown>[];

    const data = buildMetricData(rows, 'age', 'region');
    expect(data.map((d) => d.group)).toEqual(['North', '—', '—']);
  });

  it('exposes a sane minimum-point threshold', () => {
    expect(MIN_DISTRIBUTION_POINTS).toBeGreaterThan(1);
  });

  // Findings F-005: calculated metrics are enriched under their STORAGE bucket
  // (`personal.age`, `membership.years_member`), NOT a flat top-level alias. The
  // flat `row['age']` read resolved undefined for every row → "not enough data".
  // With the field config supplying the group, buildMetricData must read the
  // NESTED value via valueFor.
  it('reads the metric from its NESTED storage bucket when the config gives a group (F-005)', () => {
    const rows = [
      { member_id: '1', personal: { age: '20' } },
      { member_id: '2', personal: { age: '30' } },
      { member_id: '3', personal: { age: 'x' } }, // skipped
      { member_id: '4', personal: { age: '40' } },
    ] as unknown as MemberRow[];
    const config = {
      fields: [{ key: 'age', group: 'personal', origin: 'calculated' } as FieldConfigField],
    } as FieldConfig;

    const data = buildMetricData(rows, 'age', null, config);
    // Previously (flat read) this was [] → wrongly "not enough data".
    expect(data.map((d) => d.value)).toEqual([20, 30, 40]);
  });

  it('reads a NESTED group-by dimension via valueFor too (F-005)', () => {
    const rows = [
      { member_id: '1', membership: { years_member: '5' }, personal: { gender: 'F' } },
      { member_id: '2', membership: { years_member: '6' }, personal: { gender: 'M' } },
      { member_id: '3', membership: { years_member: '7' }, personal: { gender: 'F' } },
    ] as unknown as MemberRow[];
    const config = {
      fields: [
        { key: 'years_member', group: 'membership', origin: 'calculated' } as FieldConfigField,
        { key: 'gender', group: 'personal', origin: 'fixed' } as FieldConfigField,
      ],
    } as FieldConfig;

    const data = buildMetricData(rows, 'years_member', 'gender', config);
    expect(data).toEqual([
      { group: 'F', value: 5 },
      { group: 'M', value: 6 },
      { group: 'F', value: 7 },
    ]);
  });
});
