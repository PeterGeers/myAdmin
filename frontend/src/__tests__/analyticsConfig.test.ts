/**
 * Unit tests for the Member Analytics config-consumption helpers.
 *
 * The role / jubilee-rule / address-mapping helpers were removed (superseded by
 * the generic Dynamic Pivot Views mechanism). What remains, and is covered here:
 *   - `resolveEmailField`: recipient-email resolution from the field config
 *     alone — a field typed `email` wins, else a conventional email key, in
 *     priority order; `undefined` when none resolves (R4.12).
 *   - `applyDefinitionFilters`: generic equality definition filters — the
 *     mechanism through which every subset the removed presets used to offer
 *     (clubblad, jubilee years, joined-after, …) is now rebuilt generically
 *     (R4.4): case-insensitive/trimmed narrowing, blank-value no-narrow, nested
 *     storage group, AND semantics, purity.
 *
 * Spec: `.kiro/specs/Members/members-analytics-role-removal`.
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
});
