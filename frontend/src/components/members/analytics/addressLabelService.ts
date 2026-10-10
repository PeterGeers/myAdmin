/**
 * addressLabelService — client-side Avery address-label generation (C5, task 8.2).
 *
 * Ported from the h-dcn `AddressLabelService.ts` reference, generalized to be
 * **generic + multi-tenant**: the h-dcn Dutch field literals (`korte_naam`,
 * `straat`, `postcode`, `woonplaats`, `land`, `regio`) are gone — every address
 * line is composed from the tenant's RESOLVED field keys, read from
 * `analytics.address_mapping` via {@link resolveAddressMapping} (task 6.4). No
 * `if tenant === …` branch, no hardcoded field list (R6.1).
 *
 * This module is PURE: label-grid geometry, address formatting, member
 * filtering/sorting, and jsPDF document construction — no React, no I/O beyond
 * handing back the jsPDF document (the caller triggers the browser download /
 * print). That keeps the grid math and address formatting unit-testable in
 * isolation (task 8.3).
 *
 * What it provides (design C5 / R4.9 / R4.10):
 *   - **Shipped Avery formats** — the five standard stock labels
 *     ({@link AVERY_LABEL_FORMATS}: L7160 / L7163 / L7162 / L7161 + a Custom
 *     Large), each a {@link LabelFormat} record of grid geometry in millimetres.
 *     These are shipped DEFAULTS — a tenant need not configure a format to get
 *     labels; only the field→line mapping must resolve.
 *   - **Address composition** — compose up to five display lines (name / street /
 *     postcode + city / country / region) from the resolved field keys, dropping
 *     slots the tenant did not map. Country is uppercased for international rows.
 *   - **Incomplete-address filtering** — members missing the minimum address
 *     lines (name + at least one locating line) are DROPPED and COUNTED, so the
 *     caller can report "N excluded" (R4.10, as the h-dcn generator does).
 *   - **Sorting** — by name, postcode, or region (postcode supports bulk-mail
 *     ordering).
 *   - **jsPDF output** — lay the composed labels onto the chosen grid, honoring a
 *     start position (skip the first N cells of a partial sheet) and the per-run
 *     style options (font size, alignment, border).
 *
 * @module components/members/analytics/addressLabelService
 * @see .kiro/specs/Members/member-analytics (design C5; requirements R4.9, R4.10, R4.11, R6.1)
 */

import { jsPDF } from 'jspdf';
import type { FieldConfig, FieldConfigField, MemberRow } from '../../../types/members';
import { valueFor, groupForKey } from '../fieldValue';
import {
  resolveAddressMapping,
  type AddressSlot,
  type ResolvedAddressMapping,
} from './analyticsConfig';

/**
 * One printable label-stock format: the grid geometry (in millimetres) needed to
 * place labels on an A4 sheet. Mirrors the Avery datasheet dimensions.
 */
export interface LabelFormat {
  /** Stable key (also the UI option value), e.g. `'L7160'`. */
  key: string;
  /** Human-readable name shown in the picker (e.g. `'Avery L7160'`). */
  name: string;
  /** Labels per row (grid columns). */
  columns: number;
  /** Labels per column (grid rows). */
  rows: number;
  /** Label width, mm. */
  labelWidth: number;
  /** Label height, mm. */
  labelHeight: number;
  /** Sheet left margin to the first column, mm. */
  marginLeft: number;
  /** Sheet top margin to the first row, mm. */
  marginTop: number;
  /** Horizontal gap between columns, mm (0 for abutting labels). */
  gapX: number;
  /** Vertical gap between rows, mm (0 for abutting labels). */
  gapY: number;
}

/**
 * The five standard Avery formats shipped as defaults (design C5 / R4.10). A4
 * (210 × 297 mm) geometry. A tenant MAY add more, but none of these needs any
 * tenant configuration — they are the out-of-the-box stock.
 *
 * - **L7160** — 21/sheet (3 × 7), 63.5 × 38.1 mm.
 * - **L7163** — 14/sheet (2 × 7), 99.1 × 38.1 mm.
 * - **L7162** — 16/sheet (2 × 8), 99.1 × 33.9 mm.
 * - **L7161** — 18/sheet (3 × 6), 63.5 × 46.6 mm.
 * - **CUSTOM_LARGE** — 8/sheet (2 × 4), 99.1 × 67.7 mm.
 */
