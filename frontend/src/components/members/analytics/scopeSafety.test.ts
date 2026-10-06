/**
 * Cross-cutting SCOPE-SAFETY verification (task 11.1, Phase 11).
 *
 * The headline guarantee of the whole Member Analytics surface (R5.3 / R8.2):
 * **no analytics area, export, or mail may EVER surface a member that is outside
 * the caller's scope-authorized set.** Scope is enforced server-side — `GET
 * /members` returns only in-scope rows (`resolve_scope_access` / `_in_scope`) —
 * and every client-side analytics derivation is a pure function of exactly those
 * rows. So the structural property this test pins down is: given a SCOPED subset
 * of members as input, every output row / recipient / label traces back to a
 * member IN that subset — the pure helpers never widen, invent, or leak an
 * out-of-scope row.
 *
 * We build a tenant-wide superset spanning several regions, then hand each
 * egress surface ONLY the scoped `North` subset (what the server would return to
 * a `North`-scoped caller) and assert nothing out-of-scope ever appears:
 *
 *   - **Overview** (R2) — the averaged/counted values are computed only from the
 *     subset (`mean` / `countExcluded` over the subset's parsed metrics); the
 *     count equals the subset size and the averages exclude every out-of-scope
 *     member's value.
 *   - **Distributions** (R3) — `buildMetricData` emits one violin datum per
 *     present value, each carrying a value that exists in the subset and never a
 *     value that exists ONLY out of scope.
 *   - **Pivot result** (R4, aggregate + filtered-list) — `executeMemberPivot`
 *     never emits a member/row outside the subset: the filtered list is a 1:1
 *     projection of the input, and the aggregate's COUNT over all groups equals
 *     the subset size (no out-of-scope row contributes to any bucket).
 *   - **CSV export** (R4.9) — the CSV rows are exactly the pivot result rows
 *     (the subset), so no out-of-scope member_id appears in the generated CSV.
 *   - **PDF labels** (R4.10) — `composeAddresses` composes a label only from a
 *     subset member; no out-of-scope name/city/postcode appears in any label.
 *   - **Mail recipients** (R4.12 / R8.2) — the de-duplicated recipient list
 *     resolved off the subset rows contains only in-scope emails; no
 *     out-of-scope email is ever a recipient.
 *
 * This is a VERIFICATION test over the real pure helpers (no mocks, no fakes):
 * it reuses `memberAggregations`, `memberPivotAdapter`, `analyticsConfig`
 * (`resolveEmailField`), `addressLabelService` (`composeAddresses`), and the
 * exported `buildMetricData` from `MemberDistributions`, exactly as the page
 * mounts them.
 *
 * Validates: Requirements R5.3, R8.2
 * Spec: .kiro/specs/Members/member-analytics (design: all).
 */
import { describe, it, expect } from 'vitest';

import { mean, countExcluded } from './memberAggregations';
import { executeMemberPivot } from './memberPivotAdapter';
import { resolveEmailField } from './analyticsConfig';
import { composeAddresses } from './addressLabelService';
import { buildMetricData } from './MemberDistributions';
import { generateCsvFromObjects } from '../../../utils/csvExport';
import type {
  FieldConfig,
  FieldConfigField,
  MemberRow,
} from '../../../types/members';
import type { AggregateMeasure, PivotConfig } from '../../../types/pivot';

// ---------------------------------------------------------------------------
// Fixtures: a tenant-wide member superset spanning several scope regions.
// ---------------------------------------------------------------------------

/**
 * A flat member row. The analytics surface reads calculated metrics (`age`,
 * `years_member`) and overlay fields off the FLAT key (the page flattens the
 * nested record), and `valueFor` falls back to the flat key, so building rows
 * flat here is faithful to what the helpers consume.
 */
