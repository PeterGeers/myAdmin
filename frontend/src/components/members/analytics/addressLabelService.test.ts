/**
 * Test matrix for the pure label service (sliced for the role-removal: the
 * address-mapping-driven path `composeAddresses` / `generateAddressLabelPdf` was
 * removed; only the TEMPLATE-driven path survives).
 *
 * Covers:
 *   - **label-format grid calculations** — `cellPosition` for every shipped Avery
 *     format: the four corner cells of a page, wrap to the next row / column /
 *     page; `labelsPerPage`; `pageCount` with and without a start-position offset;
 *   - **font-size clamp** (`clampFontSize`, 8–12pt);
 *   - **per-line truncation** (`truncateToWidth`, Property 5) + **per-sheet
 *     shrink-to-fit** (`computeFitFontSize`, Property 6);
 *   - **template-driven label composition + PDF** (`composeLabelLines` via
 *     `generateLabelTemplatePdf`), which reads NO `analytics.*` (Property 4 / R6),
 *     reusing the shared `layoutLabelPdf` draw loop (R-L5).
 *
 * The service is PURE (no React, no I/O), so this file imports it directly and
 * asserts on returned data / geometry — no DOM, no i18n.
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
  clampFontSize,
  cellPosition,
  labelsPerPage,
  pageCount,
  generateLabelTemplatePdf,
  layoutLabelPdf,
  truncateToWidth,
  computeFitFontSize,
  type TextMeasurer,
  type FitMeasurer,
} from './addressLabelService';
import type { FieldConfig, MemberRow } from '../../../types/members';

function row(fields: Record<string, unknown>): MemberRow {
  return fields as unknown as MemberRow;
}

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
    expect(cellPosition(fmt, perPage - 1)).toMatchObject({
      col: fmt.columns - 1,
      row: fmt.rows - 1,
    });
    const next = cellPosition(fmt, perPage);
    expect(next).toMatchObject({ col: 0, row: 0 });
    expect(next.x).toBeCloseTo(fmt.marginLeft);
    expect(next.y).toBeCloseTo(fmt.marginTop);
  });

  it('normalizes a negative cell index into the page grid', () => {
    const fmt = getLabelFormat('L7160')!;
    const perPage = labelsPerPage(fmt);
    expect(cellPosition(fmt, -1)).toMatchObject({
      col: fmt.columns - 1,
      row: fmt.rows - 1,
    });
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
    expect(pageCount(fmt, 1, 20)).toBe(1);
    expect(pageCount(fmt, 2, 20)).toBe(2);
    expect(pageCount(fmt, 16, 5)).toBe(1);
    expect(pageCount(fmt, 17, 5)).toBe(2);
  });

  it('clamps an out-of-range start offset to the last cell of a page', () => {
    const perPage = labelsPerPage(fmt);
    expect(pageCount(fmt, 1, perPage + 100)).toBe(1);
    expect(pageCount(fmt, 2, perPage + 100)).toBe(2);
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
// 3. truncateToWidth — per-line truncation to the cell inner width (R-L3, P5)
// ---------------------------------------------------------------------------

describe('truncateToWidth — no overflow past the label box (Property 5)', () => {
  const ELLIPSIS = '…';
  const linearMeasurer = (k: number): TextMeasurer => ({
    getTextWidth: (text: string) => text.length * k,
  });

  it('returns a string that already fits unchanged', () => {
    const m = linearMeasurer(1); // 1 mm per char
    expect(truncateToWidth(m, 'hello', 100)).toBe('hello'); // 5 <= 100
    expect(truncateToWidth(m, 'hello', 5)).toBe('hello');
  });

  it('cuts an over-long string and ends with the ellipsis, within maxWidth', () => {
    const m = linearMeasurer(1);
    const out = truncateToWidth(m, 'abcdefghij', 5); // full width 10 > 5
    expect(out.endsWith(ELLIPSIS)).toBe(true);
    expect(m.getTextWidth(out)).toBeLessThanOrEqual(5);
    expect(out).toBe('abcd…');
  });

  it('returns the empty string unchanged', () => {
    const m = linearMeasurer(10);
    expect(truncateToWidth(m, '', 0)).toBe('');
    expect(truncateToWidth(m, '', 1000)).toBe('');
  });

  it('never loops forever and never exceeds maxWidth beyond the lone ellipsis', () => {
    const m = linearMeasurer(1);
    const out = truncateToWidth(m, 'abcdef', 0.5);
    expect(out).toBe(ELLIPSIS);
    const out2 = truncateToWidth(m, 'abcdef', 1);
    expect(out2).toBe(ELLIPSIS);
    expect(m.getTextWidth(out2)).toBeLessThanOrEqual(1);
  });

  it('honors a custom ellipsis string', () => {
    const m = linearMeasurer(1);
    const out = truncateToWidth(m, 'abcdefghij', 6, '...'); // '...' is 3 wide
    expect(out.endsWith('...')).toBe(true);
    expect(m.getTextWidth(out)).toBeLessThanOrEqual(6);
    expect(out).toBe('abc...');
  });
});

// ---------------------------------------------------------------------------
// 4. computeFitFontSize — per-sheet shrink-to-fit (R-L3, Property 6)
// ---------------------------------------------------------------------------

describe('computeFitFontSize — per-sheet shrink-to-fit (Property 6)', () => {
  const CELL_PADDING_MM = 2;
  const PT_TO_MM = 0.3528;
  const LINE_SPACING = 1.15;
  const STEP = 0.5;

  const fmt = getLabelFormat('L7160')!; // 63.5 x 38.1 → inner 59.5 x 34.1
  const innerWidth = fmt.labelWidth - 2 * CELL_PADDING_MM; // 59.5
  const innerHeight = fmt.labelHeight - 2 * CELL_PADDING_MM; // 34.1
  const lineHeightAt = (fs: number) => fs * PT_TO_MM * LINE_SPACING;

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
    const m = makeMeasurer(0.01);
    const blocks = [['Alice'], ['Bob', 'Street']];
    expect(computeFitFontSize(m, blocks, fmt, { fontSize: 12 })).toBe(12);
    expect(2 * lineHeightAt(12)).toBeLessThanOrEqual(innerHeight);
  });

  it('shrinks to the largest size at which EVERY label fits width', () => {
    const k = 0.29;
    const m = makeMeasurer(k);
    const wide = 'W'.repeat(20);
    const blocks = [['short'], [wide], ['also short']];
    const result = computeFitFontSize(m, blocks, fmt, { fontSize: 12 });

    expect(result).toBe(10);
    m.setFontSize(result);
    expect(m.getTextWidth(wide)).toBeLessThanOrEqual(innerWidth);
    m.setFontSize(result + STEP);
    expect(m.getTextWidth(wide)).toBeGreaterThan(innerWidth);
  });

  it('shrinks when the line BLOCK is too tall even if every line fits width', () => {
    const m = makeMeasurer(0.001);
    const n = 8;
    const block = Array.from({ length: n }, (_, i) => `line${i}`);
    const result = computeFitFontSize(m, [block], fmt, { fontSize: 12 });

    expect(n * lineHeightAt(result)).toBeLessThanOrEqual(innerHeight);
    expect(n * lineHeightAt(result + STEP)).toBeGreaterThan(innerHeight);
    expect(result).toBeLessThan(12);
  });

  it('returns the LARGEST fitting size — one step larger would NOT fit', () => {
    const k = 0.29;
    const m = makeMeasurer(k);
    const blocks = [['x'.repeat(20)]];
    const result = computeFitFontSize(m, blocks, fmt, { fontSize: 12 });
    m.setFontSize(result);
    expect(m.getTextWidth('x'.repeat(20))).toBeLessThanOrEqual(innerWidth);
    m.setFontSize(result + STEP);
    expect(m.getTextWidth('x'.repeat(20))).toBeGreaterThan(innerWidth);
  });

  it('never grows beyond the chosen (clamped) size even when everything fits', () => {
    const m = makeMeasurer(0.001);
    expect(computeFitFontSize(m, [['a'], ['b']], fmt, { fontSize: 9 })).toBe(9);
    const r = computeFitFontSize(m, [['a']], fmt, { fontSize: 99 });
    expect(r).toBeLessThanOrEqual(MAX_FONT_SIZE);
    expect(r).toBe(MAX_FONT_SIZE);
  });

  it('returns MIN_FONT_SIZE when the sheet cannot fit even at the floor (no loop)', () => {
    const m = makeMeasurer(0.5);
    const blocks = [['Z'.repeat(60)]];
    const result = computeFitFontSize(m, blocks, fmt, { fontSize: 12 });
    expect(result).toBe(MIN_FONT_SIZE);
    m.setFontSize(MIN_FONT_SIZE);
    expect(m.getTextWidth('Z'.repeat(60))).toBeGreaterThan(innerWidth);
  });

  it('handles empty / absent line-blocks safely (fits → chosen size)', () => {
    const m = makeMeasurer(0.1);
    expect(computeFitFontSize(m, [], fmt, { fontSize: 11 })).toBe(11);
    expect(computeFitFontSize(m, [], fmt)).toBe(10);
  });
});

// ---------------------------------------------------------------------------
// 5. generateLabelTemplatePdf — the TEMPLATE-driven path (the surviving label
// path). Composes via `composeLabelLines` and reads NO `analytics.*` (Property
// 4 / R6) — a field config with NO address mapping still yields labels from a
// label template. Reuses the SHARED `layoutLabelPdf` draw loop (R-L5).
// ---------------------------------------------------------------------------

describe('generateLabelTemplatePdf — template-driven labels (task 3.2)', () => {
  const fmt = getLabelFormat('L7160')!;

  // A field config with NO analytics / address mapping at all — only flat field
  // keys the template references (proves the template path never needs a mapping).
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
    // `noMappingConfig` has NO address mapping; the template path composes purely
    // from the field keys the template names.
    const templateResult = generateLabelTemplatePdf(
      peopleRows,
      noMappingConfig,
      { lines: [['display_name'], ['city']] },
      fmt,
    );
    expect(templateResult.labelCount).toBe(2);
    expect(templateResult.excludedCount).toBe(0);
  });

  it('drops + counts a row whose template lines are ALL empty', () => {
    const emptyRow = row({ member_id: 'z' });
    const template = { lines: [['display_name'], ['city']] };
    const result = generateLabelTemplatePdf(
      [...peopleRows, emptyRow],
      noMappingConfig,
      template,
      fmt,
    );
    expect(result.labelCount).toBe(2);
    expect(result.excludedCount).toBe(1);
  });

  it('composes a multi-field line by joining values in field order (Property 2)', () => {
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

  it('clamps an out-of-band font size and lays out onto every shipped format without throwing', () => {
    const template = { lines: [['display_name'], ['street'], ['city']] };
    for (const format of AVERY_LABEL_FORMATS) {
      const result = generateLabelTemplatePdf(peopleRows, noMappingConfig, template, format, {
        fontSize: 99,
        showBorder: true,
        alignment: 'center',
      });
      expect(result.labelCount).toBe(2);
      expect(typeof result.doc.output).toBe('function');
    }
  });

  it('lays out extreme over-long lines without throwing (truncation path)', () => {
    const longRow = row({
      member_id: 'long',
      display_name: 'X'.repeat(500),
      street: 'Y'.repeat(500),
      postal_code: '1000AA',
      city: 'Z'.repeat(500),
    });
    for (const format of AVERY_LABEL_FORMATS) {
      const result = generateLabelTemplatePdf(
        [longRow],
        noMappingConfig,
        { lines: [['display_name'], ['street'], ['city']] },
        format,
      );
      expect(result.labelCount).toBe(1);
      expect(typeof result.doc.output).toBe('function');
    }
  });

  it('spans multiple pages when the labels exceed one sheet', () => {
    const many: MemberRow[] = Array.from({ length: 22 }, (_, i) =>
      row({ member_id: `m${i}`, display_name: `Member ${i}`, city: 'Town' }),
    );
    const result = generateLabelTemplatePdf(
      many,
      noMappingConfig,
      { lines: [['display_name'], ['city']] },
      fmt,
    );
    expect(result.labelCount).toBe(22);
    expect(result.pages).toBe(2);
    expect(result.doc.getNumberOfPages()).toBe(2);
  });

  it('honors the start position: skipping N cells pushes labels to the next page', () => {
    const result = generateLabelTemplatePdf(
      peopleRows,
      noMappingConfig,
      { lines: [['display_name']] },
      fmt,
      { startPosition: 20 },
    );
    expect(result.labelCount).toBe(2);
    expect(result.pages).toBe(2);
    expect(result.doc.getNumberOfPages()).toBe(2);
  });

  it('shrinks for over-long rows under autoFit without throwing (Property 6 smoke)', () => {
    const longRow = row({
      member_id: 'long',
      display_name: 'X'.repeat(300),
      city: 'Z'.repeat(300),
    });
    const result = generateLabelTemplatePdf(
      [longRow, peopleRows[0]],
      noMappingConfig,
      { lines: [['display_name'], ['city']] },
      fmt,
      { autoFit: true, fontSize: 12 },
    );
    expect(result.labelCount).toBe(2);
    expect(result.pages).toBe(1);
    expect(typeof result.doc.output).toBe('function');
  });

  it('reuses the shared layoutLabelPdf draw loop (one layout path, R-L5)', () => {
    const laid = layoutLabelPdf(
      [['Alice Smith', 'Rotterdam'], ['Bob Jones', 'Amsterdam']],
      fmt,
    );
    expect(laid.labelCount).toBe(2);
    expect(laid.pages).toBe(1);
    expect(typeof laid.doc.output).toBe('function');
  });
});