export const AVERY_LABEL_FORMATS: LabelFormat[] = [
  {
    key: 'L7160',
    name: 'Avery L7160 (21/sheet)',
    columns: 3,
    rows: 7,
    labelWidth: 63.5,
    labelHeight: 38.1,
    marginLeft: 7.2,
    marginTop: 15.1,
    gapX: 2.5,
    gapY: 0,
  },
  {
    key: 'L7163',
    name: 'Avery L7163 (14/sheet)',
    columns: 2,
    rows: 7,
    labelWidth: 99.1,
    labelHeight: 38.1,
    marginLeft: 4.65,
    marginTop: 15.1,
    gapX: 2.5,
    gapY: 0,
  },
  {
    key: 'L7162',
    name: 'Avery L7162 (16/sheet)',
    columns: 2,
    rows: 8,
    labelWidth: 99.1,
    labelHeight: 33.9,
    marginLeft: 4.65,
    marginTop: 12.9,
    gapX: 2.5,
    gapY: 0,
  },
  {
    key: 'L7161',
    name: 'Avery L7161 (18/sheet)',
    columns: 3,
    rows: 6,
    labelWidth: 63.5,
    labelHeight: 46.6,
    marginLeft: 7.2,
    marginTop: 8.7,
    gapX: 2.5,
    gapY: 0,
  },
  {
    key: 'CUSTOM_LARGE',
    name: 'Custom Large (8/sheet)',
    columns: 2,
    rows: 4,
    labelWidth: 99.1,
    labelHeight: 67.7,
    marginLeft: 4.65,
    marginTop: 13.1,
    gapX: 2.5,
    gapY: 0,
  },
];

/** The default shipped format (first of the standard stock, L7160). */
export const DEFAULT_LABEL_FORMAT_KEY = AVERY_LABEL_FORMATS[0].key;

/** Look a shipped format up by key; `undefined` when unknown. */
export function getLabelFormat(key: string): LabelFormat | undefined {
  return AVERY_LABEL_FORMATS.find((f) => f.key === key);
}

/** Text alignment within a label cell. */
export type LabelAlignment = 'left' | 'center' | 'right';

/** Sort order applied before layout (name / postcode / region). */
export type LabelSortOrder = 'name' | 'postcode' | 'region';

/** Per-run style + layout options for a generation (all have sensible defaults). */
export interface LabelStyleOptions {
  /** Font size in points, clamped to 8–12 (R4.10). Default 10. */
  fontSize?: number;
  /** Text alignment within a cell. Default `'left'`. */
  alignment?: LabelAlignment;
  /** Draw a thin border around each cell (cutting guide). Default `false`. */
  showBorder?: boolean;
  /** Include the country line (uppercased for international). Default `true`. */
  showCountry?: boolean;
  /** Skip the first N label cells to reuse a partially used sheet. Default 0. */
  startPosition?: number;
  /** Sort order before layout. Default `'name'`. */
  sortOrder?: LabelSortOrder;
  /**
   * OPT-IN per-sheet shrink-to-fit (labels sub-spec R-L3, Property 6). When
   * `true`, {@link generateAddressLabelPdf} computes the LARGEST uniform font
   * size (≤ the user's clamped {@link fontSize}) at which EVERY label on the
   * sheet fits — all lines within the cell inner width AND the line block within
   * the cell inner height — and applies that one size across the whole sheet. It
   * only ever SHRINKS, never grows beyond the chosen size; truncation (Property
   * 5) remains the safety net at the font floor. Default `false` — behavior is
   * unchanged (the clamped {@link fontSize}) when absent/false.
   */
  autoFit?: boolean;
}

/** The clamp bounds for the per-run font size (R4.10: 8–12pt). */
export const MIN_FONT_SIZE = 8;
export const MAX_FONT_SIZE = 12;
const DEFAULT_FONT_SIZE = 10;

/** A4 sheet dimensions in millimetres (portrait). */
const A4_WIDTH_MM = 210;
const A4_HEIGHT_MM = 297;

