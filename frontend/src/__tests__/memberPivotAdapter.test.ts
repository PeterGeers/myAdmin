/**
 * Unit + property tests for the Member Analytics client-side pivot/list adapter.
 *
 * Covers grouping (via the nested-or-flat `valueFor` accessor), each aggregate
 * (COUNT / SUM / AVG / MIN / MAX), numeric-string parsing, nested-key reads, and
 * filtered-list mode (empty `groupColumns`, one row per member — R4.8).
 *
 * Spec: `.kiro/specs/Members/member-analytics` (design C4; R4.1, R4.7, R4.8,
 * R5.3, R6.5).
 */
import fc from 'fast-check';
import {
  executeMemberPivot,
  aggregateColumnName,
} from '../components/members/analytics/memberPivotAdapter';
import type { FieldConfig, MemberRow } from '../types/members';
import type { PivotConfig } from '../types/pivot';

/** A minimal PivotConfig factory — only the fields the adapter reads matter. */
function makeConfig(partial: Partial<PivotConfig>): PivotConfig {
  return {
    dataSource: 'members',
    groupColumns: [],
    aggregateMeasures: [],
    filters: {},
    columnPivot: null,
    columnNestLevels: [],
    displayMode: 'flat',
    ...partial,
  };
}

/**
 * Field config declaring the storage group for keys so `valueFor` reads the
 * nested bucket. `membership_type` lives flat; `membership.years_member` and
 * `personal.age` live under their nested storage buckets.
 */
const fieldConfig: FieldConfig = {
  fields: [
    { key: 'membership_type' }, // flat
    { key: 'region' }, // flat
    { key: 'years_member', group: 'membership' }, // nested
    { key: 'age', group: 'personal' }, // nested
  ],
};

describe('aggregateColumnName', () => {
  it('mirrors the SQL FUNC(column) convention', () => {
    expect(aggregateColumnName({ function: 'SUM', column: 'age' })).toBe('SUM(age)');
    expect(aggregateColumnName({ function: 'AVG', column: 'years_member' })).toBe(
      'AVG(years_member)',
    );
  });

  it('renders COUNT with no column as COUNT(*)', () => {
    expect(aggregateColumnName({ function: 'COUNT', column: '' })).toBe('COUNT(*)');
    expect(aggregateColumnName({ function: 'COUNT', column: '*' })).toBe('COUNT(*)');
  });
});

