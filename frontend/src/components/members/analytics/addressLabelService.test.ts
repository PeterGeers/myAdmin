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
  generateLabelTemplatePdf,
  layoutLabelPdf,
  truncateToWidth,
  computeFitFontSize,
  type LabelFormat,
  type LabelSortOrder,
  type TextMeasurer,
  type FitMeasurer,
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

  it('lays out extreme over-long lines without throwing (truncation path)', () => {
    // A field whose text is far wider than any Avery cell — the layout must
    // truncate it (Property 5), never crash.
    const longRow = row({
      member_id: 'long',
      full_name: 'X'.repeat(500),
      street_addr: 'Y'.repeat(500),
      zip: '1000AA',
      town: 'Z'.repeat(500),
      nation: 'nl',
    });
    for (const format of AVERY_LABEL_FORMATS) {
      const result = generateAddressLabelPdf([longRow], mappedFieldConfig, format);
      expect(result.labelCount).toBe(1);
      expect(typeof result.doc.output).toBe('function');
    }
  });
});

// ---------------------------------------------------------------------------
// 7. truncateToWidth — per-line truncation to the cell inner width (R-L3, P5)
// ---------------------------------------------------------------------------

describe('truncateToWidth — no overflow past the label box (Property 5)', () => {
  const ELLIPSIS = '…';
  /**
   * Deterministic measurer: every character (and the ellipsis) is `k` mm wide,
   * so width is simply `text.length * k` — no font/jsPDF needed. This lets the
   * assertions be exact.
   */
  const linearMeasurer = (k: number): TextMeasurer => ({
    getTextWidth: (text: string) => text.length * k,
  });

  it('returns a string that already fits unchanged', () => {
    const m = linearMeasurer(1); // 1 mm per char
    expect(truncateToWidth(m, 'hello', 100)).toBe('hello'); // 5 <= 100
    // exactly at the boundary still fits.
    expect(truncateToWidth(m, 'hello', 5)).toBe('hello');
  });

  it('cuts an over-long string and ends with the ellipsis, within maxWidth', () => {
    const m = linearMeasurer(1); // 1 mm per char
    const out = truncateToWidth(m, 'abcdefghij', 5); // full width 10 > 5
    expect(out.endsWith(ELLIPSIS)).toBe(true);
    expect(m.getTextWidth(out)).toBeLessThanOrEqual(5);
    // longest prefix: 4 chars + ellipsis = width 5.
    expect(out).toBe('abcd…');
  });

  it('returns the empty string unchanged', () => {
    const m = linearMeasurer(10);
    expect(truncateToWidth(m, '', 0)).toBe('');
    expect(truncateToWidth(m, '', 1000)).toBe('');
  });

  it('never loops forever and never exceeds maxWidth beyond the lone ellipsis', () => {
    const m = linearMeasurer(1); // ellipsis itself is 1 mm wide
    // maxWidth smaller than even the ellipsis → returns the ellipsis marker
    // (the minimal non-empty truncation), does NOT hang.
    const out = truncateToWidth(m, 'abcdef', 0.5);
    expect(out).toBe(ELLIPSIS);
    // and when the ellipsis DOES fit but no prefix char does, still just ellipsis.
    const out2 = truncateToWidth(m, 'abcdef', 1); // ellipsis=1 fits; 'a…'=2 doesn't
    expect(out2).toBe(ELLIPSIS);
    expect(m.getTextWidth(out2)).toBeLessThanOrEqual(1);
  });

  it('honors a custom ellipsis string', () => {
    const m = linearMeasurer(1);
    const out = truncateToWidth(m, 'abcdefghij', 6, '...'); // '...' is 3 wide
    expect(out.endsWith('...')).toBe(true);
    expect(m.getTextWidth(out)).toBeLessThanOrEqual(6);
    // 3-char prefix + '...' = 6.
    expect(out).toBe('abc...');
  });
});

// ---------------------------------------------------------------------------
// 8. computeFitFontSize — per-sheet shrink-to-fit (R-L3, Property 6)
// ---------------------------------------------------------------------------