/** Internal label-cell padding, mm. */
const CELL_PADDING_MM = 2;
/** Points-to-mm line height factor (approx 1.15 line spacing at the pt size). */
const PT_TO_MM = 0.3528;
const LINE_SPACING = 1.15;

/**
 * One member's composed address, ready to lay out: the display lines (already
 * dropped-of-empty, country uppercased) plus the sort keys used to order it.
 */
export interface ComposedAddress {
  /** The non-empty display lines, top to bottom. */
  lines: string[];
  /** Lower-cased name sort key (`''` when absent). */
  nameKey: string;
  /** Lower-cased postcode sort key (`''` when absent). */
  postcodeKey: string;
  /** Lower-cased region sort key (`''` when absent). */
  regionKey: string;
}

/** The outcome of composing a member set: the kept addresses + the dropped count. */
export interface ComposeResult {
  /** The addresses that passed the completeness check, in input order. */
  addresses: ComposedAddress[];
  /** How many members were dropped for an incomplete address (R4.10). */
  excludedCount: number;
}

/**
 * Read a resolved slot's raw string value off a member row, via the shared
 * nested-or-flat {@link valueFor} accessor (so a value is read the SAME way the
 * table reads it). Returns a trimmed string, or `''` when absent/blank.
 */
function readSlot(
  row: MemberRow,
  slot: AddressSlot,
  mapping: ResolvedAddressMapping,
  fieldsByKey: Map<string, FieldConfigField>,
): string {
  const key = mapping[slot];
  if (!key) {
    return '';
  }
  const group = fieldsByKey.get(key)?.group;
  const raw = valueFor(row, group, key);
  if (raw === null || raw === undefined) {
    return '';
  }
  return String(raw).trim();
}

/**
 * Compose one member's address lines from the resolved mapping.
 *
 * Lines, in order: name, street, `postcode city` (joined), country, region.
 * Country is uppercased for international mailing convention. Empty slots are
 * dropped so a missing middle line never leaves a blank gap.
 */
function composeAddress(
  row: MemberRow,
  mapping: ResolvedAddressMapping,
  fieldsByKey: Map<string, FieldConfigField>,
  showCountry: boolean,
): ComposedAddress {
  const name = readSlot(row, 'name', mapping, fieldsByKey);
  const street = readSlot(row, 'street', mapping, fieldsByKey);
  const postcode = readSlot(row, 'postcode', mapping, fieldsByKey);
  const city = readSlot(row, 'city', mapping, fieldsByKey);
  const country = readSlot(row, 'country', mapping, fieldsByKey);
  const region = readSlot(row, 'region', mapping, fieldsByKey);

  const cityLine = [postcode, city].filter((p) => p !== '').join('  ').trim();

  const lines: string[] = [];
  if (name) lines.push(name);
  if (street) lines.push(street);
  if (cityLine) lines.push(cityLine);
  if (showCountry && country) lines.push(country.toUpperCase());
  if (region) lines.push(region);

  return {
    lines,
    nameKey: name.toLowerCase(),
    postcodeKey: postcode.toLowerCase(),
    regionKey: region.toLowerCase(),
  };
}

/**
 * Is a composed address complete enough to print? It must carry a name AND at
 * least one locating line (street or postcode+city). A name-only or empty
 * address is dropped and counted (R4.10).
 */
function isComplete(address: ComposedAddress): boolean {
  if (address.lines.length === 0) {
    return false;
  }
  const hasName = address.nameKey !== '';
  // At least one line beyond the name is a locating line (street / city line).
  const hasLocator = address.lines.length >= 2;
  return hasName && hasLocator;
}

/**
 * Compose + filter + sort a member set into print-ready addresses.
 *
 * - composes each row via the resolved {@link ResolvedAddressMapping};
 * - DROPS members with an incomplete address and reports the count (R4.10);
 * - sorts the survivors by the chosen order (name / postcode / region).
 *
 * Pure: inputs are never mutated. An empty mapping yields zero addresses (and an
 * excluded count equal to the input length) — the caller treats that as "labels
 * unavailable" (R4.10).
 */