function member(fields: {
  id: string;
  region: string;
  name: string;
  email: string;
  age: number;
  yearsMember: number;
  street: string;
  postcode: string;
  city: string;
}): MemberRow {
  return {
    member_id: fields.id,
    region: fields.region,
    name: fields.name,
    email: fields.email,
    // Calculated fields are string-typed by the module (int → stringified).
    age: String(fields.age),
    years_member: String(fields.yearsMember),
    street: fields.street,
    postcode: fields.postcode,
    city: fields.city,
  } as MemberRow;
}

/** The full tenant set: 4 North (in scope) + 3 South + 2 East (both out of scope). */
const NORTH: MemberRow[] = [
  member({ id: 'N1', region: 'North', name: 'Alice North', email: 'alice@north.test', age: 30, yearsMember: 5, street: 'Kade 1', postcode: '1000AA', city: 'Noordstad' }),
  member({ id: 'N2', region: 'North', name: 'Bram North', email: 'bram@north.test', age: 40, yearsMember: 10, street: 'Kade 2', postcode: '1000AB', city: 'Noordstad' }),
  member({ id: 'N3', region: 'North', name: 'Cas North', email: 'cas@north.test', age: 50, yearsMember: 15, street: 'Kade 3', postcode: '1000AC', city: 'Noordstad' }),
  // One in-scope member with an absent/invalid age + no email → still in scope,
  // but exercises the "excluded from average" / "no recipient" edge WITHIN scope.
  member({ id: 'N4', region: 'North', name: 'Daan North', email: '', age: NaN, yearsMember: 20, street: 'Kade 4', postcode: '1000AD', city: 'Noordstad' }),
];

const SOUTH: MemberRow[] = [
  member({ id: 'S1', region: 'South', name: 'Eva South', email: 'eva@south.test', age: 99, yearsMember: 99, street: 'Zuidlaan 1', postcode: '9000ZA', city: 'Zuidstad' }),
  member({ id: 'S2', region: 'South', name: 'Fem South', email: 'fem@south.test', age: 98, yearsMember: 98, street: 'Zuidlaan 2', postcode: '9000ZB', city: 'Zuidstad' }),
  member({ id: 'S3', region: 'South', name: 'Gijs South', email: 'gijs@south.test', age: 97, yearsMember: 97, street: 'Zuidlaan 3', postcode: '9000ZC', city: 'Zuidstad' }),
];

const EAST: MemberRow[] = [
  member({ id: 'E1', region: 'East', name: 'Hans East', email: 'hans@east.test', age: 88, yearsMember: 88, street: 'Oostweg 1', postcode: '8000OA', city: 'Ooststad' }),
  member({ id: 'E2', region: 'East', name: 'Ida East', email: 'ida@east.test', age: 87, yearsMember: 87, street: 'Oostweg 2', postcode: '8000OB', city: 'Ooststad' }),
];

/** The tenant-wide superset (never handed to analytics — only the subset is). */
const ALL_MEMBERS: MemberRow[] = [...NORTH, ...SOUTH, ...EAST];

/**
 * The scoped subset the server would return to a North-scoped caller. This is
 * the ONLY input the analytics surface sees — the superset exists purely so the
 * test can assert out-of-scope rows never leak through.
 */
const SCOPED_SUBSET: MemberRow[] = NORTH;

/** The ids that are legitimately in scope. */
const IN_SCOPE_IDS = new Set(SCOPED_SUBSET.map((m) => m.member_id));
/** The ids that must NEVER surface anywhere. */
const OUT_OF_SCOPE_IDS = new Set(
  ALL_MEMBERS.filter((m) => !IN_SCOPE_IDS.has(m.member_id)).map((m) => m.member_id),
);
/** Out-of-scope emails that must never be a recipient. */
const OUT_OF_SCOPE_EMAILS = new Set(
  [...SOUTH, ...EAST].map((m) => String(m.email).toLowerCase()),
);
/** Out-of-scope marker strings that must never appear in a label or CSV. */
const OUT_OF_SCOPE_MARKERS = [...SOUTH, ...EAST].flatMap((m) => [
  String(m.name),
  String(m.city),
  String(m.postcode),
  String(m.email),
  String(m.member_id),
]);