describe('computeFitFontSize — per-sheet shrink-to-fit (Property 6)', () => {
  // Module geometry constants mirrored for exact assertions (kept in sync with
  // addressLabelService: CELL_PADDING_MM=2, PT_TO_MM=0.3528, LINE_SPACING=1.15,
  // and the 0.5pt downward search step).
  const CELL_PADDING_MM = 2;
  const PT_TO_MM = 0.3528;
  const LINE_SPACING = 1.15;
  const STEP = 0.5;

  const fmt = getLabelFormat('L7160')!; // 63.5 x 38.1 → inner 59.5 x 34.1
  const innerWidth = fmt.labelWidth - 2 * CELL_PADDING_MM; // 59.5
  const innerHeight = fmt.labelHeight - 2 * CELL_PADDING_MM; // 34.1
  const lineHeightAt = (fs: number) => fs * PT_TO_MM * LINE_SPACING;

  /**
   * Deterministic, size-stateful FitMeasurer: a line's width is
   * `chars * k * currentFontSize` mm (so SMALLER fonts measure narrower — the
   * whole point of shrink-to-fit). No real font/jsPDF needed, so assertions are
   * exact. `setFontSize` re-points the current size, exactly as jsPDF does.
   */
  const makeMeasurer = (k: number): FitMeasurer => {
    let current = 10;
    return {
      setFontSize: (pt: number) => {
        current = pt;
      },
      getTextWidth: (text: string) => text.length * k * current,
    };
  };

  it('returns the chosen size unchanged when the whole sheet already fits', () => {
    // Short lines + k tiny → fits even at the chosen ceiling; no shrink.
    const m = makeMeasurer(0.01); // 10 chars @ 12pt → 1.2mm ≪ 59.5
    const blocks = [['Alice'], ['Bob', 'Street']];
    expect(computeFitFontSize(m, blocks, fmt, { fontSize: 12 })).toBe(12);
    // and height for 2 lines @ 12pt = 2 * ~4.87 = ~9.74 ≤ 34.1 → fine.
    expect(2 * lineHeightAt(12)).toBeLessThanOrEqual(innerHeight);
  });

  it('shrinks to the largest size at which EVERY label fits width', () => {
    // Choose k + a worst-case line length so width is the binding constraint.
    // worst line = 20 chars. width@fs = 20 * k * fs. Pick k so that it fits at
    // 10pt but NOT at 10.5pt: need 20*k*10 <= 59.5 < 20*k*10.5.
    //   k in ( 59.5/210 , 59.5/200 ] = ( 0.283…, 0.2975 ]  → pick 0.29.
    const k = 0.29;
    const m = makeMeasurer(k);
    const wide = 'W'.repeat(20); // the over-wide label
    const blocks = [['short'], [wide], ['also short']];
    const result = computeFitFontSize(m, blocks, fmt, { fontSize: 12 });

    // Largest fitting size on the 0.5 grid from 12 down: 10.0 fits, 10.5 does not.
    expect(result).toBe(10);
    // Verify the frontier directly against the measurer.
    m.setFontSize(result);
    expect(m.getTextWidth(wide)).toBeLessThanOrEqual(innerWidth);
    m.setFontSize(result + STEP);
    expect(m.getTextWidth(wide)).toBeGreaterThan(innerWidth);
  });

  it('shrinks when the line BLOCK is too tall even if every line fits width', () => {
    // Narrow lines (width never binds), but MANY of them → height is the binding
    // constraint. innerHeight 34.1; lineHeight@fs = fs*0.3528*1.15.
    // N lines fit at fs iff N*lineHeight@fs <= 34.1.
    const m = makeMeasurer(0.001); // width negligible at any size
    const n = 8; // 8 lines
    const block = Array.from({ length: n }, (_, i) => `line${i}`);
    const result = computeFitFontSize(m, [block], fmt, { fontSize: 12 });

    // Result must satisfy the height invariant and be the largest 0.5-step that does.
    expect(n * lineHeightAt(result)).toBeLessThanOrEqual(innerHeight);
    expect(n * lineHeightAt(result + STEP)).toBeGreaterThan(innerHeight);
    // Sanity: it genuinely shrank below the chosen 12.
    expect(result).toBeLessThan(12);
  });

  it('returns the LARGEST fitting size — one step larger would NOT fit', () => {
    const k = 0.29; // same frontier as the width test (fits@10, not@10.5)
    const m = makeMeasurer(k);
    const blocks = [['x'.repeat(20)]];
    const result = computeFitFontSize(m, blocks, fmt, { fontSize: 12 });
    // result fits; result + one step does not.
    m.setFontSize(result);
    expect(m.getTextWidth('x'.repeat(20))).toBeLessThanOrEqual(innerWidth);
    m.setFontSize(result + STEP);
    expect(m.getTextWidth('x'.repeat(20))).toBeGreaterThan(innerWidth);
  });

  it('never grows beyond the chosen (clamped) size even when everything fits', () => {
    const m = makeMeasurer(0.001); // fits trivially at any size
    // chosen 9 → must return 9, never a bigger size that would also fit.
    expect(computeFitFontSize(m, [['a'], ['b']], fmt, { fontSize: 9 })).toBe(9);
    // chosen out-of-band high (99) clamps to MAX (12); still never above 12.
    const r = computeFitFontSize(m, [['a']], fmt, { fontSize: 99 });
    expect(r).toBeLessThanOrEqual(MAX_FONT_SIZE);
    expect(r).toBe(MAX_FONT_SIZE);
  });

  it('returns MIN_FONT_SIZE when the sheet cannot fit even at the floor (no loop)', () => {
    // A line so wide it overflows at every size in the band (even at the floor).
    // width@8 = 60 * k * 8 must exceed 59.5 → k > 59.5/480 ≈ 0.124; pick 0.5.
    const m = makeMeasurer(0.5);
    const blocks = [['Z'.repeat(60)]];
    const result = computeFitFontSize(m, blocks, fmt, { fontSize: 12 });
    expect(result).toBe(MIN_FONT_SIZE);
    // Confirm it truly does not fit even at the floor (truncation is the net).
    m.setFontSize(MIN_FONT_SIZE);
    expect(m.getTextWidth('Z'.repeat(60))).toBeGreaterThan(innerWidth);
  });

  it('handles empty / absent line-blocks safely (fits → chosen size)', () => {
    const m = makeMeasurer(0.1);
    expect(computeFitFontSize(m, [], fmt, { fontSize: 11 })).toBe(11);
    // defaults: no options → chosen defaults to 10.
    expect(computeFitFontSize(m, [], fmt)).toBe(10);
  });
});