export function composeAddresses(
  rows: MemberRow[],
  fieldConfig: FieldConfig | undefined,
  options: LabelStyleOptions = {},
): ComposeResult {
  const safeRows = Array.isArray(rows) ? rows : [];
  const mapping = resolveAddressMapping(fieldConfig);
  const showCountry = options.showCountry !== false;

  // Index fields by key once so each slot read is O(1).
  const fieldsByKey = new Map<string, FieldConfigField>();
  for (const field of fieldConfig?.fields ?? []) {
    if (field?.key) {
      fieldsByKey.set(field.key, field);
    }
  }

  // No resolvable address mapping → nothing can be composed; every row is excluded.
  if (Object.keys(mapping).length === 0) {
    return { addresses: [], excludedCount: safeRows.length };
  }

  const kept: ComposedAddress[] = [];
  let excludedCount = 0;
  for (const row of safeRows) {
    const address = composeAddress(row, mapping, fieldsByKey, showCountry);
    if (isComplete(address)) {
      kept.push(address);
    } else {
      excludedCount += 1;
    }
  }

  const sortOrder: LabelSortOrder = options.sortOrder ?? 'name';
  const sortKey = (a: ComposedAddress): string =>
    sortOrder === 'postcode'
      ? a.postcodeKey
      : sortOrder === 'region'
        ? a.regionKey
        : a.nameKey;
  // Stable sort on a copy — never mutate the caller's array.
  const addresses = [...kept].sort((a, b) => sortKey(a).localeCompare(sortKey(b)));

  return { addresses, excludedCount };
}

/**
 * The minimal label-template content a {@link composeLabelLines} run needs: the
 * ordered `lines`, each line an ordered list of pivot-result field keys (the
 * whole label content model — see the labels sub-spec data model). A local,
 * structural type keeps this module free of a hard dependency on
 * `memberTemplateService` (the stored `MemberTemplateDto` is assignable to it).
 */
export interface LabelTemplateLines {
  /** Ordered label lines; each line is an ordered list of field keys. */
  lines: string[][];
}

/** One row's composed label content: the non-empty display lines, top to bottom. */
export interface ComposedLabel {
  /** The non-empty lines for this row (empty lines dropped), in template order. */
  lines: string[];
}

/**
 * Compose label lines from a stored label template (labels sub-spec R-L3,
 * Properties 1 / 2 / 4) — the analytics-free counterpart to
 * {@link composeAddresses}.
 *
 * For each row, for each `template.lines[i]` (an ordered list of field keys):
 * resolve EACH key via the shared nested-or-flat accessor
 * `valueFor(row, groupForKey(fieldConfig, key), key)` (so a nested fixed field
 * like `personal.last_name` AND a flat alias like `display_name` both resolve
 * exactly how the table reads them), stringify + trim, DROP empty/absent values,
 * then JOIN the survivors with a single space → one output line (Property 1: N
 * lines → N lines; Property 2: multi-key join in field order).
 *
 * A line whose keys ALL resolve empty is dropped so there is no blank gap; a row
 * whose lines are ALL empty yields `{ lines: [] }` (the caller — the modal, a
 * later phase — decides whether to drop/count such a row).
 *
 * PURE (Property 4): it reads ONLY `rows` / `fieldConfig` / `template`, never any
 * `analytics.*` config, and never mutates its inputs.
 */
export function composeLabelLines(
  rows: MemberRow[],
  fieldConfig: FieldConfig | undefined,
  template: LabelTemplateLines,
): ComposedLabel[] {
  const safeRows = Array.isArray(rows) ? rows : [];
  const templateLines = Array.isArray(template?.lines) ? template.lines : [];

  return safeRows.map((row) => {
    const lines: string[] = [];
    for (const keys of templateLines) {
      const parts: string[] = [];
      for (const key of Array.isArray(keys) ? keys : []) {
        const raw = valueFor(row, groupForKey(fieldConfig, key), key);
        if (raw === null || raw === undefined) {
          continue;
        }
        const text = String(raw).trim();
        if (text !== '') {
          parts.push(text);
        }
      }
      const line = parts.join(' ');
      if (line !== '') {
        lines.push(line);
      }
    }
    return { lines };
  });
}

