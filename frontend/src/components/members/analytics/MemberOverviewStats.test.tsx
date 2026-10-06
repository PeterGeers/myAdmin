/**
 * Component tests for MemberOverviewStats (the Member Analytics Overview summary).
 *
 * Verifies task 4.1 (R2.1, R2.2, R2.4, R2.5, R6.7):
 *   - the count / avg-age / avg-years-member cards are present when their
 *     calculated fields resolve, computed over `processedData`;
 *   - a card is OMITTED (never NaN) when its calculated field is absent from the
 *     field config (R2.5), while the others still render;
 *   - averages are over present values only, and an excluded-count is surfaced
 *     when rows have absent/invalid inputs (R2.3);
 *   - the figures recompute live when `processedData` changes (R2.2 / R6.7);
 *   - the component is exported from the analytics barrel.
 *
 * i18n is echoed (keys returned verbatim) so assertions are locale-independent
 * and we prove the component uses the bilingual keys rather than hardcoded
 * English (R2.4).
 */
import { vi, describe, it, expect } from 'vitest';
import React from 'react';

// Echo i18n keys (and the excluded-count interpolation) so assertions are
// locale-independent — proves no hardcoded English (R2.4). The excluded-count
// echoes BOTH the count and the total (denominator) so the test can assert the
// figure is interpretable ("N of M excluded"), not just a bare count (R2.3).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && 'count' in opts && 'total' in opts) {
        return `${key}:${opts.count}/${opts.total}`;
      }
      if (opts && 'count' in opts) {
        return `${key}:${opts.count}`;
      }
      return key;
    },
  }),
}));

import { render, screen } from '@/test-utils';
import MemberOverviewStats from './MemberOverviewStats';
import { MemberOverviewStats as FromBarrel } from './index';
import type { FieldConfig, MemberRow } from '../../../types/members';
import type { MemberAnalyticsAreaProps } from './areas/types';

/** A field config that exposes both calculated metrics. */
const fullFieldConfig = {
  fields: [
    { key: 'age', origin: 'calculated', label: { nl: 'Leeftijd', en: 'Age' } },
    {
      key: 'years_member',
      origin: 'calculated',
      label: { nl: 'Lidjaren', en: 'Years-member' },
    },
  ],
} as unknown as FieldConfig;

function makeProps(
  processedData: MemberRow[],
  fieldConfig: FieldConfig | null = fullFieldConfig,
): MemberAnalyticsAreaProps {
  return {
    processedData,
    members: processedData,
    fieldConfig,
    hasAnalyticsConfig: true,
    language: 'en',
    capabilities: { canExport: false },
  };
}

const rows = [
  { member_id: 'a', age: '40', years_member: '10' },
  { member_id: 'b', age: '50', years_member: '20' },
] as unknown as MemberRow[];

