/**
 * Unit tests for the Member Analytics config-consumption helpers (C-CONFIG).
 *
 * Covers:
 *   - `resolveRole`: role→key resolution — mapped+present, mapped-but-absent,
 *     unmapped, and absent-config cases (R9.3 / R4.3).
 *   - `isJubileeYear`: configured `years` set vs. `multiple_of` rule vs. the
 *     default multiples-of-5 when the rule / block is absent (R9.2).
 *   - `resolveAddressMapping`: slot→key resolution incl. absent mapping and
 *     dangling (mapped-but-absent) keys (R4.10).
 *
 * Spec: `.kiro/specs/Members/member-analytics` (design C-CONFIG; R9.2, R9.3, R6.5).
 */
import {
  resolveRole,
  isJubileeYear,
  candidateJubileeYears,
  selectedJubileeYear,
  applyJubileeYearFilter,
  resolveAddressMapping,
  DEFAULT_JUBILEE_MULTIPLE,
  MAX_JUBILEE_YEAR,
  JUBILEE_YEAR_FILTER_KEY,
  candidateJoinedYears,
  selectedJoinedAfterYear,
  applyJoinedAfterFilter,
  JOINED_AFTER_FILTER_KEY,
  applyDefinitionFilters,
} from '../components/members/analytics/analyticsConfig';
import type { FieldConfig, MemberAnalyticsConfig, MemberRow } from '../types/members';

/** Build a FieldConfig with the given field keys + optional analytics block. */
function makeFieldConfig(
  keys: string[],
  analytics?: MemberAnalyticsConfig,
): FieldConfig {
  return {
    fields: keys.map((key) => ({ key })),
    ...(analytics ? { analytics } : {}),
  };
}

describe('analyticsConfig.resolveRole', () => {
  it('resolves a role mapped to a present field key', () => {
    const fieldConfig = makeFieldConfig(['opzegdatum', 'bron'], {
      field_roles: {
        cancellation_date: 'opzegdatum',
        referral_source: 'bron',
      },
    });
    expect(resolveRole(fieldConfig, 'cancellation_date')).toBe('opzegdatum');
    expect(resolveRole(fieldConfig, 'referral_source')).toBe('bron');
  });

  it('returns undefined for a role mapped to an absent field key (stale mapping)', () => {
    // The role is mapped, but the overlay field it points at is gone.
    const fieldConfig = makeFieldConfig(['name', 'email'], {
      field_roles: { cancellation_date: 'opzegdatum' },
    });
    expect(resolveRole(fieldConfig, 'cancellation_date')).toBeUndefined();
  });

  it('returns undefined for an unmapped role', () => {
    const fieldConfig = makeFieldConfig(['opzegdatum'], {
      field_roles: { cancellation_date: 'opzegdatum' },
    });
    // referral_source is not in field_roles at all.
    expect(resolveRole(fieldConfig, 'referral_source')).toBeUndefined();
  });

  it('returns undefined when there is no field_roles / analytics block', () => {
    expect(resolveRole(makeFieldConfig(['a']), 'clubblad_paper')).toBeUndefined();
    expect(
      resolveRole(makeFieldConfig(['a'], {}), 'clubblad_paper'),
    ).toBeUndefined();
    expect(
      resolveRole(makeFieldConfig(['a'], { field_roles: {} }), 'clubblad_paper'),
    ).toBeUndefined();
  });

  it('returns undefined for an undefined field config', () => {
    expect(resolveRole(undefined, 'country_detail')).toBeUndefined();
  });
});

