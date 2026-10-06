/**
 * Full test matrix for the pure address-label service (task 8.3, C5).
 *
 * Task 8.2 shipped the service + a minimal smoke test. THIS file is the full
 * matrix the plan calls for (grid geometry, address formatting from RESOLVED
 * field keys, incomplete-address filtering + count, jsPDF output smoke, and the
 * start-position / sort-order permutations) covering R4.10 / R6.5:
 *
 *   - **label-format grid calculations** — `cellPosition` for every shipped Avery
 *     format: the four corner cells of a page, wrap to the next row / column /
 *     page; `labelsPerPage`; `pageCount` with and without a start-position offset;
 *   - **address formatting from RESOLVED field keys** (never h-dcn literals) —
 *     name / street / postcode+city / country(uppercased) / region line
 *     composition, dropped-empty-slot behaviour, nested-bucket vs flat-key reads;
 *   - **incomplete-address filtering + count (R4.10)** — rows missing the name or
 *     the locating line are dropped and counted;
 *   - **jsPDF output smoke** — `generateAddressLabelPdf` returns a real jsPDF doc
 *     with the right `labelCount` / `excludedCount` / `pages`;
 *   - **start-position (skip N cells) and sort-order (name / postcode / region)**
 *     permutations.
 *
 * The service is PURE (no React, no I/O), so this file imports it directly and
 * asserts on returned data / geometry — no DOM, no i18n. (The bilingual-key and
 * capability-gating assertions live in the component test, which echoes i18n keys
 * so nothing here or there hardcodes English.)
 *
 * Validates: Requirements R4.10, R6.5
 */
import { describe, it, expect } from 'vitest';

import {
  AVERY_LABEL_FORMATS,
  DEFAULT_LABEL_FORMAT_KEY,
  MIN_FONT_SIZE,
  MAX_FONT_SIZE,
  getLabelFormat,
  composeAddresses,
  clampFontSize,
  cellPosition,
  labelsPerPage,
  pageCount,
  generateAddressLabelPdf,
  type LabelFormat,
  type LabelSortOrder,
} from './addressLabelService';
import type { FieldConfig, MemberRow } from '../../../types/members';

// ---------------------------------------------------------------------------
// Fixtures — tenant-RESOLVED field keys (deliberately NOT the h-dcn literals
// korte_naam/straat/postcode/woonplaats/land/regio, to prove composition reads
// the resolved mapping, not hardcoded field names).
// ---------------------------------------------------------------------------

/**
 * A field config mapping every address slot to a concrete, non-Dutch tenant key.
 * `region` is a nested-bucket field (group `membership`) to exercise the
 * nested-vs-flat read; the rest are flat.
 */
const mappedFieldConfig = {
  fields: [
    { key: 'full_name', group: 'personal' },
    { key: 'street_addr', group: 'personal' },
    { key: 'zip', group: 'personal' },
    { key: 'town', group: 'personal' },
    { key: 'nation', group: 'personal' },
    { key: 'chapter', group: 'membership' },
  ],
  analytics: {
    address_mapping: {
      name: 'full_name',
      street: 'street_addr',
      postcode: 'zip',
      city: 'town',
      country: 'nation',
      region: 'chapter',
    },
  },
} as unknown as FieldConfig;

/** No analytics / address mapping → nothing resolves. */
const unmappedFieldConfig = { fields: [] } as unknown as FieldConfig;

/**
 * A config whose mapping points at keys that are NOT present in `fields`
 * (stale mapping after an overlay field was removed) — must resolve to nothing.
 */
const danglingFieldConfig = {
  fields: [{ key: 'full_name', group: 'personal' }],
  analytics: {
    address_mapping: {
      name: 'full_name',
      street: 'gone_street',
      postcode: 'gone_zip',
      city: 'gone_city',
    },
  },
} as unknown as FieldConfig;

function row(fields: Record<string, unknown>): MemberRow {
  return fields as unknown as MemberRow;
}