/** Clamp a requested font size into the allowed 8–12pt band (R4.10). */
export function clampFontSize(fontSize: number | undefined): number {
  if (typeof fontSize !== 'number' || !Number.isFinite(fontSize)) {
    return DEFAULT_FONT_SIZE;
  }
  return Math.min(MAX_FONT_SIZE, Math.max(MIN_FONT_SIZE, fontSize));
}

/**
 * The grid cell position of the Nth label (0-indexed) on a given format — the
 * pure geometry the layout + tests exercise. `cellIndex` is the position WITHIN
 * a page (0 … columns*rows-1); the caller advances pages when it wraps.
 *
 * Returns the top-left corner `(x, y)` in mm of the cell.
 */
export function cellPosition(
  format: LabelFormat,
  cellIndex: number,
): { x: number; y: number; col: number; row: number } {
  const perPage = format.columns * format.rows;
  const indexInPage = ((cellIndex % perPage) + perPage) % perPage;
  const col = indexInPage % format.columns;
  const row = Math.floor(indexInPage / format.columns);
  const x = format.marginLeft + col * (format.labelWidth + format.gapX);
  const y = format.marginTop + row * (format.labelHeight + format.gapY);
  return { x, y, col, row };
}

/** Labels per sheet for a format. */
export function labelsPerPage(format: LabelFormat): number {
  return format.columns * format.rows;
}

/**
 * The number of A4 pages needed for `addressCount` labels on a format, honoring a
 * `startPosition` offset (skipped leading cells on the first page).
 */
export function pageCount(
  format: LabelFormat,
  addressCount: number,
  startPosition = 0,
): number {
  if (addressCount <= 0) {
    return 0;
  }
  const perPage = labelsPerPage(format);
  const offset = Math.max(0, Math.min(startPosition, perPage - 1));
  return Math.ceil((addressCount + offset) / perPage);
}

/**
 * The minimal measurement surface {@link truncateToWidth} needs: something that
 * can report the rendered width of a string in the current unit (mm, for our
 * `unit: 'mm'` jsPDF). A jsPDF document satisfies this structurally via its
 * `getTextWidth`, but a test can inject a deterministic fake measurer (e.g. a
 * fixed mm-per-character) without a real font/jsPDF.
 */
export interface TextMeasurer {
  /** Width of `text` in the measurer's unit, at its current font/size. */
  getTextWidth(text: string): number;
}

/**
 * Truncate `text` to fit within `maxWidthMm` as measured by `measurer`, appending
 * an ellipsis when characters are dropped (labels sub-spec R-L3, Property 5 —
 * over-long field text is cut to the cell inner width, never drawn past the box).
 *
 * - If the full text already fits (`<= maxWidthMm`), it is returned unchanged.
 * - Otherwise characters are trimmed from the END and the ellipsis appended until
 *   `trimmed + ellipsis` fits.
 * - An empty string returns `''`.
 * - Degenerate case: if even the ellipsis alone cannot fit (absurdly small
 *   `maxWidthMm`), the ellipsis is still returned — the function never loops
 *   forever and never returns a result wider than `maxWidthMm` when a narrower
 *   one is achievable.
 *
 * PURE: reads only its arguments (the measurer is consulted, never mutated).
 */
export function truncateToWidth(
  measurer: TextMeasurer,
  text: string,
  maxWidthMm: number,
  ellipsis = '…',
): string {
  if (text === '') {
    return '';
  }
  if (measurer.getTextWidth(text) <= maxWidthMm) {
    return text;
  }
  // The full text overflows → drop characters from the end, append the ellipsis,
  // and keep the longest prefix whose `prefix + ellipsis` still fits. Binary
  // search over the prefix length keeps this O(log n) measurer calls.
  let lo = 0; // longest prefix length known to NOT fit yet is > lo; lo always fits (0 + ellipsis may or may not)
  let hi = text.length - 1; // text.length itself overflows (checked above), so cap at length-1
  let best = ''; // best prefix+ellipsis found that fits; '' until we find one
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const candidate = text.slice(0, mid) + ellipsis;
    if (measurer.getTextWidth(candidate) <= maxWidthMm) {
      best = candidate; // fits — try a longer prefix
      lo = mid + 1;
    } else {
      hi = mid - 1; // too wide — try a shorter prefix
    }
  }
  // `best` is '' only when not even the ellipsis alone fit; return the ellipsis
  // as the minimal truncation marker rather than empty (never loops; this is the
  // smallest non-empty marker and only exceeds an absurdly tiny maxWidth).
  return best !== '' ? best : ellipsis;
}

