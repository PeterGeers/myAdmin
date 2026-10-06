/**
 * MemberDistributions — the Distributions / Violins content of the Member
 * Analytics panel (C3, tasks 5.1 + 5.2).
 *
 * Renders a violin distribution for each of the two calculated numeric metrics
 * the backlog names — `age` and `years_member` — over the Analytics page's OWN
 * filtered dataset (`processedData`, Option A / R1.5 / R5.1). Each metric is fed
 * through the SHARED `ViolinChart` (charts/ViolinChart.tsx, extracted task 2.1),
 * so Member Analytics and STR/BNB share one violin implementation (R3.2).
 *
 * Numeric parse (R3.5 / R2.3): the calculated fields are typed `string` by the
 * Members module (an int computed server-side then stringified), so each row's
 * value is parsed via `toNumber` (analytics/memberAggregations.ts, task 1.1).
 * Rows whose value is absent or does not parse to a finite number are SKIPPED —
 * never coerced to zero.
 *
 * Grouping (task 5.2, R3.3 / R6.1): the default is a single UNGROUPED
 * distribution per metric (one violin) — every parsed datum is tagged with one
 * shared group key so `ViolinChart` draws exactly one violin. An OPTIONAL
 * group-by selector lets the user split each distribution by a dimension
 * (region / membership_type / gender), producing one violin per distinct value
 * of that dimension. The candidate dimensions are DISCOVERED from `fieldConfig`
 * (R6.1): a dimension is offered ONLY when `fieldConfig.fields` exposes a field
 * with that key — nothing tenant-specific is hardcoded, so a tenant without a
 * `gender` field simply never sees that option. When a group-by is active the
 * bilingual `groupLabel` for that dimension is passed to `ViolinChart`.
 *
 * Empty state (R3.6): when a metric has FEWER than the minimum number of points
 * needed for a meaningful distribution, that metric renders a NEUTRAL empty
 * notice (`AnalyticsStateNotice kind="empty"`, message
 * `members:analytics.states.notEnoughPoints`) instead of a chart — not an error,
 * not a crash. The threshold is applied to the TOTAL parsed points for the
 * metric (across all groups), so a group-by never silently hides a metric that
 * had enough data ungrouped.
 *
 * Lazy (R1.6): this component is mounted INSIDE `DistributionsArea`, which the
 * panel code-splits via `React.lazy`. So the Plotly bundle `ViolinChart` pulls
 * in — and the per-metric computation here — only load/run when the user selects
 * the Distributions area, never on page open. The `useMemo` over `processedData`
 * + the active group-by means the derivation runs only while this area is
 * mounted and re-derives on a filter change (R3.6) or a group-by change.
 *
 * No hardcoded English: the metric labels, the group-by selector label + option
 * labels, and the empty-state message are resolved from the `members` namespace
 * (`analytics.distributions.metrics.*`, `analytics.distributions.groupBy.*`,
 * `analytics.states.notEnoughPoints`), bilingual via the active language.
 *
 * Accessibility (R6.6): the group-by selector is a native Chakra `Select`
 * (keyboard-navigable combobox) carrying an `aria-label` resolved from the
 * bilingual `groupBy.label` key.
 *
 * @module components/members/analytics/MemberDistributions
 * @see .kiro/specs/Members/member-analytics (design C3; requirements R3.1, R3.3, R3.5, R3.6, R6.1, R1.6)
 */

