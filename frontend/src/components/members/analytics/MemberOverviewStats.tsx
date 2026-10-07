/**
 * MemberOverviewStats — the Overview summary of the Member Analytics surface (C2, task 4.1).
 *
 * Renders the three headline figures the backlog names (R2.1) as summary stat
 * cards over the Analytics page's OWN filtered dataset (`processedData`, Option A
 * / R1.5):
 *
 *   - **count** — the number of filtered rows (always shown);
 *   - **average age** — the mean of the calculated `age` field, parsed to a number;
 *   - **average years-member** — the mean of the calculated `years_member` field.
 *
 * The two averages are computed with the pure task-1.1 helpers (`mean`,
 * `countExcluded`) inside a `useMemo` keyed on `processedData`, so the figures
 * recompute live whenever the page's filter/sort changes `processedData` and
 * never on an unrelated re-render (R2.2 / R6.7).
 *
 * Field resolution is GENERIC (R2.5): the `age` / `years_member` field *keys* are
 * discovered from the resolved field config's **calculated** entries, never
 * hardcoded. If a tenant's config does not expose one of them, that single card
 * is OMITTED gracefully (the others still render) — we never show `NaN`. An
 * average whose input is entirely absent/invalid (`mean` → `null`) likewise omits
 * the card rather than render a misleading value.
 *
 * Averages are over present values only; rows with an absent/invalid input are
 * excluded (via `toNumber` inside `mean`) and surfaced as an excluded-count where
 * it aids interpretation (R2.3) — never counted as zero. The excluded line is
 * shown ONLY when at least one row is excluded (task 4.2 — "where it aids
 * interpretation"), carries the DENOMINATOR ("N of M excluded") so the figure is
 * interpretable, is rendered as TEXT (colour is never the sole signal), and is
 * tied to its card via `aria-describedby` so assistive tech reads it as context
 * for the average. The whole memo is keyed on `processedData`, so count, average
 * AND excluded-count all re-derive together on a filter/sort change (R2.2).
 *
 * Labels are bilingual (R2.4): the card *title* comes from the
 * `analytics.overview.stats.*` i18n keys (task 0.3), and `resolveLabel` surfaces
 * the tenant's own calculated-field label (e.g. the config's `{nl,en}` label for
 * `age`) as accessible context so each card reflects the resolved field, not a
 * hardcoded English string.
 *
 * Presentation note (deviation): the design calls for Chakra `Stat` cards, but
 * the Chakra `Stat`/`StatLabel`/`StatNumber` family resolves to `undefined` under
 * this project's test runner's ESM interop and crashes the component with
 * "Element type is invalid" — the Members table's own live stats strip
 * (`MembersPage.tsx` `StatCard`) hit exactly this and is DELIBERATELY built from
 * `Box`/`Text` for that reason. This component follows that established
 * convention: the same visual shape as the shared stats-strip (`gray.800` card,
 * muted label over a large value) built from `Box`/`Text`, so the summary renders
 * and is testable.
 *
 * Read-only: this component only reads member data; it introduces no mutation.
 *
 * @module components/members/analytics/MemberOverviewStats
 * @see .kiro/specs/Members/member-analytics (design C2; requirements R2.1, R2.2, R2.4, R2.5, R6.7)
 */

import React, { useMemo } from 'react';
import { SimpleGrid, Box, Text, VStack } from '@chakra-ui/react';
import { useTypedTranslation } from '../../../hooks/useTypedTranslation';
import type {
  FieldConfig,
  FieldConfigField,
  LocalizedLabel,
  MemberRow,
} from '../../../types/members';
import type { MemberAnalyticsAreaProps } from './areas/types';
import { mean, countExcluded } from './memberAggregations';
import { valueFor, groupForKey } from '../fieldValue';

/**
 * Resolve a localized (`{nl,en}`) or plain-string label to the active language,
 * mirroring the Members table's own label resolution (`fieldForm.resolveLabel`):
 * prefer the active language, then `nl`, then `en`, then the given fallback. Kept
 * local so the Overview has no cross-module import of a form helper (R2.4).
 */
function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
): string {
  if (!label) return fallback;
  if (typeof label === 'string') return label;
  return label[lang] || label.nl || label.en || fallback;
}

/**
 * Find the resolved **calculated** field descriptor for `key`, or `undefined`
 * when the tenant's config does not expose it. Analytics sources `age` /
 * `years_member` from the calculated entries specifically (they are derived,
 * read-only fields — design C2 / R2.5), so a fixed/overlay field that happens to
 * share the key is NOT treated as the calculated metric.
 */
function findCalculatedField(
  fieldConfig: FieldConfig | null,
  key: string,
): FieldConfigField | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return undefined;
  return fields.find((field) => field?.key === key && field?.origin === 'calculated');
}

/** The calculated-field keys the Overview averages read (design C2 / R2.1). */
const AGE_KEY = 'age';
const YEARS_MEMBER_KEY = 'years_member';