/**
 * The measurement surface {@link computeFitFontSize} needs: a {@link TextMeasurer}
 * that can ALSO be re-pointed at a candidate font size before measuring, because
 * {@link TextMeasurer.getTextWidth} depends on the size currently set on the
 * document. A real jsPDF doc satisfies this structurally (it exposes
 * `setFontSize`), and a test can inject a deterministic fake whose width scales
 * with the current size (e.g. `chars * k * fontSize`).
 */
export interface FitMeasurer extends TextMeasurer {
  /** Set the current font size (points) used by subsequent `getTextWidth` calls. */
  setFontSize(pt: number): void;
}

/**
 * The downward search step (points) {@link computeFitFontSize} uses when probing
 * candidate sizes from the chosen size to the floor. Half-point granularity is
 * finer than any visible difference on an Avery cell while keeping the search
 * bounded (≤ ~9 probes across the 8–12pt band).
 */
const FIT_STEP_PT = 0.5;

/**
 * Compute the single UNIFORM font size (points) for a whole sheet of labels under
 * per-sheet shrink-to-fit (labels sub-spec R-L3, Property 6).
 *
 * Returns the LARGEST size in `[MIN_FONT_SIZE, chosen]` — where
 * `chosen = clampFontSize(options.fontSize)` — at which EVERY label fits:
 *
 *   - a single LINE fits iff `measurer.getTextWidth(line) <= innerWidth`
 *     (`innerWidth = format.labelWidth - 2 * CELL_PADDING_MM`), measured with the
 *     measurer set to the candidate size;
 *   - a LABEL fits iff all its lines fit AND the line block fits the cell height:
 *     `(lines.length * fs * PT_TO_MM * LINE_SPACING) <= innerHeight`
 *     (`innerHeight = format.labelHeight - 2 * CELL_PADDING_MM`);
 *   - the SHEET fits iff every label fits.
 *
 * The search starts at `chosen` and steps DOWN by {@link FIT_STEP_PT} to
 * `MIN_FONT_SIZE`, returning the first (largest) candidate that fits. It ONLY
 * SHRINKS: the result never exceeds `chosen`. If even `MIN_FONT_SIZE` does not
 * fit, it returns `MIN_FONT_SIZE` (the floor) — truncation (Property 5) then
 * handles any residual overflow; the search never grows and never loops forever.
 *
 * PURE: it reads only its arguments. It DOES call `measurer.setFontSize` to probe
 * each candidate (an unavoidable side effect of the measurer being size-stateful);
 * the caller is expected to re-set the size it actually wants to draw with
 * afterwards. Takes NO `analytics.*` config (R6.1) — only a measurer, the label
 * line-blocks, the format, and the style options.
 *
 * @param measurer   a size-settable text measurer (a jsPDF doc, or a test fake).
 * @param labelLineBlocks  one entry per label: that label's already-composed lines.
 * @param format     the Avery format providing the cell geometry.
 * @param options    the style options (only `fontSize` is read, for the ceiling).
 */