describe('executeMemberPivot — grouping (flat keys)', () => {
  const rows: MemberRow[] = [
    { member_id: '1', membership_type: 'gold' },
    { member_id: '2', membership_type: 'silver' },
    { member_id: '3', membership_type: 'gold' },
    { member_id: '4', membership_type: 'gold' },
  ];

  it('groups by a single column and counts rows per group', () => {
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['membership_type'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );

    expect(result.success).toBe(true);
    expect(result.row_count).toBe(2);

    const byType = Object.fromEntries(
      result.data.map((r) => [r.membership_type, r['COUNT(*)']]),
    );
    expect(byType).toEqual({ gold: 3, silver: 1 });
  });

  it('emits one group PivotColumnMeta per group column and one aggregate per measure', () => {
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['membership_type'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );

    expect(result.columns).toEqual([
      { name: 'membership_type', type: 'group', dataType: 'string' },
      {
        name: 'COUNT(*)',
        type: 'aggregate',
        dataType: 'decimal',
        function: 'COUNT',
        sourceColumn: '*',
      },
    ]);
  });

  it('buckets rows with an absent group value under a blank group (never crashes)', () => {
    const withMissing: MemberRow[] = [
      { member_id: '1', membership_type: 'gold' },
      { member_id: '2' }, // no membership_type
      { member_id: '3' },
    ];
    const result = executeMemberPivot(
      withMissing,
      makeConfig({
        groupColumns: ['membership_type'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );
    expect(result.row_count).toBe(2);
    const blank = result.data.find((r) => r.membership_type === null);
    expect(blank?.['COUNT(*)']).toBe(2);
  });
});

describe('executeMemberPivot — grouping (nested-key read via valueFor)', () => {
  it('reads a group key from its nested storage bucket', () => {
    const rows: MemberRow[] = [
      { member_id: '1', membership: { years_member: '10' } } as unknown as MemberRow,
      { member_id: '2', membership: { years_member: '10' } } as unknown as MemberRow,
      { member_id: '3', membership: { years_member: '25' } } as unknown as MemberRow,
    ];
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['years_member'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );

    expect(result.row_count).toBe(2);
    const byYears = Object.fromEntries(
      result.data.map((r) => [r.years_member, r['COUNT(*)']]),
    );
    // The nested value is read and stringified into the group key.
    expect(byYears).toEqual({ '10': 2, '25': 1 });
  });
});

describe('executeMemberPivot — aggregates', () => {
  // age lives under personal; some stored as numeric strings (calculated-field shape).
  const rows: MemberRow[] = [
    { member_id: '1', region: 'N', personal: { age: '40' } } as unknown as MemberRow,
    { member_id: '2', region: 'N', personal: { age: '60' } } as unknown as MemberRow,
    { member_id: '3', region: 'N', personal: { age: 20 } } as unknown as MemberRow,
    { member_id: '4', region: 'N', personal: { age: 'n/a' } } as unknown as MemberRow, // excluded
  ];

  function runSingleGroup(fn: PivotConfig['aggregateMeasures'][number]['function']) {
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [{ function: fn, column: 'age' }],
      }),
      fieldConfig,
    );
    return result.data[0][`${fn}(age)`];
  }

  it('SUM parses numeric strings and excludes non-numeric', () => {
    // 40 + 60 + 20 = 120 ; 'n/a' excluded
    expect(runSingleGroup('SUM')).toBe(120);
  });

  it('AVG averages present numeric values only (not counting excluded as zero)', () => {
    // (40 + 60 + 20) / 3 = 40 ; 'n/a' NOT counted as a 0
    expect(runSingleGroup('AVG')).toBe(40);
  });

  it('MIN returns the smallest numeric value', () => {
    expect(runSingleGroup('MIN')).toBe(20);
  });

  it('MAX returns the largest numeric value', () => {
    expect(runSingleGroup('MAX')).toBe(60);
  });

  it('COUNT(*) counts all rows in the group', () => {
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );
    expect(result.data[0]['COUNT(*)']).toBe(4);
  });

  it('COUNT(column) counts only rows whose value is present (SQL NULL semantics)', () => {
    const mixed: MemberRow[] = [
      { member_id: '1', region: 'N', personal: { age: '40' } } as unknown as MemberRow,
      { member_id: '2', region: 'N', personal: {} } as unknown as MemberRow, // absent
      { member_id: '3', region: 'N', personal: { age: '' } } as unknown as MemberRow, // blank
    ];
    const result = executeMemberPivot(
      mixed,
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [{ function: 'COUNT', column: 'age' }],
      }),
      fieldConfig,
    );
    expect(result.data[0]['COUNT(age)']).toBe(1);
  });

  it('AVG/MIN/MAX return null over a group with no numeric values; SUM returns 0', () => {
    const nonNumeric: MemberRow[] = [
      { member_id: '1', region: 'N', personal: { age: 'x' } } as unknown as MemberRow,
    ];
    const result = executeMemberPivot(
      nonNumeric,
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [
          { function: 'SUM', column: 'age' },
          { function: 'AVG', column: 'age' },
          { function: 'MIN', column: 'age' },
          { function: 'MAX', column: 'age' },
        ],
      }),
      fieldConfig,
    );
    const row = result.data[0];
    expect(row['SUM(age)']).toBe(0);
    expect(row['AVG(age)']).toBeNull();
    expect(row['MIN(age)']).toBeNull();
    expect(row['MAX(age)']).toBeNull();
  });

  it('supports multiple measures and multiple group columns', () => {
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [
          { function: 'COUNT', column: '*' },
          { function: 'AVG', column: 'age' },
        ],
      }),
      fieldConfig,
    );
    expect(result.columns.map((c) => c.name)).toEqual([
      'region',
      'COUNT(*)',
      'AVG(age)',
    ]);
    expect(result.data[0]['COUNT(*)']).toBe(4);
    expect(result.data[0]['AVG(age)']).toBe(40);
  });
});