/**
 * The fixed membership-type field key the Overview groups the h-dcn-parity
 * breakdown by (findings F-004 / R2.1 MAY). `membership_type` is a platform
 * fixed field, so this breakdown is always available when the field resolves.
 */
const MEMBERSHIP_TYPE_KEY = 'membership_type';

/** Fallback bucket label for a row with no membership-type value. */
const TYPE_UNKNOWN = '—';

/**
 * Find the resolved descriptor for a field `key` of ANY origin (unlike
 * {@link findCalculatedField}, which requires `calculated`). Used for the fixed
 * `membership_type` breakdown so its storage group + label resolve from config.
 */
function findField(
  fieldConfig: FieldConfig | null,
  key: string,
): FieldConfigField | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return undefined;
  return fields.find((field) => field?.key === key);
}

/**
 * How many decimals to show on an average. One decimal keeps "47.3 years" legible
 * without implying false precision on a derived mean.
 */
function formatAverage(value: number): string {
  return value.toFixed(1);
}

/**
 * One summary card — a `gray.800` box with a muted title over a large value and
 * an optional help line. Built from `Box`/`Text` (not Chakra `Stat*`, which is
 * `undefined` under the test runner — see the module note) while keeping the
 * shared stats-strip look. `role="group"` + `aria-label` keep each card
 * addressable to assistive tech with the resolved bilingual title.
 */
const SummaryCard: React.FC<{
  testId: string;
  title: string;
  ariaLabel?: string;
  valueTestId: string;
  value: string | number;
  valueColor?: string;
  helpText?: string;
  helpTestId?: string;
}> = ({
  testId,
  title,
  ariaLabel,
  valueTestId,
  value,
  valueColor = 'white',
  helpText,
  helpTestId,
}) => {
    // When a help line is present, give it a stable id and point the card's
    // `aria-describedby` at it so assistive tech reads the excluded-count as
    // context for the figure — the interpretation is conveyed by TEXT, not by
    // colour alone (R6.6 / accessibility; color is not the sole signal).
    const helpId = helpText ? `${testId}-help` : undefined;
    return (
      <Box
        data-testid={testId}
        role="group"
        aria-label={ariaLabel ?? title}
        aria-describedby={helpId}
        bg="gray.800"
        borderWidth="1px"
        borderColor="gray.700"
        borderRadius="md"
        px={4}
        py={3}
        minW="140px"
        flex="1"
      >
        <Text color="gray.400" fontSize="sm">
          {title}
        </Text>
        <Text color={valueColor} fontSize="2xl" fontWeight="bold" data-testid={valueTestId}>
          {value}
        </Text>
        {helpText && (
          <Text id={helpId} color="gray.500" fontSize="xs" mt={1} data-testid={helpTestId}>
            {helpText}
          </Text>
        )}
      </Box>
    );
  };