export function computeFitFontSize(
  measurer: FitMeasurer,
  labelLineBlocks: string[][],
  format: LabelFormat,
  options: LabelStyleOptions = {},
): number {
  const chosen = clampFontSize(options.fontSize);
  const innerWidth = format.labelWidth - 2 * CELL_PADDING_MM;
  const innerHeight = format.labelHeight - 2 * CELL_PADDING_MM;
  const blocks = Array.isArray(labelLineBlocks) ? labelLineBlocks : [];

  // Does the whole sheet fit at candidate size `fs`? (Set the measurer first —
  // getTextWidth is relative to the current size.)
  const sheetFitsAt = (fs: number): boolean => {
    measurer.setFontSize(fs);
    const lineHeightMm = fs * PT_TO_MM * LINE_SPACING;
    for (const lines of blocks) {
      const safeLines = Array.isArray(lines) ? lines : [];
      // Height: the whole line block must fit the cell inner height.
      if (safeLines.length * lineHeightMm > innerHeight) {
        return false;
      }
      // Width: every individual line must fit the cell inner width.
      for (const line of safeLines) {
        if (measurer.getTextWidth(line) > innerWidth) {
          return false;
        }
      }
    }
    return true;
  };

  // Search DOWN from the chosen ceiling to the floor; return the largest that
  // fits. Only shrink — never return above `chosen`.
  for (let fs = chosen; fs > MIN_FONT_SIZE; fs -= FIT_STEP_PT) {
    if (sheetFitsAt(fs)) {
      return fs;
    }
  }
  // Nothing above the floor fit (or `chosen` already is the floor): the floor is
  // the answer whether or not it technically fits — truncation handles the rest.
  return MIN_FONT_SIZE;
}

/** The result of a PDF generation: the jsPDF doc + the counts the UI reports. */
export interface GenerateResult {
  /** The constructed jsPDF document (caller saves / prints / attaches). */
  doc: jsPDF;
  /** How many labels were laid out. */
  labelCount: number;
  /** How many members were excluded for an incomplete address (R4.10). */
  excludedCount: number;
  /** How many A4 pages the document spans. */
  pages: number;
}

/**
 * Lay a set of already-composed label line-blocks onto a jsPDF Avery sheet — the
 * SINGLE jsPDF draw loop shared by the address path ({@link generateAddressLabelPdf})
 * and the template path ({@link generateLabelTemplatePdf}). Pure w.r.t. its
 * inputs beyond constructing + returning the document (it never reads
 * `analytics.*`, member rows, or any field config — only the already-composed
 * `labelLineBlocks`, the format, and the style options).
 *
 * Each entry of `labelLineBlocks` is ONE label's ordered text lines. The loop:
 *   - creates an A4 portrait jsPDF (unit mm);
 *   - picks the font size — per-sheet shrink-to-fit (Property 6) when
 *     `options.autoFit`, else the clamped {@link LabelStyleOptions.fontSize};
 *   - honors the start position (skip the first N cells of a partial sheet),
 *     alignment, and optional cutting-guide border;
 *   - truncates each line to the cell inner width so a field never overflows the
 *     Avery box (Property 5).
 *
 * Returns the document plus the laid-out label count + page span (the caller adds
 * its own `excludedCount` — the count of rows that produced no usable label).
 */
export function layoutLabelPdf(
  labelLineBlocks: string[][],
  format: LabelFormat,
  options: LabelStyleOptions = {},
): { doc: jsPDF; labelCount: number; pages: number } {
  const blocks = Array.isArray(labelLineBlocks) ? labelLineBlocks : [];

  const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });
  const alignment: LabelAlignment = options.alignment ?? 'left';
  const showBorder = options.showBorder === true;
  const perPage = labelsPerPage(format);
  const startOffset = Math.max(0, Math.min(options.startPosition ?? 0, perPage - 1));

  doc.setFont('helvetica', 'normal');
  // Per-sheet shrink-to-fit (Property 6): when opted in, the font is the LARGEST
  // uniform size (≤ the clamped user size) at which every label fits width AND
  // height; otherwise it is simply the clamped user size (unchanged behavior).
  // The fit search needs the label line-blocks being laid out, so it runs BEFORE
  // the draw loop. Truncation below stays the safety net.
  const fontSize =
    options.autoFit === true
      ? computeFitFontSize(doc, blocks, format, options)
      : clampFontSize(options.fontSize);
  doc.setFontSize(fontSize);
  const lineHeightMm = fontSize * PT_TO_MM * LINE_SPACING;
  // Usable text width inside the cell (both-side padding) — long lines are
  // truncated to this so a field never overflows the Avery box (Property 5).
  const innerWidth = format.labelWidth - 2 * CELL_PADDING_MM;

  blocks.forEach((lines, i) => {
    const safeLines = Array.isArray(lines) ? lines : [];
    const absoluteCell = i + startOffset;
    const pageIndex = Math.floor(absoluteCell / perPage);
    // jsPDF starts with one page; add the rest as we reach them.
    if (pageIndex > 0 && absoluteCell % perPage === 0) {
      doc.addPage('a4', 'portrait');
    }
    const { x, y } = cellPosition(format, absoluteCell);

    if (showBorder) {
      doc.rect(x, y, format.labelWidth, format.labelHeight);
    }

    // Vertically center the block of lines within the cell.
    const blockHeight = safeLines.length * lineHeightMm;
    const startY =
      y + Math.max(CELL_PADDING_MM, (format.labelHeight - blockHeight) / 2) + lineHeightMm * 0.5;

    let textX = x + CELL_PADDING_MM;
    if (alignment === 'center') {
      textX = x + format.labelWidth / 2;
    } else if (alignment === 'right') {
      textX = x + format.labelWidth - CELL_PADDING_MM;
    }

    safeLines.forEach((line, lineIdx) => {
      const drawn = truncateToWidth(doc, line, innerWidth);
      doc.text(drawn, textX, startY + lineIdx * lineHeightMm, { align: alignment });
    });
  });

  return {
    doc,
    labelCount: blocks.length,
    pages: pageCount(format, blocks.length, startOffset),
  };
}