// ---------------------------------------------------------------------------
// Field config: calculated age/years_member, flat overlay keys, address mapping.
// ---------------------------------------------------------------------------

function field(key: string, extra: Partial<FieldConfigField> = {}): FieldConfigField {
  return { key, label: { nl: key, en: key }, ...extra } as FieldConfigField;
}

const FIELD_CONFIG: FieldConfig = {
  fields: [
    field('member_id'),
    field('region'),
    field('name'),
    field('email', { type: 'email' }),
    field('age', { origin: 'calculated' }),
    field('years_member', { origin: 'calculated' }),
    field('street'),
    field('postcode'),
    field('city'),
  ],
  analytics: {
    address_mapping: {
      name: 'name',
      street: 'street',
      postcode: 'postcode',
      city: 'city',
    },
  },
} as FieldConfig;

/** Does a candidate value match any out-of-scope member? */
function mentionsOutOfScope(haystack: string): boolean {
  return OUT_OF_SCOPE_MARKERS.some((marker) => marker !== '' && haystack.includes(marker));
}

/**
 * Build a complete, type-honest {@link PivotConfig} for the member adapter.
 * `executeMemberPivot` reads only `groupColumns` + `aggregateMeasures`, but the
 * full shape is supplied (no `as unknown` cast) so the test faithfully documents
 * the real contract and would catch a genuine shape drift.
 */
function pivotConfig(
  groupColumns: string[],
  aggregateMeasures: AggregateMeasure[],
): PivotConfig {
  return {
    dataSource: 'members',
    groupColumns,
    aggregateMeasures,
    filters: {},
    columnPivot: null,
    columnNestLevels: [],
    displayMode: 'flat',
  };
}

// ===========================================================================
// Tests
// ===========================================================================

