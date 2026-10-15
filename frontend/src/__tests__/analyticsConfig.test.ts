/**
 * Unit tests for the Member Analytics config-consumption helpers.
 *
 * The role / jubilee-rule / address-mapping helpers were removed (superseded by
 * the generic Dynamic Pivot Views mechanism). What remains, and is covered here:
 *   - `resolveEmailField`: recipient-email resolution from the field config
 *     alone — a field typed `email` wins, else a conventional email key, in
 *     priority order; `undefined` when none resolves (R4.12).
 *   - `applyDefinitionFilters`: operator-aware definition filters — the
 *     mechanism through which every subset the removed presets used to offer
 *     (clubblad, jubilee years, joined-after, …) is now rebuilt generically.
 *     The first block covers the legacy `eq` default (case-insensitive/trimmed
 *     narrowing, blank-value no-narrow, nested storage group, AND semantics,
 *     purity). The second block (`— operators`) covers the per-operator
 *     contract: legacy-scalar-as-eq, ne, contains/notContains, typed numeric/
 *     date ordering + string fallback, empty/notEmpty, AND across operators,
 *     invalid-regex no-match (regex AND notRegex), notRegex exclusion,
 *     blank-value no-narrow, unknown-op clamp, and order-preserving purity.
 *
 * Specs: `.kiro/specs/Members/members-analytics-role-removal` (eq engine) and
 * `.kiro/specs/Members/member-analytics-pivot-filter-operators` (operators).
 */
import {
  resolveEmailField,
  applyDefinitionFilters,
  CONVENTIONAL_EMAIL_KEYS,
} from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, FieldConfigField, MemberRow } from '../types/members';

/** Build a FieldConfig from field descriptors (key + optional type/group). */
function makeFieldConfig(fields: Partial<FieldConfigField>[]): FieldConfig {
  return { fields: fields as FieldConfigField[] };
}

/** Build a FieldConfig from bare field keys. */
function keysConfig(keys: string[]): FieldConfig {
  return makeFieldConfig(keys.map((key) => ({ key })));
}

