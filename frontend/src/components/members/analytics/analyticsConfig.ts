/**
 * Member Analytics — analytics-config consumption helpers (C-CONFIG).
 *
 * The tenant authors an analytics config block in the Members configurator
 * ("Analytics" tab) and it is served additively on `GET /members/field-config`
 * as {@link FieldConfig.analytics} (a {@link MemberAnalyticsConfig}). These are
 * the single, pure read path the analytics surface uses to *consume* that block:
 *
 *   1. `resolveRole(fieldConfig, role)` — resolve an {@link AnalyticsRole} to the
 *      tenant's concrete field key via `analytics.field_roles`, confirming the key
 *      is actually present in `fieldConfig.fields`. An unmapped role, or a role
 *      mapped to a key that no longer resolves, returns `undefined` so the sets
 *      that depend on it are hidden with a reason rather than shown broken (R9.3 /
 *      R4.3, design C4/C-CONFIG).
 *
 *   2. `isJubileeYear(yearsMember, jubileeRule)` — evaluate the tenant's jubilee
 *      rule against a years-member value. Supports a configured `years` set, a
 *      `multiple_of` rule, and the documented default (multiples of 5) when the
 *      rule / whole block is absent (R9.2, design C-CONFIG).
 *
 *   3. `resolveAddressMapping(fieldConfig)` — resolve each address-label slot
 *      (name / street / postcode / city / country / region) to a present field
 *      key, dropping slots whose mapping is absent or no longer resolves. An empty
 *      result signals the PDF-label generator is unavailable (R9.3 / R4.10,
 *      design C5/C-CONFIG).
 *
 * Pure + unit-tested. No React, no I/O. Spec:
 * `.kiro/specs/Members/member-analytics` (design C-CONFIG; R9.2, R9.3, R6.5).
 */
import type {
  AnalyticsRole,
  FieldConfig,
  FieldConfigField,
  MemberAnalyticsConfig,
  MemberRow,
} from '../../../types/members';
import { valueFor } from '../fieldValue';
import { toNumber } from './memberAggregations';

/** The default jubilee rule when the tenant has authored none (R9.2 / design C-CONFIG). */
export const DEFAULT_JUBILEE_MULTIPLE = 5;

/**
 * The upper bound used when enumerating a `multiple_of` / default jubilee rule
 * into a finite, selectable list of candidate years.
 *
 * A `multiple_of` rule describes an infinite sequence (`N`, `2N`, `3N`, …), but
 * the year selector needs a *finite* list of options. 75 years of membership is
 * well beyond any realistic anniversary a tenant selects for a mailing, so the
 * candidate list stops here (e.g. multiples of 5 → 5…75, multiples of 10 →
 * 10…70). A configured explicit `years` set is NOT bounded by this — it is used
 * verbatim.
 */
export const MAX_JUBILEE_YEAR = 75;

/**
 * Has the tenant authored *any* analytics config block (R1.4 "no analytics
 * config" state / R9.5)?
 *
 * This is the single "no analytics config" signal the analytics surface uses to
 * distinguish its three non-happy states (R1.4): a `false` result means the
 * fixed/calculated areas (Overview, Distributions over age/years_member) still
 * render, while the config-dependent sets degrade with a bilingual reason — it
 * is explicitly NOT an error or empty state.
 *
 * "Authored" means the served {@link FieldConfig.analytics} block exists and
 * carries at least one meaningful member: a non-empty `jubilee_rule`, at least
 * one mapped `field_roles` entry, or at least one `address_mapping` slot. An
 * absent block, or a block present but entirely empty (`{}` / all-empty members),
 * counts as "no analytics config" — the surface then falls back to documented
 * defaults exactly as if the block were absent (R9.5).
 */