/** Three complete + one incomplete row, all keyed on the resolved tenant keys. */
const completeRows: MemberRow[] = [
  row({
    member_id: 'b',
    full_name: 'Bob Jones',
    street_addr: '1 High St',
    zip: '1000AA',
    town: 'Amsterdam',
    nation: 'nl',
    membership: { chapter: 'North' },
  }),
  row({
    member_id: 'a',
    full_name: 'Alice Smith',
    street_addr: '2 Low Rd',
    zip: '2000BB',
    town: 'Rotterdam',
    nation: 'de',
    membership: { chapter: 'South' },
  }),
  row({
    member_id: 'c',
    full_name: 'Carol King',
    street_addr: '3 Mid Way',
    zip: '0500CC',
    town: 'Utrecht',
    nation: 'be',
    membership: { chapter: 'East' },
  }),
];

/** A name-only row (no locating line) → must be dropped + counted. */
const nameOnlyRow = row({ member_id: 'x', full_name: 'No Address' });
/** A row with no name at all → must be dropped + counted. */
const noNameRow = row({ member_id: 'y', street_addr: '9 Nowhere', town: 'Ghost' });

// ---------------------------------------------------------------------------
// 1. Shipped formats + grid geometry (cellPosition / labelsPerPage / pageCount)
// ---------------------------------------------------------------------------

describe('shipped Avery formats', () => {
  it('ships exactly the five standard formats in order', () => {
    expect(AVERY_LABEL_FORMATS.map((f) => f.key)).toEqual([
      'L7160',
      'L7163',
      'L7162',
      'L7161',
      'CUSTOM_LARGE',
    ]);
    expect(DEFAULT_LABEL_FORMAT_KEY).toBe('L7160');
  });

  it('reports the datasheet labels-per-sheet for each format (R4.10)', () => {
    const perSheet = Object.fromEntries(
      AVERY_LABEL_FORMATS.map((f) => [f.key, labelsPerPage(f)]),
    );
    expect(perSheet).toEqual({
      L7160: 21, // 3 x 7
      L7163: 14, // 2 x 7
      L7162: 16, // 2 x 8
      L7161: 18, // 3 x 6
      CUSTOM_LARGE: 8, // 2 x 4
    });
  });

  it('getLabelFormat returns the record by key and undefined for unknown', () => {
    expect(getLabelFormat('L7160')?.name).toContain('L7160');
    expect(getLabelFormat('nope')).toBeUndefined();
  });
});

describe('cellPosition grid geometry', () => {
  it('places cell 0 at the sheet top-left margin for every format', () => {
    for (const fmt of AVERY_LABEL_FORMATS) {
      const first = cellPosition(fmt, 0);
      expect(first).toMatchObject({ col: 0, row: 0 });
      expect(first.x).toBeCloseTo(fmt.marginLeft);
      expect(first.y).toBeCloseTo(fmt.marginTop);
    }
  });

  it('computes the four corner cells of a page for every format', () => {
    for (const fmt of AVERY_LABEL_FORMATS) {
      const perPage = labelsPerPage(fmt);
      const lastCol = fmt.columns - 1;
      const lastRow = fmt.rows - 1;

      // top-right
      const tr = cellPosition(fmt, lastCol);
      expect(tr).toMatchObject({ col: lastCol, row: 0 });
      expect(tr.x).toBeCloseTo(fmt.marginLeft + lastCol * (fmt.labelWidth + fmt.gapX));
      expect(tr.y).toBeCloseTo(fmt.marginTop);

      // bottom-left
      const bl = cellPosition(fmt, lastRow * fmt.columns);
      expect(bl).toMatchObject({ col: 0, row: lastRow });
      expect(bl.y).toBeCloseTo(fmt.marginTop + lastRow * (fmt.labelHeight + fmt.gapY));

      // bottom-right (last cell on the page)
      const br = cellPosition(fmt, perPage - 1);
      expect(br).toMatchObject({ col: lastCol, row: lastRow });
    }
  });

  it('wraps the end of a row to the next row, col 0', () => {
    const fmt = getLabelFormat('L7160')!; // 3 columns
    // cell index 2 is the last of row 0; index 3 starts row 1.
    expect(cellPosition(fmt, 2)).toMatchObject({ col: 2, row: 0 });
    expect(cellPosition(fmt, 3)).toMatchObject({ col: 0, row: 1 });
  });

  it('wraps the last cell of a page back to page-local (0,0) on the next page', () => {
    const fmt = getLabelFormat('L7161')!; // 18/sheet, 3 x 6
    const perPage = labelsPerPage(fmt); // 18
    // cell perPage-1 is the page's bottom-right; cell perPage is page-local (0,0).
    expect(cellPosition(fmt, perPage - 1)).toMatchObject({
      col: fmt.columns - 1,
      row: fmt.rows - 1,
    });
    const next = cellPosition(fmt, perPage);
    expect(next).toMatchObject({ col: 0, row: 0 });
    // page-local coordinates reset to the top-left margin.
    expect(next.x).toBeCloseTo(fmt.marginLeft);
    expect(next.y).toBeCloseTo(fmt.marginTop);
  });

  it('normalizes a negative cell index into the page grid', () => {
    const fmt = getLabelFormat('L7160')!;
    const perPage = labelsPerPage(fmt);
    // -1 maps to the last cell of a page.
    expect(cellPosition(fmt, -1)).toMatchObject({
      col: fmt.columns - 1,
      row: fmt.rows - 1,
    });
    // -1 and perPage-1 land on the same page-local cell.
    expect(cellPosition(fmt, -1)).toEqual(cellPosition(fmt, perPage - 1));
  });
});