describe('analyticsConfig.isJubileeYear', () => {
  describe('configured years set', () => {
    const rule: MemberAnalyticsConfig['jubilee_rule'] = { years: [25, 40, 50] };

    it('is a jubilee only for a value in the set', () => {
      expect(isJubileeYear(25, rule)).toBe(true);
      expect(isJubileeYear(40, rule)).toBe(true);
      expect(isJubileeYear(50, rule)).toBe(true);
    });

    it('is not a jubilee for a value outside the set', () => {
      expect(isJubileeYear(5, rule)).toBe(false);
      expect(isJubileeYear(10, rule)).toBe(false);
      expect(isJubileeYear(26, rule)).toBe(false);
    });

    it('treats the set as exhaustive (does not also apply multiple_of)', () => {
      // 10 is a multiple of 5 but NOT in the explicit set → not a jubilee.
      const combined: MemberAnalyticsConfig['jubilee_rule'] = {
        years: [25, 50],
        multiple_of: 5,
      };
      expect(isJubileeYear(10, combined)).toBe(false);
      expect(isJubileeYear(25, combined)).toBe(true);
    });
  });

  describe('multiple_of rule', () => {
    const rule: MemberAnalyticsConfig['jubilee_rule'] = { multiple_of: 10 };

    it('is a jubilee for positive multiples of N', () => {
      expect(isJubileeYear(10, rule)).toBe(true);
      expect(isJubileeYear(20, rule)).toBe(true);
      expect(isJubileeYear(100, rule)).toBe(true);
    });

    it('is not a jubilee for non-multiples', () => {
      expect(isJubileeYear(5, rule)).toBe(false);
      expect(isJubileeYear(15, rule)).toBe(false);
    });
  });

  describe('default rule (multiples of 5)', () => {
    it('defaults to multiples of 5 when the rule is absent', () => {
      expect(isJubileeYear(5)).toBe(true);
      expect(isJubileeYear(10)).toBe(true);
      expect(isJubileeYear(25)).toBe(true);
      expect(isJubileeYear(7)).toBe(false);
      expect(isJubileeYear(12)).toBe(false);
    });

    it('defaults when the block is empty or has no usable rule', () => {
      expect(isJubileeYear(15, {})).toBe(true);
      expect(isJubileeYear(15, { years: [] })).toBe(true);
      expect(isJubileeYear(15, { multiple_of: 0 })).toBe(true);
      expect(isJubileeYear(13, { years: [] })).toBe(false);
    });

    it('aligns with the exported default constant', () => {
      expect(DEFAULT_JUBILEE_MULTIPLE).toBe(5);
      expect(isJubileeYear(DEFAULT_JUBILEE_MULTIPLE)).toBe(true);
    });
  });

  describe('input guards', () => {
    it('is never a jubilee for zero, negative, non-integer or non-finite input', () => {
      expect(isJubileeYear(0)).toBe(false);
      expect(isJubileeYear(0, { years: [0] })).toBe(false);
      expect(isJubileeYear(-5)).toBe(false);
      expect(isJubileeYear(2.5, { multiple_of: 2.5 })).toBe(false);
      expect(isJubileeYear(NaN)).toBe(false);
      expect(isJubileeYear(Infinity)).toBe(false);
    });
  });
});

describe('analyticsConfig.resolveAddressMapping', () => {
  it('resolves every mapped slot whose key is present', () => {
    const fieldConfig = makeFieldConfig(
      ['korte_naam', 'straat', 'postcode', 'woonplaats', 'land', 'regio'],
      {
        address_mapping: {
          name: 'korte_naam',
          street: 'straat',
          postcode: 'postcode',
          city: 'woonplaats',
          country: 'land',
          region: 'regio',
        },
      },
    );
    expect(resolveAddressMapping(fieldConfig)).toEqual({
      name: 'korte_naam',
      street: 'straat',
      postcode: 'postcode',
      city: 'woonplaats',
      country: 'land',
      region: 'regio',
    });
  });

  it('drops slots whose mapped key is absent from the field config', () => {
    const fieldConfig = makeFieldConfig(['korte_naam', 'straat'], {
      address_mapping: {
        name: 'korte_naam',
        street: 'straat',
        // these keys are not present in fields → dropped
        postcode: 'postcode',
        city: 'woonplaats',
      },
    });
    expect(resolveAddressMapping(fieldConfig)).toEqual({
      name: 'korte_naam',
      street: 'straat',
    });
  });

  it('returns an empty mapping when address_mapping is absent', () => {
    expect(resolveAddressMapping(makeFieldConfig(['korte_naam']))).toEqual({});
    expect(resolveAddressMapping(makeFieldConfig(['korte_naam'], {}))).toEqual({});
    expect(
      resolveAddressMapping(makeFieldConfig(['korte_naam'], { address_mapping: {} })),
    ).toEqual({});
  });

  it('returns an empty mapping for an undefined field config', () => {
    expect(resolveAddressMapping(undefined)).toEqual({});
  });

  it('returns an empty mapping when no mapped key resolves (labels unavailable)', () => {
    const fieldConfig = makeFieldConfig(['name', 'email'], {
      address_mapping: { name: 'korte_naam', street: 'straat' },
    });
    expect(resolveAddressMapping(fieldConfig)).toEqual({});
  });
});