export function hasAnalyticsConfig(fieldConfig: FieldConfig | null | undefined): boolean {
  const analytics = fieldConfig?.analytics;
  if (!analytics) {
    return false;
  }

  const { jubilee_rule: jubileeRule, field_roles: fieldRoles, address_mapping: addressMapping } =
    analytics;

  const hasJubileeRule =
    !!jubileeRule &&
    ((Array.isArray(jubileeRule.years) && jubileeRule.years.length > 0) ||
      (typeof jubileeRule.multiple_of === 'number' && Number.isFinite(jubileeRule.multiple_of)));

  const hasAnyRole =
    !!fieldRoles &&
    Object.values(fieldRoles).some((key) => typeof key === 'string' && key !== '');

  const hasAnyAddressSlot =
    !!addressMapping &&
    Object.values(addressMapping).some((key) => typeof key === 'string' && key !== '');

  return hasJubileeRule || hasAnyRole || hasAnyAddressSlot;
}

/** The address-label slots a tenant may map (mirrors `address_mapping` keys). */
export type AddressSlot =
  | 'name'
  | 'street'
  | 'postcode'
  | 'city'
  | 'country'
  | 'region';

/**
 * The resolved address mapping: each slot that mapped to a *present* field key.
 * A slot whose mapping is absent, or whose key no longer resolves in
 * `fieldConfig.fields`, is omitted entirely (never carried as a dangling key).
 */
export type ResolvedAddressMapping = Partial<Record<AddressSlot, string>>;

/**
 * Is `key` a field that is present in the resolved field config?
 *
 * Presence means a `fieldConfig.fields` entry carries that exact `key`. An empty
 * / non-string key is never present. This is the single membership check the
 * role / address-mapping resolvers share, so "mapped but absent" degrades the
 * same way everywhere (R9.3).
 */
function isFieldPresent(fieldConfig: FieldConfig | undefined, key: unknown): boolean {
  if (typeof key !== 'string' || key === '') {
    return false;
  }
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return false;
  }
  return fields.some((field) => field?.key === key);
}

/**
 * Resolve an {@link AnalyticsRole} to the tenant's concrete field key, confirming
 * the key resolves in the field config.
 *
 * Returns the mapped key only when `analytics.field_roles[role]` exists *and*
 * that key is present in `fieldConfig.fields`. Returns `undefined` when:
 *   - there is no analytics config / no `field_roles` block;
 *   - the role is unmapped;
 *   - the role is mapped to a key that is not present in `fieldConfig.fields`
 *     (a stale mapping after the overlay field was removed).
 *
 * Callers treat `undefined` as "this role-backed set is unavailable" and hide it
 * with a bilingual reason (R4.3), never render a broken/empty-forever set.
 */
export function resolveRole(
  fieldConfig: FieldConfig | undefined,
  role: AnalyticsRole,
): string | undefined {
  const key = fieldConfig?.analytics?.field_roles?.[role];
  return isFieldPresent(fieldConfig, key) ? (key as string) : undefined;
}

/**
 * Evaluate the tenant's jubilee rule against a `yearsMember` value.
 *
 * Precedence (design C-CONFIG):
 *   1. a non-empty configured `years` set → a jubilee iff `yearsMember` is a
 *      member of that set (the `multiple_of` rule, if any, is NOT also applied —
 *      an explicit set is exhaustive);
 *   2. otherwise a positive `multiple_of` N → a jubilee iff `yearsMember` is a
 *      positive multiple of N (`N`, `2N`, …);
 *   3. otherwise (no rule, or an empty/invalid rule, or the whole block absent) →
 *      the documented default: a positive multiple of {@link DEFAULT_JUBILEE_MULTIPLE}
 *      (every 5 years).
 *
 * `yearsMember` is parsed/guarded: a non-integer, negative, or `0` value is never
 * a jubilee (year 0 / "joined this year" is not an anniversary). The caller passes
 * the already-parsed numeric `years_member` (via `toNumber`); a non-finite value
 * is treated as not-a-jubilee.
 *
 * @param yearsMember  the member's years-member count (parsed to a number).
 * @param jubileeRule  the tenant's `analytics.jubilee_rule`, or `undefined`.
 */