describe('pageCount with and without a start-position offset', () => {
  const fmt = getLabelFormat('L7160')!; // 21/sheet

  it('is 0 for a non-positive address count', () => {
    expect(pageCount(fmt, 0)).toBe(0);
    expect(pageCount(fmt, -5)).toBe(0);
  });

  it('fills exactly one page at the sheet capacity, two at capacity+1', () => {
    expect(pageCount(fmt, 21)).toBe(1);
    expect(pageCount(fmt, 22)).toBe(2);
    expect(pageCount(fmt, 42)).toBe(2);
    expect(pageCount(fmt, 43)).toBe(3);
  });

  it('counts a start offset against the first sheet (R4.10 start position)', () => {
    // Skip 20 cells → only 1 free on page 1: 1 label fits, 2 spill to page 2.
    expect(pageCount(fmt, 1, 20)).toBe(1);
    expect(pageCount(fmt, 2, 20)).toBe(2);
    // Skip 5 → 16 free on page 1; 16 fit on one page, 17 need two.
    expect(pageCount(fmt, 16, 5)).toBe(1);
    expect(pageCount(fmt, 17, 5)).toBe(2);
  });

  it('clamps an out-of-range start offset to the last cell of a page', () => {
    const perPage = labelsPerPage(fmt);
    // startPosition >= perPage is clamped to perPage-1 (one free cell left).
    expect(pageCount(fmt, 1, perPage + 100)).toBe(1);
    expect(pageCount(fmt, 2, perPage + 100)).toBe(2);
    // A negative start offset is treated as 0.
    expect(pageCount(fmt, 21, -3)).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 2. clampFontSize (R4.10: 8-12pt)
// ---------------------------------------------------------------------------

describe('clampFontSize', () => {
  it('clamps into the 8-12pt band', () => {
    expect(clampFontSize(5)).toBe(MIN_FONT_SIZE);
    expect(clampFontSize(8)).toBe(8);
    expect(clampFontSize(10)).toBe(10);
    expect(clampFontSize(12)).toBe(12);
    expect(clampFontSize(99)).toBe(MAX_FONT_SIZE);
  });

  it('falls back to the default for a non-finite / absent size', () => {
    expect(clampFontSize(undefined)).toBe(10);
    expect(clampFontSize(Number.NaN)).toBe(10);
    expect(clampFontSize(Number.POSITIVE_INFINITY)).toBe(10);
  });
});

// ---------------------------------------------------------------------------
// 3. Address composition from RESOLVED field keys
// ---------------------------------------------------------------------------

describe('composeAddresses — formatting from resolved field keys', () => {
  it('composes the five display lines in order from the resolved mapping', () => {
    const { addresses } = composeAddresses([completeRows[0]], mappedFieldConfig);
    expect(addresses).toHaveLength(1);
    // name / street / postcode+city / COUNTRY(upper) / region
    expect(addresses[0].lines).toEqual([
      'Bob Jones',
      '1 High St',
      '1000AA  Amsterdam',
      'NL',
      'North',
    ]);
  });

  it('reads a region mapped to a NESTED bucket, not just flat keys', () => {
    // `chapter` lives under membership.{chapter}; the flat key is absent.
    const { addresses } = composeAddresses([completeRows[1]], mappedFieldConfig);
    expect(addresses[0].lines).toContain('South');
    expect(addresses[0].regionKey).toBe('south');
  });

  it('uppercases the country line for international mailing', () => {
    const { addresses } = composeAddresses(
      [completeRows[0], completeRows[1]],
      mappedFieldConfig,
      { sortOrder: 'name' },
    );
    // de → DE, nl → NL
    expect(addresses[0].lines).toContain('DE'); // Alice
    expect(addresses[1].lines).toContain('NL'); // Bob
  });

  it('joins postcode + city on a single line', () => {
    const { addresses } = composeAddresses([completeRows[2]], mappedFieldConfig);
    expect(addresses[0].lines).toContain('0500CC  Utrecht');
  });

  it('drops empty slots so a missing middle line leaves no blank gap', () => {
    // No street, no region: name / postcode+city / country only.
    const partial = row({
      member_id: 'p',
      full_name: 'Dana Lee',
      zip: '3000DD',
      town: 'Delft',
      nation: 'nl',
    });
    const { addresses } = composeAddresses([partial], mappedFieldConfig);
    expect(addresses[0].lines).toEqual(['Dana Lee', '3000DD  Delft', 'NL']);
    // no empty strings anywhere.
    expect(addresses[0].lines.every((l) => l.trim() !== '')).toBe(true);
  });

  it('omits the country line when showCountry is false', () => {
    const { addresses } = composeAddresses([completeRows[0]], mappedFieldConfig, {
      showCountry: false,
    });
    expect(addresses[0].lines).not.toContain('NL');
    expect(addresses[0].lines).toEqual([
      'Bob Jones',
      '1 High St',
      '1000AA  Amsterdam',
      'North',
    ]);
  });

  it('does not read the h-dcn Dutch literals when they are not the mapped keys', () => {
    // A row carrying ONLY the h-dcn literals, with the tenant mapping pointing
    // elsewhere → nothing composes (proves no hardcoded korte_naam/straat/...).
    const hdcnLiteralRow = row({
      member_id: 'z',
      korte_naam: 'Should Not Appear',
      straat: 'Verboden Straat 1',
      postcode: '9999ZZ',
      woonplaats: 'Nergens',
      land: 'xx',
    });
    const { addresses, excludedCount } = composeAddresses(
      [hdcnLiteralRow],
      mappedFieldConfig,
    );
    expect(addresses).toHaveLength(0);
    expect(excludedCount).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 4. Incomplete-address filtering + count (R4.10)
// ---------------------------------------------------------------------------

describe('composeAddresses — incomplete-address filtering + count (R4.10)', () => {
  it('keeps complete rows and drops+counts a name-only row', () => {
    const { addresses, excludedCount } = composeAddresses(
      [...completeRows, nameOnlyRow],
      mappedFieldConfig,
    );
    expect(addresses).toHaveLength(3);
    expect(excludedCount).toBe(1);
  });

  it('drops+counts a row with no name even when it has a locating line', () => {
    const { addresses, excludedCount } = composeAddresses(
      [completeRows[0], noNameRow],
      mappedFieldConfig,
    );
    expect(addresses).toHaveLength(1);
    expect(excludedCount).toBe(1);
  });

  it('counts every row excluded when the mapping does not resolve', () => {
    const absent = composeAddresses(completeRows, unmappedFieldConfig);
    expect(absent.addresses).toHaveLength(0);
    expect(absent.excludedCount).toBe(completeRows.length);

    // A dangling mapping (keys not present in fields) resolves to nothing too.
    const dangling = composeAddresses(completeRows, danglingFieldConfig);
    expect(dangling.addresses).toHaveLength(0);
    expect(dangling.excludedCount).toBe(completeRows.length);
  });

  it('handles an undefined field config and non-array rows safely', () => {
    expect(composeAddresses(completeRows, undefined)).toEqual({
      addresses: [],
      excludedCount: completeRows.length,
    });
    expect(
      composeAddresses(undefined as unknown as MemberRow[], mappedFieldConfig),
    ).toEqual({ addresses: [], excludedCount: 0 });
  });

  it('does not mutate the caller rows array', () => {
    const input = [...completeRows];
    const snapshot = [...input];
    composeAddresses(input, mappedFieldConfig, { sortOrder: 'postcode' });
    expect(input).toEqual(snapshot);
  });
});

// ---------------------------------------------------------------------------
// 5. Sort order permutations (name / postcode / region)
// ---------------------------------------------------------------------------

describe('composeAddresses — sort-order permutations', () => {
  const names = (order: LabelSortOrder) =>
    composeAddresses(completeRows, mappedFieldConfig, { sortOrder: order }).addresses.map(
      (a) => a.lines[0],
    );

  it('sorts by name by default and when name is requested', () => {
    // Alice, Bob, Carol
    expect(names('name')).toEqual(['Alice Smith', 'Bob Jones', 'Carol King']);
    const dflt = composeAddresses(completeRows, mappedFieldConfig).addresses.map(
      (a) => a.lines[0],
    );
    expect(dflt).toEqual(['Alice Smith', 'Bob Jones', 'Carol King']);
  });

  it('sorts by postcode for bulk-mail ordering', () => {
    // zips: Bob 1000AA, Alice 2000BB, Carol 0500CC → 0500 < 1000 < 2000
    expect(names('postcode')).toEqual(['Carol King', 'Bob Jones', 'Alice Smith']);
  });

  it('sorts by region', () => {
    // chapters: Bob North, Alice South, Carol East → East < North < South
    expect(names('region')).toEqual(['Carol King', 'Bob Jones', 'Alice Smith']);
  });
});

// ---------------------------------------------------------------------------
// 6. jsPDF output smoke + start-position in the generated doc
// ---------------------------------------------------------------------------

describe('generateAddressLabelPdf — jsPDF smoke + counts', () => {
  const fmt = getLabelFormat('L7160')!;

  it('returns a real jsPDF document with the right counts', () => {
    const result = generateAddressLabelPdf(
      [...completeRows, nameOnlyRow],
      mappedFieldConfig,
      fmt,
      { fontSize: 10, startPosition: 0 },
    );
    expect(result.labelCount).toBe(3);
    expect(result.excludedCount).toBe(1);
    expect(result.pages).toBe(1);
    // A real jsPDF doc exposes output() and produces a non-trivial blob url.
    expect(typeof result.doc.output).toBe('function');
    expect(result.doc.output('bloburl').toString()).toContain('blob:');
  });

  it('spans multiple pages when the labels exceed one sheet', () => {
    // 22 rows → 2 pages on a 21/sheet format.
    const many: MemberRow[] = Array.from({ length: 22 }, (_, i) =>
      row({
        member_id: `m${i}`,
        full_name: `Member ${String(i).padStart(2, '0')}`,
        street_addr: `${i} Some St`,
        zip: `${1000 + i}AA`,
        town: 'Town',
        nation: 'nl',
      }),
    );
    const result = generateAddressLabelPdf(many, mappedFieldConfig, fmt);
    expect(result.labelCount).toBe(22);
    expect(result.pages).toBe(2);
    expect(result.doc.getNumberOfPages()).toBe(2);
  });

  it('honors the start position: skipping N cells pushes labels to the next page', () => {
    // 2 labels, skip 20 of a 21/sheet → only 1 fits on page 1, 1 on page 2.
    const result = generateAddressLabelPdf(
      [completeRows[0], completeRows[1]],
      mappedFieldConfig,
      fmt,
      { startPosition: 20 },
    );
    expect(result.labelCount).toBe(2);
    expect(result.pages).toBe(2);
    expect(result.doc.getNumberOfPages()).toBe(2);
  });

  it('produces a single-page empty doc when nothing resolves', () => {
    const result = generateAddressLabelPdf(completeRows, unmappedFieldConfig, fmt);
    expect(result.labelCount).toBe(0);
    expect(result.excludedCount).toBe(completeRows.length);
    expect(result.pages).toBe(0);
    // jsPDF always starts with one physical page even if we drew nothing.
    expect(result.doc.getNumberOfPages()).toBe(1);
  });

  it('clamps an out-of-band font size without throwing (R4.10 8-12pt)', () => {
    const result = generateAddressLabelPdf(completeRows, mappedFieldConfig, fmt, {
      fontSize: 99,
      showBorder: true,
      alignment: 'center',
    });
    expect(result.labelCount).toBe(3);
    expect(typeof result.doc.output).toBe('function');
  });

  it('lays out onto every shipped format without throwing', () => {
    for (const format of AVERY_LABEL_FORMATS) {
      const result = generateAddressLabelPdf(completeRows, mappedFieldConfig, format);
      expect(result.labelCount).toBe(3);
      expect(result.pages).toBe(1);
    }
  });
});