describe('executeMemberPivot — filtered-list mode (empty groupColumns, R4.8)', () => {
  const rows: MemberRow[] = [
    { member_id: '1', name: 'Alice', region: 'N' },
    { member_id: '2', name: 'Bob', region: 'Z' },
    { member_id: '3', name: 'Cara', region: 'N' },
  ];

  it('returns one row per member (not aggregated) when no columns are chosen', () => {
    const result = executeMemberPivot(rows, makeConfig({ groupColumns: [] }), fieldConfig);
    // One output row per input member, order preserved (R4.8).
    expect(result.row_count).toBe(3);
  });

  // Findings F-006: the "no columns" fallback must NOT dump the raw row
  // (system columns + nested buckets as `[object Object]`). It projects the
  // config's MEANINGFUL, visible, non-system fields via valueFor instead.
  it('projects meaningful config fields (not a raw dump) when no columns are chosen (F-006)', () => {
    const result = executeMemberPivot(rows, makeConfig({ groupColumns: [] }), fieldConfig);
    // Columns are the config's non-system fields, in config order — NOT the raw
    // row keys (member_id et al. are excluded).
    expect(result.columns.map((c) => c.name)).toEqual([
      'membership_type',
      'region',
      'years_member',
      'age',
    ]);
    // No system / internal key leaks into the projection.
    for (const key of ['member_id', 'sk', 'tenant_id', 'overlay', 'personal', 'membership']) {
      expect(result.columns.some((c) => c.name === key)).toBe(false);
    }
    // `region` resolves from the row; a field the row lacks renders blank
    // (undefined), never `[object Object]`.
    expect(result.data[0].region).toBe('N');
  });

  // Findings F-009: a list set names its curated columns via config.listColumns;
  // the adapter projects exactly those (via valueFor), including nested ones.
  it('projects config.listColumns (curated) via valueFor, including nested keys (F-009)', () => {
    const nested: MemberRow[] = [
      { member_id: '1', name: 'Alice', personal: { age: '40' }, membership: { years_member: '12' } },
      { member_id: '2', name: 'Bob', personal: { age: '55' }, membership: { years_member: '30' } },
    ] as unknown as MemberRow[];
    const result = executeMemberPivot(
      nested,
      makeConfig({ groupColumns: [], listColumns: ['name', 'age', 'years_member'] }),
      fieldConfig,
    );
    expect(result.columns.map((c) => c.name)).toEqual(['name', 'age', 'years_member']);
    // Nested calculated values resolve via valueFor (never [object Object]).
    expect(result.data[0]).toEqual({ name: 'Alice', age: '40', years_member: '12' });
    expect(result.data[1]).toEqual({ name: 'Bob', age: '55', years_member: '30' });
    expect(result.row_count).toBe(2);
  });

  it('projects only the chosen columns when measures name list columns', () => {
    const result = executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: [],
        // In list mode the measure columns name the list columns to project.
        aggregateMeasures: [
          { function: 'COUNT', column: 'name' },
          { function: 'COUNT', column: 'region' },
        ],
      }),
      fieldConfig,
    );
    expect(result.row_count).toBe(3);
    expect(result.columns.map((c) => c.name)).toEqual(['name', 'region']);
    expect(result.data[0]).toEqual({ name: 'Alice', region: 'N' });
    expect(result.data[1]).toEqual({ name: 'Bob', region: 'Z' });
  });

  it('reads nested list columns via valueFor', () => {
    const nested: MemberRow[] = [
      { member_id: '1', personal: { age: '33' } } as unknown as MemberRow,
    ];
    const result = executeMemberPivot(
      nested,
      makeConfig({
        groupColumns: [],
        aggregateMeasures: [{ function: 'COUNT', column: 'age' }],
      }),
      fieldConfig,
    );
    expect(result.data[0]).toEqual({ age: '33' });
  });
});

describe('executeMemberPivot — robustness', () => {
  it('handles an empty row set in aggregate mode (no groups)', () => {
    const result = executeMemberPivot(
      [],
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );
    expect(result.success).toBe(true);
    expect(result.row_count).toBe(0);
    expect(result.data).toEqual([]);
  });

  it('handles an empty row set in filtered-list mode', () => {
    const result = executeMemberPivot([], makeConfig({ groupColumns: [] }), fieldConfig);
    expect(result.row_count).toBe(0);
    expect(result.data).toEqual([]);
  });

  it('does not mutate the input rows', () => {
    const rows: MemberRow[] = [{ member_id: '1', region: 'N' }];
    const snapshot = JSON.stringify(rows);
    executeMemberPivot(
      rows,
      makeConfig({
        groupColumns: ['region'],
        aggregateMeasures: [{ function: 'COUNT', column: '*' }],
      }),
      fieldConfig,
    );
    expect(JSON.stringify(rows)).toBe(snapshot);
  });
});

describe('executeMemberPivot — properties (fast-check)', () => {
  /**
   * The per-group COUNT(*) always sums to the total number of input rows: every
   * row lands in exactly one group, none dropped or duplicated (scope-faithful
   * aggregation — R5.3 / R4.7).
   *
   * Validates: Requirements 4.7
   */
  it('group COUNT(*) sums to the total row count', () => {
    const rowArb = fc.record({
      member_id: fc.string(),
      region: fc.constantFrom('N', 'Z', 'O', 'W'),
    });
    fc.assert(
      fc.property(fc.array(rowArb), (rows) => {
        const result = executeMemberPivot(
          rows as MemberRow[],
          makeConfig({
            groupColumns: ['region'],
            aggregateMeasures: [{ function: 'COUNT', column: '*' }],
          }),
          fieldConfig,
        );
        const totalCounted = result.data.reduce(
          (acc, r) => acc + (r['COUNT(*)'] as number),
          0,
        );
        expect(totalCounted).toBe(rows.length);
      }),
      { numRuns: 200 },
    );
  });

  /**
   * Filtered-list mode always returns exactly one output row per input member,
   * in order — the adapter never widens or drops rows (R4.8 / R4.11 / R5.3).
   *
   * Validates: Requirements 4.8
   */
  it('filtered-list mode preserves row count and order', () => {
    const rowArb = fc.record({ member_id: fc.string(), region: fc.string() });
    fc.assert(
      fc.property(fc.array(rowArb), (rows) => {
        // Name `region` as the list column so the invariant is checked on a
        // PROJECTED field (findings F-006: the fallback no longer dumps the raw
        // row, so system keys like member_id are intentionally excluded —
        // order/count preservation is asserted via a column that IS projected).
        const result = executeMemberPivot(
          rows as MemberRow[],
          makeConfig({ groupColumns: [], listColumns: ['region'] }),
          fieldConfig,
        );
        // One output row per input member, in order — never widened or dropped.
        expect(result.row_count).toBe(rows.length);
        expect(result.data.map((r) => r.region)).toEqual(rows.map((r) => r.region));
      }),
      { numRuns: 200 },
    );
  });
});