describe('analyticsConfig.candidateJubileeYears', () => {
  describe('configured years set', () => {
    it('uses the configured set verbatim, sorted ascending', () => {
      expect(candidateJubileeYears({ years: [40, 25, 50] })).toEqual([25, 40, 50]);
    });

    it('de-duplicates and drops non-positive / non-integer entries', () => {
      expect(
        candidateJubileeYears({ years: [25, 25, 0, -5, 2.5, 50] }),
      ).toEqual([25, 50]);
    });

    it('is exhaustive — the multiple_of rule is NOT also enumerated', () => {
      // 10 is a multiple of 5 but not in the explicit set → not offered.
      const years = candidateJubileeYears({ years: [25, 50], multiple_of: 5 });
      expect(years).toEqual([25, 50]);
      expect(years).not.toContain(10);
    });

    it('every configured candidate also satisfies isJubileeYear', () => {
      const rule: MemberAnalyticsConfig['jubilee_rule'] = { years: [25, 40, 50] };
      for (const year of candidateJubileeYears(rule)) {
        expect(isJubileeYear(year, rule)).toBe(true);
      }
    });
  });

  describe('multiple_of rule', () => {
    it('enumerates multiples of N up to the ceiling', () => {
      expect(candidateJubileeYears({ multiple_of: 10 })).toEqual([
        10, 20, 30, 40, 50, 60, 70,
      ]);
    });

    it('respects a custom ceiling and includes it when it is a multiple', () => {
      expect(candidateJubileeYears({ multiple_of: 10 }, 30)).toEqual([10, 20, 30]);
      expect(candidateJubileeYears({ multiple_of: 10 }, 25)).toEqual([10, 20]);
    });

    it('every multiple_of candidate also satisfies isJubileeYear', () => {
      const rule: MemberAnalyticsConfig['jubilee_rule'] = { multiple_of: 10 };
      for (const year of candidateJubileeYears(rule)) {
        expect(isJubileeYear(year, rule)).toBe(true);
      }
    });
  });

  describe('default rule (multiples of 5)', () => {
    it('defaults to multiples of 5 when the rule / block is absent', () => {
      const expected: number[] = [];
      for (let y = DEFAULT_JUBILEE_MULTIPLE; y <= MAX_JUBILEE_YEAR; y += DEFAULT_JUBILEE_MULTIPLE) {
        expected.push(y);
      }
      expect(candidateJubileeYears()).toEqual(expected);
      expect(candidateJubileeYears(undefined)).toEqual(expected);
    });

    it('defaults when the block is empty or carries no usable rule', () => {
      expect(candidateJubileeYears({})).toEqual(candidateJubileeYears());
      expect(candidateJubileeYears({ years: [] })).toEqual(candidateJubileeYears());
      expect(candidateJubileeYears({ multiple_of: 0 })).toEqual(candidateJubileeYears());
      // A non-integer multiple cannot enumerate whole years → falls back to default.
      expect(candidateJubileeYears({ multiple_of: 2.5 })).toEqual(candidateJubileeYears());
    });

    it('always returns an ascending, duplicate-free, positive-integer list', () => {
      for (const rule of [undefined, { multiple_of: 5 }, { years: [50, 25, 25, 40] }]) {
        const years = candidateJubileeYears(rule as MemberAnalyticsConfig['jubilee_rule']);
        const ascending = [...years].sort((a, b) => a - b);
        expect(years).toEqual(ascending);
        expect(new Set(years).size).toBe(years.length);
        expect(years.every((y) => Number.isInteger(y) && y > 0)).toBe(true);
      }
    });
  });
});