export function isJubileeYear(
  yearsMember: number,
  jubileeRule?: MemberAnalyticsConfig['jubilee_rule'],
): boolean {
  // Guard the input: only a positive integer can be a jubilee anniversary.
  if (!Number.isFinite(yearsMember) || !Number.isInteger(yearsMember) || yearsMember <= 0) {
    return false;
  }

  // 1. An explicit, non-empty configured set is exhaustive.
  const years = jubileeRule?.years;
  if (Array.isArray(years) && years.length > 0) {
    return years.includes(yearsMember);
  }

  // 2. A positive multiple-of rule.
  const multipleOf = jubileeRule?.multiple_of;
  if (typeof multipleOf === 'number' && Number.isFinite(multipleOf) && multipleOf > 0) {
    return yearsMember % multipleOf === 0;
  }

  // 3. Documented default: multiples of 5.
  return yearsMember % DEFAULT_JUBILEE_MULTIPLE === 0;
}

/**
 * Produce the finite, ordered list of *selectable* jubilee years for the tenant's
 * jubilee rule — the candidate options a year selector renders (task 7.6).
 *
 * This is the list-producing counterpart to {@link isJubileeYear} (the per-value
 * predicate): it enumerates which years *qualify* as a jubilee so the UI can
 * offer them, rather than testing a single value. The two agree by construction —
 * every year this returns satisfies `isJubileeYear(year, rule) === true`, and the
 * same precedence (design C-CONFIG) applies:
 *
 *   1. a non-empty configured `years` set → exactly those years, de-duplicated,
 *      guarded to positive integers, sorted ascending (the set is exhaustive —
 *      the `multiple_of` rule, if any, is NOT also enumerated);
 *   2. otherwise a positive `multiple_of` N → `N, 2N, 3N, …` up to and including
 *      {@link MAX_JUBILEE_YEAR};
 *   3. otherwise (no rule / empty / invalid / block absent) → the documented
 *      default: multiples of {@link DEFAULT_JUBILEE_MULTIPLE} up to
 *      {@link MAX_JUBILEE_YEAR}.
 *
 * The result is always ascending, free of duplicates, and contains only positive
 * integers (`year 0` / "joined this year" is never a jubilee). It is a pure
 * function of the rule, safe to memoize on `fieldConfig.analytics.jubilee_rule`.
 *
 * @param jubileeRule the tenant's `analytics.jubilee_rule`, or `undefined`.
 * @param maxYear     the enumeration ceiling for a `multiple_of`/default rule
 *                    (defaults to {@link MAX_JUBILEE_YEAR}); ignored for an
 *                    explicit `years` set.
 */
export function candidateJubileeYears(
  jubileeRule?: MemberAnalyticsConfig['jubilee_rule'],
  maxYear: number = MAX_JUBILEE_YEAR,
): number[] {
  // 1. An explicit, non-empty configured set is exhaustive — use it verbatim
  //    (guarded to positive integers, de-duplicated, sorted).
  const years = jubileeRule?.years;
  if (Array.isArray(years) && years.length > 0) {
    const cleaned = years.filter(
      (y) => typeof y === 'number' && Number.isInteger(y) && y > 0,
    );
    return Array.from(new Set(cleaned)).sort((a, b) => a - b);
  }

  // 2. / 3. Enumerate a positive multiple-of rule, or the default multiple-of-5.
  const multipleOf =
    typeof jubileeRule?.multiple_of === 'number' &&
      Number.isFinite(jubileeRule.multiple_of) &&
      jubileeRule.multiple_of > 0
      ? jubileeRule.multiple_of
      : DEFAULT_JUBILEE_MULTIPLE;

  // A non-integer multiple (e.g. 2.5) cannot enumerate whole jubilee years —
  // fall back to the default so the selector is never empty.
  const step = Number.isInteger(multipleOf) ? multipleOf : DEFAULT_JUBILEE_MULTIPLE;

  const result: number[] = [];
  for (let year = step; year <= maxYear; year += step) {
    result.push(year);
  }
  return result;
}