const MemberOverviewStats: React.FC<MemberAnalyticsAreaProps> = ({
  processedData,
  fieldConfig,
  language,
}) => {
  const { t } = useTypedTranslation('members');

  // Resolve the two calculated metrics from the field config. A metric the
  // tenant's config does not expose stays `undefined` → its card is omitted
  // (R2.5), never rendered as NaN.
  const ageField = findCalculatedField(fieldConfig, AGE_KEY);
  const yearsMemberField = findCalculatedField(fieldConfig, YEARS_MEMBER_KEY);
  // The fixed membership-type field for the breakdown (F-004 / R2.1 MAY). Any
  // origin accepted (it is a platform fixed field); its card is omitted when the
  // tenant's config does not expose it.
  const membershipTypeField = findField(fieldConfig, MEMBERSHIP_TYPE_KEY);

  // Compute every figure in ONE memo keyed on the inputs that actually change the
  // result — the filtered dataset and which metrics resolved. This is the live
  // recompute path (R2.2 / R6.7): a new `processedData` reference (after a
  // filter/sort change) recomputes; an unrelated re-render does not.
  const stats = useMemo(() => {
    const count = processedData.length;

    // Read the calculated values through the shared nested-first `valueFor`
    // accessor, resolving each field's STORAGE group from its config descriptor
    // (findings F-003): calculated fields are enriched under their bucket
    // (`personal.age`, `membership.years_member`), NOT promoted to a flat
    // top-level alias by `flattenMember`, so the old `row['age']` read always
    // resolved `undefined` → `mean([])` → `null` → the card was wrongly omitted.
    const ageValues: unknown[] = ageField
      ? processedData.map((row: MemberRow) => valueFor(row, ageField.group, AGE_KEY))
      : [];
    const yearsValues: unknown[] = yearsMemberField
      ? processedData.map((row: MemberRow) =>
        valueFor(row, yearsMemberField.group, YEARS_MEMBER_KEY),
      )
      : [];

    // Per-membership-type breakdown (F-004 / R2.1 MAY): count members grouped by
    // the resolved `membership_type` value, read nested-first via `valueFor`.
    // Rows with no type bucket under the neutral placeholder. Sorted by count
    // desc then label asc for a stable, meaningful order.
    let membersByType: { type: string; count: number }[] = [];
    if (membershipTypeField) {
      const group = groupForKey(fieldConfig, MEMBERSHIP_TYPE_KEY);
      const counts = new Map<string, number>();
      for (const row of processedData) {
        const raw = valueFor(row, group, MEMBERSHIP_TYPE_KEY);
        const key =
          raw === null || raw === undefined || String(raw).trim() === ''
            ? TYPE_UNKNOWN
            : String(raw);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      membersByType = Array.from(counts.entries())
        .map(([type, c]) => ({ type, count: c }))
        .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));
    }

    return {
      count,
      avgAge: ageField ? mean(ageValues) : null,
      ageExcluded: ageField ? countExcluded(ageValues) : 0,
      avgYearsMember: yearsMemberField ? mean(yearsValues) : null,
      yearsMemberExcluded: yearsMemberField ? countExcluded(yearsValues) : 0,
      membersByType,
    };
  }, [processedData, ageField, yearsMemberField, membershipTypeField, fieldConfig]);

  return (
    <Box data-testid="analytics-area-overview">
      <SimpleGrid columns={{ base: 1, sm: 2, md: 3 }} spacing={4}>
        {/* Count — always present (R2.1); no field dependency, cannot be NaN. */}
        <SummaryCard
          testId="overview-stat-count"
          title={t('analytics.overview.stats.count')}
          valueTestId="overview-stat-count-value"
          value={stats.count}
        />

        {/* Average age — only when the calculated `age` field resolves AND at
            least one row has a valid value (mean non-null). Otherwise omitted so
            we never show NaN (R2.5 / R2.3). The accessible label pairs the
            bilingual stat title with the tenant's resolved field label (R2.4). */}
        {ageField && stats.avgAge !== null && (
          <SummaryCard
            testId="overview-stat-avg-age"
            title={t('analytics.overview.stats.avgAge')}
            ariaLabel={`${t('analytics.overview.stats.avgAge')} — ${resolveLabel(
              ageField.label,
              language,
              AGE_KEY,
            )}`}
            valueTestId="overview-stat-avg-age-value"
            value={formatAverage(stats.avgAge)}
            helpText={
              stats.ageExcluded > 0
                ? t('analytics.overview.excludedCount', {
                  count: stats.ageExcluded,
                  total: stats.count,
                })
                : undefined
            }
            helpTestId="overview-stat-avg-age-excluded"
          />
        )}

        {/* Average years-member — same omit-when-absent rule as avg age. */}
        {yearsMemberField && stats.avgYearsMember !== null && (
          <SummaryCard
            testId="overview-stat-avg-years-member"
            title={t('analytics.overview.stats.avgYearsMember')}
            ariaLabel={`${t('analytics.overview.stats.avgYearsMember')} — ${resolveLabel(
              yearsMemberField.label,
              language,
              YEARS_MEMBER_KEY,
            )}`}
            valueTestId="overview-stat-avg-years-member-value"
            value={formatAverage(stats.avgYearsMember)}
            helpText={
              stats.yearsMemberExcluded > 0
                ? t('analytics.overview.excludedCount', {
                  count: stats.yearsMemberExcluded,
                  total: stats.count,
                })
                : undefined
            }
            helpTestId="overview-stat-avg-years-member-excluded"
          />
        )}
      </SimpleGrid>

      {/* Per-membership-type breakdown (F-004 / R2.1 MAY). Rendered only when the
          tenant's config exposes `membership_type` AND there is at least one row
          to break down. A simple type → count list in a card matching the
          stats-strip look; the heading + the field's resolved label are
          bilingual (R2.4). Each row is text (count never conveyed by colour
          alone, R6.6). */}
      {membershipTypeField && stats.membersByType.length > 0 && (
        <Box
          data-testid="overview-members-by-type"
          mt={4}
          bg="gray.800"
          borderWidth="1px"
          borderColor="gray.700"
          borderRadius="md"
          px={4}
          py={3}
        >
          <Text
            color="gray.400"
            fontSize="sm"
            mb={2}
            aria-label={`${t('analytics.overview.stats.membersPerType')} — ${resolveLabel(
              membershipTypeField.label,
              language,
              MEMBERSHIP_TYPE_KEY,
            )}`}
          >
            {t('analytics.overview.stats.membersPerType')}
          </Text>
          <VStack align="stretch" spacing={1}>
            {stats.membersByType.map(({ type, count }) => (
              <Box
                key={type}
                display="flex"
                justifyContent="space-between"
                data-testid={`overview-members-by-type-row-${type}`}
              >
                <Text color="gray.200" fontSize="sm">
                  {type}
                </Text>
                <Text color="white" fontSize="sm" fontWeight="bold">
                  {count}
                </Text>
              </Box>
            ))}
          </VStack>
        </Box>
      )}
    </Box>
  );
};

export default MemberOverviewStats;