describe('analyticsConfig.selectedJubileeYear', () => {
  it('reads a numeric year written into the filter map', () => {
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: 25 })).toBe(25);
  });

  it('parses a numeric string (round-tripped through a saved definition)', () => {
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: '40' })).toBe(40);
  });

  it('returns undefined when no year / an invalid year is set', () => {
    expect(selectedJubileeYear(undefined)).toBeUndefined();
    expect(selectedJubileeYear({})).toBeUndefined();
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: '' })).toBeUndefined();
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: 'abc' })).toBeUndefined();
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: 0 })).toBeUndefined();
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: -5 })).toBeUndefined();
    expect(selectedJubileeYear({ [JUBILEE_YEAR_FILTER_KEY]: 2.5 })).toBeUndefined();
  });
});

describe('analyticsConfig.applyJubileeYearFilter', () => {
  // years_member is a flat calculated field (no storage group).
  const fieldConfig = makeFieldConfig(['years_member']);
  const rows = [
    { member_id: 'a', years_member: '25' },
    { member_id: 'b', years_member: '40' },
    { member_id: 'c', years_member: '25' },
    { member_id: 'd', years_member: '26' },
  ] as unknown as MemberRow[];

  it('keeps only members whose years_member equals the chosen year', () => {
    const result = applyJubileeYearFilter(
      rows,
      { [JUBILEE_YEAR_FILTER_KEY]: 25 },
      fieldConfig,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['a', 'c']);
  });

  it('matches a numeric filter against a stringified value (and vice versa)', () => {
    const result = applyJubileeYearFilter(
      rows,
      { [JUBILEE_YEAR_FILTER_KEY]: '40' },
      fieldConfig,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['b']);
  });

  it('returns all rows unchanged when no jubilee year is set', () => {
    expect(applyJubileeYearFilter(rows, undefined, fieldConfig)).toBe(rows);
    expect(applyJubileeYearFilter(rows, {}, fieldConfig)).toBe(rows);
  });

  it('reads a nested storage bucket when the field declares a group', () => {
    const grouped = {
      fields: [{ key: 'years_member', group: 'membership' }],
    } as unknown as FieldConfig;
    const nestedRows = [
      { member_id: 'x', membership: { years_member: 50 } },
      { member_id: 'y', membership: { years_member: 25 } },
    ] as unknown as MemberRow[];
    const result = applyJubileeYearFilter(
      nestedRows,
      { [JUBILEE_YEAR_FILTER_KEY]: 50 },
      grouped,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['x']);
  });

  it('does not mutate the input rows', () => {
    const copy = [...rows];
    applyJubileeYearFilter(rows, { [JUBILEE_YEAR_FILTER_KEY]: 25 }, fieldConfig);
    expect(rows).toEqual(copy);
  });
});

// ---------------------------------------------------------------------------
// Findings F-010: New-members "joined in or after <year>" filter.
// ---------------------------------------------------------------------------

describe('analyticsConfig.candidateJoinedYears', () => {
  it('lists the current year first, descending, back the default span', () => {
    const years = candidateJoinedYears(2026, 15);
    expect(years[0]).toBe(2026);
    expect(years[years.length - 1]).toBe(2011);
    expect(years).toHaveLength(16); // inclusive of both ends
    // Strictly descending.
    for (let i = 1; i < years.length; i += 1) {
      expect(years[i]).toBe(years[i - 1] - 1);
    }
  });

  it('respects a custom span', () => {
    expect(candidateJoinedYears(2026, 3)).toEqual([2026, 2025, 2024, 2023]);
  });
});

describe('analyticsConfig.selectedJoinedAfterYear', () => {
  it('reads a numeric year written into the filter map', () => {
    expect(selectedJoinedAfterYear({ [JOINED_AFTER_FILTER_KEY]: 2020 })).toBe(2020);
  });

  it('parses a round-tripped numeric string', () => {
    expect(selectedJoinedAfterYear({ [JOINED_AFTER_FILTER_KEY]: '2019' })).toBe(2019);
  });

  it('is undefined for an absent / blank / non-positive / non-integer value', () => {
    expect(selectedJoinedAfterYear(undefined)).toBeUndefined();
    expect(selectedJoinedAfterYear({})).toBeUndefined();
    expect(selectedJoinedAfterYear({ [JOINED_AFTER_FILTER_KEY]: '' })).toBeUndefined();
    expect(selectedJoinedAfterYear({ [JOINED_AFTER_FILTER_KEY]: 0 })).toBeUndefined();
    expect(selectedJoinedAfterYear({ [JOINED_AFTER_FILTER_KEY]: 2020.5 })).toBeUndefined();
    expect(selectedJoinedAfterYear({ [JOINED_AFTER_FILTER_KEY]: 'abc' })).toBeUndefined();
  });
});