/**
 * The conventional member email field keys, in resolution priority order. These
 * mirror the backend `members_mail._extract_emails` candidate keys so the field
 * the compose UI resolves is the SAME one the mail route reads off each row
 * (R4.12). `AnalyticsRole` carries no dedicated email role, so the recipient
 * email field is resolved from the tenant's own field config rather than from a
 * `field_roles` entry — but a future email role mapping would take precedence
 * (see {@link resolveEmailField}).
 */
export const CONVENTIONAL_EMAIL_KEYS: readonly string[] = [
  'email',
  'e_mail',
  'emailaddress',
  'email_address',
];

/**
 * Resolve the recipient EMAIL field key for a member set (R4.12).
 *
 * Precedence:
 *   1. a `field_roles` entry whose key *looks* like an email field (so a tenant
 *      that maps an email role in a future config wins) — resolved + presence-
 *      checked exactly like {@link resolveRole};
 *   2. a `fieldConfig.fields` entry typed `email`;
 *   3. a `fieldConfig.fields` entry whose key matches one of
 *      {@link CONVENTIONAL_EMAIL_KEYS}, in priority order.
 *
 * Returns the resolved field key, or `undefined` when no email field resolves —
 * the compose UI then disables the send with a bilingual reason rather than
 * mailing an unresolvable set. The result is always a key present in
 * `fieldConfig.fields` (never a dangling key).
 */
export function resolveEmailField(
  fieldConfig: FieldConfig | undefined,
): string | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return undefined;
  }

  // 1. A role mapped to an email-looking key wins (future-proofs an email role).
  const roles = fieldConfig?.analytics?.field_roles;
  if (roles) {
    for (const key of Object.values(roles)) {
      if (
        typeof key === 'string' &&
        CONVENTIONAL_EMAIL_KEYS.includes(key.toLowerCase()) &&
        isFieldPresent(fieldConfig, key)
      ) {
        return key;
      }
    }
  }

  // 2. A field explicitly typed `email`.
  const typedEmail = fields.find(
    (f) => f?.type === 'email' && typeof f.key === 'string' && f.key !== '',
  );
  if (typedEmail?.key) {
    return typedEmail.key;
  }

  // 3. A field whose key is a conventional email key, in priority order.
  for (const candidate of CONVENTIONAL_EMAIL_KEYS) {
    const match = fields.find((f) => f?.key?.toLowerCase() === candidate);
    if (match?.key) {
      return match.key;
    }
  }

  return undefined;
}

/**
 * Resolve the tenant's `address_mapping` slots to present field keys.
 *
 * Each slot (name / street / postcode / city / country / region) is included in
 * the result only when it maps to a key that is present in `fieldConfig.fields`.
 * A slot with no mapping — or a mapping to a key that no longer resolves — is
 * dropped. The returned object therefore contains exactly the slots the label
 * generator can actually fill.
 *
 * An empty result (no slots resolved, or no `address_mapping` / analytics block
 * at all) is the signal that PDF address labels are unavailable for the tenant
 * (R4.10 — CSV export stays available regardless).
 */
export function resolveAddressMapping(
  fieldConfig: FieldConfig | undefined,
): ResolvedAddressMapping {
  const mapping = fieldConfig?.analytics?.address_mapping;
  const resolved: ResolvedAddressMapping = {};
  if (!mapping) {
    return resolved;
  }

  const slots: AddressSlot[] = [
    'name',
    'street',
    'postcode',
    'city',
    'country',
    'region',
  ];
  for (const slot of slots) {
    const key = mapping[slot];
    if (isFieldPresent(fieldConfig, key)) {
      resolved[slot] = key as string;
    }
  }
  return resolved;
}