describe('analyticsConfig.resolveEmailField', () => {
  it('resolves a field explicitly typed `email` first', () => {
    const fieldConfig = makeFieldConfig([
      { key: 'name' },
      { key: 'contact_mail', type: 'email' },
      { key: 'email' },
    ]);
    // The typed-`email` field wins even over a conventional `email` key.
    expect(resolveEmailField(fieldConfig)).toBe('contact_mail');
  });

  it('falls back to a conventional email key, in priority order', () => {
    // No typed-email field; `email` (first conventional key) wins over `e_mail`.
    const fieldConfig = keysConfig(['name', 'e_mail', 'email']);
    expect(resolveEmailField(fieldConfig)).toBe('email');
  });

  it('matches a conventional key case-insensitively', () => {
    const fieldConfig = makeFieldConfig([{ key: 'Email_Address' }]);
    expect(resolveEmailField(fieldConfig)).toBe('Email_Address');
  });

  it('resolves each conventional key when it is the only email-ish field', () => {
    for (const key of CONVENTIONAL_EMAIL_KEYS) {
      expect(resolveEmailField(keysConfig(['name', key]))).toBe(key);
    }
  });

  it('returns undefined when no email field resolves', () => {
    expect(resolveEmailField(keysConfig(['name', 'phone']))).toBeUndefined();
  });

  it('returns undefined for an undefined / empty field config', () => {
    expect(resolveEmailField(undefined)).toBeUndefined();
    expect(resolveEmailField({ fields: [] })).toBeUndefined();
  });

  it('never consults any analytics role config (field-config only)', () => {
    // Even if a stray `analytics`-looking member were present, the resolver reads
    // ONLY `fields`. A config with no email-ish field resolves to undefined.
    const fieldConfig = {
      fields: [{ key: 'opzegdatum' }],
      // A leftover block must not influence resolution — only `fields` is read.
      analytics: { field_roles: { email: 'opzegdatum' } },
    } as unknown as FieldConfig;
    expect(resolveEmailField(fieldConfig)).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// applyDefinitionFilters — generic saved-set equality filters (R4.4). This is
// the single generic mechanism through which every subset the removed presets
// used to offer is now rebuilt (clubblad equality, jubilee years-member
// equality, joined-after via the user's own filter, …).
// ---------------------------------------------------------------------------
describe('analyticsConfig.applyDefinitionFilters', () => {
  const rows: MemberRow[] = [
    { member_id: '1', clubblad: 'Papier' },
    { member_id: '2', clubblad: 'Digitaal' },
    { member_id: '3', clubblad: 'papier' }, // case-insensitive match
    { member_id: '4' }, // absent → excluded
  ] as unknown as MemberRow[];
  const fieldConfig = keysConfig(['clubblad']);

  it('narrows rows to those whose field equals the filter value (case-insensitive, trimmed)', () => {
    const result = applyDefinitionFilters(rows, { clubblad: ' papier ' }, fieldConfig);
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['1', '3']);
  });

  it('returns all rows when no filters are set (or filters is undefined)', () => {
    expect(applyDefinitionFilters(rows, undefined, fieldConfig)).toHaveLength(rows.length);
    expect(applyDefinitionFilters(rows, {}, fieldConfig)).toHaveLength(rows.length);
  });

  it('treats a blank filter value as no narrowing', () => {
    expect(applyDefinitionFilters(rows, { clubblad: '' }, fieldConfig)).toHaveLength(rows.length);
    expect(applyDefinitionFilters(rows, { clubblad: null }, fieldConfig)).toHaveLength(
      rows.length,
    );
    expect(
      applyDefinitionFilters(rows, { clubblad: undefined }, fieldConfig),
    ).toHaveLength(rows.length);
  });

  it('rebuilds a jubilee subset: a generic equality filter on the calculated years-member field', () => {
    // The removed Jubilees preset is now just a generic equality filter on the
    // calculated `years_member` field — no dedicated year selector.
    const jubileeRows: MemberRow[] = [
      { member_id: 'a', years_member: '25' },
      { member_id: 'b', years_member: '40' },
      { member_id: 'c', years_member: 25 }, // numeric matches stringified filter
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(
      jubileeRows,
      { years_member: 25 },
      keysConfig(['years_member']),
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['a', 'c']);
  });

  it('matches a numeric filter against a stringified value and vice versa', () => {
    const mixed: MemberRow[] = [
      { member_id: '1', count: 1 },
      { member_id: '2', count: '1' },
      { member_id: '3', count: 2 },
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(mixed, { count: '1' }, keysConfig(['count']));
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['1', '2']);
  });

  it('reads a nested field value via valueFor + the storage group', () => {
    const nestedRows: MemberRow[] = [
      { member_id: '1', membership: { clubblad: 'Papier' } },
      { member_id: '2', membership: { clubblad: 'Digitaal' } },
    ] as unknown as MemberRow[];
    const nestedConfig: FieldConfig = {
      fields: [{ key: 'clubblad', group: 'membership' }] as FieldConfigField[],
    };
    const result = applyDefinitionFilters(nestedRows, { clubblad: 'Papier' }, nestedConfig);
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['1']);
  });

  it('applies multiple filters with AND semantics', () => {
    const multiRows: MemberRow[] = [
      { member_id: '1', clubblad: 'Papier', country: 'NL' },
      { member_id: '2', clubblad: 'Papier', country: 'BE' },
      { member_id: '3', clubblad: 'Digitaal', country: 'NL' },
    ] as unknown as MemberRow[];
    const multiConfig = keysConfig(['clubblad', 'country']);
    const result = applyDefinitionFilters(
      multiRows,
      { clubblad: 'Papier', country: 'NL' },
      multiConfig,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['1']);
  });

  it('does not mutate the input rows', () => {
    const snapshot = JSON.stringify(rows);
    applyDefinitionFilters(rows, { clubblad: 'Papier' }, fieldConfig);
    expect(JSON.stringify(rows)).toBe(snapshot);
  });

  it('handles a non-array rows input safely', () => {
    expect(
      applyDefinitionFilters(undefined as unknown as MemberRow[], { clubblad: 'Papier' }, fieldConfig),
    ).toEqual([]);
  });

  it('handles a null / non-object rows input safely', () => {
    // Any non-array rows input is treated as [] (never crashes).
    expect(
      applyDefinitionFilters(null as unknown as MemberRow[], { clubblad: 'Papier' }, fieldConfig),
    ).toEqual([]);
    expect(
      applyDefinitionFilters(
        { not: 'an array' } as unknown as MemberRow[],
        { clubblad: 'Papier' },
        fieldConfig,
      ),
    ).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// applyDefinitionFilters — operator-aware narrowing (member-analytics filter
// contract, R5.1–5.13, R6.*, R7.5/7.6, R8.1). A filter entry is either the new
// object form `{ op, value? }` or a legacy scalar (reads as `eq`). The eq cases
// above remain the legacy default; the cases below exercise the explicit
// operators. ids used throughout are stable so the asserted order documents the
// order-preserving contract.
// ---------------------------------------------------------------------------
describe('analyticsConfig.applyDefinitionFilters — operators', () => {
  /** Project member_ids out of a result for compact order-preserving assertions. */
  const ids = (result: MemberRow[]): unknown[] =>
    result.map((r) => (r as Record<string, unknown>).member_id);

  // --- legacy scalar still reads as eq (R8.1) ---------------------------------
  it('reads a legacy scalar entry as an eq clause (backward compatible)', () => {
    const rows: MemberRow[] = [
      { member_id: '1', clubblad: 'Papier' },
      { member_id: '2', clubblad: 'Digitaal' },
      { member_id: '3', clubblad: ' papier ' }, // trimmed + case-insensitive eq
    ] as unknown as MemberRow[];
    const legacy = applyDefinitionFilters(rows, { clubblad: 'Papier' }, keysConfig(['clubblad']));
    const objectEq = applyDefinitionFilters(
      rows,
      { clubblad: { op: 'eq', value: 'Papier' } },
      keysConfig(['clubblad']),
    );
    // The legacy scalar narrows identically to the explicit object-eq form.
    expect(ids(legacy)).toEqual(['1', '3']);
    expect(ids(objectEq)).toEqual(ids(legacy));
  });

  // --- ne (R5.1 / 5.2) --------------------------------------------------------
  it('ne excludes rows equal to the value and keeps the rest (present cells only)', () => {
    const rows: MemberRow[] = [
      { member_id: '1', clubblad: 'Papier' },
      { member_id: '2', clubblad: 'Digitaal' },
      { member_id: '3', clubblad: 'papier' }, // case-insensitive eq → excluded by ne
      { member_id: '4' }, // absent cell → excluded (value-taking op never matches absent)
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(
      rows,
      { clubblad: { op: 'ne', value: 'Papier' } },
      keysConfig(['clubblad']),
    );
    expect(ids(result)).toEqual(['2']);
  });

  // --- contains (R5.3) --------------------------------------------------------
  it('contains matches a case-insensitive substring', () => {
    const rows: MemberRow[] = [
      { member_id: '1', name: 'Jan de Vries' },
      { member_id: '2', name: 'Piet Jansen' }, // 'jan' substring (case-insensitive)
      { member_id: '3', name: 'Klaas' },
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(
      rows,
      { name: { op: 'contains', value: 'jan' } },
      keysConfig(['name']),
    );
    expect(ids(result)).toEqual(['1', '2']);
  });

  // --- notContains (R5.12 / 5.13) --------------------------------------------
  it('notContains is the complement of contains for present cells and excludes absent cells', () => {
    const rows: MemberRow[] = [
      { member_id: '1', name: 'Jan de Vries' }, // contains 'jan' → excluded
      { member_id: '2', name: 'Piet Jansen' }, // contains 'jan' → excluded
      { member_id: '3', name: 'Klaas' }, // keeps
      { member_id: '4' }, // absent cell → excluded (not "matches everything")
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(
      rows,
      { name: { op: 'notContains', value: 'jan' } },
      keysConfig(['name']),
    );
    expect(ids(result)).toEqual(['3']);
  });

  // --- typed ordering: numeric (R5.4 / 5.5 / 5.6) -----------------------------
  it('orders a number-typed field numerically (9 lt 10, gte 25 jubilee)', () => {
    const rows: MemberRow[] = [
      { member_id: '1', years_member: '9' },
      { member_id: '2', years_member: '10' },
      { member_id: '3', years_member: 25 }, // numeric cell
      { member_id: '4', years_member: '40' },
    ] as unknown as MemberRow[];
    const numericConfig = makeFieldConfig([{ key: 'years_member', type: 'number' }]);

    // '9' < '10' numerically (a string compare would make '9' > '10').
    const lt = applyDefinitionFilters(
      rows,
      { years_member: { op: 'lt', value: '10' } },
      numericConfig,
    );
    expect(ids(lt)).toEqual(['1']);

    // A generic jubilee list: years_member >= 25.
    const gte = applyDefinitionFilters(
      rows,
      { years_member: { op: 'gte', value: '25' } },
      numericConfig,
    );
    expect(ids(gte)).toEqual(['3', '4']);
  });

  // --- typed ordering: date (R5.4 / 5.5 / 5.6) --------------------------------
  it('orders a date-typed field chronologically', () => {
    const rows: MemberRow[] = [
      { member_id: '1', joined_date: '2020-01-15' },
      { member_id: '2', joined_date: '2023-06-01' },
      { member_id: '3', joined_date: '2024-12-31' },
    ] as unknown as MemberRow[];
    const dateConfig = makeFieldConfig([{ key: 'joined_date', type: 'date' }]);
    const result = applyDefinitionFilters(
      rows,
      { joined_date: { op: 'gte', value: '2023-01-01' } },
      dateConfig,
    );
    expect(ids(result)).toEqual(['2', '3']);
  });

  // --- typed ordering: string fallback (R5.6) --------------------------------
  it('falls back to a locale string compare when the field is not numeric/date', () => {
    const rows: MemberRow[] = [
      { member_id: '1', clubblad: 'Apple' },
      { member_id: '2', clubblad: 'Mango' },
      { member_id: '3', clubblad: 'Zebra' },
    ] as unknown as MemberRow[];
    // Untyped field → locale string compare of the trimmed values.
    const result = applyDefinitionFilters(
      rows,
      { clubblad: { op: 'gt', value: 'Lemon' } },
      keysConfig(['clubblad']),
    );
    expect(ids(result)).toEqual(['2', '3']);
  });

  // --- empty / notEmpty (R5.7 / 5.8) -----------------------------------------
  it('empty / notEmpty partition rows by presence (no value input consumed)', () => {
    const rows: MemberRow[] = [
      { member_id: '1', clubblad: 'Papier' },
      { member_id: '2', clubblad: '' }, // blank → empty
      { member_id: '3', clubblad: '   ' }, // whitespace-only → empty
      { member_id: '4' }, // absent → empty
      { member_id: '5', clubblad: 'Digitaal' },
    ] as unknown as MemberRow[];
    const config = keysConfig(['clubblad']);

    const empty = applyDefinitionFilters(rows, { clubblad: { op: 'empty' } }, config);
    expect(ids(empty)).toEqual(['2', '3', '4']);

    const notEmpty = applyDefinitionFilters(rows, { clubblad: { op: 'notEmpty' } }, config);
    expect(ids(notEmpty)).toEqual(['1', '5']);
  });

  // --- AND semantics across operators (R5.9) ----------------------------------
  it('applies multiple operator clauses with AND semantics', () => {
    const rows: MemberRow[] = [
      { member_id: '1', years_member: '30', clubblad: 'Papier' },
      { member_id: '2', years_member: '30', clubblad: 'Digitaal' },
      { member_id: '3', years_member: '10', clubblad: 'Papier' },
    ] as unknown as MemberRow[];
    const config = makeFieldConfig([
      { key: 'years_member', type: 'number' },
      { key: 'clubblad' },
    ]);
    // years_member >= 25 AND clubblad contains 'pap'.
    const result = applyDefinitionFilters(
      rows,
      {
        years_member: { op: 'gte', value: '25' },
        clubblad: { op: 'contains', value: 'pap' },
      },
      config,
    );
    expect(ids(result)).toEqual(['1']);
  });

  // --- invalid regex never matches, never throws (R7.1 / 7.2) -----------------
  it('an invalid regex pattern matches no row for both regex and notRegex (never throws)', () => {
    const rows: MemberRow[] = [
      { member_id: '1', name: 'Alpha' },
      { member_id: '2', name: 'Beta' },
    ] as unknown as MemberRow[];
    const config = keysConfig(['name']);

    // '([' is an invalid pattern → never-match sentinel for BOTH forms.
    const regexResult = applyDefinitionFilters(
      rows,
      { name: { op: 'regex', value: '([' } },
      config,
    );
    expect(regexResult).toEqual([]);

    const notRegexResult = applyDefinitionFilters(
      rows,
      { name: { op: 'notRegex', value: '([' } },
      config,
    );
    // Invalid notRegex matches NOTHING too (never "match everything").
    expect(notRegexResult).toEqual([]);
  });

  // --- notRegex excludes rows matching a valid pattern (R7.5 / 7.6) -----------
  it('notRegex (valid pattern) excludes matching present cells and excludes absent cells', () => {
    const rows: MemberRow[] = [
      { member_id: '1', name: 'Jansen' }, // matches ^jan → excluded
      { member_id: '2', name: 'janssen' }, // case-insensitive match → excluded
      { member_id: '3', name: 'Pietersen' }, // no match → kept
      { member_id: '4' }, // absent → excluded (negation is on the comparison, not presence)
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(
      rows,
      { name: { op: 'notRegex', value: '^jan' } },
      keysConfig(['name']),
    );
    expect(ids(result)).toEqual(['3']);
  });

  // --- blank value never narrows for value-taking ops (R6.1 / 6.3) ------------
  it('a blank value on a value-taking operator never narrows', () => {
    const rows: MemberRow[] = [
      { member_id: '1', clubblad: 'Papier' },
      { member_id: '2', clubblad: 'Digitaal' },
      { member_id: '3' },
    ] as unknown as MemberRow[];
    const config = keysConfig(['clubblad']);
    // A blank-value contains/ne/gte clause is inactive → all rows returned.
    expect(
      applyDefinitionFilters(rows, { clubblad: { op: 'contains', value: '' } }, config),
    ).toHaveLength(rows.length);
    expect(
      applyDefinitionFilters(rows, { clubblad: { op: 'ne', value: '  ' } }, config),
    ).toHaveLength(rows.length);
    expect(
      applyDefinitionFilters(rows, { clubblad: { op: 'gte' } }, config),
    ).toHaveLength(rows.length);
  });

  // --- unknown operator clamps to eq (R8.3, documents normalizeClause) --------
  it('clamps an unknown stored operator to eq', () => {
    const rows: MemberRow[] = [
      { member_id: '1', clubblad: 'Papier' },
      { member_id: '2', clubblad: 'Digitaal' },
    ] as unknown as MemberRow[];
    const result = applyDefinitionFilters(
      rows,
      { clubblad: { op: 'bogus', value: 'Papier' } as unknown as never },
      keysConfig(['clubblad']),
    );
    expect(ids(result)).toEqual(['1']);
  });

  // --- order-preserving + pure across operators (R5.10 / 5.11 / 6.4) ----------
  it('preserves row order and does not mutate inputs across operators', () => {
    const rows: MemberRow[] = [
      { member_id: '3', years_member: '40' },
      { member_id: '1', years_member: '25' },
      { member_id: '2', years_member: '30' },
    ] as unknown as MemberRow[];
    const snapshot = JSON.stringify(rows);
    const result = applyDefinitionFilters(
      rows,
      { years_member: { op: 'gte', value: '25' } },
      makeFieldConfig([{ key: 'years_member', type: 'number' }]),
    );
    // Input order preserved (not sorted by value).
    expect(ids(result)).toEqual(['3', '1', '2']);
    // Inputs untouched.
    expect(JSON.stringify(rows)).toBe(snapshot);
  });
});