import React, { useMemo, useState } from 'react';
import { Box, FormControl, FormLabel, Heading, Select, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import { ViolinChart, type ViolinDatum } from '../../charts';
import { toNumber } from './memberAggregations';
import AnalyticsStateNotice from './areas/AnalyticsStateNotice';
import type { MemberAnalyticsAreaProps } from './areas/types';
import type { FieldConfig, MemberRow } from '../../../types/members';
import { valueFor, groupForKey } from '../fieldValue';

/**
 * Minimum number of parsed points a metric needs before a distribution is shown.
 * Below this, the metric renders the neutral "not enough points" state (R3.6).
 * A violin's shape (quartiles + KDE) is meaningless for one or two points, so
 * we require a small handful. Applied to the metric's TOTAL parsed points, not
 * per group, so turning on a group-by never hides a metric that had enough data.
 */
export const MIN_DISTRIBUTION_POINTS = 5;

/** The single group key used for the ungrouped default distribution (R3.3). */
const UNGROUPED_KEY = '__all__';

/** The sentinel `<Select>` value for the ungrouped (default) choice. */
export const UNGROUPED_SELECT_VALUE = '';

/** Fallback group label for rows whose group-by field value is absent/blank. */
const UNGROUPED_VALUE_FALLBACK = '—';

/** The calculated metrics this area distributes, in display order (R3.1). */
const METRICS = [
  { key: 'age', labelKey: 'analytics.distributions.metrics.age' },
  { key: 'years_member', labelKey: 'analytics.distributions.metrics.yearsMember' },
] as const;

/**
 * The candidate group-by dimensions, in display order (R3.3). Each names a
 * member field `key` and the bilingual label key for its selector option. These
 * are only CANDIDATES — a dimension is offered to the user ONLY when the tenant's
 * resolved `fieldConfig` actually exposes that field (R6.1, discovered not
 * hardcoded — see {@link discoverGroupByDimensions}).
 */
const GROUP_BY_CANDIDATES = [
  { key: 'region', labelKey: 'analytics.distributions.groupBy.region' },
  { key: 'membership_type', labelKey: 'analytics.distributions.groupBy.membershipType' },
  { key: 'gender', labelKey: 'analytics.distributions.groupBy.gender' },
] as const;

/** A group-by dimension the current tenant's field config actually exposes. */
export interface GroupByDimension {
  /** The member field key to read the group value from. */
  key: string;
  /** The bilingual i18n label key for this dimension's selector option. */
  labelKey: string;
}

/**
 * Discover which of the candidate group-by dimensions the tenant's field config
 * exposes (R6.1). A candidate is kept ONLY when `fieldConfig.fields` contains a
 * field with the same `key` — so nothing tenant-specific is assumed: a tenant
 * without a `gender` field never offers grouping by gender. Order follows
 * {@link GROUP_BY_CANDIDATES} (region, membership_type, gender).
 */
export function discoverGroupByDimensions(
  fieldConfig: FieldConfig | null,
): GroupByDimension[] {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return [];
  const presentKeys = new Set(
    fields.map((field) => field?.key).filter((key): key is string => typeof key === 'string'),
  );
  return GROUP_BY_CANDIDATES.filter((candidate) => presentKeys.has(candidate.key)).map(
    (candidate) => ({ key: candidate.key, labelKey: candidate.labelKey }),
  );
}

/**
 * Normalize a raw group-by cell value to a display group key. Absent/blank
 * values fall back to a neutral placeholder so those rows still contribute a
 * violin (rather than silently vanishing) when a group-by is active.
 */
function groupValueOf(raw: unknown): string {
  if (raw === null || raw === undefined) return UNGROUPED_VALUE_FALLBACK;
  const text = String(raw).trim();
  return text === '' ? UNGROUPED_VALUE_FALLBACK : text;
}

/**
 * Build the `ViolinDatum[]` for one metric from the filtered rows.
 *
 * The metric value is read through the shared nested-first `valueFor` accessor,
 * resolving the metric's STORAGE group from `fieldConfig` via `groupForKey`
 * (findings F-005): the calculated metrics (`age`, `years_member`) are enriched
 * under their bucket (`personal.age`, `membership.years_member`), NOT promoted to
 * a flat top-level alias — so the old flat `row[metricKey]` read resolved
 * `undefined` for every row → 0 valid points → the violin wrongly showed "not
 * enough data". The parsed value goes through {@link toNumber}; rows that do not
 * parse to a finite number are skipped (R3.5), never coerced to zero.
 *
 * The group-by value is read the SAME nested-first way (a dimension like `gender`
 * is a nested `personal` field, not a flat alias), so grouping resolves whether
 * the dimension is flat-aliased (`region`) or nested. The `group` tag depends on
 * the active group-by:
 *   - no group-by (`groupByKey` null/absent) → every surviving value is tagged
 *     with the single {@link UNGROUPED_KEY}, so `ViolinChart` renders exactly one
 *     violin (the ungrouped default, R3.3);
 *   - a group-by key → each value is tagged with that dimension's value for the
 *     row (via {@link groupValueOf}), so `ViolinChart` renders one violin per
 *     distinct value (R3.3).
 */
export function buildMetricData(
  rows: ReadonlyArray<Record<string, unknown>>,
  metricKey: string,
  groupByKey?: string | null,
  fieldConfig?: FieldConfig | null,
): ViolinDatum[] {
  const metricGroup = groupForKey(fieldConfig, metricKey);
  const groupByGroup = groupByKey ? groupForKey(fieldConfig, groupByKey) : undefined;
  const data: ViolinDatum[] = [];
  for (const row of rows) {
    const member = row as MemberRow;
    const value = toNumber(valueFor(member, metricGroup, metricKey));
    if (value !== null) {
      const group = groupByKey
        ? groupValueOf(valueFor(member, groupByGroup, groupByKey))
        : UNGROUPED_KEY;
      data.push({ group, value });
    }
  }
  return data;
}

const MemberDistributions: React.FC<MemberAnalyticsAreaProps> = ({ processedData, fieldConfig }) => {
  const { t } = useTypedTranslation('members');

  // Which group-by dimensions this tenant's config exposes (R6.1). Discovered,
  // never hardcoded: only fields actually present in the resolved config are
  // offered as options.
  const dimensions = useMemo(() => discoverGroupByDimensions(fieldConfig), [fieldConfig]);

  // The active group-by key. Default is UNGROUPED_SELECT_VALUE (ungrouped, R3.3).
  const [groupByKey, setGroupByKey] = useState<string>(UNGROUPED_SELECT_VALUE);

  // Guard against a stale selection if the discovered dimensions change (e.g. a
  // new field config): if the active key is no longer offered, fall back to
  // ungrouped so we never group by a field the config no longer exposes.
  const activeGroupBy =
    groupByKey && dimensions.some((d) => d.key === groupByKey) ? groupByKey : UNGROUPED_SELECT_VALUE;

  // The bilingual axis label for the active group-by, passed to ViolinChart so
  // its x-axis + stats table name the grouping (R3.3). Undefined when ungrouped.
  const groupLabel = useMemo(() => {
    if (!activeGroupBy) return undefined;
    const dimension = dimensions.find((d) => d.key === activeGroupBy);
    return dimension ? t(dimension.labelKey) : undefined;
  }, [activeGroupBy, dimensions, t]);

  // Derive the per-metric datasets once per (filtered-dataset, group-by) change.
  // This only runs while the Distributions area is mounted (lazy, R1.6) and
  // re-runs when the page's filter narrows `processedData` (R3.6) or the user
  // changes the group-by.
  const metricData = useMemo(
    () =>
      METRICS.map((metric) => ({
        ...metric,
        data: buildMetricData(processedData, metric.key, activeGroupBy || null, fieldConfig),
      })),
    [processedData, activeGroupBy, fieldConfig],
  );

  return (
    <VStack spacing={8} align="stretch" data-testid="member-distributions">
      {/* Optional group-by selector (task 5.2). Only rendered when the tenant's
          config exposes at least one candidate dimension (R6.1). A native Chakra
          Select is keyboard-navigable (combobox) and carries a bilingual
          aria-label (R6.6). The first option is the ungrouped default (R3.3). */}
      {dimensions.length > 0 && (
        <FormControl maxW="320px" data-testid="distributions-group-by">
          <FormLabel color="white" fontSize="sm" mb={1} htmlFor="distributions-group-by-select">
            {t('analytics.distributions.groupBy.label')}
          </FormLabel>
          <Select
            id="distributions-group-by-select"
            aria-label={t('analytics.distributions.groupBy.label')}
            value={activeGroupBy}
            onChange={(e) => setGroupByKey(e.target.value)}
            bg="gray.800"
            color="white"
            size="sm"
          >
            <option value={UNGROUPED_SELECT_VALUE}>
              {t('analytics.distributions.groupBy.none')}
            </option>
            {dimensions.map((dimension) => (
              <option key={dimension.key} value={dimension.key}>
                {t(dimension.labelKey)}
              </option>
            ))}
          </Select>
        </FormControl>
      )}

      {metricData.map(({ key, labelKey, data }) => {
        const metricLabel = t(labelKey);
        const hasEnough = data.length >= MIN_DISTRIBUTION_POINTS;
        return (
          <Box key={key} data-testid={`distribution-${key}`}>
            <Heading as="h3" size="sm" color="white" mb={3}>
              {metricLabel}
            </Heading>
            {hasEnough ? (
              <ViolinChart data={data} metricLabel={metricLabel} groupLabel={groupLabel} />
            ) : (
              <AnalyticsStateNotice
                kind="empty"
                message={t('analytics.states.notEnoughPoints')}
                testId={`distribution-${key}-empty`}
              />
            )}
          </Box>
        );
      })}
    </VStack>
  );
};

export default MemberDistributions;