/**
 * The field key the Jubilees preset filters on — the calculated `years_member`
 * count a member has been enrolled. The jubilee year selector writes the chosen
 * year into `PivotConfig.filters[JUBILEE_YEAR_FILTER_KEY]` so it (a) travels with
 * the set when saved (R4.4 — task 7.5's save path persists it verbatim) and (b)
 * narrows the executed rows to members *at* that jubilee anniversary.
 *
 * It matches the Jubilees preset's `requiresFields: ['years_member']` so the
 * filter resolves against the same value the preset is defined over.
 */
export const JUBILEE_YEAR_FILTER_KEY = 'years_member';

/**
 * Read the chosen jubilee year out of a `PivotConfig.filters` map, or `undefined`
 * when none is set.
 *
 * The year is persisted as `filters[JUBILEE_YEAR_FILTER_KEY]`; it may arrive as a
 * real number (set in this session) or a numeric string (round-tripped through a
 * saved model's JSON definition), so it is parsed via {@link toNumber}. A value
 * that is not a positive integer resolves to `undefined` (no filter applied) —
 * the set then lists all jubilee-eligible members rather than filtering to a
 * single, nonsensical year.
 */
export function selectedJubileeYear(
  filters: Record<string, unknown> | undefined,
): number | undefined {
  if (!filters) {
    return undefined;
  }
  const raw = filters[JUBILEE_YEAR_FILTER_KEY];
  const parsed = toNumber(raw);
  if (parsed === null || !Number.isInteger(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}

/**
 * Resolve the storage group for a field key from the field config, mirroring the
 * pivot adapter's `groupForKey` so a value is read the SAME way everywhere
 * (nested bucket first via {@link valueFor}, then the flat alias).
 */
function groupForKey(
  fieldConfig: FieldConfig | undefined,
  key: string,
): string | undefined {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) {
    return undefined;
  }
  const field: FieldConfigField | undefined = fields.find((f) => f?.key === key);
  return field?.group;
}

/**
 * The field key the New-members preset filters on (findings F-010) — the fixed
 * `joined_date` (an ISO `YYYY-MM-DD` string). The join-year selector writes the
 * chosen year into `PivotConfig.filters[JOINED_AFTER_FILTER_KEY]` so it (a)
 * travels with the set when saved (R4.4) and (b) narrows the executed rows to
 * members who joined IN OR AFTER that year. Matches the New-members preset's
 * `requiresFields: ['joined_date']`.
 */
export const JOINED_AFTER_FILTER_KEY = 'joined_after_year';

/**
 * How many years back the New-members join-year selector offers, counting back
 * from the current year. ~15 years covers the useful "joined since …" range for
 * a recurring new-member mailing without an unbounded dropdown.
 */
export const JOINED_AFTER_YEARS_BACK = 15;

/**
 * The finite, DESCENDING list of selectable "joined in or after" years for the
 * New-members preset (findings F-010) — current year first, back
 * {@link JOINED_AFTER_YEARS_BACK} years. Descending because the most-recent
 * join years are the common choice for a "new members since …" list.
 *
 * `now` is injectable for deterministic tests; it defaults to the current year.
 */
export function candidateJoinedYears(
  now: number = new Date().getFullYear(),
  yearsBack: number = JOINED_AFTER_YEARS_BACK,
): number[] {
  const years: number[] = [];
  for (let y = now; y >= now - yearsBack; y -= 1) {
    years.push(y);
  }
  return years;
}

/**
 * Read the chosen "joined after" year out of a `PivotConfig.filters` map, or
 * `undefined` when none is set. Mirrors {@link selectedJubileeYear}: the value
 * may be a number (this session) or a numeric string (round-tripped through a
 * saved set's JSON), parsed via {@link toNumber}; a non-positive / non-integer
 * value resolves to `undefined` (no filter → all members listed).
 */
export function selectedJoinedAfterYear(
  filters: Record<string, unknown> | undefined,
): number | undefined {
  if (!filters) {
    return undefined;
  }
  const parsed = toNumber(filters[JOINED_AFTER_FILTER_KEY]);
  if (parsed === null || !Number.isInteger(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}

/**
 * Parse the YEAR out of a member's `joined_date` value. Accepts an ISO
 * `YYYY-MM-DD` (or full ISO timestamp) string or a `Date`; returns `null` when
 * it cannot parse a 4-digit year. Kept local + lenient so a blank/garbled
 * join-date simply excludes the row from a "joined after" filter rather than
 * crashing.
 */
function joinedYearOf(raw: unknown): number | null {
  if (raw === null || raw === undefined || raw === '') {
    return null;
  }
  if (raw instanceof Date) {
    return Number.isNaN(raw.getTime()) ? null : raw.getFullYear();
  }
  const text = String(raw).trim();
  // Leading 4-digit year (ISO date / timestamp).
  const match = text.match(/^(\d{4})\b/);
  if (match) {
    return Number(match[1]);
  }
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date.getFullYear();
}

/**
 * Narrow a set of member rows to those who joined IN OR AFTER the chosen year —
 * the definition filter the New-members preset carries (findings F-010, R4.2 /
 * R4.4). Mirrors {@link applyJubileeYearFilter}:
 *
 * The chosen year is read from `config.filters[JOINED_AFTER_FILTER_KEY]` (via
 * {@link selectedJoinedAfterYear}); when none is set the rows are returned
 * unchanged (the set lists all members). When a year IS set, only members whose
 * `joined_date` year is >= that year are kept — the date is read through the
 * shared nested-or-flat {@link valueFor} accessor and its year parsed leniently
 * ({@link joinedYearOf}); a member with an absent/unparseable join date is
 * excluded from the narrowed list. Row order is preserved; inputs are never
 * mutated (pure). Applied in the Pivot Views panel BEFORE `executeMemberPivot`,
 * like the jubilee filter, because the client adapter does not itself apply
 * `config.filters`.
 */
export function applyJoinedAfterFilter(
  rows: MemberRow[],
  filters: Record<string, unknown> | undefined,
  fieldConfig: FieldConfig | undefined,
): MemberRow[] {
  const safeRows = Array.isArray(rows) ? rows : [];
  const year = selectedJoinedAfterYear(filters);
  if (year === undefined) {
    return safeRows;
  }
  const group = groupForKey(fieldConfig, 'joined_date');
  return safeRows.filter((row) => {
    const joinedYear = joinedYearOf(valueFor(row, group, 'joined_date'));
    return joinedYear !== null && joinedYear >= year;
  });
}

/**
 * Narrow a set of member rows to those *at* the chosen jubilee year — the
 * definition filter the Jubilees preset carries (task 7.6, R4.2 / R4.4).
 *
 * The chosen year is read from `config.filters[JUBILEE_YEAR_FILTER_KEY]` (via
 * {@link selectedJubileeYear}); when none is set the rows are returned unchanged
 * (the set lists all members). When a year *is* set, only members whose
 * `years_member` equals that year are kept — read through the shared
 * nested-or-flat {@link valueFor} accessor and parsed via {@link toNumber} so a
 * stringified calculated value matches a numeric filter. Row order is preserved
 * and inputs are never mutated (pure).
 *
 * This is applied in the Pivot Views panel BEFORE `executeMemberPivot`, because
 * the client adapter aggregates/lists its input rows as-is and does not itself
 * apply `config.filters`; the saved set keeps the filter in its definition so
 * it reappears on reload (R4.4).
 */
export function applyJubileeYearFilter(
  rows: MemberRow[],
  filters: Record<string, unknown> | undefined,
  fieldConfig: FieldConfig | undefined,
): MemberRow[] {
  const safeRows = Array.isArray(rows) ? rows : [];
  const year = selectedJubileeYear(filters);
  if (year === undefined) {
    return safeRows;
  }
  const group = groupForKey(fieldConfig, JUBILEE_YEAR_FILTER_KEY);
  return safeRows.filter(
    (row) => toNumber(valueFor(row, group, JUBILEE_YEAR_FILTER_KEY)) === year,
  );
}

/**
 * The reserved filter keys that are NOT generic equality filters — each has its
 * own dedicated applier ({@link applyJubileeYearFilter} /
 * {@link applyJoinedAfterFilter}) that interprets the stored value as a *year*
 * rather than an exact field value. {@link applyDefinitionFilters} skips these so
 * a jubilee/joined-after year is never mistaken for a literal `years_member` /
 * `joined_after_year` equality match.
 */
const RESERVED_FILTER_KEYS: ReadonlySet<string> = new Set([
  JUBILEE_YEAR_FILTER_KEY,
  JOINED_AFTER_FILTER_KEY,
]);

/**
 * Apply a saved set's GENERIC definition filters to a set of member rows
 * (findings: "field picker cannot save a definition filter"; R4.4).
 *
 * A saved set may carry plain equality filters in `config.filters`, e.g.
 * `{ clubblad: 'Papier' }` (the "clubblad Nederland / paper" set) — one entry
 * per field key, the value the member's field must equal. This narrows the rows
 * to members whose value for each filtered key equals the configured value:
 *
 *   - the member value is read through the shared nested-or-flat {@link valueFor}
 *     accessor (resolving the storage group from the field config first), so a
 *     fixed/overlay/calculated field all resolve the same way the adapter reads
 *     them;
 *   - comparison is as STRINGS, case-insensitive, trimmed, so `'Papier'` matches
 *     a stored `' papier '` and a numeric `1` matches `'1'` — robust to the
 *     stringy shape member values arrive in;
 *   - a BLANK filter value (`''`/`null`/`undefined`) is treated as "no narrowing"
 *     for that key (an unset filter never hides everyone);
 *   - the {@link RESERVED_FILTER_KEYS} (jubilee year / joined-after year) are
 *     SKIPPED — they have their own year-aware appliers and must not be matched
 *     as literal equality;
 *   - ALL remaining filter entries must match (AND semantics).
 *
 * Row order is preserved and inputs are never mutated (pure). Applied in the
 * Pivot Views panel BEFORE `executeMemberPivot`, like the jubilee/joined-after
 * filters, because the client adapter aggregates/lists its input rows as-is and
 * does not itself apply `config.filters`.
 */
export function applyDefinitionFilters(
  rows: MemberRow[],
  filters: Record<string, unknown> | undefined,
  fieldConfig: FieldConfig | undefined,
): MemberRow[] {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (!filters) {
    return safeRows;
  }

  // The active (non-reserved, non-blank) equality filters, pre-resolved to their
  // storage group + normalized comparison value so the row loop stays cheap.
  const active: { group: string | undefined; key: string; expected: string }[] = [];
  for (const [key, raw] of Object.entries(filters)) {
    if (RESERVED_FILTER_KEYS.has(key)) {
      continue;
    }
    if (raw === null || raw === undefined) {
      continue;
    }
    const expected = String(raw).trim().toLowerCase();
    if (expected === '') {
      continue; // blank filter → no narrowing for this key
    }
    active.push({ group: groupForKey(fieldConfig, key), key, expected });
  }

  if (active.length === 0) {
    return safeRows;
  }

  return safeRows.filter((row) =>
    active.every(({ group, key, expected }) => {
      const value = valueFor(row, group, key);
      if (value === null || value === undefined) {
        return false;
      }
      return String(value).trim().toLowerCase() === expected;
    }),
  );
}