describe('analyticsConfig.applyJoinedAfterFilter', () => {
  const fieldConfig = makeFieldConfig(['joined_date']);
  const rows = [
    { member_id: 'a', joined_date: '2018-03-01' },
    { member_id: 'b', joined_date: '2021-07-15' },
    { member_id: 'c', joined_date: '2024-01-10' },
    { member_id: 'd', joined_date: '' }, // no join date → excluded when filtered
  ] as unknown as MemberRow[];

  it('keeps only members who joined in or after the chosen year', () => {
    const result = applyJoinedAfterFilter(
      rows,
      { [JOINED_AFTER_FILTER_KEY]: 2021 },
      fieldConfig,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['b', 'c']);
  });

  it('includes a member who joined exactly in the chosen year (inclusive)', () => {
    const result = applyJoinedAfterFilter(
      rows,
      { [JOINED_AFTER_FILTER_KEY]: 2024 },
      fieldConfig,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['c']);
  });

  it('excludes members with an absent/unparseable join date when filtered', () => {
    const result = applyJoinedAfterFilter(
      rows,
      { [JOINED_AFTER_FILTER_KEY]: 2000 },
      fieldConfig,
    );
    // d (blank join date) drops out; a/b/c all joined after 2000.
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['a', 'b', 'c']);
  });

  it('returns all rows unchanged when no joined-after year is set', () => {
    expect(applyJoinedAfterFilter(rows, undefined, fieldConfig)).toBe(rows);
    expect(applyJoinedAfterFilter(rows, {}, fieldConfig)).toBe(rows);
  });

  it('reads a nested joined_date storage bucket when the field declares a group', () => {
    const grouped = {
      fields: [{ key: 'joined_date', group: 'membership' }],
    } as unknown as FieldConfig;
    const nestedRows = [
      { member_id: 'x', membership: { joined_date: '2022-05-01' } },
      { member_id: 'y', membership: { joined_date: '2015-05-01' } },
    ] as unknown as MemberRow[];
    const result = applyJoinedAfterFilter(
      nestedRows,
      { [JOINED_AFTER_FILTER_KEY]: 2020 },
      grouped,
    );
    expect(result.map((r) => (r as Record<string, unknown>).member_id)).toEqual(['x']);
  });

  it('does not mutate the input rows', () => {
    const copy = [...rows];
    applyJoinedAfterFilter(rows, { [JOINED_AFTER_FILTER_KEY]: 2021 }, fieldConfig);
    expect(rows).toEqual(copy);
  });
});

// ---------------------------------------------------------------------------
// applyDefinitionFilters — generic saved-set equality filters (issue 3).
// ---------------------------------------------------------------------------
describe('analyticsConfig.applyDefinitionFilters', () => {
  const rows: MemberRow[] = [
    { member_id: '1', clubblad: 'Papier' },
    { member_id: '2', clubblad: 'Digitaal' },
    { member_id: '3', clubblad: 'papier' }, // case-insensitive match
    { member_id: '4' }, // absent → excluded
  ] as unknown as MemberRow[];
  const fieldConfig = makeFieldConfig(['clubblad']);

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
  });

  it('SKIPS the reserved jubilee / joined-after year keys (own appliers handle them)', () => {
    // A years_member/joined_after_year value must NOT be matched as a literal
    // equality filter here — it is a year handled by the dedicated appliers.
    const result = applyDefinitionFilters(
      rows,
      { [JUBILEE_YEAR_FILTER_KEY]: 25, [JOINED_AFTER_FILTER_KEY]: 2020 },
      fieldConfig,
    );
    expect(result).toHaveLength(rows.length);
  });

  it('reads a nested field value via valueFor + the storage group', () => {
    const nestedRows: MemberRow[] = [
      { member_id: '1', membership: { clubblad: 'Papier' } },
      { member_id: '2', membership: { clubblad: 'Digitaal' } },
    ] as unknown as MemberRow[];
    const nestedConfig: FieldConfig = {
      fields: [{ key: 'clubblad', group: 'membership' }],
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
    const multiConfig = makeFieldConfig(['clubblad', 'country']);
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
});