describe('MemberOverviewStats', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberOverviewStats);
  });

  it('renders count, avg age and avg years-member cards over processedData', () => {
    render(<MemberOverviewStats {...makeProps(rows)} />);

    // Count = number of filtered rows (R2.1).
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('2');
    // Mean age over the two present values (40, 50) → 45.0 (R2.1).
    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('45.0');
    // Mean years-member (10, 20) → 15.0.
    expect(screen.getByTestId('overview-stat-avg-years-member-value')).toHaveTextContent(
      '15.0'
    );
    // Bilingual stat titles use the 0.3 i18n keys (no hardcoded English, R2.4).
    expect(screen.getByText('analytics.overview.stats.count')).toBeInTheDocument();
    expect(screen.getByText('analytics.overview.stats.avgAge')).toBeInTheDocument();
    expect(
      screen.getByText('analytics.overview.stats.avgYearsMember')
    ).toBeInTheDocument();
  });

  it('omits a card (never NaN) when its calculated field is absent (R2.5)', () => {
    // Field config exposes only `age`; `years_member` is absent.
    const ageOnly = {
      fields: [{ key: 'age', origin: 'calculated', label: { en: 'Age' } }],
    } as unknown as FieldConfig;

    render(<MemberOverviewStats {...makeProps(rows, ageOnly)} />);

    // Count + avg age present; avg years-member card omitted gracefully.
    expect(screen.getByTestId('overview-stat-count')).toBeInTheDocument();
    expect(screen.getByTestId('overview-stat-avg-age')).toBeInTheDocument();
    expect(
      screen.queryByTestId('overview-stat-avg-years-member')
    ).not.toBeInTheDocument();
    // Definitely no stray NaN anywhere.
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it('does not treat a calculated metric sourced from a fixed field as the metric', () => {
    // `age` present but as a FIXED field → not the calculated metric (R2.5).
    const fixedAge = {
      fields: [{ key: 'age', origin: 'fixed', label: { en: 'Age' } }],
    } as unknown as FieldConfig;

    render(<MemberOverviewStats {...makeProps(rows, fixedAge)} />);
    expect(screen.queryByTestId('overview-stat-avg-age')).not.toBeInTheDocument();
    // Count still renders.
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('2');
  });

  it('averages present values only and surfaces an excluded-count (R2.3)', () => {
    const mixed = [
      { member_id: 'a', age: '30', years_member: '5' },
      { member_id: 'b', age: '', years_member: '15' }, // age absent → excluded
      { member_id: 'c', age: 'abc', years_member: '25' }, // age invalid → excluded
    ] as unknown as MemberRow[];

    render(<MemberOverviewStats {...makeProps(mixed)} />);

    // Only the single valid age (30) is averaged → 30.0, not coerced to 0.
    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('30.0');
    // Two of the three rows excluded from the age average — surfaced with the
    // denominator so the figure is interpretable (R2.3: "2 of 3 excluded").
    expect(screen.getByTestId('overview-stat-avg-age-excluded')).toHaveTextContent(
      'analytics.overview.excludedCount:2/3'
    );
    // Count is still all three rows.
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('3');
  });

  it('surfaces the excluded-count only where it aids interpretation — hidden when zero (R2.3)', () => {
    // Every row has a valid age and years_member → nothing is excluded, so the
    // excluded help line is NOT rendered on either average card.
    render(<MemberOverviewStats {...makeProps(rows)} />);

    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('45.0');
    expect(
      screen.queryByTestId('overview-stat-avg-age-excluded')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('overview-stat-avg-years-member-excluded')
    ).not.toBeInTheDocument();
  });

  it('ties the excluded-count to its card for assistive tech (color not the sole signal)', () => {
    const mixed = [
      { member_id: 'a', age: '30', years_member: '5' },
      { member_id: 'b', age: '', years_member: '15' }, // age excluded
    ] as unknown as MemberRow[];

    render(<MemberOverviewStats {...makeProps(mixed)} />);

    // The help line is rendered as TEXT (not conveyed by colour alone) …
    const help = screen.getByTestId('overview-stat-avg-age-excluded');
    expect(help).toHaveTextContent('analytics.overview.excludedCount:1/2');
    // … and is programmatically associated with its card via aria-describedby,
    // so a screen reader reads the exclusion as context for the figure.
    const card = screen.getByTestId('overview-stat-avg-age');
    expect(card).toHaveAttribute('aria-describedby', help.id);
    expect(help.id).toBeTruthy();
  });

  it('recomputes the excluded-count live when processedData changes (R2.2 / R2.3)', () => {
    // Start: no exclusions (both ages valid) → no excluded line.
    const clean = [
      { member_id: 'a', age: '40', years_member: '10' },
      { member_id: 'b', age: '50', years_member: '20' },
    ] as unknown as MemberRow[];
    const { rerender } = render(<MemberOverviewStats {...makeProps(clean)} />);

    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('45.0');
    expect(
      screen.queryByTestId('overview-stat-avg-age-excluded')
    ).not.toBeInTheDocument();

    // A filter change swaps in a dataset where one of three rows has an invalid
    // age: count, the average AND the excluded-count all re-derive together.
    const filtered = [
      { member_id: 'a', age: '20', years_member: '2' },
      { member_id: 'b', age: '40', years_member: '4' },
      { member_id: 'c', age: 'n/a', years_member: '6' }, // age invalid → excluded
    ] as unknown as MemberRow[];
    rerender(<MemberOverviewStats {...makeProps(filtered)} />);

    // Count = 3 (all rows), average over the two valid ages (20, 40) = 30.0,
    // excluded-count = 1 of 3 — all three figures reflect the new processedData.
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('3');
    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('30.0');
    expect(screen.getByTestId('overview-stat-avg-age-excluded')).toHaveTextContent(
      'analytics.overview.excludedCount:1/3'
    );
  });

  it('recomputes figures live when processedData changes (R2.2 / R6.7)', () => {
    const { rerender } = render(<MemberOverviewStats {...makeProps(rows)} />);
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('2');
    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('45.0');

    // Simulate a filter change narrowing the dataset to one row.
    const narrowed = [
      { member_id: 'a', age: '60', years_member: '30' },
    ] as unknown as MemberRow[];
    rerender(<MemberOverviewStats {...makeProps(narrowed)} />);

    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('1');
    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('60.0');
    expect(screen.getByTestId('overview-stat-avg-years-member-value')).toHaveTextContent(
      '30.0'
    );
  });

  it('omits both averages but keeps count when no calculated metrics resolve', () => {
    const noMetrics = { fields: [] } as unknown as FieldConfig;
    render(<MemberOverviewStats {...makeProps(rows, noMetrics)} />);

    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('2');
    expect(screen.queryByTestId('overview-stat-avg-age')).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('overview-stat-avg-years-member')
    ).not.toBeInTheDocument();
  });

  // Findings F-003: real member rows keep calculated fields in their NESTED
  // storage bucket (`personal.age`, `membership.years_member`), NOT a flat
  // top-level alias. The old `row['age']` read resolved undefined for every row,
  // so `mean([])` → null and BOTH average cards were wrongly omitted (only the
  // count showed). With the config supplying each field's `group`, the averages
  // must resolve from the nested value via valueFor.
  // Findings F-004 / R2.1 MAY: a per-membership-type breakdown in the Overview.
  it('shows a per-membership-type breakdown when the field resolves (F-004)', () => {
    const cfg = {
      fields: [
        { key: 'age', origin: 'calculated', label: { en: 'Age' } },
        { key: 'membership_type', origin: 'fixed', label: { nl: 'Type', en: 'Membership type' } },
      ],
    } as unknown as FieldConfig;
    const typedRows = [
      { member_id: 'a', age: '30', membership_type: 'Gold' },
      { member_id: 'b', age: '40', membership_type: 'Gold' },
      { member_id: 'c', age: '50', membership_type: 'Silver' },
      { member_id: 'd', age: '60' }, // no type → neutral bucket
    ] as unknown as MemberRow[];

    render(<MemberOverviewStats {...makeProps(typedRows, cfg)} />);

    const breakdown = screen.getByTestId('overview-members-by-type');
    expect(breakdown).toBeInTheDocument();
    // Gold (2) sorts before Silver (1) before the neutral bucket (1, label '—').
    expect(screen.getByTestId('overview-members-by-type-row-Gold')).toHaveTextContent('Gold');
    expect(screen.getByTestId('overview-members-by-type-row-Gold')).toHaveTextContent('2');
    expect(screen.getByTestId('overview-members-by-type-row-Silver')).toHaveTextContent('1');
    // Heading uses the bilingual i18n key (no hardcoded English).
    expect(screen.getByText('analytics.overview.stats.membersPerType')).toBeInTheDocument();
  });

  it('omits the membership-type breakdown when the field is absent (R2.5)', () => {
    // fullFieldConfig exposes only age + years_member, no membership_type.
    render(<MemberOverviewStats {...makeProps(rows)} />);
    expect(screen.queryByTestId('overview-members-by-type')).not.toBeInTheDocument();
  });

  it('reads calculated averages from the NESTED storage bucket via the config group (F-003)', () => {
    const nestedRows = [
      { member_id: 'a', personal: { age: '40' }, membership: { years_member: '10' } },
      { member_id: 'b', personal: { age: '50' }, membership: { years_member: '20' } },
    ] as unknown as MemberRow[];
    const nestedConfig = {
      fields: [
        { key: 'age', group: 'personal', origin: 'calculated', label: { en: 'Age' } },
        {
          key: 'years_member',
          group: 'membership',
          origin: 'calculated',
          label: { en: 'Years-member' },
        },
      ],
    } as unknown as FieldConfig;

    render(<MemberOverviewStats {...makeProps(nestedRows, nestedConfig)} />);

    // Previously these cards were omitted (null averages); now they resolve.
    expect(screen.getByTestId('overview-stat-avg-age-value')).toHaveTextContent('45.0');
    expect(screen.getByTestId('overview-stat-avg-years-member-value')).toHaveTextContent(
      '15.0',
    );
    expect(screen.getByTestId('overview-stat-count-value')).toHaveTextContent('2');
  });
});