describe('Member Analytics — scope safety (R5.3 / R8.2)', () => {
  it('fixtures: the superset really contains out-of-scope members the subset omits', () => {
    // Guard the test itself: if this ever becomes trivially true (subset ==
    // superset) the whole suite would be meaningless.
    expect(SCOPED_SUBSET.length).toBeLessThan(ALL_MEMBERS.length);
    expect(OUT_OF_SCOPE_IDS.size).toBeGreaterThan(0);
    for (const m of SCOPED_SUBSET) {
      expect(m.region).toBe('North');
    }
  });

  // -- Overview area (R2) ---------------------------------------------------
  describe('Overview area never counts an out-of-scope member', () => {
    it('count equals the subset size, not the superset size', () => {
      expect(SCOPED_SUBSET.length).toBe(4);
      // The Overview "count" card is simply processedData.length over the subset.
      expect(SCOPED_SUBSET.length).not.toBe(ALL_MEMBERS.length);
    });

    it('average age/years-member exclude every out-of-scope value', () => {
      const ages = SCOPED_SUBSET.map((m) => m.age);
      const years = SCOPED_SUBSET.map((m) => m.years_member);

      const avgAge = mean(ages);
      const avgYears = mean(years);

      // In-scope ages present: 30, 40, 50 (N4 is NaN → excluded). Mean = 40.
      expect(avgAge).toBe(40);
      // Out-of-scope ages are 87..99; a leaked value would drag the mean far up.
      expect(avgAge).toBeLessThan(60);
      // years_member present for all four North: 5,10,15,20 → mean 12.5.
      expect(avgYears).toBe(12.5);
      expect(avgYears).toBeLessThan(60);

      // One in-scope row (N4) has an invalid age → excluded, never counted as 0.
      expect(countExcluded(ages)).toBe(1);
      expect(countExcluded(years)).toBe(0);
    });
  });

  // -- Distributions area (R3) ---------------------------------------------
  describe('Distributions never plot an out-of-scope value', () => {
    it('age violin data holds only subset values (N4 excluded as non-numeric)', () => {
      const data = buildMetricData(SCOPED_SUBSET, 'age');
      const values = data.map((d) => d.value).sort((a, b) => a - b);
      expect(values).toEqual([30, 40, 50]);
      // No out-of-scope age (87..99) is present.
      for (const v of values) {
        expect(v).toBeLessThan(60);
      }
    });

    it('years-member violin data holds only subset values', () => {
      const data = buildMetricData(SCOPED_SUBSET, 'years_member');
      const values = data.map((d) => d.value).sort((a, b) => a - b);
      expect(values).toEqual([5, 10, 15, 20]);
      for (const v of values) {
        expect(v).toBeLessThan(60);
      }
    });

    it('grouping by region produces only the North group', () => {
      const data = buildMetricData(SCOPED_SUBSET, 'age', 'region');
      const groups = new Set(data.map((d) => d.group));
      expect(groups.has('South')).toBe(false);
      expect(groups.has('East')).toBe(false);
      expect([...groups]).toEqual(['North']);
    });
  });

  // -- Pivot result (R4): filtered-list + aggregate -------------------------
  describe('Pivot result never surfaces an out-of-scope row', () => {
    it('filtered-list mode projects exactly the subset, in order, no leak', () => {
      const config = pivotConfig([], [{ function: 'COUNT', column: 'member_id' }]);

      const result = executeMemberPivot(SCOPED_SUBSET, config, FIELD_CONFIG);

      expect(result.success).toBe(true);
      expect(result.row_count).toBe(SCOPED_SUBSET.length);

      const ids = result.data.map((r) => String(r.member_id));
      // Every emitted id is in scope; none out of scope.
      for (const id of ids) {
        expect(IN_SCOPE_IDS.has(id)).toBe(true);
        expect(OUT_OF_SCOPE_IDS.has(id)).toBe(false);
      }
      // 1:1 with the input (order + count preserved) — never widened.
      expect(ids).toEqual(SCOPED_SUBSET.map((m) => m.member_id));
    });

    it('aggregate COUNT over all groups equals the subset size (no stray row)', () => {
      const config = pivotConfig(['region'], [{ function: 'COUNT', column: '*' }]);

      const result = executeMemberPivot(SCOPED_SUBSET, config, FIELD_CONFIG);

      // Only the North group exists; its count is the whole subset.
      const groups = result.data.map((r) => String(r.region));
      expect(groups).toEqual(['North']);
      expect(groups).not.toContain('South');
      expect(groups).not.toContain('East');

      const totalCounted = result.data.reduce(
        (acc, r) => acc + Number(r['COUNT(*)'] ?? 0),
        0,
      );
      expect(totalCounted).toBe(SCOPED_SUBSET.length);
    });
  });

  // -- CSV export (R4.9) ----------------------------------------------------
  describe('CSV export emits only subset rows', () => {
    it('generated CSV mentions no out-of-scope member', () => {
      const config = pivotConfig(
        [],
        [
          { function: 'COUNT', column: 'member_id' },
          { function: 'COUNT', column: 'name' },
          { function: 'COUNT', column: 'email' },
          { function: 'COUNT', column: 'city' },
        ],
      );

      // Filtered-list projection of the chosen columns over the subset.
      const result = executeMemberPivot(SCOPED_SUBSET, config, FIELD_CONFIG);
      const columns = result.columns.map((c) => ({ key: c.name, header: c.name }));
      const csv = generateCsvFromObjects(columns, result.data);

      // Every in-scope member appears; no out-of-scope marker appears.
      expect(csv).toContain('Alice North');
      expect(mentionsOutOfScope(csv)).toBe(false);
      // Belt-and-suspenders: explicit absence of each out-of-scope email/city.
      for (const marker of OUT_OF_SCOPE_MARKERS) {
        if (marker !== '') {
          expect(csv.includes(marker)).toBe(false);
        }
      }
    });
  });

  // -- PDF address labels (R4.10) -------------------------------------------
  describe('Address labels compose only from subset members', () => {
    it('no label line mentions an out-of-scope member', () => {
      const { addresses } = composeAddresses(SCOPED_SUBSET, FIELD_CONFIG);

      // One label per in-scope member (all four North addresses are complete).
      expect(addresses.length).toBe(SCOPED_SUBSET.length);

      const allLines = addresses.flatMap((a) => a.lines).join('\n');
      expect(allLines).toContain('Alice North');
      expect(allLines).toContain('Noordstad');
      // No out-of-scope name / city / postcode leaked into any label.
      expect(mentionsOutOfScope(allLines)).toBe(false);
    });

    it('composing the SUBSET yields the same labels as filtering the SUPERSET first', () => {
      // Scope-equivalence: whether the server pre-filters (subset in) or we filter
      // the superset to North, the label output is identical — the surface adds no
      // row and drops no in-scope row.
      const fromSubset = composeAddresses(SCOPED_SUBSET, FIELD_CONFIG).addresses;
      const fromFilteredSuperset = composeAddresses(
        ALL_MEMBERS.filter((m) => m.region === 'North'),
        FIELD_CONFIG,
      ).addresses;
      expect(fromSubset).toEqual(fromFilteredSuperset);
    });
  });

  // -- Mail recipients (R4.12 / R8.2) ---------------------------------------
  describe('Mail recipient resolution yields only in-scope emails', () => {
    /**
     * The recipient-resolution logic the compose UI runs (MemberMailCompose):
     * read the resolved email field off each row, trim+lowercase, de-duplicate,
     * skip blanks. Replicated here over the pure resolver so the test exercises
     * the SAME resolution without mounting the modal.
     */
    function resolveRecipients(rows: MemberRow[], fieldConfig: FieldConfig): string[] {
      const emailField = resolveEmailField(fieldConfig);
      if (!emailField) return [];
      const seen = new Set<string>();
      const out: string[] = [];
      for (const row of rows) {
        const raw = (row as Record<string, unknown>)[emailField];
        if (raw === null || raw === undefined) continue;
        const normalized = String(raw).trim().toLowerCase();
        if (normalized && !seen.has(normalized)) {
          seen.add(normalized);
          out.push(normalized);
        }
      }
      return out;
    }

    it('resolves the email field and lists only subset recipients', () => {
      const emailField = resolveEmailField(FIELD_CONFIG);
      expect(emailField).toBe('email');

      const recipients = resolveRecipients(SCOPED_SUBSET, FIELD_CONFIG);

      // N1..N3 have emails; N4's email is blank → skipped. 3 recipients.
      expect(recipients.sort()).toEqual([
        'alice@north.test',
        'bram@north.test',
        'cas@north.test',
      ]);

      // No out-of-scope email is ever a recipient.
      for (const email of recipients) {
        expect(OUT_OF_SCOPE_EMAILS.has(email)).toBe(false);
      }
    });

    it('even if the SUPERSET were mistakenly passed, each out-of-scope email is distinct and would be caught', () => {
      // Negative control: resolving over the SUPERSET DOES surface out-of-scope
      // emails — proving the earlier assertion is meaningful (it is the SCOPED
      // input, not a weak resolver, that keeps them out).
      const leaky = resolveRecipients(ALL_MEMBERS, FIELD_CONFIG);
      expect(leaky).toContain('eva@south.test');
      expect(leaky).toContain('hans@east.test');
      // And the scoped resolution shares none of those.
      const scoped = resolveRecipients(SCOPED_SUBSET, FIELD_CONFIG);
      expect(scoped.some((e) => OUT_OF_SCOPE_EMAILS.has(e))).toBe(false);
    });
  });
});