/**
 * Build the Avery address-label PDF for a member set.
 *
 * Composes + filters + sorts the rows (via {@link composeAddresses}), then lays
 * the surviving addresses onto the chosen {@link LabelFormat} grid via the shared
 * {@link layoutLabelPdf} draw loop, honoring the per-run {@link LabelStyleOptions}
 * (font size, alignment, border, country, start position). Returns the document
 * plus the label/excluded/page counts the UI surfaces as text badges (R6.6).
 *
 * The caller decides what to do with `result.doc` — `doc.save(filename)` to
 * download, `doc.output('bloburl')` to preview/print, or
 * `doc.output('arraybuffer')` to attach to a mail (task 9.x).
 */
export function generateAddressLabelPdf(
  rows: MemberRow[],
  fieldConfig: FieldConfig | undefined,
  format: LabelFormat,
  options: LabelStyleOptions = {},
): GenerateResult {
  const { addresses, excludedCount } = composeAddresses(rows, fieldConfig, options);
  const { doc, labelCount, pages } = layoutLabelPdf(
    addresses.map((a) => a.lines),
    format,
    options,
  );
  return { doc, labelCount, excludedCount, pages };
}

/**
 * Build the Avery label PDF from a stored LABEL TEMPLATE (labels sub-spec R-L2 /
 * R-L3 / R-L4) — the analytics-free counterpart to {@link generateAddressLabelPdf}.
 *
 * Composes the current result rows through the chosen label `template` via
 * {@link composeLabelLines} (NOT `composeAddresses`/`resolveAddressMapping` — it
 * reads NO `analytics.*`, Property 4), DROPS rows whose composed `lines` are all
 * empty (counting them as `excludedCount` so the UI can report "N excluded"),
 * then lays the surviving label line-blocks onto the chosen {@link LabelFormat}
 * via the SAME shared {@link layoutLabelPdf} draw loop the address path uses
 * (one layout code path, no second draw loop — R-L5). Returns the document plus
 * the label/excluded/page counts the UI surfaces as badges.
 *
 * It reads ONLY `rows` / `fieldConfig` / `template` / `format` / `options`
 * (Property 4). The caller does `result.doc.save(filename)` to download or
 * `result.doc.output('bloburl')` to print (R-L4).
 */
export function generateLabelTemplatePdf(
  rows: MemberRow[],
  fieldConfig: FieldConfig | undefined,
  template: LabelTemplateLines,
  format: LabelFormat,
  options: LabelStyleOptions = {},
): GenerateResult {
  const composed = composeLabelLines(rows, fieldConfig, template);
  // Drop (and count) rows whose template produced NO usable line — a row with
  // every line empty yields no printable label, never a blank cell.
  const kept = composed.filter((c) => c.lines.length > 0);
  const excludedCount = composed.length - kept.length;

  const { doc, labelCount, pages } = layoutLabelPdf(
    kept.map((c) => c.lines),
    format,
    options,
  );
  return { doc, labelCount, excludedCount, pages };
}