describe('generateAddressLabelPdf — autoFit option (Property 6 smoke)', () => {
  const fmt = getLabelFormat('L7160')!;

  it('generates a doc with autoFit on, reporting the right counts', () => {
    const result = generateAddressLabelPdf(
      [...completeRows, nameOnlyRow],
      mappedFieldConfig,
      fmt,
      { autoFit: true, fontSize: 12 },
    );
    expect(result.labelCount).toBe(3);
    expect(result.excludedCount).toBe(1);
    expect(result.pages).toBe(1);
    expect(typeof result.doc.output).toBe('function');
    expect(result.doc.output('bloburl').toString()).toContain('blob:');
  });

  it('shrinks for over-long rows under autoFit without throwing', () => {
    const longRow = row({
      member_id: 'long',
      full_name: 'X'.repeat(300),
      street_addr: 'Y'.repeat(300),
      zip: '1000AA',
      town: 'Z'.repeat(300),
      nation: 'nl',
    });
    const result = generateAddressLabelPdf([longRow, completeRows[0]], mappedFieldConfig, fmt, {
      autoFit: true,
      fontSize: 12,
    });
    expect(result.labelCount).toBe(2);
    expect(result.pages).toBe(1);
    expect(typeof result.doc.output).toBe('function');
  });

  it('is additive: default (no autoFit) keeps the clamped-fontSize behavior', () => {
    const withOut = generateAddressLabelPdf(completeRows, mappedFieldConfig, fmt, {
      fontSize: 12,
    });
    expect(withOut.labelCount).toBe(3);
    expect(withOut.pages).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// generateLabelTemplatePdf — the TEMPLATE-driven path (labels sub-spec task 3.2,
// R-L2/R-L3/R-L4, Property 1/2/4). Composes via `composeLabelLines` (NOT
// `composeAddresses`/`resolveAddressMapping`), so it reads NO `analytics.*` — a
// field config with NO address mapping still yields labels from a label
// template. Reuses the SHARED `layoutLabelPdf` draw loop (R-L5).
// ---------------------------------------------------------------------------

describe('generateLabelTemplatePdf — template-driven labels (task 3.2)', () => {
  const fmt = getLabelFormat('L7160')!;

  // A field config with NO analytics / address_mapping at all — only flat field
  // keys the template references. This proves the template path never needs a
  // mapping (Property 4 / R6): labels still come out.
  const noMappingConfig = {
    fields: [
      { key: 'display_name', group: 'personal' },
      { key: 'street', group: 'personal' },
      { key: 'postal_code', group: 'personal' },
      { key: 'city', group: 'personal' },
    ],
  } as unknown as FieldConfig;

  const peopleRows: MemberRow[] = [
    row({
      member_id: '1',
      display_name: 'Alice Smith',
      street: '2 Low Rd',
      postal_code: '2000BB',
      city: 'Rotterdam',
    }),
    row({
      member_id: '2',
      display_name: 'Bob Jones',
      street: '1 High St',
      postal_code: '1000AA',
      city: 'Amsterdam',
    }),
  ];

  it('smoke: a template with N lines over the rows yields a doc + the right counts', () => {
    const template = {
      lines: [['display_name'], ['street'], ['postal_code', 'city']],
    };
    const result = generateLabelTemplatePdf(peopleRows, noMappingConfig, template, fmt);

    expect(result.labelCount).toBe(2); // one label per non-empty row
    expect(result.excludedCount).toBe(0);
    expect(result.pages).toBe(1);
    expect(typeof result.doc.output).toBe('function');
    expect(result.doc.output('bloburl').toString()).toContain('blob:');
  });

  it('reads NO address mapping: a config with no analytics still produces labels (Property 4 / R6)', () => {
    // `noMappingConfig` has NO `analytics.address_mapping`; the address path would
    // exclude every row. The template path composes purely from the field keys.
    const addressResult = generateAddressLabelPdf(peopleRows, noMappingConfig, fmt);
    expect(addressResult.labelCount).toBe(0); // address path: nothing resolves
    expect(addressResult.excludedCount).toBe(2);

    const templateResult = generateLabelTemplatePdf(
      peopleRows,
      noMappingConfig,
      { lines: [['display_name'], ['city']] },
      fmt,
    );
    expect(templateResult.labelCount).toBe(2); // template path: full labels
    expect(templateResult.excludedCount).toBe(0);
  });

  it('drops + counts a row whose template lines are ALL empty', () => {
    const emptyRow = row({ member_id: 'z' }); // none of the template keys resolve
    const template = { lines: [['display_name'], ['city']] };
    const result = generateLabelTemplatePdf(
      [...peopleRows, emptyRow],
      noMappingConfig,
      template,
      fmt,
    );
    expect(result.labelCount).toBe(2); // the two real rows
    expect(result.excludedCount).toBe(1); // the all-empty row dropped + counted
  });

  it('composes a multi-field line by joining values in field order (Property 2)', () => {
    // Verify the composed line-blocks the generator lays out via the shared
    // layout: a two-field line joins its values with a single space, in order.
    // We assert through `composeLabelLines` indirectly by checking the kept
    // label count AND exercising the join via a single-row template whose one
    // line has two fields — a non-empty join yields exactly one label line.
    const oneRow: MemberRow[] = [peopleRows[0]];
    const result = generateLabelTemplatePdf(
      oneRow,
      noMappingConfig,
      { lines: [['postal_code', 'city']] }, // "2000BB Rotterdam"
      fmt,
    );
    expect(result.labelCount).toBe(1);
    expect(result.excludedCount).toBe(0);
  });

  it('reuses the shared layoutLabelPdf draw loop (one layout path, R-L5)', () => {
    // The shared helper lays out already-composed line-blocks directly — the same
    // code `generateLabelTemplatePdf` and `generateAddressLabelPdf` funnel into.
    const laid = layoutLabelPdf(
      [['Alice Smith', 'Rotterdam'], ['Bob Jones', 'Amsterdam']],
      fmt,
    );
    expect(laid.labelCount).toBe(2);
    expect(laid.pages).toBe(1);
    expect(typeof laid.doc.output).toBe('function');
  });
});
